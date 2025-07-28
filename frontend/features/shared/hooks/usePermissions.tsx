/**
 * usePermissions Hook
 *
 * Provides permission checking utilities for RBAC in the frontend.
 * Works with the backend RBAC system to control UI elements based on user permissions.
 */

import React from 'react';
import { useAuth } from './useAuth';
import { PermissionName } from '@/types/enums';

export function usePermissions() {
  const { user } = useAuth();

  /**
   * Check if the current user has a specific permission
   */
  const hasPermission = (permission: PermissionName | string): boolean => {
    if (!user || !user.permissions) return false;
    return user.permissions.includes(permission);
  };

  /**
   * Check if the current user has ANY of the specified permissions
   */
  const hasAnyPermission = (...permissions: (PermissionName | string)[]): boolean => {
    if (!user || !user.permissions) return false;
    return permissions.some((permission) => user.permissions.includes(permission));
  };

  /**
   * Check if the current user has ALL of the specified permissions
   */
  const hasAllPermissions = (...permissions: (PermissionName | string)[]): boolean => {
    if (!user || !user.permissions) return false;
    return permissions.every((permission) => user.permissions.includes(permission));
  };

  /**
   * Check if user can perform student actions
   */
  const canBookLessons = (): boolean => {
    return hasPermission(PermissionName.CREATE_BOOKINGS);
  };

  /**
   * Check if user can manage instructor profile
   */
  const canManageInstructorProfile = (): boolean => {
    return hasPermission(PermissionName.MANAGE_INSTRUCTOR_PROFILE);
  };

  /**
   * Check if user can view analytics
   */
  const canViewAnalytics = (): boolean => {
    return hasAnyPermission(
      PermissionName.VIEW_SYSTEM_ANALYTICS,
      PermissionName.VIEW_OWN_INSTRUCTOR_ANALYTICS
    );
  };

  /**
   * Check if user can access admin features
   */
  const isAdmin = (): boolean => {
    // Admin has all permissions, so check for admin-specific ones
    return hasAnyPermission(
      PermissionName.MANAGE_USERS,
      PermissionName.VIEW_SYSTEM_ANALYTICS,
      PermissionName.MANAGE_ROLES
    );
  };

  return {
    // Core permission checks
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,

    // Convenience methods
    canBookLessons,
    canManageInstructorProfile,
    canViewAnalytics,
    isAdmin,

    // Raw data
    permissions: user?.permissions || [],
  };
}

/**
 * Higher-order component for permission-based rendering
 */
export function withPermission(
  Component: React.ComponentType,
  permission: PermissionName | string,
  fallback?: React.ReactNode
) {
  return function PermissionProtectedComponent(props: any) {
    const { hasPermission } = usePermissions();

    if (!hasPermission(permission)) {
      return fallback ? <>{fallback}</> : null;
    }

    return <Component {...props} />;
  };
}

/**
 * Component for conditional rendering based on permissions
 */
export function PermissionGate({
  permission,
  children,
  fallback = null,
  requireAll = false,
}: {
  permission: PermissionName | string | (PermissionName | string)[];
  children: React.ReactNode;
  fallback?: React.ReactNode;
  requireAll?: boolean;
}) {
  const { hasPermission, hasAnyPermission, hasAllPermissions } = usePermissions();

  const hasAccess = Array.isArray(permission)
    ? requireAll
      ? hasAllPermissions(...permission)
      : hasAnyPermission(...permission)
    : hasPermission(permission);

  return hasAccess ? <>{children}</> : <>{fallback}</>;
}
