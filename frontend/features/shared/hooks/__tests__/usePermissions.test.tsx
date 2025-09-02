/**
 * Tests for usePermissions hook and PermissionGate component
 */

import React from 'react';
import { renderHook, render, screen } from '@testing-library/react';
import { usePermissions, PermissionGate, withPermission } from '../usePermissions';
import { useAuth } from '../useAuth';
import { PermissionName } from '@/types/enums';

// Mock useAuth hook
jest.mock('../useAuth');
const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;

describe('usePermissions', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('hasPermission', () => {
    it('should return false when user is null', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: null,
        login: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn().mockResolvedValue(undefined),
        redirectToLogin: jest.fn(),
      });

      const { result } = renderHook(() => usePermissions());

      expect(result.current.hasPermission(PermissionName.CREATE_BOOKINGS)).toBe(false);
    });

    it('should return false when user has no permissions', () => {
      mockUseAuth.mockReturnValue({
        user: { id: '1', email: 'test@test.com', first_name: 'A', last_name: 'B', roles: [], permissions: [], is_active: true, created_at: '', updated_at: '' },
        isAuthenticated: true,
        isLoading: false,
        error: null,
        login: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn().mockResolvedValue(undefined),
        redirectToLogin: jest.fn(),
      });

      const { result } = renderHook(() => usePermissions());

      expect(result.current.hasPermission(PermissionName.CREATE_BOOKINGS)).toBe(false);
    });

    it('should return true when user has the required permission', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          email: 'student@test.com',
          first_name: 'A',
          last_name: 'B',
          roles: [],
          permissions: [PermissionName.CREATE_BOOKINGS, PermissionName.VIEW_OWN_BOOKINGS],
          is_active: true,
          created_at: '',
          updated_at: '',
        },
        isAuthenticated: true,
        isLoading: false,
        error: null,
        login: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn().mockResolvedValue(undefined),
        redirectToLogin: jest.fn(),
      });

      const { result } = renderHook(() => usePermissions());

      expect(result.current.hasPermission(PermissionName.CREATE_BOOKINGS)).toBe(true);
      expect(result.current.hasPermission(PermissionName.VIEW_OWN_BOOKINGS)).toBe(true);
      expect(result.current.hasPermission(PermissionName.MANAGE_USERS)).toBe(false);
    });

    it('should work with string permissions', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          email: 'test@test.com',
          first_name: 'A',
          last_name: 'B',
          roles: [],
          permissions: ['create_bookings', 'view_own_bookings'],
          is_active: true,
          created_at: '',
          updated_at: '',
        },
        isAuthenticated: true,
        isLoading: false,
        error: null,
        login: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn().mockResolvedValue(undefined),
        redirectToLogin: jest.fn(),
      });

      const { result } = renderHook(() => usePermissions());

      expect(result.current.hasPermission('create_bookings')).toBe(true);
      expect(result.current.hasPermission('manage_users')).toBe(false);
    });
  });

  describe('hasAnyPermission', () => {
    it('should return false when user has none of the required permissions', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          email: 'test@test.com',
          first_name: 'A',
          last_name: 'B',
          roles: [],
          permissions: [PermissionName.VIEW_OWN_BOOKINGS],
          is_active: true,
          created_at: '',
          updated_at: '',
        },
        isAuthenticated: true,
        isLoading: false,
        error: null,
        login: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn().mockResolvedValue(undefined),
        redirectToLogin: jest.fn(),
      });

      const { result } = renderHook(() => usePermissions());

      expect(
        result.current.hasAnyPermission(
          PermissionName.MANAGE_USERS,
          PermissionName.VIEW_SYSTEM_ANALYTICS
        )
      ).toBe(false);
    });

    it('should return true when user has at least one of the required permissions', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          email: 'admin@test.com',
          first_name: 'A',
          last_name: 'B',
          roles: [],
          permissions: [PermissionName.VIEW_SYSTEM_ANALYTICS, PermissionName.VIEW_OWN_BOOKINGS],
          is_active: true,
          created_at: '',
          updated_at: '',
        },
        isAuthenticated: true,
        isLoading: false,
        error: null,
        login: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn().mockResolvedValue(undefined),
        redirectToLogin: jest.fn(),
      });

      const { result } = renderHook(() => usePermissions());

      expect(
        result.current.hasAnyPermission(
          PermissionName.MANAGE_USERS,
          PermissionName.VIEW_SYSTEM_ANALYTICS
        )
      ).toBe(true);
    });
  });

  describe('hasAllPermissions', () => {
    it('should return false when user is missing some required permissions', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          email: 'test@test.com',
          first_name: 'A',
          last_name: 'B',
          roles: [],
          permissions: [PermissionName.VIEW_SYSTEM_ANALYTICS],
          is_active: true,
          created_at: '',
          updated_at: '',
        },
        isAuthenticated: true,
        isLoading: false,
        error: null,
        login: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn().mockResolvedValue(undefined),
        redirectToLogin: jest.fn(),
      });

      const { result } = renderHook(() => usePermissions());

      expect(
        result.current.hasAllPermissions(
          PermissionName.VIEW_SYSTEM_ANALYTICS,
          PermissionName.MANAGE_USERS
        )
      ).toBe(false);
    });

    it('should return true when user has all required permissions', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          email: 'admin@test.com',
          first_name: 'A',
          last_name: 'B',
          roles: [],
          permissions: [
            PermissionName.VIEW_SYSTEM_ANALYTICS,
            PermissionName.MANAGE_USERS,
            PermissionName.EXPORT_ANALYTICS,
          ],
          is_active: true,
          created_at: '',
          updated_at: '',
        },
        isAuthenticated: true,
        isLoading: false,
        error: null,
        login: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn().mockResolvedValue(undefined),
        redirectToLogin: jest.fn(),
      });

      const { result } = renderHook(() => usePermissions());

      expect(
        result.current.hasAllPermissions(
          PermissionName.VIEW_SYSTEM_ANALYTICS,
          PermissionName.MANAGE_USERS
        )
      ).toBe(true);
    });
  });

  describe('convenience methods', () => {
    it('canBookLessons should check CREATE_BOOKINGS permission', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          email: 'student@test.com',
          first_name: 'A',
          last_name: 'B',
          roles: [],
          permissions: [PermissionName.CREATE_BOOKINGS],
          is_active: true,
          created_at: '',
          updated_at: '',
        },
        isAuthenticated: true,
        isLoading: false,
        error: null,
        login: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn().mockResolvedValue(undefined),
        redirectToLogin: jest.fn(),
      });

      const { result } = renderHook(() => usePermissions());

      expect(result.current.canBookLessons()).toBe(true);
    });

    it('canManageInstructorProfile should check MANAGE_INSTRUCTOR_PROFILE permission', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          email: 'instructor@test.com',
          first_name: 'A',
          last_name: 'B',
          roles: [],
          permissions: [PermissionName.MANAGE_INSTRUCTOR_PROFILE],
          is_active: true,
          created_at: '',
          updated_at: '',
        },
        isAuthenticated: true,
        isLoading: false,
        error: null,
        login: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn().mockResolvedValue(undefined),
        redirectToLogin: jest.fn(),
      });

      const { result } = renderHook(() => usePermissions());

      expect(result.current.canManageInstructorProfile()).toBe(true);
    });

    it('canViewAnalytics should check both system and instructor analytics permissions', () => {
      // Test with system analytics permission
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          email: 'admin@test.com',
          first_name: 'A',
          last_name: 'B',
          roles: [],
          permissions: [PermissionName.VIEW_SYSTEM_ANALYTICS],
          is_active: true,
          created_at: '',
          updated_at: '',
        },
        isAuthenticated: true,
        isLoading: false,
        error: null,
        login: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn().mockResolvedValue(undefined),
        redirectToLogin: jest.fn(),
      });

      const { result: adminResult } = renderHook(() => usePermissions());
      expect(adminResult.current.canViewAnalytics()).toBe(true);

      // Test with instructor analytics permission
      mockUseAuth.mockReturnValue({
        user: {
          id: '2',
          email: 'instructor@test.com',
          first_name: 'A',
          last_name: 'B',
          roles: [],
          permissions: [PermissionName.VIEW_OWN_INSTRUCTOR_ANALYTICS],
          is_active: true,
          created_at: '',
          updated_at: '',
        },
        isAuthenticated: true,
        isLoading: false,
        error: null,
        login: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn().mockResolvedValue(undefined),
        redirectToLogin: jest.fn(),
      });

      const { result: instructorResult } = renderHook(() => usePermissions());
      expect(instructorResult.current.canViewAnalytics()).toBe(true);
    });

    it('isAdmin should check for admin-specific permissions', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          email: 'admin@test.com',
          first_name: 'A',
          last_name: 'B',
          roles: [],
          permissions: [PermissionName.MANAGE_USERS, PermissionName.VIEW_SYSTEM_ANALYTICS],
          is_active: true,
          created_at: '',
          updated_at: '',
        },
        isAuthenticated: true,
        isLoading: false,
        error: null,
        login: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn().mockResolvedValue(undefined),
        redirectToLogin: jest.fn(),
      });

      const { result } = renderHook(() => usePermissions());

      expect(result.current.isAdmin()).toBe(true);
    });

    it('should return raw permissions array', () => {
      const permissions = [PermissionName.CREATE_BOOKINGS, PermissionName.VIEW_OWN_BOOKINGS];

      mockUseAuth.mockReturnValue({
        user: {
          id: '1',
          email: 'student@test.com',
          first_name: 'A',
          last_name: 'B',
          roles: [],
          permissions,
          is_active: true,
          created_at: '',
          updated_at: '',
        },
        isAuthenticated: true,
        isLoading: false,
        error: null,
        login: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn().mockResolvedValue(undefined),
        redirectToLogin: jest.fn(),
      });

      const { result } = renderHook(() => usePermissions());

      expect(result.current.permissions).toEqual(permissions);
    });
  });
});

describe('PermissionGate', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should render children when user has required permission', () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: '1',
        email: 'student@test.com',
        first_name: 'A',
        last_name: 'B',
        roles: [],
        permissions: [PermissionName.CREATE_BOOKINGS],
        is_active: true,
        created_at: '',
        updated_at: '',
      },
      isAuthenticated: true,
      isLoading: false,
      error: null,
      login: jest.fn(),
      logout: jest.fn(),
      checkAuth: jest.fn().mockResolvedValue(undefined),
      redirectToLogin: jest.fn(),
    });

    render(
      <PermissionGate permission={PermissionName.CREATE_BOOKINGS}>
        <div data-testid="protected-content">Book a lesson</div>
      </PermissionGate>
    );

    expect(screen.getByTestId('protected-content')).toBeInTheDocument();
  });

  it('should not render children when user lacks required permission', () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: '1',
        email: 'student@test.com',
        first_name: 'A',
        last_name: 'B',
        roles: [],
        permissions: [PermissionName.VIEW_OWN_BOOKINGS],
        is_active: true,
        created_at: '',
        updated_at: '',
      },
      isAuthenticated: true,
      isLoading: false,
      error: null,
      login: jest.fn(),
      logout: jest.fn(),
      checkAuth: jest.fn().mockResolvedValue(undefined),
      redirectToLogin: jest.fn(),
    });

    render(
      <PermissionGate permission={PermissionName.MANAGE_USERS}>
        <div data-testid="protected-content">Admin panel</div>
      </PermissionGate>
    );

    expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
  });

  it('should render fallback when user lacks permission and fallback is provided', () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: '1',
        email: 'student@test.com',
        first_name: 'A',
        last_name: 'B',
        roles: [],
        permissions: [PermissionName.VIEW_OWN_BOOKINGS],
        is_active: true,
        created_at: '',
        updated_at: '',
      },
      isAuthenticated: true,
      isLoading: false,
      error: null,
      login: jest.fn(),
      logout: jest.fn(),
      checkAuth: jest.fn().mockResolvedValue(undefined),
      redirectToLogin: jest.fn(),
    });

    render(
      <PermissionGate
        permission={PermissionName.MANAGE_USERS}
        fallback={<div data-testid="fallback">Access denied</div>}
      >
        <div data-testid="protected-content">Admin panel</div>
      </PermissionGate>
    );

    expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
    expect(screen.getByTestId('fallback')).toBeInTheDocument();
  });

  it('should work with array of permissions (ANY logic)', () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: '1',
        email: 'user@test.com',
        first_name: 'A',
        last_name: 'B',
        roles: [],
        permissions: [PermissionName.VIEW_SYSTEM_ANALYTICS],
        is_active: true,
        created_at: '',
        updated_at: '',
      },
      isAuthenticated: true,
      isLoading: false,
      error: null,
      login: jest.fn(),
      logout: jest.fn(),
      checkAuth: jest.fn().mockResolvedValue(undefined),
      redirectToLogin: jest.fn(),
    });

    render(
      <PermissionGate
        permission={[
          PermissionName.VIEW_SYSTEM_ANALYTICS,
          PermissionName.VIEW_OWN_INSTRUCTOR_ANALYTICS,
        ]}
      >
        <div data-testid="analytics-content">Analytics Dashboard</div>
      </PermissionGate>
    );

    expect(screen.getByTestId('analytics-content')).toBeInTheDocument();
  });

  it('should work with array of permissions (ALL logic)', () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: '1',
        email: 'admin@test.com',
        first_name: 'A',
        last_name: 'B',
        roles: [],
        permissions: [PermissionName.MANAGE_USERS, PermissionName.VIEW_SYSTEM_ANALYTICS],
        is_active: true,
        created_at: '',
        updated_at: '',
      },
      isAuthenticated: true,
      isLoading: false,
      error: null,
      login: jest.fn(),
      logout: jest.fn(),
      checkAuth: jest.fn().mockResolvedValue(undefined),
      redirectToLogin: jest.fn(),
    });

    render(
      <PermissionGate
        permission={[PermissionName.MANAGE_USERS, PermissionName.VIEW_SYSTEM_ANALYTICS]}
        requireAll={true}
      >
        <div data-testid="super-admin-content">Super Admin Panel</div>
      </PermissionGate>
    );

    expect(screen.getByTestId('super-admin-content')).toBeInTheDocument();
  });

  it('should not render when requireAll=true and user lacks some permissions', () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: '1',
        email: 'user@test.com',
        first_name: 'A',
        last_name: 'B',
        roles: [],
        permissions: [PermissionName.VIEW_SYSTEM_ANALYTICS], // Missing MANAGE_USERS
        is_active: true,
        created_at: '',
        updated_at: '',
      },
      isAuthenticated: true,
      isLoading: false,
      error: null,
      login: jest.fn(),
      logout: jest.fn(),
      checkAuth: jest.fn().mockResolvedValue(undefined),
      redirectToLogin: jest.fn(),
    });

    render(
      <PermissionGate
        permission={[PermissionName.MANAGE_USERS, PermissionName.VIEW_SYSTEM_ANALYTICS]}
        requireAll={true}
      >
        <div data-testid="super-admin-content">Super Admin Panel</div>
      </PermissionGate>
    );

    expect(screen.queryByTestId('super-admin-content')).not.toBeInTheDocument();
  });
});

describe('withPermission HOC', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  const TestComponent = () => <div data-testid="test-component">Test Content</div>;

  it('should render component when user has required permission', () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: '1',
        email: 'admin@test.com',
        first_name: 'A',
        last_name: 'B',
        roles: [],
        permissions: [PermissionName.MANAGE_USERS],
        is_active: true,
        created_at: '',
        updated_at: '',
      },
      isAuthenticated: true,
      isLoading: false,
      error: null,
      login: jest.fn(),
      logout: jest.fn(),
      checkAuth: jest.fn().mockResolvedValue(undefined),
      redirectToLogin: jest.fn(),
    });

    const ProtectedComponent = withPermission(TestComponent, PermissionName.MANAGE_USERS);

    render(<ProtectedComponent />);

    expect(screen.getByTestId('test-component')).toBeInTheDocument();
  });

  it('should not render component when user lacks required permission', () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: '1',
        email: 'student@test.com',
        first_name: 'A',
        last_name: 'B',
        roles: [],
        permissions: [PermissionName.CREATE_BOOKINGS],
        is_active: true,
        created_at: '',
        updated_at: '',
      },
      isAuthenticated: true,
      isLoading: false,
      error: null,
      login: jest.fn(),
      logout: jest.fn(),
      checkAuth: jest.fn().mockResolvedValue(undefined),
      redirectToLogin: jest.fn(),
    });

    const ProtectedComponent = withPermission(TestComponent, PermissionName.MANAGE_USERS);

    render(<ProtectedComponent />);

    expect(screen.queryByTestId('test-component')).not.toBeInTheDocument();
  });

  it('should render fallback when user lacks permission and fallback is provided', () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: '1',
        email: 'student@test.com',
        first_name: 'A',
        last_name: 'B',
        roles: [],
        permissions: [PermissionName.CREATE_BOOKINGS],
        is_active: true,
        created_at: '',
        updated_at: '',
      },
      isAuthenticated: true,
      isLoading: false,
      error: null,
      login: jest.fn(),
      logout: jest.fn(),
      checkAuth: jest.fn().mockResolvedValue(undefined),
      redirectToLogin: jest.fn(),
    });

    const fallback = <div data-testid="fallback">Access denied</div>;
    const ProtectedComponent = withPermission(TestComponent, PermissionName.MANAGE_USERS, fallback);

    render(<ProtectedComponent />);

    expect(screen.queryByTestId('test-component')).not.toBeInTheDocument();
    expect(screen.getByTestId('fallback')).toBeInTheDocument();
  });
});
