import { useQuery } from '@tanstack/react-query';
import type { User } from '@/features/shared/api/types';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { httpJson } from '@/features/shared/api/http';
import { withApiBase } from '@/lib/apiBase';
import { loadMeSchema } from '@/features/shared/api/schemas/me';

// Type alias for backwards compatibility
type UserData = User;

/**
 * Hook to fetch and cache the current user data
 *
 * This hook fetches user data from the /auth/me endpoint and caches it
 * for the duration of the session. The data is automatically refetched
 * when the user logs in or when explicitly invalidated.
 *
 * @example
 * ```tsx
 * function UserProfile() {
 *   const { data: user, isLoading, error } = useUser();
 *
 *   if (isLoading) return <Spinner />;
 *   if (error) return <ErrorMessage />;
 *   if (!user) return <LoginPrompt />;
 *
 *   return <div>Welcome, {user.full_name}!</div>;
 * }
 * ```
 *
 * @returns React Query result with user data
 */
export function useUser() {
  return useQuery<UserData>({
    queryKey: queryKeys.user,
    queryFn: async () =>
      httpJson<UserData>(withApiBase('/auth/me'), { method: 'GET' }, loadMeSchema, { endpoint: 'GET /auth/me' }),
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
 * Hook variant that doesn't throw errors to error boundary
 * Useful for components that want to handle errors inline
 *
 * @example
 * ```tsx
 * function NavBar() {
 *   const { data: user } = useUserSafe();
 *
 *   return (
 *     <nav>
 *       {user ? (
 *         <UserMenu user={user} />
 *       ) : (
 *         <LoginButton />
 *       )}
 *     </nav>
 *   );
 * }
 * ```
 */
export function useUserSafe() {
  return useQuery<UserData>({
    queryKey: queryKeys.user,
    queryFn: async () =>
      httpJson<UserData>(withApiBase('/auth/me'), { method: 'GET' }, loadMeSchema, { endpoint: 'GET /auth/me' }),
    staleTime: CACHE_TIMES.SESSION,
    gcTime: CACHE_TIMES.SESSION,
    retry: false, // Don't retry for safe variant
    throwOnError: false, // Don't throw to error boundary
  });
}

/**
 * Hook to check if user is authenticated
 * Returns loading state and authentication status
 *
 * @example
 * ```tsx
 * function ProtectedRoute({ children }) {
 *   const { isAuthenticated, isLoading } = useIsAuthenticated();
 *
 *   if (isLoading) return <LoadingScreen />;
 *   if (!isAuthenticated) return <Navigate to="/login" />;
 *
 *   return children;
 * }
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
