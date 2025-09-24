/**
 * API base resolver with host-aware overrides and proxy support.
 */

import { logger } from '@/lib/logger';
import { APP_ENV, APP_URL, IS_DEVELOPMENT, USE_PROXY } from '@/lib/publicEnv';

const DEPRECATED_API_URL_KEY = 'NEXT_PUBLIC_API_URL';
const API_BASE_KEY = 'NEXT_PUBLIC_API_BASE';
const LOCAL_DEFAULT_API = 'http://localhost:8000';
const LOCAL_BETA_FE_HOST = 'beta-local.instainstru.com';
const LOCAL_BETA_API_BASE = 'http://api.beta-local.instainstru.com:8000';

function sanitize(base: string): string {
  return base.replace(/\/+$/, '');
}

function readEnvBase(): string | undefined {
  const value = process.env[API_BASE_KEY];
  return value ? sanitize(value.trim()) : undefined;
}

function shouldUseProxy(): boolean {
  return USE_PROXY && (APP_ENV === 'local' || IS_DEVELOPMENT);
}

// Guard against deprecated NEXT_PUBLIC_API_URL usage
if (typeof process !== 'undefined' && process.env[DEPRECATED_API_URL_KEY]) {
  if (IS_DEVELOPMENT) {
    throw new Error('[apiBase] NEXT_PUBLIC_API_URL is deprecated. Use NEXT_PUBLIC_API_BASE.');
  }
  logger.error('[apiBase] WARNING: NEXT_PUBLIC_API_URL is deprecated. Use NEXT_PUBLIC_API_BASE.');
}

/**
 * Resolve the API base URL for the current execution environment.
 * Handles SSR, browser runtime, and local host overrides.
 */
export function getApiBase(): string {
  if (shouldUseProxy()) {
    return '/api/proxy';
  }

  const envBase = readEnvBase();

  // SSR / RSC branch – rely on env or fall back to localhost API
  if (typeof window === 'undefined') {
    return envBase ?? LOCAL_DEFAULT_API;
  }

  const host = window.location.hostname;

  if (host === LOCAL_BETA_FE_HOST) {
    // Same-site API so SameSite=Lax cookies flow between beta-local hosts
    return LOCAL_BETA_API_BASE;
  }

  if (host === 'localhost' || host === '127.0.0.1') {
    return LOCAL_DEFAULT_API;
  }

  if (envBase) {
    return envBase;
  }

  throw new Error('NEXT_PUBLIC_API_BASE must be set for this host');
}

/**
 * Legacy constant export for modules that expect a string.
 * Note: resolves once per environment – prefer calling getApiBase directly.
 */
export const API_BASE = getApiBase();

/**
 * Prefix a relative path with the resolved API base, avoiding duplicate slashes.
 */
export function withApiBase(path: string): string {
  const base = getApiBase();
  const cleanPath = path.replace(/^\/+/, '');
  const normalizedBase = base.replace(/\/+$/, '');
  return `${normalizedBase}/${cleanPath}`;
}

// Dev ergonomics: surface resolved base + proxy mode in console
if (typeof window !== 'undefined' && IS_DEVELOPMENT) {
  logger.info(`[apiBase] resolved base = ${getApiBase()}`);
  logger.info(`[apiBase] proxy mode = ${shouldUseProxy()}`);
  if (shouldUseProxy()) {
    logger.info(`[apiBase] proxying through origin ${APP_URL}`);
  }
}
