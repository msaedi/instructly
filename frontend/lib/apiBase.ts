import { logger } from '@/lib/logger';

// Get the absolute backend URL
const ABSOLUTE_BASE =
  (process.env.NEXT_PUBLIC_API_BASE as string) ||
  (process.env.NEXT_PUBLIC_API_URL as string) ||
  'http://localhost:8000';

// Module-level flag for runtime proxy override (dev safety net)
let forceDirectMode = false;

/**
 * Ensures a path has a leading slash
 */
function ensureLeadingSlash(path: string): string {
  if (!path) return '';
  return path.startsWith('/') ? path : `/${path}`;
}

/**
 * Get the API base URL based on proxy configuration
 * In proxy mode: returns /api/proxy
 * In direct mode: returns the absolute backend URL
 */
export function getApiBase(): string {
  const useProxy = process.env.NEXT_PUBLIC_USE_PROXY === 'true' && !forceDirectMode;
  return useProxy ? '/api/proxy' : ABSOLUTE_BASE;
}

// Export for backward compatibility
export const API_BASE = getApiBase();

/**
 * Build a complete API URL for the given path
 * Handles both proxy and direct modes, avoiding double slashes
 */
export function withApiBase(path: string): string {
  const normalizedPath = ensureLeadingSlash(path);
  const base = getApiBase();

  // For proxy mode, just concatenate
  if (base === '/api/proxy') {
    return `${base}${normalizedPath}`;
  }

  // For direct mode with absolute URL
  // Remove trailing slash from base if present
  const cleanBase = base.endsWith('/') ? base.slice(0, -1) : base;
  return `${cleanBase}${normalizedPath}`;
}

/**
 * Dev safety net: Check if proxy is working when enabled
 * Falls back to direct mode if proxy fails
 */
async function checkProxyHealth() {
  if (
    process.env.NODE_ENV !== 'development' ||
    process.env.NEXT_PUBLIC_USE_PROXY !== 'true' ||
    typeof window === 'undefined'
  ) {
    return;
  }

  try {
    const response = await fetch('/api/proxy/health', {
      method: 'GET',
      cache: 'no-store',
    });

    if (!response.ok) {
      logger.error('[Proxy Check] Proxy route returned error, falling back to direct mode', {
        status: response.status,
      });
      forceDirectMode = true;

      // Show dev-only warning
      if (process.env.NODE_ENV === 'development') {
        logger.warn('⚠️ Proxy disabled (handler error). Using direct API.');
      }
    } else {
      logger.info('[Proxy Check] Proxy route is working');
    }
  } catch (error) {
    logger.error('[Proxy Check] Proxy route failed, falling back to direct mode', error);
    forceDirectMode = true;

    if (process.env.NODE_ENV === 'development') {
      logger.warn('⚠️ Proxy disabled (no handler or backend down). Using direct API.');
    }
  }
}

// Run health check on module load in dev
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
  checkProxyHealth();
}

// Dev-only banner showing proxy mode status
if (process.env.NODE_ENV === 'development' && typeof window !== 'undefined') {
  const isProxyMode = process.env.NEXT_PUBLIC_USE_PROXY === 'true';
  const apiBase = getApiBase();

  if (isProxyMode) {
    // Show proxy mode banner
    logger.info(`🔄 Proxy Mode: ON → /api/proxy → ${ABSOLUTE_BASE}`);

    // Check health and show result
    setTimeout(async () => {
      try {
        const response = await fetch('/api/proxy/health', { cache: 'no-store' });
        if (response.ok) {
          logger.info('✅ Health check: OK - Proxy is working');
        } else {
          logger.warn(`⚠️ Health check: Failed (${response.status}) - Will fallback to direct mode`);
        }
      } catch (err) {
        logger.warn('⚠️ Health check: Network error - Will fallback to direct mode');
      }
    }, 100); // Small delay to avoid blocking initial render
  } else {
    // Show direct mode banner
    logger.info(`🔗 Direct Mode: API calls → ${apiBase}`);
  }

  logger.info(`[apiBase] Initial API_BASE = ${apiBase}`);
}
