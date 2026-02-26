/**
 * @deprecated This file is deprecated. Use @/src/api/hooks/useSession instead.
 *
 * Migration guide:
 * - useUser() → useSession() (or useCurrentUser() for simpler cases)
 * - useUserSafe() → useCurrentUser()
 * - useIsAuthenticated() → useIsAuthenticated() (same name, different return type)
 *
 * The new hooks use Orval-generated clients and are the canonical way to access /auth/me.
 */

import { useQuery } from '@tanstack/react-query';
import type { User } from '@/features/shared/api/types';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { httpJson } from '@/features/shared/api/http';
import { withApiBase } from '@/lib/apiBase';
import { loadMeSchema } from '@/features/shared/api/schemas/me';

// Type alias for convenience
type UserData = User;

/**
 * @deprecated Use useSession() from @/src/api/hooks/useSession instead.
 *
 * Hook to fetch and cache the current user data
 *
 * This hook fetches user data from the /auth/me endpoint and caches it
 * for the duration of the session. The data is automatically refetched
 * when the user logs in or when explicitly invalidated.
 *
 * @example
 * ```tsx
 * // OLD (deprecated):
 * const { data: user, isLoading, error } = useUser();
 *
 * // NEW (preferred):
 * import { useSession } from '@/src/api/hooks/useSession';
 * const { data: user, isLoading, error } = useSession();
 * ```
 *
 * @returns React Query result with user data
 */
export function useUser() {
  return useQuery<UserData>({
    queryKey: queryKeys.user,
    queryFn: async () =>
      httpJson<UserData>(withApiBase('/api/v1/auth/me'), { method: 'GET' }, loadMeSchema, { endpoint: 'GET /api/v1/auth/me' }),
    staleTime: CACHE_TIMES.SESSION, // User data is fresh for the entire session
    gcTime: CACHE_TIMES.SESSION, // Keep in cache for the entire session
    retry: (failureCount, error: unknown) => {
      // Don't retry on 401 (unauthorized) - user needs to log in
      if (error && typeof error === 'object' && 'status' in error && error.status === 401) return false;
      // Retry other errors up to 3 times
      return failureCount < 3;
    },
  });
}

/**
 * @deprecated Use useCurrentUser() from @/src/api/hooks/useSession instead.
 *
 * Hook variant that doesn't throw errors to error boundary
 * Useful for components that want to handle errors inline
 *
 * @example
 * ```tsx
 * // OLD (deprecated):
 * const { data: user } = useUserSafe();
 *
 * // NEW (preferred):
 * import { useCurrentUser } from '@/src/api/hooks/useSession';
 * const user = useCurrentUser();
 * ```
 */
export function useUserSafe() {
  return useQuery<UserData>({
    queryKey: queryKeys.user,
    queryFn: async () =>
      httpJson<UserData>(withApiBase('/api/v1/auth/me'), { method: 'GET' }, loadMeSchema, { endpoint: 'GET /api/v1/auth/me' }),
    staleTime: CACHE_TIMES.SESSION,
    gcTime: CACHE_TIMES.SESSION,
    retry: false, // Don't retry for safe variant
    throwOnError: false, // Don't throw to error boundary
  });
}

/**
 * @deprecated Use useIsAuthenticated() from @/src/api/hooks/useSession instead.
 * Note: The new hook returns a boolean, not an object.
 *
 * Hook to check if user is authenticated
 * Returns loading state and authentication status
 *
 * @example
 * ```tsx
 * // OLD (deprecated):
 * const { isAuthenticated, isLoading, user } = useIsAuthenticated();
 *
 * // NEW (preferred):
 * import { useIsAuthenticated, useSession } from '@/src/api/hooks/useSession';
 * const isAuthenticated = useIsAuthenticated();
 * const { isLoading } = useSession();
 * ```
 */
export function useIsAuthenticated() {
  const { data: user, isLoading, error } = useUserSafe();

  return {
    isAuthenticated: !!user && !error,
    isLoading,
    user,
  };
}
