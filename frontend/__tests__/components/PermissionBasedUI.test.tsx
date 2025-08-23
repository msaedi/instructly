/**
 * Integration tests for permission-based UI rendering
 * Tests real-world scenarios of how different user types see different UI elements
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { PermissionGate } from '@/features/shared/hooks/usePermissions';
import { PermissionName } from '@/types/enums';

// Mock useAuth hook
jest.mock('@/features/shared/hooks/useAuth');
const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;

// Sample components that would use permission gates
const AdminDashboard = () => (
  <PermissionGate permission={PermissionName.VIEW_SYSTEM_ANALYTICS}>
    <div data-testid="admin-dashboard">Admin Analytics Dashboard</div>
  </PermissionGate>
);

const UserManagement = () => (
  <PermissionGate permission={PermissionName.MANAGE_USERS}>
    <div data-testid="user-management">User Management Panel</div>
  </PermissionGate>
);

const BookingActions = () => (
  <>
    <PermissionGate permission={PermissionName.CREATE_BOOKINGS}>
      <button data-testid="book-lesson-btn">Book a Lesson</button>
    </PermissionGate>

    <PermissionGate permission={PermissionName.VIEW_OWN_BOOKINGS}>
      <div data-testid="my-bookings">My Bookings</div>
    </PermissionGate>

    <PermissionGate permission={PermissionName.CANCEL_OWN_BOOKINGS}>
      <button data-testid="cancel-booking-btn">Cancel Booking</button>
    </PermissionGate>
  </>
);

const InstructorTools = () => (
  <>
    <PermissionGate permission={PermissionName.MANAGE_INSTRUCTOR_PROFILE}>
      <div data-testid="instructor-profile">Manage Profile</div>
    </PermissionGate>

    <PermissionGate permission={PermissionName.MANAGE_AVAILABILITY}>
      <div data-testid="manage-availability">Set Availability</div>
    </PermissionGate>

    <PermissionGate permission={PermissionName.VIEW_INCOMING_BOOKINGS}>
      <div data-testid="incoming-bookings">Incoming Bookings</div>
    </PermissionGate>

    <PermissionGate permission={PermissionName.COMPLETE_BOOKINGS}>
      <button data-testid="complete-booking-btn">Mark Complete</button>
    </PermissionGate>
  </>
);

const NavigationMenu = () => (
  <nav data-testid="navigation-menu">
    {/* Analytics menu - only for users who can view analytics */}
    <PermissionGate
      permission={[
        PermissionName.VIEW_SYSTEM_ANALYTICS,
        PermissionName.VIEW_OWN_INSTRUCTOR_ANALYTICS,
      ]}
    >
      <a data-testid="analytics-link" href="/analytics">
        Analytics
      </a>
    </PermissionGate>

    {/* Admin menu - only for admin users */}
    <PermissionGate permission={PermissionName.MANAGE_USERS}>
      <a data-testid="admin-link" href="/admin">
        Admin Panel
      </a>
    </PermissionGate>

    {/* Student menu */}
    <PermissionGate permission={PermissionName.CREATE_BOOKINGS}>
      <a data-testid="search-link" href="/search">
        Find Instructors
      </a>
    </PermissionGate>

    {/* Instructor menu */}
    <PermissionGate permission={PermissionName.MANAGE_INSTRUCTOR_PROFILE}>
      <a data-testid="instructor-dashboard-link" href="/instructor/dashboard">
        Instructor Dashboard
      </a>
    </PermissionGate>
  </nav>
);

const CompleteAppLayout = () => (
  <div data-testid="app-layout">
    <NavigationMenu />
    <AdminDashboard />
    <UserManagement />
    <BookingActions />
    <InstructorTools />
  </div>
);

describe('Permission-Based UI Rendering', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Student User Experience', () => {
    const studentUser = {
      id: 1,
      email: 'student@test.com',
      permissions: [
        PermissionName.MANAGE_OWN_PROFILE,
        PermissionName.VIEW_OWN_BOOKINGS,
        PermissionName.CHANGE_OWN_PASSWORD,
        PermissionName.DELETE_OWN_ACCOUNT,
        PermissionName.VIEW_OWN_SEARCH_HISTORY,
        PermissionName.VIEW_INSTRUCTORS,
        PermissionName.VIEW_INSTRUCTOR_AVAILABILITY,
        PermissionName.CREATE_BOOKINGS,
        PermissionName.CANCEL_OWN_BOOKINGS,
        PermissionName.VIEW_BOOKING_DETAILS,
      ],
    };

    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: studentUser,
        isAuthenticated: true,
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
      });
    });

    it('should show student-specific UI elements', () => {
      render(<CompleteAppLayout />);

      // Should see student booking actions
      expect(screen.getByTestId('book-lesson-btn')).toBeInTheDocument();
      expect(screen.getByTestId('my-bookings')).toBeInTheDocument();
      expect(screen.getByTestId('cancel-booking-btn')).toBeInTheDocument();

      // Should see student navigation
      expect(screen.getByTestId('search-link')).toBeInTheDocument();
    });

    it('should NOT show admin-specific UI elements', () => {
      render(<CompleteAppLayout />);

      // Should NOT see admin elements
      expect(screen.queryByTestId('admin-dashboard')).not.toBeInTheDocument();
      expect(screen.queryByTestId('user-management')).not.toBeInTheDocument();
      expect(screen.queryByTestId('admin-link')).not.toBeInTheDocument();
    });

    it('should NOT show instructor-specific UI elements', () => {
      render(<CompleteAppLayout />);

      // Should NOT see instructor elements
      expect(screen.queryByTestId('instructor-profile')).not.toBeInTheDocument();
      expect(screen.queryByTestId('manage-availability')).not.toBeInTheDocument();
      expect(screen.queryByTestId('incoming-bookings')).not.toBeInTheDocument();
      expect(screen.queryByTestId('complete-booking-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('instructor-dashboard-link')).not.toBeInTheDocument();
    });
  });

  describe('Instructor User Experience', () => {
    const instructorUser = {
      id: 2,
      email: 'instructor@test.com',
      permissions: [
        // Shared permissions
        PermissionName.MANAGE_OWN_PROFILE,
        PermissionName.VIEW_OWN_BOOKINGS,
        PermissionName.CHANGE_OWN_PASSWORD,
        PermissionName.DELETE_OWN_ACCOUNT,
        PermissionName.VIEW_OWN_SEARCH_HISTORY,
        // Instructor-specific permissions
        PermissionName.MANAGE_INSTRUCTOR_PROFILE,
        PermissionName.MANAGE_SERVICES,
        PermissionName.MANAGE_AVAILABILITY,
        PermissionName.VIEW_INCOMING_BOOKINGS,
        PermissionName.COMPLETE_BOOKINGS,
        PermissionName.CANCEL_STUDENT_BOOKINGS,
        PermissionName.VIEW_OWN_INSTRUCTOR_ANALYTICS,
        PermissionName.SUSPEND_OWN_INSTRUCTOR_ACCOUNT,
      ],
    };

    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: instructorUser,
        isAuthenticated: true,
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
      });
    });

    it('should show instructor-specific UI elements', () => {
      render(<CompleteAppLayout />);

      // Should see instructor tools
      expect(screen.getByTestId('instructor-profile')).toBeInTheDocument();
      expect(screen.getByTestId('manage-availability')).toBeInTheDocument();
      expect(screen.getByTestId('incoming-bookings')).toBeInTheDocument();
      expect(screen.getByTestId('complete-booking-btn')).toBeInTheDocument();

      // Should see instructor navigation
      expect(screen.getByTestId('instructor-dashboard-link')).toBeInTheDocument();
      expect(screen.getByTestId('analytics-link')).toBeInTheDocument(); // Has instructor analytics
    });

    it('should show shared booking elements', () => {
      render(<CompleteAppLayout />);

      // Should see shared booking elements
      expect(screen.getByTestId('my-bookings')).toBeInTheDocument();
    });

    it('should NOT show student-specific booking actions', () => {
      render(<CompleteAppLayout />);

      // Should NOT see student booking actions
      expect(screen.queryByTestId('book-lesson-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('cancel-booking-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('search-link')).not.toBeInTheDocument();
    });

    it('should NOT show admin-specific UI elements', () => {
      render(<CompleteAppLayout />);

      // Should NOT see admin elements
      expect(screen.queryByTestId('admin-dashboard')).not.toBeInTheDocument();
      expect(screen.queryByTestId('user-management')).not.toBeInTheDocument();
      expect(screen.queryByTestId('admin-link')).not.toBeInTheDocument();
    });
  });

  describe('Admin User Experience', () => {
    const adminUser = {
      id: 3,
      email: 'admin@test.com',
      permissions: [
        // All permissions for admin
        PermissionName.MANAGE_OWN_PROFILE,
        PermissionName.VIEW_OWN_BOOKINGS,
        PermissionName.CHANGE_OWN_PASSWORD,
        PermissionName.DELETE_OWN_ACCOUNT,
        PermissionName.VIEW_OWN_SEARCH_HISTORY,
        PermissionName.VIEW_INSTRUCTORS,
        PermissionName.VIEW_INSTRUCTOR_AVAILABILITY,
        PermissionName.CREATE_BOOKINGS,
        PermissionName.CANCEL_OWN_BOOKINGS,
        PermissionName.VIEW_BOOKING_DETAILS,
        PermissionName.MANAGE_INSTRUCTOR_PROFILE,
        PermissionName.MANAGE_SERVICES,
        PermissionName.MANAGE_AVAILABILITY,
        PermissionName.VIEW_INCOMING_BOOKINGS,
        PermissionName.COMPLETE_BOOKINGS,
        PermissionName.CANCEL_STUDENT_BOOKINGS,
        PermissionName.VIEW_OWN_INSTRUCTOR_ANALYTICS,
        PermissionName.SUSPEND_OWN_INSTRUCTOR_ACCOUNT,
        PermissionName.VIEW_ALL_USERS,
        PermissionName.MANAGE_USERS,
        PermissionName.VIEW_SYSTEM_ANALYTICS,
        PermissionName.EXPORT_ANALYTICS,
        PermissionName.VIEW_ALL_BOOKINGS,
        PermissionName.MANAGE_ALL_BOOKINGS,
        PermissionName.ACCESS_MONITORING,
        PermissionName.MODERATE_CONTENT,
        PermissionName.VIEW_FINANCIALS,
        PermissionName.MANAGE_FINANCIALS,
        PermissionName.MANAGE_ROLES,
        PermissionName.MANAGE_PERMISSIONS,
      ],
    };

    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: adminUser,
        isAuthenticated: true,
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
      });
    });

    it('should show all UI elements (admin has all permissions)', () => {
      render(<CompleteAppLayout />);

      // Should see admin elements
      expect(screen.getByTestId('admin-dashboard')).toBeInTheDocument();
      expect(screen.getByTestId('user-management')).toBeInTheDocument();
      expect(screen.getByTestId('admin-link')).toBeInTheDocument();

      // Should see all navigation elements
      expect(screen.getByTestId('analytics-link')).toBeInTheDocument();
      expect(screen.getByTestId('search-link')).toBeInTheDocument();
      expect(screen.getByTestId('instructor-dashboard-link')).toBeInTheDocument();

      // Should see all booking actions
      expect(screen.getByTestId('book-lesson-btn')).toBeInTheDocument();
      expect(screen.getByTestId('my-bookings')).toBeInTheDocument();
      expect(screen.getByTestId('cancel-booking-btn')).toBeInTheDocument();

      // Should see all instructor tools
      expect(screen.getByTestId('instructor-profile')).toBeInTheDocument();
      expect(screen.getByTestId('manage-availability')).toBeInTheDocument();
      expect(screen.getByTestId('incoming-bookings')).toBeInTheDocument();
      expect(screen.getByTestId('complete-booking-btn')).toBeInTheDocument();
    });
  });

  describe('Unauthenticated User Experience', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
      });
    });

    it('should not show any protected UI elements', () => {
      render(<CompleteAppLayout />);

      // Should NOT see any protected elements
      expect(screen.queryByTestId('admin-dashboard')).not.toBeInTheDocument();
      expect(screen.queryByTestId('user-management')).not.toBeInTheDocument();
      expect(screen.queryByTestId('book-lesson-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('my-bookings')).not.toBeInTheDocument();
      expect(screen.queryByTestId('instructor-profile')).not.toBeInTheDocument();
      expect(screen.queryByTestId('analytics-link')).not.toBeInTheDocument();
      expect(screen.queryByTestId('admin-link')).not.toBeInTheDocument();
    });

    it('should show the basic layout structure', () => {
      render(<CompleteAppLayout />);

      // Should see the basic app structure
      expect(screen.getByTestId('app-layout')).toBeInTheDocument();
      expect(screen.getByTestId('navigation-menu')).toBeInTheDocument();
    });
  });

  describe('Loading State', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        isLoading: true,
        login: jest.fn(),
        logout: jest.fn(),
      });
    });

    it('should not show protected elements while loading', () => {
      render(<CompleteAppLayout />);

      // Should NOT see any protected elements while loading
      expect(screen.queryByTestId('admin-dashboard')).not.toBeInTheDocument();
      expect(screen.queryByTestId('user-management')).not.toBeInTheDocument();
      expect(screen.queryByTestId('book-lesson-btn')).not.toBeInTheDocument();
    });
  });

  describe('Permission Edge Cases', () => {
    it('should handle user with mixed permissions correctly', () => {
      // User with some student and some instructor permissions (edge case)
      const mixedUser = {
        id: 4,
        email: 'mixed@test.com',
        permissions: [
          PermissionName.CREATE_BOOKINGS, // Student permission
          PermissionName.MANAGE_INSTRUCTOR_PROFILE, // Instructor permission
          PermissionName.VIEW_SYSTEM_ANALYTICS, // Admin permission
        ],
      };

      mockUseAuth.mockReturnValue({
        user: mixedUser,
        isAuthenticated: true,
        isLoading: false,
        login: jest.fn(),
        logout: jest.fn(),
      });

      render(<CompleteAppLayout />);

      // Should see elements based on actual permissions
      expect(screen.getByTestId('book-lesson-btn')).toBeInTheDocument(); // Has CREATE_BOOKINGS
      expect(screen.getByTestId('instructor-profile')).toBeInTheDocument(); // Has MANAGE_INSTRUCTOR_PROFILE
      expect(screen.getByTestId('admin-dashboard')).toBeInTheDocument(); // Has VIEW_SYSTEM_ANALYTICS

      // Should NOT see elements for missing permissions
      expect(screen.queryByTestId('user-management')).not.toBeInTheDocument(); // Missing MANAGE_USERS
      expect(screen.queryByTestId('manage-availability')).not.toBeInTheDocument(); // Missing MANAGE_AVAILABILITY
    });
  });
});
