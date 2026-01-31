/* frontend/lib/http.ts
 * Unified HTTP client for browser + SSR.
 */

import { logger } from '@/lib/logger';
import { getApiBase } from '@/lib/apiBase';
import { APP_URL } from '@/lib/publicEnv';
import { captureFetchError } from '@/lib/sentry';
import type { ApiErrorResponse } from '@/features/shared/api/types';
type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export class ApiError extends Error {
  public headers: Headers | undefined;
  public requestId: string | undefined;

  constructor(
    message: string,
    public status: number,
    public data?: unknown,
    headers?: Headers,
    requestId?: string
  ) {
    super(message);
    this.name = 'ApiError';
    this.headers = headers;
    this.requestId = requestId;
  }
}

export class AuthError extends ApiError {}
export class ClientError extends ApiError {}

const ABSOLUTE_URL_REGEX = /^https?:\/\//i;

function isJsonLike(body: unknown): boolean {
  return body != null && (typeof body === 'object' || typeof body === 'string');
}

function resolveUrl(url: string): string {
  if (ABSOLUTE_URL_REGEX.test(url)) {
    return url;
  }

  // Preserve already-proxied paths
  if (url.startsWith('/api/proxy')) {
    return url;
  }

  const base = getApiBase();
  const normalizedBase = base.replace(/\/+$/, '');
  const cleanPath = url.startsWith('/') ? url : `/${url}`;
  return `${normalizedBase}${cleanPath}`;
}

export interface HttpOptions extends Omit<RequestInit, 'body'> {
  headers?: Record<string, string>;
  query?: Record<string, string | number | boolean | undefined>;
  auth?: boolean; // allow Authorization header if token is present
  body?: unknown;
}

export async function http<T = unknown>(method: HttpMethod, url: string, options: HttpOptions = {}): Promise<T> {
  const { headers = {}, query, body, auth, ...rest } = options;

  const resolvedUrl = resolveUrl(url);
  const baseForRelative = typeof window !== 'undefined' ? window.location.origin : APP_URL;
  const u = new URL(resolvedUrl, baseForRelative);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null) u.searchParams.append(k, String(v));
    }
  }

  const finalHeaders: Record<string, string> = {
    ...headers,
  };
  if (isJsonLike(body) && !finalHeaders['Content-Type']) {
    finalHeaders['Content-Type'] = 'application/json';
  }

  // Authorization header intentionally omitted; cookie-based sessions are the source of truth

  // Always include credentials for cookie-based auth
  const init: RequestInit = {
    method,
    // Always include credentials to support cookie-based sessions
    credentials: 'include',
    headers: finalHeaders,
    ...rest,
  };
  if (body !== undefined) {
    init.body = isJsonLike(body)
      ? (typeof body === 'string' ? body : JSON.stringify(body))
      : body as BodyInit;
  }
  let resp: Response;
  try {
    resp = await fetch(u.toString(), init);
  } catch (error) {
    captureFetchError({ url: u.toString(), method, error });
    throw error;
  }

  let data: unknown = null;
  try {
    // Some Jest mocks don't implement clone(); fall back to json()
    const anyResp = resp as unknown as { clone?: () => Response; json: () => Promise<unknown> };
    if (typeof anyResp.clone === 'function') {
      data = await anyResp.clone().json();
    } else if (typeof anyResp.json === 'function') {
      data = await anyResp.json();
    }
  } catch {}

  if (process.env.NODE_ENV !== 'production' && resp.status === 429) {
    try {
      const dedupeKey =
        resp.headers.get('x-dedupe-key') ||
        resp.headers.get('x-rate-limit-dedupe-key') ||
        resp.headers.get('x-ratelimit-dedupe-key') ||
        '';
      logger.info('[429-dev] rate-limit triage', { dedupeKey: dedupeKey || 'unknown' });
    } catch {}
  }

  if (!resp.ok) {
    const status = resp.status;
    const errorData = data as ApiErrorResponse;
    const message = errorData?.detail || errorData?.message || `HTTP ${status}`;
    const requestIdFromBody =
      typeof (errorData as Record<string, unknown> | null)?.['request_id'] === 'string'
        ? (errorData as Record<string, unknown>)['request_id']
        : undefined;
    const requestIdFromHeaders = resp.headers.get('x-request-id') || resp.headers.get('X-Request-ID');
    const requestId = (requestIdFromBody as string | undefined) || requestIdFromHeaders || undefined;
    if (status === 401 || status === 403 || status === 419) {
      throw new AuthError(message, status, data, resp.headers, requestId);
    }
    if (status >= 400 && status < 500) {
      throw new ClientError(message, status, data, resp.headers, requestId);
    }
    const serverError = new ApiError(message, status, data, resp.headers, requestId);
    captureFetchError({ url: u.toString(), method, status, error: serverError });
    throw serverError;
  }

  return data as T;
}

export const httpGet = <T = unknown>(url: string, options?: HttpOptions) => http<T>('GET', url, options);
export const httpPost = <T = unknown>(url: string, body?: unknown, options?: HttpOptions) =>
  http<T>('POST', url, { ...(options || {}), body: body as BodyInit });
export const httpPut = <T = unknown>(url: string, body?: unknown, options?: HttpOptions) =>
  http<T>('PUT', url, { ...(options || {}), body: body as BodyInit });
export const httpPatch = <T = unknown>(url: string, body?: unknown, options?: HttpOptions) =>
  http<T>('PATCH', url, { ...(options || {}), body: body as BodyInit });
export const httpDelete = <T = unknown>(url: string, options?: HttpOptions) => http<T>('DELETE', url, options);

export async function postWithRetry(
  url: string,
  init: RequestInit = {},
  attempts = 3,
  baseDelayMs = 120
): Promise<Response> {
  const resolvedUrl = resolveUrl(url);
  const makeRequest = () =>
    fetch(resolvedUrl, {
      credentials: init.credentials ?? 'include',
      ...init,
      method: init.method ?? 'POST',
    });

  let lastError: unknown = null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await makeRequest();
      if (response.ok || (response.status >= 400 && response.status < 500)) {
        return response;
      }
    } catch (error) {
      lastError = error;
    }
    const jitter = Math.floor(Math.random() * 60);
    await new Promise((resolve) => setTimeout(resolve, baseDelayMs * (attempt + 1) + jitter));
  }
  if (lastError) {
    throw lastError;
  }
  return makeRequest();
}
