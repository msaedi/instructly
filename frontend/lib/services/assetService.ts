// frontend/lib/services/assetService.ts
// R2 asset URL builder and activity background resolver with Cloudflare Image Transformations

import { R2_URL } from '@/lib/publicEnv';

type Viewport = 'mobile' | 'tablet' | 'desktop';

// Cloudflare Image Transformation options
export interface ImageTransformOptions {
  width?: number;
  height?: number;
  quality?: number;
  format?: 'auto' | 'webp' | 'avif' | 'json';
  fit?: 'scale-down' | 'contain' | 'cover' | 'crop' | 'pad';
  sharpen?: number;
  blur?: number;
  dpr?: number; // Device Pixel Ratio for retina displays
}

const R2_BASE = R2_URL;

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

/**
 * Builds an optimized image URL using Cloudflare Image Transformations
 * @param path - The image path (e.g., '/backgrounds/auth/default.png')
 * @param options - Transformation options
 * @returns Optimized URL with transformations applied
 */
export function getOptimizedUrl(path: string, options: ImageTransformOptions = {}): string | null {
  if (!R2_BASE) return null;

  const baseUrl = R2_BASE.replace(/\/$/, '');
  const cleanPath = path.startsWith('/') ? path : `/${path}`;

  // Build transformation parameters
  const params: string[] = [];

  if (options.width) params.push(`width=${options.width}`);
  if (options.height) params.push(`height=${options.height}`);
  if (options.quality !== undefined) params.push(`quality=${options.quality}`);
  if (options.format) params.push(`format=${options.format}`);
  if (options.fit) params.push(`fit=${options.fit}`);
  if (options.sharpen !== undefined) params.push(`sharpen=${options.sharpen}`);
  if (options.blur !== undefined) params.push(`blur=${options.blur}`);
  if (options.dpr !== undefined) params.push(`dpr=${options.dpr}`);

  // Default to auto format if any transformations are specified but format is not
  if (params.length > 0 && !options.format) {
    params.push('format=auto');
  }

  // If no transformations, return original URL
  if (params.length === 0) {
    return `${baseUrl}${cleanPath}`;
  }

  // Build optimized URL with Cloudflare transformations
  return `${baseUrl}/cdn-cgi/image/${params.join(',')}${cleanPath}`;
}

/**
 * Helper to detect appropriate width based on viewport
 */
export function getViewportWidth(viewport: Viewport = 'desktop'): number {
  switch (viewport) {
    case 'mobile':
      return 640;
    case 'tablet':
      return 1024;
    case 'desktop':
    default:
      return 1920;
  }
}

/**
 * Helper to get device-appropriate quality
 */
export function getViewportQuality(viewport: Viewport = 'desktop'): number {
  switch (viewport) {
    case 'mobile':
      return 75;
    case 'tablet':
      return 80;
    case 'desktop':
    default:
      return 85;
  }
}

/**
 * Detect current viewport based on window width
 */
export function detectViewport(): Viewport {
  if (typeof window === 'undefined') return 'desktop';
  const width = window.innerWidth;
  if (width < 640) return 'mobile';
  if (width < 1024) return 'tablet';
  return 'desktop';
}

export function getAuthBackground(variant: 'default' | 'morning' | 'evening' | 'night' = 'default', viewport: Viewport = 'desktop'): string | null {
  const key = `auth:${variant}:${viewport}:optimized`;
  if (urlCache.has(key)) return urlCache.get(key)!;

  // If R2_BASE is not set, return null (no background in tests)
  if (!R2_BASE) return null;

  // Find the base image path
  const paths = [
    `backgrounds/auth/default.webp`,
    `backgrounds/auth/default.png`,
    `backgrounds/auth/${variant}.webp`,
    `backgrounds/auth/${variant}.png`,
    `backgrounds/auth/${variant}-${VIEWPORT_SUFFIX[viewport]}.webp`,
    `backgrounds/auth/${variant}-${VIEWPORT_SUFFIX[viewport]}.png`
  ];

  // Find first valid path
  const validPath = paths.find(p => buildR2Url(p));
  if (!validPath) return null;

  // Apply optimizations based on viewport
  const optimized = getOptimizedUrl(validPath, {
    width: getViewportWidth(viewport),
    quality: getViewportQuality(viewport),
    format: 'auto',
    fit: 'cover'
  });

  if (optimized) urlCache.set(key, optimized);
  return optimized;
}

export function getActivityBackground(activity?: string, viewport: Viewport = 'desktop'): string | null {
  const normalized = normalizeActivity(activity);
  const key = `activity:${normalized}:${viewport}:optimized`;
  if (urlCache.has(key)) return urlCache.get(key)!;

  // If R2_BASE is not set, return null (no background in tests)
  if (!R2_BASE) return null;

  // Build list of paths to try
  const paths: string[] = [];

  if (normalized === 'home') {
    // Try dedicated home path first
    paths.push(
      `backgrounds/home/default.webp`,
      `backgrounds/home/default.png`,
      `backgrounds/home/${VIEWPORT_SUFFIX[viewport]}.webp`,
      `backgrounds/home/${VIEWPORT_SUFFIX[viewport]}.png`
    );
  }

  // Then try activities path
  paths.push(
    `backgrounds/activities/${normalized}/default.webp`,
    `backgrounds/activities/${normalized}/default.png`,
    `backgrounds/activities/${normalized}/${VIEWPORT_SUFFIX[viewport]}.webp`,
    `backgrounds/activities/${normalized}/${VIEWPORT_SUFFIX[viewport]}.png`
  );

  // Finally fallback to auth default
  paths.push(
    `backgrounds/auth/default.webp`,
    `backgrounds/auth/default.png`
  );

  // Find first valid path
  const validPath = paths.find(p => buildR2Url(p));
  if (!validPath) return null;

  // Apply optimizations based on viewport
  const optimized = getOptimizedUrl(validPath, {
    width: getViewportWidth(viewport),
    quality: getViewportQuality(viewport),
    format: 'auto',
    fit: 'cover'
  });

  if (optimized) urlCache.set(key, optimized);
  return optimized;
}

export function getResponsiveSet(urlBasePath: string): { mobile: string | null; tablet: string | null; desktop: string | null } {
  return {
    mobile: getOptimizedUrl(`${urlBasePath}-mobile.webp`, {
      width: 640,
      quality: 75,
      format: 'auto',
      fit: 'cover'
    }),
    tablet: getOptimizedUrl(`${urlBasePath}-tablet.webp`, {
      width: 1024,
      quality: 80,
      format: 'auto',
      fit: 'cover'
    }),
    desktop: getOptimizedUrl(`${urlBasePath}-desktop.webp`, {
      width: 1920,
      quality: 85,
      format: 'auto',
      fit: 'cover'
    }),
  };
}

/**
 * Generate a low-quality placeholder URL for blur-up effect
 * @param path - The image path
 * @returns Low-quality optimized URL for quick loading
 */
export function getLowQualityUrl(path: string): string | null {
  return getOptimizedUrl(path, {
    width: 100,  // Small for quick load but visible
    quality: 40,
    format: 'auto',
    fit: 'scale-down'
  });
}

/**
 * Generate optimized URL for current device
 * @param path - The image path
 * @returns Optimized URL based on current viewport
 */
export function getOptimizedForDevice(path: string): string | null {
  const viewport = detectViewport();
  return getOptimizedUrl(path, {
    width: getViewportWidth(viewport),
    quality: getViewportQuality(viewport),
    format: 'auto',
    fit: 'cover'
  });
}

export function clearAssetCache() {
  urlCache.clear();
}

// ---------------- Smart Activity Backgrounds (variants + category fallback) ----------------
import { publicApi } from '@/features/shared/api/client';

type ServiceMeta = {
  id: string;
  slug: string;
  name: string;
  categorySlug: string;
};

const serviceIdToMeta = new Map<string, ServiceMeta>();
const serviceSlugToMeta = new Map<string, ServiceMeta>();
const serviceNameToMeta = new Map<string, ServiceMeta>();
let catalogLoadedPromise: Promise<void> | null = null;

async function ensureServiceCatalogLoaded(): Promise<void> {
  if (catalogLoadedPromise) return catalogLoadedPromise;
  catalogLoadedPromise = (async () => {
    try {
      const resp = await publicApi.getAllServicesWithInstructors();
      if (!resp || resp.error || !resp.data) return;
      const categories = resp.data.categories ?? [];
      for (const cat of categories) {
        const categorySlug = (cat.name ?? '').toLowerCase().replace(/&/g, '').replace(/\s+/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
        const services = cat.services ?? [];
        for (const svc of services) {
          const meta: ServiceMeta = {
            id: String(svc.id),
            slug: svc.slug,
            name: svc.name,
            categorySlug,
          };
          serviceIdToMeta.set(meta.id, meta);
          serviceSlugToMeta.set(meta.slug.toLowerCase(), meta);
          serviceNameToMeta.set(meta.name.toLowerCase(), meta);
        }
      }
    } catch {
      // ignore; fallback to static mapping
    }
  })();
  return catalogLoadedPromise;
}

// Minimal mapping for known specific activities → category and specific key
const CATEGORY_FOR_ACTIVITY: Record<string, { category: string; specific?: string }> = {
  // Arts
  dance: { category: 'arts', specific: 'dance' },
  'hip hop dance': { category: 'arts', specific: 'dance' },
  'jazz dance': { category: 'arts', specific: 'dance' },
  'contemporary dance': { category: 'arts', specific: 'dance' },
  'tap dance': { category: 'arts', specific: 'dance' },
  dancing: { category: 'arts', specific: 'dance' },
  ballet: { category: 'arts', specific: 'dance' },
  painting: { category: 'arts' },
  drawing: { category: 'arts' },
  // Sports & Fitness
  pilates: { category: 'sports-fitness', specific: 'yoga' },
  tennis: { category: 'sports-fitness', specific: 'tennis' },
  'personal training': { category: 'sports-fitness' },
  'personal trainer': { category: 'sports-fitness' },
  trainer: { category: 'sports-fitness' },
  fitness: { category: 'sports-fitness' },
  workout: { category: 'sports-fitness' },
  'dance fitness': { category: 'arts', specific: 'dance' },
  // Music
  guitar: { category: 'music', specific: 'guitar' },
  piano: { category: 'music' },
  drums: { category: 'music' },
};

const imageExistsCache = new Map<string, boolean>();
const variantCache = new Map<string, string[]>(); // key: `${category}/${specific}`
const categoryVariantCache = new Map<string, string[]>(); // key: `${category}`
const currentVariantIndex = new Map<string, number>(); // key: `${category}-${specific}`
const lastRotationTs = new Map<string, number>();

function initializeRotation() {
  if (typeof window === 'undefined') return;
  try {
    const stored = window.sessionStorage.getItem('background-variants');
    if (stored) {
      const entries: Array<[string, number]> = JSON.parse(stored);
      entries.forEach(([k, v]) => currentVariantIndex.set(k, v));
    }
  } catch {
    // ignore
  }
}

function saveRotationState() {
  if (typeof window === 'undefined') return;
  try {
    const entries = Array.from(currentVariantIndex.entries());
    window.sessionStorage.setItem('background-variants', JSON.stringify(entries));
  } catch {
    // ignore
  }
}

async function imageExists(cleanPath: string): Promise<boolean> {
  if (!R2_BASE) return false;
  if (imageExistsCache.has(cleanPath)) return imageExistsCache.get(cleanPath)!;
  const url = getOptimizedUrl(cleanPath, { width: 1, quality: 1 }) || buildR2Url(cleanPath) || '';
  if (!url) return false;

  // Prefer Image probe in browser to avoid HEAD/CORS issues
  if (typeof window !== 'undefined') {
    const result = await new Promise<boolean>((resolve) => {
      const img = new Image();
      img.onload = () => resolve(true);
      img.onerror = () => resolve(false);
      img.src = url;
    });
    imageExistsCache.set(cleanPath, result);
    return result;
  }

  // Fallback for non-browser environments
  try {
    const res = await fetch(url, { method: 'HEAD' });
    const ok = res.ok;
    imageExistsCache.set(cleanPath, ok);
    return ok;
  } catch {
    imageExistsCache.set(cleanPath, false);
    return false;
  }
}

async function getActivityVariants(category: string, specific: string): Promise<string[]> {
  const cacheKey = `${category}/${specific}`;
  if (variantCache.has(cacheKey)) return variantCache.get(cacheKey)!;

  const variants: string[] = [];
  const base = `/backgrounds/activities/${category}/${specific}`;

  // Base file: prefer webp then png
  if (await imageExists(`${base}.webp`)) variants.push(`${base}.webp`);
  else if (await imageExists(`${base}.png`)) variants.push(`${base}.png`);

  // Numbered variants 2..10
  for (let i = 2; i <= 10; i++) {
    const webp = `${base}-${i}.webp`;
    const png = `${base}-${i}.png`;
    if (await imageExists(webp)) variants.push(webp);
    else if (await imageExists(png)) variants.push(png);
    else break;
  }

  variantCache.set(cacheKey, variants);
  return variants;
}

function getCategoryDefaultPath(category: string): string {
  // Prefer webp; fall back to png (best-effort without HEAD)
  return `/backgrounds/activities/${category}/default.webp`;
}

async function getCategoryVariants(category: string): Promise<string[]> {
  if (categoryVariantCache.has(category)) return categoryVariantCache.get(category)!;

  const variants: string[] = [];
  const base = `/backgrounds/activities/${category}/default`;

  // Base default
  if (await imageExists(`${base}.webp`)) variants.push(`${base}.webp`);
  else if (await imageExists(`${base}.png`)) variants.push(`${base}.png`);

  // Numbered defaults 2..10
  for (let i = 2; i <= 10; i++) {
    const webp = `${base}-${i}.webp`;
    const png = `${base}-${i}.png`;
    if (await imageExists(webp)) variants.push(webp);
    else if (await imageExists(png)) variants.push(png);
    else break;
  }

  categoryVariantCache.set(category, variants);
  return variants;
}

function getRotatedVariant(
  variants: string[],
  key: string,
  enableRotation: boolean,
  rotationIntervalMs: number,
): string {
  if (variants.length <= 1) return variants[0] || '';

  // Ensure rotation state is hydrated
  if (typeof window !== 'undefined' && currentVariantIndex.size === 0) initializeRotation();

  const now = Date.now();
  const lastTs = lastRotationTs.get(key) || 0;
  let idx = currentVariantIndex.get(key) || 0;

  if (enableRotation) {
    if (rotationIntervalMs > 0) {
      if (now - lastTs >= rotationIntervalMs) {
        idx = (idx + 1) % variants.length;
        currentVariantIndex.set(key, idx);
        lastRotationTs.set(key, now);
        saveRotationState();
      }
    } else {
      idx = (idx + 1) % variants.length;
      currentVariantIndex.set(key, idx);
      lastRotationTs.set(key, now);
      saveRotationState();
    }
  }

  return variants[idx] || '';
}

/**
 * Return a clean background path for a service/activity. If a categorySlug is provided,
 * use it as fallback when no specific mapping exists.
 */
export async function getSmartBackgroundForService(
  serviceIdentifier: string,
  categorySlug?: string,
  options?: { enableRotation?: boolean; rotationIntervalMs?: number }
): Promise<string | null> {
  const enableRotation = options?.enableRotation ?? true;
  const rotationIntervalMs = options?.rotationIntervalMs ?? 0;
  if (!serviceIdentifier) return categorySlug ? getCategoryDefaultPath(categorySlug) : '/backgrounds/activities/arts/default.webp';

  const key = serviceIdentifier.trim().toLowerCase();

  // Alias override BEFORE catalog lookup (handles synonyms taking precedence over slug assets)
  const aliasDirect = CATEGORY_FOR_ACTIVITY[key] as { category: string; specific?: string } | undefined;
  const aliasSpaceToDash = CATEGORY_FOR_ACTIVITY[key.replace(/\s+/g, '-')] as { category: string; specific?: string } | undefined;
  const aliasDashToSpace = CATEGORY_FOR_ACTIVITY[key.replace(/-/g, ' ')] as { category: string; specific?: string } | undefined;
  const aliasResolved = (aliasDirect || aliasSpaceToDash || aliasDashToSpace) as { category: string; specific?: string } | undefined;
  if (aliasResolved?.specific) {
    const variants = await getActivityVariants(aliasResolved.category, aliasResolved.specific);
    if (variants.length > 0) {
      const rotated = getRotatedVariant(variants, `${aliasResolved.category}-${aliasResolved.specific}`, enableRotation, rotationIntervalMs);
      return rotated;
    }
    const catVariants = await getCategoryVariants(aliasResolved.category);
    if (catVariants.length > 0) {
      const rotated = getRotatedVariant(catVariants, `${aliasResolved.category}__category__`, enableRotation, rotationIntervalMs);
      return rotated;
    }
    return getCategoryDefaultPath(aliasResolved.category);
  } else if (aliasResolved) {
    const catVariants = await getCategoryVariants(aliasResolved.category);
    if (catVariants.length > 0) {
      const rotated = getRotatedVariant(catVariants, `${aliasResolved.category}__category__`, enableRotation, rotationIntervalMs);
      return rotated;
    }
    return getCategoryDefaultPath(aliasResolved.category);
  }

  // PRIORITY 1: Explicit alias override mapping (handles synonyms like hip hop dance → arts/dance)
  const alias = CATEGORY_FOR_ACTIVITY[key];
  if (alias?.specific) {
    const variants = await getActivityVariants(alias.category, alias.specific);
    if (variants.length > 0) {
      const rotated = getRotatedVariant(variants, `${alias.category}-${alias.specific}`, enableRotation, rotationIntervalMs);
      return rotated;
    }
    const catVariants = await getCategoryVariants(alias.category);
    if (catVariants.length > 0) {
      const rotated = getRotatedVariant(catVariants, `${alias.category}__category__`, enableRotation, rotationIntervalMs);
      return rotated;
    }
    return getCategoryDefaultPath(alias.category);
  } else if (alias) {
    const catVariants = await getCategoryVariants(alias.category);
    if (catVariants.length > 0) {
      const rotated = getRotatedVariant(catVariants, `${alias.category}__category__`, enableRotation, rotationIntervalMs);
      return rotated;
    }
    return getCategoryDefaultPath(alias.category);
  }

  // Dynamic catalog-based resolution
  await ensureServiceCatalogLoaded();
  let meta: ServiceMeta | undefined = undefined;

  // Try slug match
  meta = serviceSlugToMeta.get(key);
  // Try name match
  if (!meta) meta = serviceNameToMeta.get(key);
  // Try id match
  if (!meta && serviceIdToMeta.has(key)) meta = serviceIdToMeta.get(key);

  if (meta) {
    // Try specific variants under category/service slug
    const variants = await getActivityVariants(meta.categorySlug, meta.slug);
    if (variants.length > 0) {
      const rotated = getRotatedVariant(variants, `${meta.categorySlug}-${meta.slug}`, enableRotation, rotationIntervalMs);
      return rotated;
    }
    // Fallback to category variants rotation if present, else category default
    const catVariants = await getCategoryVariants(meta.categorySlug);
    if (catVariants.length > 0) {
      const rotated = getRotatedVariant(catVariants, `${meta.categorySlug}__category__`, enableRotation, rotationIntervalMs);
      return rotated;
    }
    return getCategoryDefaultPath(meta.categorySlug);
  }

  // Static synonyms mapping as a final helper (supports minor slug/name differences)
  const mapping = CATEGORY_FOR_ACTIVITY[key] || CATEGORY_FOR_ACTIVITY[key.replace(/-/g, ' ')] || CATEGORY_FOR_ACTIVITY[key.replace(/\s+/g, '-')];
  if (mapping?.specific) {
    const variants = await getActivityVariants(mapping.category, mapping.specific);
    if (variants.length > 0) {
      const rotated = getRotatedVariant(variants, `${mapping.category}-${mapping.specific}`, enableRotation, rotationIntervalMs);
      return rotated;
    }
    const catVariants = await getCategoryVariants(mapping.category);
    if (catVariants.length > 0) {
      const rotated = getRotatedVariant(catVariants, `${mapping.category}__category__`, enableRotation, rotationIntervalMs);
      return rotated;
    }
    return getCategoryDefaultPath(mapping.category);
  }
  if (mapping) {
    const catVariants = await getCategoryVariants(mapping.category);
    if (catVariants.length > 0) {
      const rotated = getRotatedVariant(catVariants, `${mapping.category}__category__`, enableRotation, rotationIntervalMs);
      return rotated;
    }
    return getCategoryDefaultPath(mapping.category);
  }

  // If a category slug is provided by the caller, use that
  if (categorySlug) return getCategoryDefaultPath(categorySlug);

  return '/backgrounds/activities/arts/default.webp';
}

/**
 * Determine whether a given service has multiple specific image variants available.
 * Returns true only if there are >1 variants for the specific service under its category.
 */
export async function hasMultipleVariantsForService(
  serviceIdentifier: string,
  _categorySlug?: string
): Promise<boolean> {
  if (!serviceIdentifier) return false;
  const key = serviceIdentifier.trim().toLowerCase();

  // Alias override BEFORE catalog lookup
  const aliasDirect2 = CATEGORY_FOR_ACTIVITY[key] as { category: string; specific?: string } | undefined;
  const aliasSpaceToDash2 = CATEGORY_FOR_ACTIVITY[key.replace(/\s+/g, '-')] as { category: string; specific?: string } | undefined;
  const aliasDashToSpace2 = CATEGORY_FOR_ACTIVITY[key.replace(/-/g, ' ')] as { category: string; specific?: string } | undefined;
  const aliasResolved2 = (aliasDirect2 || aliasSpaceToDash2 || aliasDashToSpace2) as { category: string; specific?: string } | undefined;
  if (aliasResolved2?.specific) {
    const variants = await getActivityVariants(aliasResolved2.category, aliasResolved2.specific);
    if (variants.length > 1) return true;
    const catVariants = await getCategoryVariants(aliasResolved2.category);
    return catVariants.length > 1;
  } else if (aliasResolved2) {
    const catVariants = await getCategoryVariants(aliasResolved2.category);
    return catVariants.length > 1;
  }

  await ensureServiceCatalogLoaded();
  const meta: ServiceMeta | undefined = serviceSlugToMeta.get(key) || serviceNameToMeta.get(key) || serviceIdToMeta.get(key);

  if (meta) {
    const variants = await getActivityVariants(meta.categorySlug, meta.slug);
    if (variants.length > 1) return true;
    // If no specific variants, see if category has multiple
    const catVariants = await getCategoryVariants(meta.categorySlug);
    return catVariants.length > 1;
  }

  // Fallback to static mapping if catalog resolution not found (supports slug/name differences)
  const mapping = CATEGORY_FOR_ACTIVITY[key] || CATEGORY_FOR_ACTIVITY[key.replace(/-/g, ' ')] || CATEGORY_FOR_ACTIVITY[key.replace(/\s+/g, '-')];
  if (mapping?.specific) {
    const variants = await getActivityVariants(mapping.category, mapping.specific);
    if (variants.length > 1) return true;
    const catVariants = await getCategoryVariants(mapping.category);
    return catVariants.length > 1;
  }

  if (mapping) {
    const catVariants = await getCategoryVariants(mapping.category);
    return catVariants.length > 1;
  }

  return false;
}
