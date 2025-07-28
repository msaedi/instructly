/**
 * Tests for useAdminAuth hook
 */

import { renderHook } from '@testing-library/react';
import { useRouter } from 'next/navigation';
import { useAdminAuth } from '../useAdminAuth';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { usePermissions } from '@/features/shared/hooks/usePermissions';
import { PermissionName } from '@/types/enums';

// Mock dependencies
jest.mock('next/navigation');
jest.mock('@/features/shared/hooks/useAuth');
jest.mock('@/features/shared/hooks/usePermissions');

const mockPush = jest.fn();
const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;
const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;
const mockUsePermissions = usePermissions as jest.MockedFunction<typeof usePermissions>;

describe('useAdminAuth', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseRouter.mockReturnValue({
      push: mockPush,
      replace: jest.fn(),
      prefetch: jest.fn(),
    } as any);

    // Clear localStorage mock
    (window.localStorage.getItem as jest.Mock).mockReturnValue(null);
  });

  it('should not redirect while loading', () => {
    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: true,
      login: jest.fn(),
      logout: jest.fn(),
    });

    mockUsePermissions.mockReturnValue({
      hasPermission: jest.fn().mockReturnValue(false),
      hasAnyPermission: jest.fn(),
      hasAllPermissions: jest.fn(),
      canBookLessons: jest.fn(),
      canManageInstructorProfile: jest.fn(),
      canViewAnalytics: jest.fn(),
      isAdmin: jest.fn(),
      permissions: [],
    });

    const { result } = renderHook(() => useAdminAuth());

    expect(mockPush).not.toHaveBeenCalled();
    expect(result.current.isLoading).toBe(true);
    expect(result.current.isAdmin).toBe(false);
  });

  it('should redirect to login when not authenticated and no token in localStorage', () => {
    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      login: jest.fn(),
      logout: jest.fn(),
    });

    mockUsePermissions.mockReturnValue({
      hasPermission: jest.fn().mockReturnValue(false),
      hasAnyPermission: jest.fn(),
      hasAllPermissions: jest.fn(),
      canBookLessons: jest.fn(),
      canManageInstructorProfile: jest.fn(),
      canViewAnalytics: jest.fn(),
      isAdmin: jest.fn(),
      permissions: [],
    });

    // No token in localStorage
    (window.localStorage.getItem as jest.Mock).mockReturnValue(null);

    renderHook(() => useAdminAuth());

    expect(mockPush).toHaveBeenCalledWith('/login?redirect=/admin/analytics/search');
  });

  it('should not redirect to login when token exists in localStorage', () => {
    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      login: jest.fn(),
      logout: jest.fn(),
    });

    mockUsePermissions.mockReturnValue({
      hasPermission: jest.fn().mockReturnValue(false),
      hasAnyPermission: jest.fn(),
      hasAllPermissions: jest.fn(),
      canBookLessons: jest.fn(),
      canManageInstructorProfile: jest.fn(),
      canViewAnalytics: jest.fn(),
      isAdmin: jest.fn(),
      permissions: [],
    });

    // Token exists in localStorage
    (window.localStorage.getItem as jest.Mock).mockReturnValue('fake-token');

    renderHook(() => useAdminAuth());

    expect(mockPush).not.toHaveBeenCalledWith('/login?redirect=/admin/analytics/search');
  });

  it('should redirect to home when user lacks admin permissions', () => {
    const mockUser = {
      id: 1,
      email: 'student@test.com',
      permissions: [PermissionName.CREATE_BOOKINGS],
    };

    mockUseAuth.mockReturnValue({
      user: mockUser,
      isAuthenticated: true,
      isLoading: false,
      login: jest.fn(),
      logout: jest.fn(),
    });

    mockUsePermissions.mockReturnValue({
      hasPermission: jest.fn().mockImplementation((permission) => {
        return permission !== PermissionName.VIEW_SYSTEM_ANALYTICS;
      }),
      hasAnyPermission: jest.fn(),
      hasAllPermissions: jest.fn(),
      canBookLessons: jest.fn(),
      canManageInstructorProfile: jest.fn(),
      canViewAnalytics: jest.fn(),
      isAdmin: jest.fn(),
      permissions: [PermissionName.CREATE_BOOKINGS],
    });

    renderHook(() => useAdminAuth());

    expect(mockPush).toHaveBeenCalledWith('/');
  });

  it('should not redirect when user has admin permissions', () => {
    const mockUser = {
      id: 1,
      email: 'admin@test.com',
      permissions: [PermissionName.VIEW_SYSTEM_ANALYTICS, PermissionName.MANAGE_USERS],
    };

    mockUseAuth.mockReturnValue({
      user: mockUser,
      isAuthenticated: true,
      isLoading: false,
      login: jest.fn(),
      logout: jest.fn(),
    });

    mockUsePermissions.mockReturnValue({
      hasPermission: jest.fn().mockImplementation((permission) => {
        return mockUser.permissions.includes(permission);
      }),
      hasAnyPermission: jest.fn(),
      hasAllPermissions: jest.fn(),
      canBookLessons: jest.fn(),
      canManageInstructorProfile: jest.fn(),
      canViewAnalytics: jest.fn(),
      isAdmin: jest.fn(),
      permissions: mockUser.permissions,
    });

    const { result } = renderHook(() => useAdminAuth());

    expect(mockPush).not.toHaveBeenCalled();
    expect(result.current.isAdmin).toBe(true);
    expect(result.current.user).toEqual(mockUser);
  });

  it('should return correct isAdmin value based on permissions', () => {
    const adminUser = {
      id: 1,
      email: 'admin@test.com',
      permissions: [PermissionName.VIEW_SYSTEM_ANALYTICS],
    };

    mockUseAuth.mockReturnValue({
      user: adminUser,
      isAuthenticated: true,
      isLoading: false,
      login: jest.fn(),
      logout: jest.fn(),
    });

    mockUsePermissions.mockReturnValue({
      hasPermission: jest.fn().mockImplementation((permission) => {
        return permission === PermissionName.VIEW_SYSTEM_ANALYTICS;
      }),
      hasAnyPermission: jest.fn(),
      hasAllPermissions: jest.fn(),
      canBookLessons: jest.fn(),
      canManageInstructorProfile: jest.fn(),
      canViewAnalytics: jest.fn(),
      isAdmin: jest.fn(),
      permissions: [PermissionName.VIEW_SYSTEM_ANALYTICS],
    });

    const { result } = renderHook(() => useAdminAuth());

    expect(result.current.isAdmin).toBe(true);
  });

  it('should handle state changes and re-evaluate permissions', () => {
    // Start with no user
    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      login: jest.fn(),
      logout: jest.fn(),
    });

    mockUsePermissions.mockReturnValue({
      hasPermission: jest.fn().mockReturnValue(false),
      hasAnyPermission: jest.fn(),
      hasAllPermissions: jest.fn(),
      canBookLessons: jest.fn(),
      canManageInstructorProfile: jest.fn(),
      canViewAnalytics: jest.fn(),
      isAdmin: jest.fn(),
      permissions: [],
    });

    const { result, rerender } = renderHook(() => useAdminAuth());

    expect(result.current.isAdmin).toBe(false);

    // Update to have admin user
    const adminUser = {
      id: 1,
      email: 'admin@test.com',
      permissions: [PermissionName.VIEW_SYSTEM_ANALYTICS],
    };

    mockUseAuth.mockReturnValue({
      user: adminUser,
      isAuthenticated: true,
      isLoading: false,
      login: jest.fn(),
      logout: jest.fn(),
    });

    mockUsePermissions.mockReturnValue({
      hasPermission: jest.fn().mockImplementation((permission) => {
        return permission === PermissionName.VIEW_SYSTEM_ANALYTICS;
      }),
      hasAnyPermission: jest.fn(),
      hasAllPermissions: jest.fn(),
      canBookLessons: jest.fn(),
      canManageInstructorProfile: jest.fn(),
      canViewAnalytics: jest.fn(),
      isAdmin: jest.fn(),
      permissions: [PermissionName.VIEW_SYSTEM_ANALYTICS],
    });

    rerender();

    expect(result.current.isAdmin).toBe(true);
    expect(result.current.user).toEqual(adminUser);
  });
});
