import { withApiBaseForRequest } from '@/lib/apiBase';
import { logger } from '@/lib/logger';

const REFRESH_ENDPOINT = '/api/v1/auth/refresh';
const LOGOUT_ENDPOINT = '/api/v1/public/logout';
const SESSION_EXPIRED_EVENT = 'instainstru:session-expired';

let inFlightRefresh: Promise<boolean> | null = null;
let redirectTriggered = false;

function isBrowser(): boolean {
  return typeof window !== 'undefined';
}

function toUrlString(input: RequestInfo | URL): string {
  if (typeof input === 'string') {
    return input;
  }
  if (input instanceof URL) {
    return input.toString();
  }
  return input.url;
}

function toPathname(input: RequestInfo | URL): string {
  try {
    const raw = toUrlString(input);
    if (isBrowser()) {
      return new URL(raw, window.location.origin).pathname;
    }
    return new URL(raw, 'http://localhost').pathname;
  } catch {
    return '';
  }
}

function isRefreshPath(pathname: string): boolean {
  return (
    pathname.endsWith('/api/v1/auth/refresh') ||
    pathname.endsWith('/api/proxy/api/v1/auth/refresh')
  );
}

function isApiPath(pathname: string): boolean {
  return pathname.includes('/api/v1/');
}

async function clearSessionCookiesBestEffort(): Promise<void> {
  try {
    await fetch(withApiBaseForRequest(LOGOUT_ENDPOINT, 'POST'), {
      method: 'POST',
      credentials: 'include',
      keepalive: true,
    });
  } catch {
    // Best effort only.
  }
}

function redirectToLogin(): void {
  if (!isBrowser() || redirectTriggered) {
    return;
  }

  redirectTriggered = true;

  const returnUrl = `${window.location.pathname}${window.location.search}`;
  const loginUrl = `/login?redirect=${encodeURIComponent(returnUrl)}`;

  try {
    window.dispatchEvent(
      new CustomEvent(SESSION_EXPIRED_EVENT, {
        detail: { reason: 'refresh_failed' },
      })
    );
  } catch {
    // ignore event dispatch failures
  }

  if (window.location.pathname !== '/login') {
    if (process.env.NODE_ENV === 'test') {
      return;
    }
    try {
      window.location.assign(loginUrl);
    } catch (error) {
      logger.warn('[auth-refresh] login redirect failed', {
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }
}

async function runRefreshRequest(): Promise<boolean> {
  try {
    const response = await fetch(withApiBaseForRequest(REFRESH_ENDPOINT, 'POST'), {
      method: 'POST',
      credentials: 'include',
      cache: 'no-store',
      headers: {
        'Cache-Control': 'no-cache',
        Pragma: 'no-cache',
      },
    });
    return response.ok;
  } catch (error) {
    logger.warn('[auth-refresh] refresh request failed', {
      error: error instanceof Error ? error.message : String(error),
    });
    return false;
  }
}

export async function refreshAuthSession(): Promise<boolean> {
  if (!inFlightRefresh) {
    inFlightRefresh = runRefreshRequest().finally(() => {
      inFlightRefresh = null;
    });
  }
  return inFlightRefresh;
}

export async function fetchWithSessionRefresh(
  input: RequestInfo | URL,
  init: RequestInit = {}
): Promise<Response> {
  const firstResponse = await fetch(input, init);

  if (firstResponse.status !== 401 || !isBrowser()) {
    return firstResponse;
  }

  const pathname = toPathname(input);
  if (!isApiPath(pathname) || isRefreshPath(pathname)) {
    return firstResponse;
  }

  const refreshed = await refreshAuthSession();
  if (!refreshed) {
    await clearSessionCookiesBestEffort();
    redirectToLogin();
    return firstResponse;
  }

  return fetch(input, init);
}

export function __resetSessionRefreshForTests(): void {
  inFlightRefresh = null;
  redirectTriggered = false;
}
