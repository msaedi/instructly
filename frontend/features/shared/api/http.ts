/**
 * Generic HTTP client with type safety
 *
 * This module provides a typed wrapper around fetch for making API calls
 * with compile-time type checking via TypeScript generics.
 */

import { validateWithZod, type SchemaLoader } from '@/features/shared/api/validation';

/**
 * Generic JSON fetch wrapper with type safety
 *
 * @param input - The resource to fetch (URL or Request object)
 * @param init - Optional fetch initialization parameters
 * @returns Promise resolving to the typed response data
 * @throws Error if the response is not ok (status outside 200-299 range)
 *
 * @example
 * ```ts
 * import { httpJson } from '@/features/shared/api/http';
 * import type { User } from '@/features/shared/api/types';
 *
 * const user = await httpJson<User>('/api/auth/me');
 * ```
 */
export async function httpJson<T>(
  input: RequestInfo,
  init?: RequestInit,
  schemaLoader?: SchemaLoader,
  ctx?: { endpoint: string; note?: string }
): Promise<T> {
  const res = await fetch(input, {
    credentials: 'include',
    ...init
  });

  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }

  const data = (await res.json()) as T;
  if (!schemaLoader) return data;
  return validateWithZod<T>(schemaLoader, data, { endpoint: ctx?.endpoint || String(input), note: ctx?.note });
}

/**
 * Type-safe wrapper for GET requests
 */
export async function httpGet<T>(url: string, init?: Omit<RequestInit, 'method'>): Promise<T> {
  return httpJson<T>(url, { ...init, method: 'GET' });
}

/**
 * Type-safe wrapper for POST requests
 */
export async function httpPost<T>(url: string, body?: unknown, init?: Omit<RequestInit, 'method' | 'body'>): Promise<T> {
  return httpJson<T>(url, {
    ...init,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
    body: body ? (JSON.stringify(body) as BodyInit) : null,
  });
}

/**
 * Type-safe wrapper for PUT requests
 */
export async function httpPut<T>(url: string, body?: unknown, init?: Omit<RequestInit, 'method' | 'body'>): Promise<T> {
  return httpJson<T>(url, {
    ...init,
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
    body: body ? (JSON.stringify(body) as BodyInit) : null,
  });
}

/**
 * Type-safe wrapper for DELETE requests
 */
export async function httpDelete<T>(url: string, init?: Omit<RequestInit, 'method'>): Promise<T> {
  return httpJson<T>(url, { ...init, method: 'DELETE' });
}
