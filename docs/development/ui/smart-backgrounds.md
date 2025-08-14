## Smart Backgrounds (Frontend)

This document explains how the global background system works in the frontend, how to add new images, how service/category resolution works, and how to tune rotation.

### Overview

- Global background is rendered once in `frontend/components/ui/GlobalBackground.tsx` and mounted in `frontend/app/layout.tsx`.
- Background selection and image optimization live in `frontend/lib/services/assetService.ts`.
- Global UI knobs are centralized in `frontend/lib/config/uiConfig.ts`.
- Pages can set an “activity” and/or overrides via the provider in `frontend/lib/config/backgroundProvider.tsx`.

### R2 paths and naming

All background assets live under your R2 bucket (base: `NEXT_PUBLIC_R2_URL`). Clean paths are used and then delivered via Cloudflare Image Transformations for performance.

- Category default(s):
  - `/backgrounds/activities/{category}/default.webp`
  - Variants supported: `/default-2.webp`, `/default-3.webp`, … (WebP-first, PNG fallback)

- Service-specific:
  - `/backgrounds/activities/{category}/{service}.webp`
  - Variants supported: `/{service}-2.webp`, `/{service}-3.webp`, … (WebP-first, PNG fallback)

Examples:

```text
/backgrounds/activities/sports-fitness/yoga.webp
/backgrounds/activities/sports-fitness/yoga-2.webp
/backgrounds/activities/music/piano.webp
/backgrounds/activities/music/piano-2.webp
/backgrounds/activities/music/default.webp
/backgrounds/activities/music/default-2.webp
```

### Naming conventions (required)

- Filenames must be lowercase and use the service slug (hyphen-separated) exactly as in the catalog.
  - Examples: `piano`, `hip-hop-dance`, `personal-training`.
- Specific service variants:
  - `{serviceSlug}.webp`, `{serviceSlug}-2.webp`, `{serviceSlug}-3.webp`, … up to `-10`.
  - The base without a suffix is considered variant #1.
  - Variants must be consecutive; discovery stops at the first missing number.
- Category defaults and variants:
  - `default.webp`, `default-2.webp`, `default-3.webp`, … up to `-10`.
  - Used whenever a service has no specific asset. If multiple exist, they rotate.
- Preferred format is `.webp`. `.png` with the same name is accepted as a fallback.
  - Example: `piano.png`, `piano-2.png`, `default.png`, `default-2.png`.
- Directory placement:
  - Service-specific: `/backgrounds/activities/{categorySlug}/{serviceSlug}.webp`
  - Category variants: `/backgrounds/activities/{categorySlug}/default.webp`

How they are used:
- If a service has specific files (`{serviceSlug}.webp` and variants), those are used (and rotated if >1).
- If no specific files exist, the system looks for category defaults (`default.webp` and numbered variants) and rotates among them if >1.
- If neither exists, falls back to `arts/default.webp`.

### How an activity resolves to an image

Resolution logic in `frontend/lib/services/assetService.ts`:

1) Aliases (optional, highest priority)
   - `CATEGORY_FOR_ACTIVITY` maps arbitrary terms to a `{ category, specific? }` target.
   - Aliases are matched flexibly by trying the raw key, spaces→dashes, and dashes→spaces.
   - Use this to point synonyms or non-catalog terms to a specific asset.

2) Catalog-based resolution (default)
   - Loads categories/services once via `publicApi.getAllServicesWithInstructors()`.
   - Matches the given service id/slug/name to a category slug and service slug.
   - If a specific image exists, it’s used (and rotated if multiple variants exist).
   - If no specific image, rotates among category defaults if multiple exist, otherwise uses category default.

3) Final fallback
   - If nothing matches, falls back to `/backgrounds/activities/arts/default.webp`.

Cloudflare delivery:
- Final URLs are delivered via `/cdn-cgi/image/width=...,quality=...,format=auto/...` using viewport-specific width/quality.

### Centralized configuration

File: `frontend/lib/config/uiConfig.ts`

```ts
export interface UIConfig {
  backgrounds: {
    blur: boolean;
    blurAmount: number;
    overlay: boolean;
    overlayOpacity: number; // 0..1
    overlayColorLight: string;
    overlayColorDark: string;
    transitionDuration: number; // ms
    enableRotation: boolean;
    rotationInterval: number; // ms
  };
  darkMode: {
    backgroundOpacity: number; // 0..1
    cardOpacity: number; // 0..1
    enableTransparency: boolean;
  };
}
```

Key rotation behaviors:
- `enableRotation = true` and `rotationInterval = 0`: rotate on each resolve (e.g., when navigating or re-resolving).
- `enableRotation = true` and `rotationInterval > 0`: also auto-rotate in place using a timer.
- `enableRotation = false`: no rotation.

Auto-rotation guardrails:
- Only starts a timer if the current activity/category has more than one variant.
- Pauses when the tab is hidden.
- Compares new URL vs current to avoid unnecessary blur-up when the image hasn’t changed.

### Page-level usage

Provider: `frontend/lib/config/backgroundProvider.tsx`

- Wraps the app in `frontend/app/layout.tsx`:

```tsx
// layout.tsx
import { BackgroundProvider } from '@/lib/config/backgroundProvider';
import GlobalBackground from '../components/ui/GlobalBackground';

<BackgroundProvider>
  <GlobalBackground />
  <Providers>{children}</Providers>
</BackgroundProvider>
```

- Pages can set activity (service id/slug/name) with `useBackgroundConfig()`:

```tsx
import { useBackgroundConfig } from '@/lib/config/backgroundProvider';

const { setActivity, setOverrides, clearOverrides } = useBackgroundConfig();

// Example: set from query or service slug
setActivity('yoga');            // service slug/name/id
setOverrides({ overlayOpacity: 0.7, blur: true, blurAmount: 8 });
```

Notes:
- Home/login/signup clear any carried activity so route defaults apply immediately.
- Avoid page root backgrounds that hide the global background (e.g., remove `bg-gray-50` from the root container if needed).

### Aliases with `CATEGORY_FOR_ACTIVITY`

File: `frontend/lib/services/assetService.ts`

Use `CATEGORY_FOR_ACTIVITY` to point synonyms or non-catalog terms to an existing specific or category target.

```ts
const CATEGORY_FOR_ACTIVITY: Record<string, { category: string; specific?: string }> = {
  // Arts → point multiple terms to arts/dance images
  'dance': { category: 'arts', specific: 'dance' },
  'hip hop dance': { category: 'arts', specific: 'dance' },
  'jazz dance': { category: 'arts', specific: 'dance' },
  'contemporary dance': { category: 'arts', specific: 'dance' },
  'tap dance': { category: 'arts', specific: 'dance' },

  // Sports & Fitness → map to category default (no specific)
  'personal trainer': { category: 'sports-fitness' },
  'personal training': { category: 'sports-fitness' },
  'dance fitness': { category: 'arts', specific: 'dance' },
};
```

Matching:
- Aliases are matched against: exact key, spaces→dashes, and dashes→spaces. So `hip hop dance` and `hip-hop-dance` both work.
- When `specific` is present, it must match the service slug that your files use under the target category (e.g., `specific: 'dance'` expects files like `/backgrounds/activities/arts/dance.webp`, `dance-2.webp`, …).

When to add aliases:
- You want a term to reuse an existing specific image (e.g., “pilates” → `sports-fitness/yoga`).
- You want a non-catalog term to resolve to a category default.

When you don’t need aliases:
- The term exists in the services catalog, and your assets use the service slug for filenames (the system resolves it automatically).

### Rotation details

Variant discovery order:
- Specific: `{service}.webp`, then `{service}-2.webp`, `{service}-3.webp`, … up to `-10` (WebP-first, PNG fallback).
- Category defaults: `default.webp`, then `default-2.webp`, `default-3.webp`, … up to `-10` (WebP-first, PNG fallback).

Rotation state:
- Per-activity index is stored in `sessionStorage` (`background-variants`) to provide variety across page loads.
- Index updates on each rotation and is cached per-session.

Auto-rotation:
- Controlled by `uiConfig.backgrounds.enableRotation` and `uiConfig.backgrounds.rotationInterval` (ms).
- If multiple variants exist and interval > 0, the global background auto-advances while the page is visible.

### Troubleshooting

- Background not visible: ensure the page root doesn’t set an opaque background color that covers the global background.
- Stuck on a blur: this should be handled, but if you add custom code, avoid resetting blur state when the URL didn’t change.
- No image for a term: either add a matching service slug image under its category, or add an alias in `CATEGORY_FOR_ACTIVITY`.

### File references

- Global background component:
  - `frontend/components/ui/GlobalBackground.tsx`

- Layout (provider mount point):
  - `frontend/app/layout.tsx`

- Configuration:
  - `frontend/lib/config/uiConfig.ts`
  - `frontend/lib/config/backgroundProvider.tsx`

- Asset resolution and optimization:
  - `frontend/lib/services/assetService.ts`
