# Cloudflare R2 Asset Management Guide

## Overview
InstaInstru uses Cloudflare R2 for all image assets (backgrounds, icons, instructor photos) to prevent repository bloat and enable dynamic content delivery. This guide covers how to manage and upload assets.

## Why R2?
- **Cost**: ~$1/month vs $100s with S3 (free bandwidth!)
- **Scale**: Handles 1000s of images without bloating git
- **Performance**: Global CDN via Cloudflare
- **Dynamic**: Activity-specific backgrounds based on user searches

## Architecture

### Asset URL Structure
All assets are served from: `https://assets.instainstru.com/`

### Folder Structure in R2
```
instainstru-assets/
├── backgrounds/
│   ├── auth/           # Login/signup backgrounds
│   │   ├── default.webp
│   │   ├── default.png (fallback)
│   │   └── [seasonal variants]
│   ├── home/           # Homepage backgrounds
│   │   ├── default.webp
│   │   └── default.png
│   └── activities/     # Activity-specific backgrounds
│       ├── yoga/
│       ├── piano/
│       └── [activity]/
├── instructors/        # Profile images
│   └── [instructor-id]/
└── icons/             # Category icons
```

## How to Upload Assets

### Prerequisites
1. **Install wrangler**: `npm install -g wrangler`
2. **Configure credentials**: Ensure `scripts/.env` has R2 credentials:
   ```bash
   R2_ACCOUNT_ID=your-account-id
   R2_ACCESS_KEY_ID=your-access-key
   R2_SECRET_ACCESS_KEY=your-secret-key
   R2_BUCKET_NAME=instainstru-assets
   ```

### Method 1: Automated Upload Script (Recommended)

1. **Prepare your images**:
   ```bash
   # Create local asset directories
   mkdir -p assets/backgrounds/auth
   mkdir -p assets/backgrounds/home
   mkdir -p assets/backgrounds/activities/yoga

   # Add your images (PNG or JPG)
   cp your-image.png assets/backgrounds/auth/default.png
   ```

2. **Run upload script**:
   ```bash
   node scripts/upload-assets.js
   ```

   The script will:
   - Auto-convert PNG/JPG to WebP (when ImageMagick available)
   - Upload both WebP and original formats
   - Generate `assets-manifest.json` with all URLs
   - Show upload progress and final URLs

3. **Verify upload**:
   ```bash
   # Check your uploaded image
   curl https://assets.instainstru.com/backgrounds/auth/default.webp
   ```

### Method 2: Manual Upload with Wrangler

For individual files:
```bash
# Upload a single file
wrangler r2 object put instainstru-assets/backgrounds/auth/hero.webp \
  --file ./hero.webp --remote

# Delete a file
wrangler r2 object delete instainstru-assets/backgrounds/auth/old.webp --remote
```

## Adding New Activity Backgrounds

1. **Choose activity name** (must match search terms):
   - Use lowercase, no spaces: `yoga`, `piano`, `cooking`

2. **Prepare images**:
   ```bash
   mkdir -p assets/backgrounds/activities/yoga
   # Add at least: default.png or default.jpg
   # Optional: hero.png, pattern.png, mobile.png
   ```

3. **Upload**:
   ```bash
   node scripts/upload-assets.js
   ```

4. **Test**: Search for "yoga" on the platform - background should appear!

## Image Optimization Guidelines

### Recommended Specs
- **Format**: WebP preferred (auto-converted), PNG/JPG as source
- **Dimensions**:
  - Desktop: 1920x1080 minimum
  - Mobile: 640x1136 minimum
- **File size**: Keep under 500KB for backgrounds
- **Quality**: 85% for WebP conversion

### Responsive Variants
The asset service supports responsive loading:
```
default.webp       # Desktop
default-tablet.webp # Tablet (optional)
default-mobile.webp # Mobile (optional)
```

## Frontend Integration

### Using the Asset Service
```typescript
import { assetService } from '@/lib/services/assetService';

// Get auth background
const authBg = assetService.getAuthBackground();

// Get activity background
const yogaBg = await assetService.getActivityBackground('yoga');

// Get with fallback chain
const bg = await assetService.getActivityBackground('piano') ||
          assetService.getHomeBackground();
```

### Global Background Component
The site uses `GlobalBackground.tsx` which:
- Automatically selects backgrounds based on route
- Implements blur-up loading for performance
- Handles WebP with PNG fallback
- Maintains proper z-index layering

## Troubleshooting

### Upload Issues
- **"Unknown arguments: remote"**: Ensure you're using wrangler v3+
- **Authentication errors**: Check `scripts/.env` credentials
- **CORS errors**: Not needed for image display via `<img>` or CSS

### Display Issues
- **404 errors**: Check exact path/filename in R2 dashboard
- **Slow loading**: Ensure WebP conversion is working
- **No background**: Check browser console for errors

### Testing R2 Access
```bash
# Test API access
node scripts/test-r2.js

# List all files (via dashboard)
# Go to: dash.cloudflare.com → R2 → instainstru-assets → Objects
```

## Cost Monitoring
- **Storage**: $0.015/GB/month (first 10GB free)
- **Operations**: First 1M writes, 10M reads free/month
- **Bandwidth**: FREE (vs $0.09/GB on S3)
- **Current usage**: Check R2 dashboard → Analytics

## Best Practices
1. **Always upload both WebP and fallback formats**
2. **Use descriptive filenames**: `yoga-hero.webp` not `img1.webp`
3. **Test on slow connections** to ensure blur-up works
4. **Keep originals** in `assets/` (gitignored) for re-processing
5. **Update manifest** after bulk uploads for tracking

## Monitoring (Profile Picture URL Cache)

- Prometheus counters exposed by the backend:
  - `instainstru_profile_pic_url_cache_hits_total{variant="display|thumb|original"}`
  - `instainstru_profile_pic_url_cache_misses_total{variant="display|thumb|original"}`
- Grafana dashboard JSON: `monitoring/grafana/dashboards/profile_picture_cache.json`
  - Panels: per-variant hit rate, hits/misses time-series, overall hit rate.
  - Suggested alert: hit rate < 0.6 for 10m.

## Runbook

### Rotate a user’s profile picture
1. Ask the user to upload a new photo (recommended).
2. Or admin-driven: delete current variants via API:
   - `DELETE /api/users/me/profile-picture` (as the user) or an admin endpoint.
   - User re-uploads. Version increments; URLs change with `v{version}`.
3. Confirm by calling `/auth/me` to see `profile_picture_version` updated.

### Invalidate stale presigned URLs
- Presigned GETs are cached in Redis for ~45 minutes using key `profile_pic_url:{userId}:{variant}:v{version}`.
- To force refresh for one user:
  - Delete keys matching `profile_pic_url:{userId}:*` in Redis (CacheService supports delete-pattern).
  - Next request regenerates a new presigned URL and repopulates the cache.
- To blanket-flush all profile pic URLs (rare):
  - Delete keys matching `profile_pic_url:*`.

### CORS/Upload issues checklist
- Ensure bucket CORS allows `PUT,GET` from `http://localhost:3000` and production origins.
- Verify env vars in `backend/.env`: `r2_account_id`, `r2_access_key_id`, `r2_secret_access_key`, `r2_bucket_name`.
- For asset upload script: set uppercase equivalents in `scripts/.env`.
