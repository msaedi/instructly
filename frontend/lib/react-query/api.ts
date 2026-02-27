import { ApiResponse } from '@/features/shared/api/client';

/**
 * React Query API Integration
 *
 * This module provides utilities to integrate the existing API client
 * with React Query, handling errors, cancellation, and response parsing.
 */

import { httpGet, httpPost, httpPut, httpPatch, httpDelete, ApiError } from '@/lib/http';

/**
 * Custom error class for API errors with proper typing
 */
// Use ApiError from unified http client

/**
 * Query function options type
 */
export interface QueryOptions extends RequestInit {
  params?: Record<string, string | number | boolean>;
  requireAuth?: boolean;
}

/**
 * Main query function for React Query
 *
 * This function wraps fetch to provide:
 * - Automatic auth token inclusion
 * - AbortController support for cancellation
 * - Consistent error handling
 * - Response parsing
 *
 * @example
 * ```ts
 * useQuery({
 *   queryKey: ['user'],
 *   queryFn: queryFn('/api/auth/me', { requireAuth: true })
 * })
 * ```
 */
export function queryFn<T = unknown>(endpoint: string, options: QueryOptions = {}) {
  return async (): Promise<T> => {
    const { params } = options;
    // Use unified client; cookies are always included
    const data = await httpGet(endpoint, params ? { query: params } : {});
    return data as T;
  };
}

/**
 * Mutation function for React Query mutations
 *
 * Similar to queryFn but designed for mutations (POST, PUT, DELETE)
 *
 * @example
 * ```ts
 * useMutation({
 *   mutationFn: mutationFn('/api/bookings', {
 *     method: 'POST',
 *     requireAuth: true
 *   })
 * })
 * ```
 */
export function mutationFn<TData = unknown, TVariables = unknown>(
  endpoint: string,
  options: QueryOptions = {}
) {
  return async (variables: TVariables): Promise<TData> => {
    const { params } = options;
    const method = (options.method ?? 'POST').toUpperCase();
    const requestOptions = params ? { query: params } : {};

    if (method === 'POST') {
      const data = await httpPost(endpoint, variables, requestOptions);
      return data as TData;
    }
    if (method === 'PUT') {
      const data = await httpPut(endpoint, variables, requestOptions);
      return data as TData;
    }
    if (method === 'PATCH') {
      const data = await httpPatch(endpoint, variables, requestOptions);
      return data as TData;
    }
    if (method === 'DELETE') {
      const data = await httpDelete(endpoint, requestOptions);
      return data as TData;
    }

    const data = await httpPost(endpoint, variables, requestOptions);
    return data as TData;
  };
}

/**
 * Helper to determine if an error is an API error
 */
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/**
 * Helper to determine if an error is a network error
 */
export function isNetworkError(error: unknown): boolean {
  return isApiError(error) && error.status === 0;
}

/**
 * Helper to determine if an error is an auth error
 */
export function isAuthError(error: unknown): boolean {
  return isApiError(error) && error.status === 401;
}

/**
 * Convert ApiResponse to React Query format
 *
 * This helper converts the ApiResponse<T> format from the existing
 * API client to throw errors that React Query expects
 */
export function convertApiResponse<T>(response: ApiResponse<T>): T {
  if (response.error) {
    throw new ApiError(response.error, response.status);
  }

  if (!response.data) {
    throw new ApiError('No data in response', response.status);
  }

  return response.data;
}
