/**
 * Canonical useSession hook - owns /auth/me endpoint.
 *
 * This is the ONLY hook that should directly call /auth/me.
 * All other hooks/components should use this hook to get user session data.
 *
 * Features:
 * - Uses Orval-generated React Query hook
 * - Centralized query key from queryKeys.auth.me
 * - Session-long caching (Infinity staleTime/gcTime)
 * - No automatic refetching (explicit invalidation only)
 */

import { useReadUsersMeApiV1AuthMeGet } from '@/src/api/generated/auth-v1/auth-v1';
import { queryKeys } from '@/src/api/queryKeys';
import type { AuthUserWithPermissionsResponse } from '@/src/api/generated/instructly.schemas';

export type SessionUser = AuthUserWithPermissionsResponse;

/**
 * Get current user session.
 *
 * Returns React Query result with user data.
 * The session is cached for the lifetime of the app session.
 *
 * @example
 * ```tsx
 * function MyComponent() {
 *   const { data: user, isLoading, error } = useSession();
 *
 *   if (isLoading) return <div>Loading...</div>;
 *   if (error) return <div>Not authenticated</div>;
 *   if (!user) return <div>Please log in</div>;
 *
 *   return <div>Hello, {user.first_name}!</div>;
 * }
 * ```
 */
export function useSession() {
  return useReadUsersMeApiV1AuthMeGet({
    query: {
      queryKey: queryKeys.auth.me,
      staleTime: Infinity,
      gcTime: Infinity,
      refetchOnWindowFocus: false,
      refetchOnMount: false,
      retry: false, // Don't retry 401s - user is just not logged in
    },
  });
}

/**
 * Get current user if authenticated, null otherwise.
 * Convenience wrapper around useSession for components that need the user or null.
 *
 * @example
 * ```tsx
 * function ProfileBadge() {
 *   const user = useCurrentUser();
 *
 *   if (!user) {
 *     return <LoginButton />;
 *   }
 *
 *   return <div>{user.email}</div>;
 * }
 * ```
 */
export function useCurrentUser(): SessionUser | null {
  const { data } = useSession();
  return data ?? null;
}

/**
 * Check if user is authenticated.
 * Returns true if user is logged in, false otherwise.
 *
 * @example
 * ```tsx
 * function ProtectedFeature() {
 *   const isAuthenticated = useIsAuthenticated();
 *
 *   if (!isAuthenticated) {
 *     return <Navigate to="/login" />;
 *   }
 *
 *   return <div>Protected content</div>;
 * }
 * ```
 */
export function useIsAuthenticated(): boolean {
  const { data } = useSession();
  return Boolean(data);
}

/**
 * Get user permissions for authorization checks.
 *
 * @example
 * ```tsx
 * function AdminPanel() {
 *   const permissions = useUserPermissions();
 *
 *   if (!permissions.includes('ADMIN_ACCESS')) {
 *     return <div>Access denied</div>;
 *   }
 *
 *   return <div>Admin panel</div>;
 * }
 * ```
 */
export function useUserPermissions(): string[] {
  const { data } = useSession();
  return data?.permissions ?? [];
}

/**
 * Check if user has a specific permission.
 *
 * @example
 * ```tsx
 * function DeleteButton() {
 *   const canDelete = useHasPermission('DELETE_ITEMS');
 *
 *   if (!canDelete) return null;
 *
 *   return <button>Delete</button>;
 * }
 * ```
 */
export function useHasPermission(permission: string): boolean {
  const permissions = useUserPermissions();
  return permissions.includes(permission);
}
