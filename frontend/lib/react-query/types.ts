import { UseQueryOptions, UseMutationOptions, QueryKey } from '@tanstack/react-query';
import { ApiError } from './api';

/**
 * React Query TypeScript Types and Utilities
 *
 * This module provides strong typing for React Query usage across
 * the InstaInstru application, ensuring type safety and consistency.
 */

/**
 * Custom query options type that includes our ApiError
 */
export type AppQueryOptions<
  TData = unknown,
  TError = ApiError,
  TQueryKey extends QueryKey = QueryKey,
> = Omit<UseQueryOptions<TData, TError, TData, TQueryKey>, 'queryKey' | 'queryFn'>;

/**
 * Custom mutation options type that includes our ApiError
 */
export type AppMutationOptions<
  TData = unknown,
  TError = ApiError,
  TVariables = void,
  TContext = unknown,
> = Omit<UseMutationOptions<TData, TError, TVariables, TContext>, 'mutationFn'>;

/**
 * Pagination parameters for list queries
 */
export interface PaginationParams {
  page?: number;
  limit?: number;
  offset?: number;
}

/**
 * Common list response format
 */
export interface ListResponse<T> {
  items: T[];
  total: number;
  page?: number;
  limit?: number;
  hasMore?: boolean;
}

/**
 * Date range parameters for queries
 */
export interface DateRangeParams {
  startDate: string; // ISO date string
  endDate: string; // ISO date string
}

/**
 * Search parameters
 */
export interface SearchParams {
  query: string;
  filters?: Record<string, unknown>;
  sort?: string;
  order?: 'asc' | 'desc';
}

/**
 * Mutation result with optimistic update support
 */
export interface MutationResult<T> {
  data?: T;
  success: boolean;
  message?: string;
}

/**
 * Helper type for query key factories
 */
export type QueryKeyFactory<TParams = void> = TParams extends void
  ? () => readonly unknown[]
  : (params: TParams) => readonly unknown[];

/**
 * Type-safe query key builder
 *
 * @example
 * ```ts
 * const userKeys = {
 *   all: createQueryKey(['users']),
 *   detail: createQueryKey((id: string) => ['users', id]),
 *   search: createQueryKey((params: SearchParams) => ['users', 'search', params])
 * };
 * ```
 */
export function createQueryKey<TParams = void>(
  keyFn: TParams extends void ? () => readonly unknown[] : (params: TParams) => readonly unknown[]
): QueryKeyFactory<TParams> {
  return keyFn as QueryKeyFactory<TParams>;
}

/**
 * Extract data type from a query hook
 *
 * @example
 * ```ts
 * type UserData = ExtractQueryData<typeof useUser>;
 * ```
 */
export type ExtractQueryData<T> = T extends (...args: unknown[]) => { data?: infer D } ? D : never;

/**
 * Extract error type from a query hook
 */
export type ExtractQueryError<T> = T extends (...args: unknown[]) => { error?: infer E } ? E : never;

/**
 * Common query states
 */
export interface QueryState<TData = unknown, TError = unknown> {
  data?: TData;
  error?: TError;
  isLoading: boolean;
  isError: boolean;
  isSuccess: boolean;
  isFetching: boolean;
  isRefetching: boolean;
}

/**
 * Infinite query pagination info
 */
export interface InfiniteQueryPage<T> {
  items: T[];
  nextCursor?: string | number;
  previousCursor?: string | number;
  hasNextPage: boolean;
  hasPreviousPage: boolean;
}

/**
 * Type guard to check if error is an API error
 */
export function isQueryApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/**
 * Type guard to check if data is a list response
 */
export function isListResponse<T>(data: unknown): data is ListResponse<T> {
  return (
    typeof data === 'object' &&
    data !== null &&
    'items' in data &&
    'total' in data
  );
}

/**
 * Helper to create typed query options
 *
 * @example
 * ```ts
 * const options = createQueryOptions({
 *   queryKey: ['users'],
 *   queryFn: fetchUsers,
 *   staleTime: 5 * 60 * 1000,
 * });
 * ```
 */
export function createQueryOptions<
  TData = unknown,
  TError = ApiError,
  TQueryKey extends QueryKey = QueryKey,
>(
  options: UseQueryOptions<TData, TError, TData, TQueryKey>
): UseQueryOptions<TData, TError, TData, TQueryKey> {
  return options;
}

/**
 * Helper to create typed mutation options
 */
export function createMutationOptions<
  TData = unknown,
  TError = ApiError,
  TVariables = void,
  TContext = unknown,
>(
  options: UseMutationOptions<TData, TError, TVariables, TContext>
): UseMutationOptions<TData, TError, TVariables, TContext> {
  return options;
}
