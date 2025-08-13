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

    // Only redirect if we're definitely not authenticated (no token in localStorage)
    if (!isAuthenticated && !localStorage.getItem('access_token')) {
      const currentPath =
        typeof window !== 'undefined' ? window.location.pathname + window.location.search : '';
      const returnUrl = currentPath && currentPath !== '/' ? currentPath : '/admin/analytics/search';
      router.push(`/login?redirect=${encodeURIComponent(returnUrl)}`);
      return;
    }

    // Check for admin permissions using RBAC
    if (user && !hasPermission(PermissionName.VIEW_SYSTEM_ANALYTICS)) {
      // Redirect to home page for non-admins
      router.push('/');
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
