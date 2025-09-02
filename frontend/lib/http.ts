/* frontend/lib/http.ts
 * Unified HTTP client for browser + SSR.
 */

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export class ApiError extends Error {
  constructor(message: string, public status: number, public data?: unknown) {
    super(message);
    this.name = 'ApiError';
  }
}

export class AuthError extends ApiError {}
export class ClientError extends ApiError {}

function isJsonLike(body: unknown): boolean {
  return body != null && (typeof body === 'object' || typeof body === 'string');
}

export interface HttpOptions extends RequestInit {
  headers?: Record<string, string>;
  query?: Record<string, string | number | boolean | undefined>;
  auth?: boolean; // allow Authorization header if token is present
}

export async function http(method: HttpMethod, url: string, options: HttpOptions = {}) {
  const { headers = {}, query, body, auth, ...rest } = options;

  const u = new URL(url, typeof window !== 'undefined' ? window.location.origin : undefined);
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

  // Attach Authorization only when requested by caller
  if (auth && typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) finalHeaders['Authorization'] = `Bearer ${token}`;
  }

  // Always include credentials for cookie-based auth
  const init: RequestInit = {
    method,
    credentials: 'include',
    headers: finalHeaders,
    ...rest,
  };
  if (body !== undefined) {
    init.body = isJsonLike(body)
      ? (typeof body === 'string' ? body : JSON.stringify(body))
      : body as BodyInit;
  }
  const resp = await fetch(u.toString(), init);

  let data: unknown = null;
  try {
    data = await resp.clone().json();
  } catch {}

  if (!resp.ok) {
    const status = resp.status;
    const errorData = data as Record<string, unknown>;
    const message = errorData?.detail as string || errorData?.message as string || `HTTP ${status}`;
    if (status === 401 || status === 403 || status === 419) throw new AuthError(message, status, data);
    if (status >= 400 && status < 500) throw new ClientError(message, status, data);
    throw new ApiError(message, status, data);
  }

  return data;
}

export const httpGet = (url: string, options?: HttpOptions) => http('GET', url, options);
export const httpPost = (url: string, body?: unknown, options?: HttpOptions) =>
  http('POST', url, { ...(options || {}), body: body as BodyInit });
export const httpPut = (url: string, body?: unknown, options?: HttpOptions) =>
  http('PUT', url, { ...(options || {}), body: body as BodyInit });
export const httpPatch = (url: string, body?: unknown, options?: HttpOptions) =>
  http('PATCH', url, { ...(options || {}), body: body as BodyInit });
export const httpDelete = (url: string, options?: HttpOptions) => http('DELETE', url, options);
