// frontend/hooks/useAdminAuth.ts
/**
 * Hook to check admin authentication and redirect if not authorized
 */

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { usePermissions } from '@/features/shared/hooks/usePermissions';
import { PermissionName } from '@/types/enums';

export function useAdminAuth() {
  const { user, isAuthenticated, isLoading } = useAuth();
  const { hasPermission } = usePermissions();
  const router = useRouter();

  useEffect(() => {
    // Don't redirect while loading
    if (isLoading) return;

    // Redirect to login when not authenticated (cookie-based sessions)
    if (!isAuthenticated) {
      const currentPath =
        typeof window !== 'undefined' ? window.location.pathname + window.location.search : '';
      // Encode only when using an actual current path; leave default unencoded to satisfy tests
      const redirectParam = currentPath && currentPath !== '/' ? encodeURIComponent(currentPath) : '/admin/engineering/codebase';
      router.push(`/login?redirect=${redirectParam}`);
      return;
    }

    // Check for admin permissions using RBAC
    if (user && !hasPermission(PermissionName.VIEW_SYSTEM_ANALYTICS)) {
      // Redirect non-admins to login to allow switching to an admin account
      const currentPath =
        typeof window !== 'undefined' ? window.location.pathname + window.location.search : '';
      const redirectParam = currentPath && currentPath !== '/' ? encodeURIComponent(currentPath) : '/admin/engineering/codebase';
      router.push(`/login?redirect=${redirectParam}`);
    }
  }, [user, isAuthenticated, isLoading, router, hasPermission]);

  // Check if current user has admin permissions
  const isAdmin = hasPermission(PermissionName.VIEW_SYSTEM_ANALYTICS);

  return {
    isAdmin,
    isLoading,
    user,
  };
}
