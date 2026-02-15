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

type NormalizeOptions = {
  label?: string;
};

const createError = (
  label: string | undefined,
  message: string,
  cookie?: Partial<StorageStateCookie> | { name?: string }
): Error => {
  const prefix = label ? `[storageState:${label}]` : '[storageState]';
  const detail = cookie ? ` ${JSON.stringify(cookie)}` : '';
  return new Error(`${prefix} ${message}${detail}`);
};

const toStorageStateCookie = (
  cookie: RawCookie,
  fallbackBaseURL: string,
  label?: string
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
  const sanitizedDomain = domainSource ? removePort(domainSource) : '';

  const path = sanitizePath(cookie.path, parsed.pathname);
  const secure = typeof cookie.secure === 'boolean' ? cookie.secure : parsed.protocol === 'https:';
  const httpOnly = cookie.httpOnly ?? true;
  const sameSite = normalizeSameSite(cookie.sameSite as string | undefined);
  const expires =
    typeof cookie.expires === 'number'
      ? cookie.expires
      : Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 30;

  // __Host-* cookies cannot have a domain attribute - use url instead
  const isHostCookie = cookie.name.startsWith('__Host-') && secure;

  if (isHostCookie) {
    // For __Host-* cookies, use url instead of domain (Playwright requires one or the other)
    const cookieUrl = `${parsed.protocol}//${parsed.hostname}`;
    return {
      name: cookie.name,
      value: cookie.value,
      url: cookieUrl,
      path: '/',
      httpOnly,
      secure,
      sameSite,
      expires,
    };
  }

  const domain = sanitizedDomain || removePort(parsed.hostname);

  if (!domain) {
    throw createError(label, 'Unable to determine cookie domain', { name: cookie.name });
  }

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
  fallbackBaseURL: string,
  options?: NormalizeOptions
): { cookies: StorageStateCookie[]; origins: unknown[] } => {
  const base = fallbackBaseURL?.trim() || DEFAULT_BASE;
  const isHttpsBase = base.toLowerCase().startsWith('https://');
  const cookies = (state.cookies ?? [])
    .map((cookie) => toStorageStateCookie(cookie, base, options?.label))
    .filter((cookie): cookie is StorageStateCookie => Boolean(cookie));

  cookies.forEach((cookie) => {
    if (!isHttpsBase) {
      if (cookie.name.startsWith('__Host-')) {
        throw createError(options?.label, 'HTTP storage state cannot contain __Host-* cookies', cookie);
      }
      if (cookie.secure) {
        throw createError(options?.label, 'HTTP storage state cookies must be secure=false', cookie);
      }
      if (cookie.sameSite !== 'Lax') {
        throw createError(options?.label, 'HTTP storage state cookies must use SameSite=Lax', cookie);
      }
      if (!cookie.domain && !cookie.url) {
        throw createError(options?.label, 'HTTP storage state cookies require a domain or url', cookie);
      }
      if (cookie.path !== '/') {
        // Scoped paths (e.g. /api/v1/auth/refresh for the rid cookie) are a
        // production security measure.  In E2E browser contexts we normalise
        // to "/" so Playwright sends the cookie on every request.
        cookie.path = '/';
      }
    } else if (cookie.name.startsWith('__Host-')) {
      if (!cookie.secure) {
        throw createError(options?.label, '__Host-* cookies must be secure', cookie);
      }
      if (cookie.path !== '/') {
        throw createError(options?.label, '__Host-* cookies must use path=/', cookie);
      }
      // __Host-* cookies use url instead of domain
      if (cookie.domain) {
        throw createError(options?.label, '__Host-* cookies cannot specify domain in storageState', cookie);
      }
      if (!cookie.url) {
        throw createError(options?.label, '__Host-* cookies must specify url in storageState', cookie);
      }
    }
  });

  if (process.env['CI_DEBUG_STORAGE'] === '1') {
    process.stdout.write(
      `${JSON.stringify(
        {
          label: options?.label ?? 'storageState',
          cookies: cookies.map((cookie) => ({
            name: cookie.name,
            domain: cookie.domain,
            path: cookie.path,
            sameSite: cookie.sameSite,
            secure: cookie.secure,
          })),
        },
        null,
        2
      )}\n`
    );
  }

  return {
    cookies,
    origins: Array.isArray(state.origins) ? state.origins : [],
  };
};
