/**
 * Higher-order component and utility components for permission-based rendering
 */

import React from 'react';
import { usePermissions } from './usePermissions';
import { PermissionName } from '@/types/enums';

/**
 * Higher-order component for permission-based rendering
 */
export function withPermission(
  Component: React.ComponentType,
  permission: PermissionName | string,
  fallback?: React.ReactNode
) {
  return function PermissionProtectedComponent(props: Record<string, unknown>) {
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
