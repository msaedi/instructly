# SSL/HTTPS Implementation Summary for InstaInstru

## Overview
A complete SSL/HTTPS implementation has been added to InstaInstru, enabling secure communication for both local development and production environments.

## What Was Implemented

### 1. SSL Certificate Generation
- **Script**: `setup-local-ssl.sh`
- **Purpose**: Generates local SSL certificates using mkcert
- **Output**: Creates certificates in `backend/certs/` and `frontend/certs/`
- **Usage**: One-time setup for developers

### 2. Backend HTTPS Support

#### HTTP Server (run.py)
- **Port**: 8000
- **Database**: Test database (local development)
- **Purpose**: Standard development server
- **Key Feature**: Forces `is_testing=True` to ensure test database usage

#### HTTPS Server (run_ssl.py)
- **Port**: 8001
- **Database**: Test database (local development)
- **Purpose**: HTTPS development server for testing secure features
- **SSL**: Uses locally generated certificates

#### HTTPS Redirect Middleware
- **File**: `backend/app/middleware/https_redirect.py`
- **Purpose**: Forces HTTP → HTTPS redirect in production
- **Behavior**:
  - Production: All HTTP requests redirect to HTTPS
  - Development: No redirect (allows both HTTP and HTTPS)

### 3. Frontend HTTPS Support

#### HTTPS Development Server
- **File**: `frontend/server.js`
- **Port**: 3001
- **Purpose**: Serves Next.js app over HTTPS for local development

#### NPM Scripts
```json
"dev:http": "rm -rf .next && NEXT_PUBLIC_API_URL=http://localhost:8000 next dev",
"dev:https": "rm -rf .next && cross-env NEXT_PUBLIC_API_URL=https://localhost:8001 NEXT_PUBLIC_APP_URL=https://localhost:3001 node server.js"
```
- Automatically clears Next.js cache when switching modes
- Prevents "file not found" errors

### 4. CORS Configuration
Updated `ALLOWED_ORIGINS` in `constants.py` to include:
- `http://localhost:3000` - HTTP frontend
- `https://localhost:3000` - HTTPS frontend (same port)
- `https://localhost:3001` - HTTPS frontend (alternate port)
- `http://localhost:8000` - HTTP backend
- `https://localhost:8001` - HTTPS backend

### 5. Cookie Security
Authentication cookies automatically adjust based on protocol:
- **HTTP**: `secure=false`, `sameSite=lax`
- **HTTPS**: `secure=true`, `sameSite=none`

## Environment Usage

### Local Development
Both HTTP and HTTPS are available for testing:

| Mode | Backend | Frontend | Database |
|------|---------|----------|----------|
| HTTP | http://localhost:8000 | http://localhost:3000 | Test DB |
| HTTPS | https://localhost:8001 | https://localhost:3001 | Test DB |

**Key Point**: Both modes use the test database to protect production data.

### Production (Vercel)
- **Frontend**: Automatically serves over HTTPS (Vercel provides SSL)
- **Backend**: When deployed, the HTTPS redirect middleware activates
- **Database**: Uses production database (Supabase)
- **SSL Certificates**: Managed by hosting providers (not self-signed)

## How to Use

### Local Development Setup

1. **Generate certificates** (one-time):
   ```bash
   ./setup-local-ssl.sh
   ```

2. **Choose your development mode**:

   **Option A - HTTP Only (Simpler)**:
   ```bash
   # Terminal 1
   python backend/run.py

   # Terminal 2
   npm run dev:http
   ```

   **Option B - HTTPS Only**:
   ```bash
   # Terminal 1
   python backend/run_ssl.py

   # Terminal 2
   npm run dev:https
   ```

   **Option C - Both (Full Testing)**:
   ```bash
   # Terminal 1
   python backend/run.py

   # Terminal 2
   python backend/run_ssl.py

   # Terminal 3
   npm run dev:http

   # Terminal 4
   npm run dev:https
   ```

### Switching Between Modes
When switching between HTTP/HTTPS in frontend:
- The npm scripts automatically clear the `.next` cache
- This prevents build artifacts conflicts

## Testing Procedures

### 1. Basic Connectivity Test
```bash
# Test all endpoints
curl http://localhost:8000/health
curl -k https://localhost:8001/health
curl http://localhost:3000
curl -k https://localhost:3001
```

### 2. Authentication Test
```bash
# Run the comprehensive test script
python backend/scripts/test_ssl_login.py
```

Expected output:
```
Testing login with sarah.chen@example.com
HTTP on port 8000:
  Status: 200
  ✅ Success! Token: eyJhbGciOiJIUzI1NiIsInR5cCI6Ik...
HTTPS on port 8001:
  Status: 200
  ✅ Success! Token: eyJhbGciOiJIUzI1NiIsInR5cCI6Ik...
```

### 3. Database Verification
```bash
# Verify both use test database
curl http://localhost:8000/test/settings-debug
curl -k https://localhost:8001/test/settings-debug
```

Both should show:
- `"is_testing": true`
- `"actual_db_used": "postgresql://...localhost:5432/instainstru_test"`

### 4. CORS Testing
From the browser console at https://localhost:3001:
```javascript
fetch('https://localhost:8001/health')
  .then(r => r.json())
  .then(console.log)
```

Should return health check without CORS errors.

### 5. Cookie Security Test
1. Login via HTTPS frontend (https://localhost:3001)
2. Open DevTools → Application → Cookies
3. Verify the auth cookie has:
   - `Secure`: ✓ (checked)
   - `HttpOnly`: ✓ (checked)
   - `SameSite`: None

### 6. Production Simulation
To test HTTPS redirect (production behavior):
```bash
# Temporarily set production environment
ENVIRONMENT=production python backend/run.py
```

Then try accessing http://localhost:8000 - it should redirect to HTTPS.

## Common Issues and Solutions

### Certificate Warnings
- **Issue**: Browser shows "Not Secure" for localhost
- **Solution**: Click "Advanced" → "Proceed to localhost"
- **Note**: This is normal for self-signed certificates

### Port Conflicts
- **Issue**: "Address already in use"
- **Solution**: Kill existing processes or use different ports

### Frontend Cache Issues
- **Issue**: "ENOENT: no such file or directory" when switching modes
- **Solution**: Already handled by npm scripts that clear cache

### Database Connection
- **Issue**: Login fails with 401
- **Solution**: Ensure test database is seeded:
  ```bash
  python backend/scripts/reset_and_seed_database_enhanced.py
  ```

## Security Considerations

### Local Development
- Self-signed certificates are acceptable
- Both HTTP and HTTPS use test database
- No production data at risk

### Production
- HTTPS redirect middleware forces secure connections
- Cookies marked as secure
- SSL certificates from trusted CAs (Vercel/hosting provider)
- All API endpoints protected by HTTPS

## File Structure
```
project/
├── setup-local-ssl.sh              # Certificate generation script
├── backend/
│   ├── run.py                      # HTTP development server
│   ├── run_ssl.py                  # HTTPS development server
│   ├── certs/                      # SSL certificates (gitignored)
│   ├── app/
│   │   ├── middleware/
│   │   │   └── https_redirect.py   # HTTPS redirect for production
│   │   └── core/
│   │       └── constants.py        # Updated ALLOWED_ORIGINS
│   └── scripts/
│       └── test_ssl_login.py       # SSL testing script
├── frontend/
│   ├── server.js                   # HTTPS development server
│   ├── certs/                      # SSL certificates (gitignored)
│   └── package.json                # Updated npm scripts
└── docs/
    └── SSL_SETUP.md                # Detailed setup guide
```

## Verification Checklist

- [ ] Local certificates generated
- [ ] HTTP server runs on port 8000
- [ ] HTTPS server runs on port 8001
- [ ] Frontend works on both HTTP (3000) and HTTPS (3001)
- [ ] Login works on both protocols
- [ ] Both servers use test database
- [ ] CORS allows all configured origins
- [ ] Cookies are secure on HTTPS
- [ ] No mixed content warnings
- [ ] Frontend can switch between modes without errors

## Summary

The SSL/HTTPS implementation provides:
1. **Complete local HTTPS development environment**
2. **Production-ready HTTPS configuration**
3. **Secure cookie handling**
4. **Proper CORS for all environments**
5. **Database isolation (test DB for local dev)**
6. **Easy mode switching for developers**

The implementation is designed to be:
- **Secure**: Proper HTTPS in production
- **Flexible**: Support both HTTP and HTTPS locally
- **Safe**: Always uses test database for development
- **Simple**: Easy commands to start either mode
