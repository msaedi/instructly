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

export async function http<T = unknown>(method: HttpMethod, url: string, options: HttpOptions = {}): Promise<T> {
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
  const resp = await fetch(u.toString(), init);

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

  if (!resp.ok) {
    const status = resp.status;
    const errorData = data as Record<string, unknown>;
    const message = errorData?.detail as string || errorData?.message as string || `HTTP ${status}`;
    if (status === 401 || status === 403 || status === 419) throw new AuthError(message, status, data);
    if (status >= 400 && status < 500) throw new ClientError(message, status, data);
    throw new ApiError(message, status, data);
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
