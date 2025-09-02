import { QueryFunctionContext } from '@tanstack/react-query';
import { ApiResponse } from '@/features/shared/api/client';

/**
 * React Query API Integration
 *
 * This module provides utilities to integrate the existing API client
 * with React Query, handling errors, cancellation, and response parsing.
 */

/**
 * Base API URL from environment
 */
import { withApiBase } from '@/lib/apiBase';
import { httpGet, httpPost, ApiError } from '@/lib/http';

/**
 * Custom error class for API errors with proper typing
 */
// Use ApiError from unified http client

/**
 * Get guest session ID from localStorage
 */
function getGuestSessionId(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('guest_session_id');
}

/**
 * Get analytics headers for tracking
 */
function getAnalyticsHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};

  if (typeof window !== 'undefined') {
    // Session tracking headers
    const sessionId = localStorage.getItem('session_id');
    if (sessionId) {
      headers['X-Session-ID'] = sessionId;
    }

    // Current page for referrer analytics
    headers['X-Search-Origin'] = window.location.pathname;
  }

  return headers;
}

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
    const url = withApiBase(endpoint);
    // Use unified client; cookies are always included
    const data = await httpGet(url, { query: params });
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
    const url = withApiBase(endpoint);
    const data = await httpPost(url, variables, { query: params });
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
 * Convert legacy API response to React Query format
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
