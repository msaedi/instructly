/**
 * API base resolver with host-aware overrides and proxy support.
 */

import { logger } from '@/lib/logger';
import { publicEnv, APP_URL, IS_DEVELOPMENT, USE_PROXY } from '@/lib/publicEnv';

type StorageLayer = {
  get(host: string): string | undefined;
  set(host: string, base: string): void;
};

type ResolveContext = {
  envBase: string;
  appEnv: string;
  host: string | null;
  platform: 'csr' | 'ssr';
  storage?: StorageLayer | undefined;
  useProxy?: boolean | undefined;
};

type DebugReason = 'env' | 'proxy' | 'cache-or-derived' | 'app-env';

const LOCAL_DEFAULT_API = 'http://localhost:8000';
const LOCAL_BETA_FE_HOST = 'beta-local.instainstru.com';
const LOCAL_BETA_API_BASE = 'http://api.beta-local.instainstru.com:8000';
const PREVIEW_API_BASE = 'https://preview-api.instainstru.com';
const PROD_API_BASE = 'https://api.instainstru.com';
const IPV4_REGEX = /^(?:\d{1,3}\.){3}\d{1,3}$/;
const LAN_IPV4_REGEX = /^(?:10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[0-1])\.)/;
const ABSOLUTE_URL_REGEX = /^https?:\/\//i;
const memoryStorage = new Map<string, string>();
const REMOTE_APP_ENVS = new Set(['preview', 'beta', 'prod', 'production']);
const DEV_APP_ENVS = new Set(['development', 'dev', 'local']);
const INSTAINSTRU_DOMAIN_SUFFIX = 'instainstru.com';

function sanitize(base?: string | null): string {
  if (!base) {
    return '';
  }
  return base.replace(/\/+$/, '');
}

function shouldUseProxy(appEnv: string): boolean {
  return USE_PROXY && (appEnv === 'local' || appEnv === 'development' || IS_DEVELOPMENT);
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

type HostContext = {
  hostname?: string | undefined;
  port?: string | undefined;
  protocol?: string | undefined;
};

function parseHost(host: string | null, protocol?: string): HostContext {
  if (!host) {
    return { protocol };
  }
  const [hostname, port] = host.split(':');
  return {
    hostname: (hostname ?? '').trim().toLowerCase() || undefined,
    port: port || undefined,
    protocol,
  };
}

function resolveFromHost(ctx: HostContext): string | undefined {
  const hostname = ctx.hostname;
  if (!hostname) {
    return undefined;
  }
  if (hostname === LOCAL_BETA_FE_HOST) {
    return LOCAL_BETA_API_BASE;
  }
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return `${ctx.protocol ?? 'http:'}//${hostname}:8000`;
  }
  if (IPV4_REGEX.test(hostname)) {
    const protocol = ctx.protocol ?? 'http:';
    return `${protocol}//${hostname}:8000`;
  }
  return undefined;
}

function isLanIp(hostname?: string): boolean {
  if (!hostname) {
    return false;
  }
  return IPV4_REGEX.test(hostname) && LAN_IPV4_REGEX.test(hostname);
}

function isInstainstruHost(hostname?: string): boolean {
  if (!hostname) {
    return false;
  }
  return hostname === LOCAL_BETA_FE_HOST || hostname.endsWith(`.${INSTAINSTRU_DOMAIN_SUFFIX}`);
}

function isLocalHost(hostname?: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1';
}

function isValidCachedBase(host: string, cached: string | undefined): boolean {
  if (!cached) {
    return false;
  }
  try {
    const parsed = new URL(cached);
    const hostCtx = parseHost(host, parsed.protocol);
    const hostname = hostCtx.hostname;
    if (!hostname) {
      return true;
    }
    if (isInstainstruHost(hostname) && (parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1')) {
      return false;
    }
    if (isLocalHost(hostname) && parsed.hostname && parsed.hostname.endsWith(INSTAINSTRU_DOMAIN_SUFFIX)) {
      return false;
    }
    if (isLanIp(hostname)) {
      const expected = `${parsed.protocol}//${hostname}:8000`;
      if (parsed.href !== expected && parsed.href !== LOCAL_BETA_API_BASE) {
        return false;
      }
    }
    return true;
  } catch {
    return false;
  }
}

function createSessionStorageLayer(): StorageLayer | undefined {
  if (typeof window === 'undefined') {
    return undefined;
  }

  try {
    const storage = window.sessionStorage;
    const probeKey = '__api_base_probe__';
    storage.setItem(probeKey, '1');
    storage.removeItem(probeKey);
    return {
      get(host: string) {
        return storage.getItem(host) ?? undefined;
      },
      set(host: string, base: string) {
        storage.setItem(host, base);
      },
    };
  } catch {
    return undefined;
  }
}

function getMemoryStorageLayer(): StorageLayer {
  return {
    get(host: string) {
      return memoryStorage.get(host);
    },
    set(host: string, base: string) {
      memoryStorage.set(host, base);
    },
  };
}

function resolveClientBase(host: string, protocol: string, storage: StorageLayer | undefined, shouldCache: boolean): string | undefined {
  if (storage) {
    const cached = storage.get(host);
    if (isValidCachedBase(host, cached)) {
      return cached;
    }
  }

  const ctx = parseHost(host, protocol);
  const derived = resolveFromHost(ctx);
  const normalized = sanitize(derived);
  if (normalized && storage && shouldCache) {
    storage.set(host, normalized);
  }
  return normalized || undefined;
}

function deriveDevBase(host: string, protocol: string, storage: StorageLayer | undefined, canCache: boolean): string | undefined {
  const result = resolveClientBase(host, protocol, storage, canCache);
  if (result) {
    return result;
  }
  return LOCAL_DEFAULT_API;
}

function resolveBase(context: ResolveContext): { base: string; reason: DebugReason } {
  const envBase = sanitize(context.envBase);
  if (envBase) {
    return { base: envBase, reason: 'env' };
  }

  const normalizedAppEnv = context.appEnv.trim().toLowerCase();
  const remoteBase = REMOTE_APP_ENVS.has(normalizedAppEnv)
    ? sanitize(resolveFromAppEnv(normalizedAppEnv))
    : undefined;

  if (context.platform === 'ssr') {
    if (remoteBase) {
      return { base: remoteBase, reason: 'app-env' };
    }
    return { base: '', reason: 'app-env' };
  }

  if (remoteBase) {
    return { base: remoteBase, reason: 'app-env' };
  }

  if (context.useProxy && DEV_APP_ENVS.has(normalizedAppEnv)) {
    return { base: '/api/proxy', reason: 'proxy' };
  }

  if (context.platform === 'csr' && context.host) {
    const protocol = typeof window !== 'undefined' ? window.location?.protocol ?? 'http:' : 'http:';
    const shouldCache = DEV_APP_ENVS.has(normalizedAppEnv);
    const resolved = deriveDevBase(context.host, protocol, shouldCache ? context.storage ?? getMemoryStorageLayer() : undefined, shouldCache);
    if (resolved) {
      return { base: resolved, reason: 'cache-or-derived' };
    }
  }

  if (remoteBase) {
    return { base: remoteBase, reason: 'app-env' };
  }

  return { base: LOCAL_DEFAULT_API, reason: 'app-env' };
}

export function getApiBase(): string {
  const appEnv = (publicEnv.NEXT_PUBLIC_APP_ENV || '').trim().toLowerCase();
  const envBase = sanitize(publicEnv.NEXT_PUBLIC_API_BASE);
  if (envBase) {
    return envBase;
  }

  const remoteBaseRaw = REMOTE_APP_ENVS.has(appEnv) ? resolveFromAppEnv(appEnv) : undefined;
  const remoteBase = remoteBaseRaw ? sanitize(remoteBaseRaw) : undefined;
  const platform = typeof window === 'undefined' ? 'ssr' : 'csr';

  if (platform === 'ssr') {
    return remoteBase ?? '';
  }

  if (remoteBase) {
    return remoteBase;
  }

  const host = window.location.host;
  const storage = DEV_APP_ENVS.has(appEnv)
    ? createSessionStorageLayer() ?? getMemoryStorageLayer()
    : undefined;

  const baseArgs: ResolveContext = {
    envBase,
    appEnv,
    host,
    platform,
    useProxy: shouldUseProxy(appEnv),
    ...(storage ? { storage } : {}),
  };

  const result = resolveBase(baseArgs);

  debugLog(result.reason, result.base, host, appEnv);
  return result.base;
}

export function resolveBaseForTest(context: ResolveContext): string {
  const result = resolveBase(context);
  return result.base;
}

export function resetApiBaseTestState(): void {
  memoryStorage.clear();
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

function debugLog(reason: DebugReason, decidedBase: string, host?: string | null, appEnv?: string): void {
  if (process.env.NODE_ENV === 'production') {
    return;
  }

  logger.debug('[api-base]', {
    ctx: typeof window === 'undefined' ? 'SSR' : 'CSR',
    host,
    decidedBase,
    reason,
    appEnv,
  });
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
  const runtimeAppEnv = (publicEnv.NEXT_PUBLIC_APP_ENV || '').trim().toLowerCase();
  logger.info(`[apiBase] resolved base = ${getApiBase()}`);
  logger.info(`[apiBase] proxy mode = ${shouldUseProxy(runtimeAppEnv)}`);
  if (shouldUseProxy(runtimeAppEnv)) {
    logger.info(`[apiBase] proxying through origin ${APP_URL}`);
  }
}
