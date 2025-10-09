/**
 * API base resolver with host-aware overrides and proxy support.
 */

import { logger } from '@/lib/logger';
import { publicEnv, APP_ENV, APP_URL, IS_DEVELOPMENT, USE_PROXY } from '@/lib/publicEnv';

const LOCAL_DEFAULT_API = 'http://localhost:8000';
const LOCAL_BETA_FE_HOST = 'beta-local.instainstru.com';
const LOCAL_BETA_API_BASE = 'http://api.beta-local.instainstru.com:8000';
const PREVIEW_API_BASE = 'https://preview-api.instainstru.com';
const PROD_API_BASE = 'https://api.instainstru.com';

const ABSOLUTE_URL_REGEX = /^https?:\/\//i;

let memoizedBase: string | undefined;

function sanitize(base?: string | null): string {
  if (!base) return '';
  return base.replace(/\/+$/, '');
}

function shouldUseProxy(): boolean {
  return USE_PROXY && (APP_ENV === 'local' || IS_DEVELOPMENT);
}

function resolveFromAppEnv(appEnv: string): string | undefined {
  switch (appEnv) {
    case 'preview':
      return PREVIEW_API_BASE;
    case 'beta':
    case 'prod':
    case 'production':
      return PROD_API_BASE;
    default:
      return undefined;
  }
}

function resolveFromHost(host?: string | null): string | undefined {
  if (!host) return undefined;
  const normalized = host.trim().toLowerCase();
  if (!normalized) return undefined;
  if (normalized === LOCAL_BETA_FE_HOST) return LOCAL_BETA_API_BASE;
  if (normalized === 'localhost' || normalized === '127.0.0.1') return LOCAL_DEFAULT_API;
  return undefined;
}

function formatResolutionError(host: string | null | undefined, appEnv: string): Error {
  const hostLabel = host ?? '(server)';
  const envLabel = appEnv || 'unset';
  return new Error(`NEXT_PUBLIC_API_BASE must be set or resolvable (host=${hostLabel}, appEnv=${envLabel})`);
}

export type ResolveApiBaseOptions = {
  envBase?: string;
  appEnv?: string;
  host?: string | null;
};

export function resolveApiBase({ envBase, appEnv, host }: ResolveApiBaseOptions): string {
  const sanitizedEnv = sanitize(envBase);
  if (sanitizedEnv) {
    return sanitizedEnv;
  }

  const normalizedAppEnv = (appEnv ?? '').trim().toLowerCase();
  const appEnvBase = resolveFromAppEnv(normalizedAppEnv);
  if (appEnvBase) {
    return appEnvBase;
  }

  const hostBase = resolveFromHost(host);
  if (hostBase) {
    return hostBase;
  }

  throw formatResolutionError(host, normalizedAppEnv);
}

export function getApiBase(): string {
  if (memoizedBase) {
    return memoizedBase;
  }

  const envOverride = sanitize(publicEnv.NEXT_PUBLIC_API_BASE);
  if (envOverride) {
    memoizedBase = envOverride;
    return memoizedBase;
  }

  if (shouldUseProxy()) {
    memoizedBase = '/api/proxy';
    return memoizedBase;
  }

  const appEnv = (publicEnv.NEXT_PUBLIC_APP_ENV || '').trim().toLowerCase();
  const host = typeof window !== 'undefined' ? window.location.hostname : null;

  memoizedBase = resolveApiBase({
    envBase: envOverride,
    appEnv,
    host: typeof window !== 'undefined' ? host : null,
  });
  return memoizedBase;
}

export function resetApiBaseMemoForTests(): void {
  memoizedBase = undefined;
}

export function withApiBase(path: string): string {
  if (ABSOLUTE_URL_REGEX.test(path)) {
    return path;
  }

  const base = getApiBase();
  const cleanPath = path.replace(/^\/+/, '');
  const normalizedBase = base.replace(/\/+$/, '');
  return `${normalizedBase}/${cleanPath}`;
}

// Guard against deprecated NEXT_PUBLIC_API_URL usage
if (typeof process !== 'undefined' && process.env['NEXT_PUBLIC_API_URL']) {
  if (IS_DEVELOPMENT) {
    throw new Error('[apiBase] NEXT_PUBLIC_API_URL is deprecated. Use NEXT_PUBLIC_API_BASE.');
  }
  logger.error('[apiBase] WARNING: NEXT_PUBLIC_API_URL is deprecated. Use NEXT_PUBLIC_API_BASE.');
}

// Dev ergonomics: surface resolved base + proxy mode in console
if (typeof window !== 'undefined' && IS_DEVELOPMENT) {
  logger.info(`[apiBase] resolved base = ${getApiBase()}`);
  logger.info(`[apiBase] proxy mode = ${shouldUseProxy()}`);
  if (shouldUseProxy()) {
    logger.info(`[apiBase] proxying through origin ${APP_URL}`);
  }
}
