// frontend/lib/services/assetService.ts
// R2 asset URL builder and activity background resolver with Cloudflare Image Transformations

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
