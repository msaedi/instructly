/**
 * Orval Custom Mutator
 *
 * Wraps all Orval-generated API calls with our existing infrastructure:
 * - Base URL resolution via getApiBase()
 * - Credentials for cookie-based sessions
 * - Error normalization
 */

import { withApiBase } from '@/lib/apiBase';
import { logger } from '@/lib/logger';

// Helper to check if this is a messaging-related request (for focused debug logging)
const isMessagingRequest = (url: string): boolean =>
  url.includes('/messages') || url.includes('/reactions');

export type ErrorType<Error> = Error;

/**
 * Generic configuration interface for Orval-generated clients.
 * Uses generics to maintain exact type safety with exactOptionalPropertyTypes.
 */
export interface OrvalMutatorConfig<TData = unknown, TParams = unknown> {
  url: string;
  method: string;
  params?: TParams;
  data?: TData;
  headers?: HeadersInit;
  signal?: AbortSignal | undefined;
}

/**
 * Custom fetch function for Orval-generated clients.
 *
 * This is called by all generated React Query hooks and provides:
 * - Automatic base URL resolution
 * - Credentials support (cookies)
 * - JSON request/response handling
 * - AbortSignal support
 */
export async function customFetch<
  TResponse,
  TData = unknown,
  TParams = unknown,
>(config: OrvalMutatorConfig<TData, TParams>): Promise<TResponse> {
  const { url, method, params, data, headers: configHeaders, signal } = config;

  // Build query string from params
  const queryString = params
    ? '?' +
      Object.entries(params as Record<string, unknown>)
        .filter(([_, value]) => value !== undefined && value !== null)
        .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
        .join('&')
    : '';

  // Build full URL with base
  const fullUrl = withApiBase(url + queryString);

  // Build headers
  const headers: Record<string, string> = {
    ...(configHeaders as Record<string, string> || {}),
  };

  // Add Content-Type for requests with body
  if (data && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  // Build fetch options - convert signal from AbortSignal | undefined to AbortSignal | null
  const options: RequestInit = {
    method,
    headers,
    credentials: 'include', // Always include credentials for cookie-based auth
    signal: signal ?? null,
  };

  // Add body if present
  if (data) {
    options.body = JSON.stringify(data);
  }

  // [MSG-DEBUG] Log messaging requests
  const isMessaging = isMessagingRequest(url);
  if (isMessaging) {
    logger.debug('[MSG-DEBUG] API Request', {
      method,
      url: fullUrl,
      hasBody: !!data,
      timestamp: new Date().toISOString()
    });
  }

  // Make request
  const startTime = Date.now();
  const response = await fetch(fullUrl, options);
  const duration = Date.now() - startTime;

  // [MSG-DEBUG] Log messaging responses
  if (isMessaging) {
    logger.debug('[MSG-DEBUG] API Response', {
      method,
      url: fullUrl,
      status: response.status,
      statusText: response.statusText,
      durationMs: duration,
      ok: response.ok,
      timestamp: new Date().toISOString()
    });
  }

  // Handle errors
  if (!response.ok) {
    // Try to parse error response
    let errorData: unknown;
    try {
      const contentType = response.headers.get('content-type');
      if (contentType?.includes('application/json')) {
        errorData = (await response.json()) as unknown;
      } else {
        errorData = await response.text();
      }
    } catch {
      errorData = null;
    }

    // [MSG-DEBUG] Log messaging errors with detail
    if (isMessaging) {
      logger.error('[MSG-DEBUG] API Error', {
        method,
        url: fullUrl,
        status: response.status,
        errorData,
        durationMs: duration,
        timestamp: new Date().toISOString()
      });
    }

    // Throw with consistent error structure
    interface FetchErrorWithContext extends Error {
      response: Response;
      status: number;
      data: unknown;
    }

    const error = new Error(
      typeof errorData === 'object' && errorData && 'detail' in errorData
        ? String((errorData as { detail: unknown }).detail)
        : `HTTP ${response.status}: ${response.statusText}`
    ) as FetchErrorWithContext;
    error.response = response;
    error.status = response.status;
    error.data = errorData;
    throw error;
  }

  // Handle empty responses (204 No Content, etc.)
  if (response.status === 204 || response.headers.get('content-length') === '0') {
    return undefined as TResponse;
  }

  // Parse JSON response
  const contentType = response.headers.get('content-type');
  if (contentType?.includes('application/json')) {
    const jsonResponse = (await response.json()) as TResponse;
    // [MSG-DEBUG] Log successful messaging response data preview
    if (isMessaging) {
      logger.debug('[MSG-DEBUG] API Response Data', {
        method,
        url: fullUrl,
        hasData: !!jsonResponse,
        dataKeys: jsonResponse ? Object.keys(jsonResponse) : [],
        timestamp: new Date().toISOString()
      });
    }
    return jsonResponse;
  }

  // Fallback: return text
  return (await response.text()) as unknown as TResponse;
}
