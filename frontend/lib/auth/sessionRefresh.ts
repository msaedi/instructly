import { withApiBaseForRequest } from '@/lib/apiBase';
import { logger } from '@/lib/logger';

const REFRESH_ENDPOINT = '/api/v1/auth/refresh';
const LOGOUT_ENDPOINT = '/api/v1/public/logout';

let inFlightRefresh: Promise<boolean> | null = null;

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
    return firstResponse;
  }

  return fetch(input, init);
}

export function __resetSessionRefreshForTests(): void {
  inFlightRefresh = null;
}
