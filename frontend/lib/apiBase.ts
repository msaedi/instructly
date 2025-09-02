/**
 * Single source of truth for API base URL configuration
 * ONLY uses NEXT_PUBLIC_API_BASE - fails loudly if missing or if old API_URL is present
 */

import { logger } from '@/lib/logger';

// Phase A.2: Guard against deprecated NEXT_PUBLIC_API_URL
if (process.env.NEXT_PUBLIC_API_URL) {
  // Deliberately crash in dev/preview to catch drift
  if (process.env.NODE_ENV !== 'production') {
    throw new Error(
      '[apiBase] NEXT_PUBLIC_API_URL is deprecated. Use NEXT_PUBLIC_API_BASE.'
    );
  }
  logger.error('[apiBase] WARNING: NEXT_PUBLIC_API_URL is deprecated. Use NEXT_PUBLIC_API_BASE.');
}

// Phase A.1: Single source of truth
const rawBase = process.env.NEXT_PUBLIC_API_BASE?.trim() || '';

// Optional: allow local proxy only in local env
const USE_PROXY =
  process.env.NEXT_PUBLIC_USE_PROXY === 'true' &&
  (process.env.NEXT_PUBLIC_APP_ENV === 'local' || process.env.NODE_ENV === 'development');

export const API_BASE = (() => {
  if (USE_PROXY) return '/api/proxy'; // same-origin dev proxy

  if (!rawBase) {
    // Fail fast so we notice misconfig right away
    throw new Error(
      '[apiBase] NEXT_PUBLIC_API_BASE is not set. Refusing to default to localhost.'
    );
  }

  return rawBase.replace(/\/+$/, ''); // Remove trailing slashes
})();

/**
 * Build a complete API URL for the given path
 * Handles both proxy and direct modes, avoiding double slashes
 */
export function withApiBase(path: string): string {
  // Remove leading slashes from path
  const cleanPath = path.replace(/^\/+/, '');

  // Ensure single slash between base and path
  return `${API_BASE}/${cleanPath}`;
}

// Dev-only logging
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
  logger.info(`[apiBase] API_BASE = ${API_BASE}`);
  logger.info(`[apiBase] USE_PROXY = ${USE_PROXY}`);
  if (USE_PROXY) {
    logger.info(`[apiBase] Proxy mode active, forwarding to: ${rawBase || '(not set)'}`);
  }
}
