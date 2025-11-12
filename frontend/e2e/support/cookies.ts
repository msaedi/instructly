export type SameSiteOption = 'Strict' | 'Lax' | 'None';

export type PlaywrightCookie = {
  name: string;
  value: string;
  url: string;
  httpOnly: boolean;
  secure: boolean;
  sameSite: SameSiteOption;
  expires?: number;
};

export type StorageStateCookie = {
  name: string;
  value: string;
  domain: string;
  path: string;
  httpOnly: boolean;
  secure: boolean;
  sameSite: SameSiteOption;
  expires?: number;
};

type BuildSessionCookieArgs = {
  baseURL: string;
  nameFromEnv?: string | null;
  token: string;
};

const trimBaseURL = (baseURL: string): string => {
  const fallback = 'http://localhost:3100';
  const input = (baseURL || fallback).trim() || fallback;
  return input.endsWith('/') ? input.slice(0, -1) : input;
};

export const buildSessionCookie = ({
  baseURL,
  nameFromEnv,
  token,
}: BuildSessionCookieArgs): PlaywrightCookie => {
  const normalizedBase = trimBaseURL(baseURL);
  const isHttps = normalizedBase.startsWith('https://');
  const fallbackName = process.env['SESSION_COOKIE_NAME'] ?? 'sid';
  const rawName = (nameFromEnv ?? fallbackName).trim();
  const cookieName = isHttps ? '__Host-sid' : rawName.replace(/^__Host-/, '') || 'sid';

  return {
    name: cookieName,
    value: token.trim(),
    url: normalizedBase,
    httpOnly: true,
    secure: isHttps,
    sameSite: 'Lax',
  };
};

type BuildStorageStateCookieArgs = {
  baseURL: string;
  name: string;
  value: string;
  expires?: number;
};

// Storage-state cookie (for browser.newContext({ storageState }))
export const buildStorageStateCookie = ({
  baseURL,
  name,
  value,
  expires,
}: BuildStorageStateCookieArgs): StorageStateCookie | null => {
  const input = (baseURL || 'http://localhost:3100').trim() || 'http://localhost:3100';
  let parsed: URL;
  try {
    parsed = new URL(input);
  } catch {
    parsed = new URL('http://localhost:3100');
  }
  const host = parsed.hostname || 'localhost';
  const isHttps = parsed.protocol === 'https:';

  // __Host-* cookies cannot carry Domain; skip from storage state and seed via addCookies instead.
  if (isHttps && name.startsWith('__Host-')) {
    return null;
  }

  const cookie: StorageStateCookie = {
    name,
    value,
    domain: host,
    path: '/',
    httpOnly: true,
    secure: isHttps,
    sameSite: 'Lax',
  };
  if (typeof expires === 'number') {
    cookie.expires = expires;
  }
  return cookie;
};

// Seed a session cookie after context creation (works both HTTP and HTTPS, handles __Host-*)
export const seedSessionCookie = async (
  context: import('@playwright/test').BrowserContext,
  baseURL: string,
  token: string,
  nameFromEnv?: string | null
) => {
  const cookie = buildSessionCookie({
    baseURL,
    nameFromEnv: nameFromEnv ?? process.env['SESSION_COOKIE_NAME'] ?? null,
    token,
  });
  await context.addCookies([cookie]);
};

type PartialCookie = {
  name: string;
  value: string;
  domain?: string;
  path?: string;
  url?: string;
  expires?: number;
  httpOnly?: boolean;
  secure?: boolean;
  sameSite?: SameSiteOption;
};

export type CookieInput = PartialCookie;

export const normalizeCookiesForContext = (
  cookies: CookieInput[] | undefined,
  baseURL: string,
): PlaywrightCookie[] => {
  if (!cookies || !cookies.length) {
    return [];
  }
  const normalizedBase = trimBaseURL(baseURL);
  const isHttps = normalizedBase.startsWith('https://');

  return cookies
    .map((cookie) => {
      const name = (cookie.name || '').trim();
      const value = (cookie.value || '').trim();
      if (!name || !value) {
        return null;
      }
      const finalName = !isHttps && name.startsWith('__Host-') ? 'sid' : name;
      const normalized: PlaywrightCookie = {
        name: finalName,
        value,
        url: normalizedBase,
        httpOnly: cookie.httpOnly ?? true,
        secure: isHttps,
        sameSite: 'Lax',
      };
      if (typeof cookie.expires === 'number') {
        normalized.expires = cookie.expires;
      }
      return normalized;
    })
    .filter((cookie): cookie is PlaywrightCookie => Boolean(cookie));
};
