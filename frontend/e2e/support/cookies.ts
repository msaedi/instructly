type SameSiteOption = 'Strict' | 'Lax' | 'None';

export type PlaywrightCookie = {
  name: string;
  value: string;
  url: string;
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
  const rawName = (nameFromEnv ?? process.env.SESSION_COOKIE_NAME ?? 'sid').trim();
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
