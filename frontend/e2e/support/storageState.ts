import type { StorageStateCookie, CookieInput, SameSiteOption } from './cookies';

type RawCookie = (CookieInput & { url?: string; sameSite?: SameSiteOption | string }) | undefined;

export type RawStorageState = {
  cookies?: RawCookie[];
  origins?: unknown[];
};

const DEFAULT_BASE = 'http://localhost:3100';

const normalizeSameSite = (value?: string): SameSiteOption => {
  if (!value) return 'Lax';
  const normalized = value.toLowerCase();
  if (normalized === 'strict') return 'Strict';
  if (normalized === 'none') return 'None';
  return 'Lax';
};

const sanitizePath = (pathValue?: string, fallbackPath?: string): string => {
  const candidate = pathValue || fallbackPath || '/';
  return candidate.startsWith('/') ? candidate || '/' : `/${candidate}`;
};

const parseUrl = (value?: string): URL => {
  try {
    return new URL(value ?? DEFAULT_BASE);
  } catch {
    return new URL(DEFAULT_BASE);
  }
};

const removePort = (domain: string): string => domain.replace(/:\d+$/, '');

const toStorageStateCookie = (
  cookie: RawCookie,
  fallbackBaseURL: string
): StorageStateCookie | null => {
  if (!cookie?.name || !cookie.value) {
    return null;
  }

  const baseCandidate =
    cookie.url ||
    (cookie.domain ? `${cookie.secure ? 'https' : 'http'}://${cookie.domain}` : fallbackBaseURL) ||
    DEFAULT_BASE;
  const parsed = parseUrl(baseCandidate);

  const domainSource = cookie.domain || parsed.hostname;
  const domain = domainSource ? removePort(domainSource) : '';
  if (!domain) {
    return null;
  }

  const path = sanitizePath(cookie.path, parsed.pathname);
  const secure = typeof cookie.secure === 'boolean' ? cookie.secure : parsed.protocol === 'https:';
  const httpOnly = cookie.httpOnly ?? true;
  const sameSite = normalizeSameSite(cookie.sameSite as string | undefined);
  const expires =
    typeof cookie.expires === 'number'
      ? cookie.expires
      : Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 30;

  return {
    name: cookie.name,
    value: cookie.value,
    domain,
    path: path || '/',
    httpOnly,
    secure,
    sameSite,
    expires,
  };
};

export const normalizeStorageState = (
  state: RawStorageState,
  fallbackBaseURL: string
): { cookies: StorageStateCookie[]; origins: unknown[] } => {
  const base = fallbackBaseURL?.trim() || DEFAULT_BASE;
  const cookies = (state.cookies ?? [])
    .map((cookie) => toStorageStateCookie(cookie, base))
    .filter((cookie): cookie is StorageStateCookie => Boolean(cookie));

  return {
    cookies,
    origins: Array.isArray(state.origins) ? state.origins : [],
  };
};
