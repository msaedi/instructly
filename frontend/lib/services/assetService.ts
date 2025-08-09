// frontend/lib/services/assetService.ts
// R2 asset URL builder and activity background resolver

type Viewport = 'mobile' | 'tablet' | 'desktop';

const R2_BASE = process.env.NEXT_PUBLIC_R2_URL || '';

// Simple in-memory cache (per session)
const urlCache = new Map<string, string>();

const ACTIVITY_ALIASES: Record<string, string> = {
  piano: 'piano', keyboard: 'piano',
  yoga: 'yoga', pilates: 'yoga',
  cooking: 'cooking', baking: 'cooking',
  math: 'math', algebra: 'math', calculus: 'math',
  fitness: 'fitness', workout: 'fitness',
};

const VIEWPORT_SUFFIX: Record<Viewport, string> = {
  mobile: 'mobile',
  tablet: 'tablet',
  desktop: 'desktop',
};

function normalizeActivity(input?: string): string {
  if (!input) return 'default';
  const key = input.trim().toLowerCase();
  return ACTIVITY_ALIASES[key] || key || 'default';
}

function buildR2Url(path: string): string | null {
  if (!R2_BASE) return null;
  return `${R2_BASE.replace(/\/$/, '')}/${path.replace(/^\//, '')}`;
}

export function getAuthBackground(variant: 'default' | 'morning' | 'evening' | 'night' = 'default', viewport: Viewport = 'desktop'): string | null {
  const key = `auth:${variant}:${viewport}`;
  if (urlCache.has(key)) return urlCache.get(key)!;
  // Prefer known, generic defaults first to avoid selecting non-existent responsive variants.
  const candidate =
    // Prefer WebP first (more efficient); fall back to PNG
    buildR2Url(`backgrounds/auth/default.webp`) ||
    buildR2Url(`backgrounds/auth/default.png`) ||
    buildR2Url(`backgrounds/auth/${variant}.webp`) ||
    buildR2Url(`backgrounds/auth/${variant}.png`) ||
    buildR2Url(`backgrounds/auth/${variant}-${VIEWPORT_SUFFIX[viewport]}.webp`) ||
    buildR2Url(`backgrounds/auth/${variant}-${VIEWPORT_SUFFIX[viewport]}.png`);
  if (candidate) urlCache.set(key, candidate);
  return candidate;
}

export function getActivityBackground(activity?: string, viewport: Viewport = 'desktop'): string | null {
  const normalized = normalizeActivity(activity);
  const key = `activity:${normalized}:${viewport}`;
  if (urlCache.has(key)) return urlCache.get(key)!;

  // Support both backgrounds/activities/<activity>/ and backgrounds/<activity>/ for special cases like 'home'
  const candidates: Array<string | null> = [];

  if (normalized === 'home') {
    // Try dedicated home path first
    candidates.push(
      buildR2Url(`backgrounds/home/default.webp`),
      buildR2Url(`backgrounds/home/default.png`),
      buildR2Url(`backgrounds/home/${VIEWPORT_SUFFIX[viewport]}.webp`),
      buildR2Url(`backgrounds/home/${VIEWPORT_SUFFIX[viewport]}.png`)
    );
  }

  // Then try activities path
  candidates.push(
    buildR2Url(`backgrounds/activities/${normalized}/default.webp`),
    buildR2Url(`backgrounds/activities/${normalized}/default.png`),
    buildR2Url(`backgrounds/activities/${normalized}/${VIEWPORT_SUFFIX[viewport]}.webp`),
    buildR2Url(`backgrounds/activities/${normalized}/${VIEWPORT_SUFFIX[viewport]}.png`)
  );

  // Finally fallback to auth default
  candidates.push(
    buildR2Url(`backgrounds/auth/default.webp`),
    buildR2Url(`backgrounds/auth/default.png`)
  );

  const resolved = candidates.find(Boolean) || null;
  if (resolved) urlCache.set(key, resolved);
  return resolved;
}

export function getResponsiveSet(urlBasePath: string): { mobile: string | null; tablet: string | null; desktop: string | null } {
  return {
    mobile: buildR2Url(`${urlBasePath}-mobile.webp`),
    tablet: buildR2Url(`${urlBasePath}-tablet.webp`),
    desktop: buildR2Url(`${urlBasePath}-desktop.webp`),
  };
}

export function clearAssetCache() {
  urlCache.clear();
}
