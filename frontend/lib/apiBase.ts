const DIRECT_BASE =
  (process.env.NEXT_PUBLIC_API_BASE as string) ||
  (process.env.NEXT_PUBLIC_API_URL as string) ||
  '';

export const API_BASE =
  process.env.NEXT_PUBLIC_USE_PROXY === 'true' ? '/api/proxy' : DIRECT_BASE;

export function withApiBase(path: string): string {
  let normalizedPath = path || '';
  if (!normalizedPath.startsWith('/')) normalizedPath = `/${normalizedPath}`;

  const base = API_BASE || '';
  if (base.endsWith('/')) {
    return `${base.slice(0, -1)}${normalizedPath}`;
  }
  return `${base}${normalizedPath}`;
}

// Dev-only sanity: print API_BASE once (do not run in tests)
import { logger } from '@/lib/logger';
if (process.env.NODE_ENV === 'development') {
  logger.info(`[apiBase] API_BASE = ${API_BASE || '(empty)'}`);
}
