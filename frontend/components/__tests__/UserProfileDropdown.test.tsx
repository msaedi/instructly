// frontend/components/__tests__/UserProfileDropdown.test.tsx
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import UserProfileDropdown from '../UserProfileDropdown';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useRouter, usePathname } from 'next/navigation';
import { useInstructorProfileMe } from '@/hooks/queries/useInstructorProfileMe';
import { RoleName } from '@/types/enums';
import { createPortal } from 'react-dom';

// Mock dependencies
jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(),
}));

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  usePathname: jest.fn(),
}));

jest.mock('@/hooks/queries/useInstructorProfileMe', () => ({
  useInstructorProfileMe: jest.fn(),
}));

jest.mock('@/components/user/UserAvatar', () => ({
  UserAvatar: ({ size }: { user: unknown; size: number }) => (
    <div data-testid="user-avatar" data-size={size}>Avatar</div>
  ),
}));

jest.mock('react-dom', () => {
  const actual = jest.requireActual('react-dom');
  return {
    ...actual,
    createPortal: jest.fn((element) => element),
  };
});

const mockUseAuth = useAuth as jest.Mock;
const mockUseRouter = useRouter as jest.Mock;
const mockUsePathname = usePathname as jest.Mock;
const mockUseInstructorProfileMe = useInstructorProfileMe as jest.Mock;
const mockCreatePortal = createPortal as jest.Mock;

describe('UserProfileDropdown', () => {
  const mockPush = jest.fn();
  const mockLogout = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    mockCreatePortal.mockImplementation((element) => element);
    mockUseRouter.mockReturnValue({ push: mockPush });
    mockUsePathname.mockReturnValue('/');
    mockUseInstructorProfileMe.mockReturnValue({ data: null });
  });

  describe('Loading state', () => {
    it('shows loading skeleton when auth is loading', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        logout: mockLogout,
        isLoading: true,
      });

      const { container } = render(<UserProfileDropdown />);

      // Should show animate-pulse skeleton
      const skeleton = container.querySelector('.animate-pulse');
      expect(skeleton).toBeInTheDocument();
      expect(container.querySelector('.bg-gray-200.rounded-full')).toBeInTheDocument();
    });
  });

  describe('Guest user', () => {
    it('shows Sign In button when no user is logged in', () => {
      mockUseAuth.mockReturnValue({
        user: null,
        logout: mockLogout,
        isLoading: false,
      });

      render(<UserProfileDropdown />);

      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
    });

    it('navigates to login page when Sign In is clicked', async () => {
      const user = userEvent.setup();
      mockUseAuth.mockReturnValue({
        user: null,
        logout: mockLogout,
        isLoading: false,
      });

      render(<UserProfileDropdown />);

      await user.click(screen.getByRole('button', { name: /sign in/i }));
      expect(mockPush).toHaveBeenCalledWith('/login');
    });
  });

  describe('Student user', () => {
    const studentUser = {
      id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
      first_name: 'John',
      last_name: 'Doe',
      roles: [RoleName.STUDENT],
      has_profile_picture: false,
    };

    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: studentUser,
        logout: mockLogout,
        isLoading: false,
      });
    });

    it('renders user avatar button', () => {
      render(<UserProfileDropdown />);

      const button = screen.getByRole('button', { name: /open user menu/i });
      expect(button).toBeInTheDocument();
    });

    it('opens dropdown when avatar is clicked', async () => {
      const user = userEvent.setup();
      render(<UserProfileDropdown />);

      await user.click(screen.getByRole('button', { name: /open user menu/i }));

      expect(screen.getByText('My Account')).toBeInTheDocument();
      expect(screen.getByText('Rewards')).toBeInTheDocument();
      expect(screen.getByText('My Lessons')).toBeInTheDocument();
      expect(screen.getByText('Sign Out')).toBeInTheDocument();
    });

    it('closes dropdown when clicking again', async () => {
      const user = userEvent.setup();
      render(<UserProfileDropdown />);

      await user.click(screen.getByRole('button', { name: /open user menu/i }));
      expect(screen.getByText('My Account')).toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: /close user menu/i }));
      expect(screen.queryByText('My Account')).not.toBeInTheDocument();
    });

    it('navigates to student dashboard when My Account is clicked', async () => {
      const user = userEvent.setup();
      render(<UserProfileDropdown />);

      await user.click(screen.getByRole('button', { name: /open user menu/i }));
      await user.click(screen.getByText('My Account'));

      expect(mockPush).toHaveBeenCalledWith('/student/dashboard');
    });

    it('navigates to rewards tab when Rewards is clicked', async () => {
      const user = userEvent.setup();
      render(<UserProfileDropdown />);

      await user.click(screen.getByRole('button', { name: /open user menu/i }));
      await user.click(screen.getByText('Rewards'));

      expect(mockPush).toHaveBeenCalledWith('/student/dashboard?tab=rewards');
    });

    it('navigates to lessons page when My Lessons is clicked', async () => {
      const user = userEvent.setup();
      render(<UserProfileDropdown />);

      await user.click(screen.getByRole('button', { name: /open user menu/i }));
      await user.click(screen.getByText('My Lessons'));

      expect(mockPush).toHaveBeenCalledWith('/student/lessons');
    });

    it('calls logout when Sign Out is clicked', async () => {
      const user = userEvent.setup();
      render(<UserProfileDropdown />);

      await user.click(screen.getByRole('button', { name: /open user menu/i }));
      await user.click(screen.getByText('Sign Out'));

      expect(mockLogout).toHaveBeenCalled();
    });
  });

  describe('Instructor user - onboarding incomplete', () => {
    const instructorUser = {
      id: '01K2GY3VEVJWKZDVH5HMNXEVR2',
      first_name: 'Jane',
      last_name: 'Smith',
      roles: [RoleName.INSTRUCTOR],
      has_profile_picture: false,
    };

    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: instructorUser,
        logout: mockLogout,
        isLoading: false,
      });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [],
          stripe_connect_enabled: false,
          identity_verified_at: null,
        },
      });
    });

    it('shows Finish Onboarding option when onboarding incomplete', async () => {
      const user = userEvent.setup();
      render(<UserProfileDropdown />);

      await user.click(screen.getByRole('button', { name: /open user menu/i }));

      expect(screen.getByText('Finish Onboarding')).toBeInTheDocument();
    });

    it('navigates to onboarding when Finish Onboarding is clicked', async () => {
      const user = userEvent.setup();
      render(<UserProfileDropdown />);

      await user.click(screen.getByRole('button', { name: /open user menu/i }));
      await user.click(screen.getByText('Finish Onboarding'));

      expect(mockPush).toHaveBeenCalledWith('/instructor/onboarding/skill-selection');
    });
  });

  describe('Instructor user - onboarding complete', () => {
    const instructorUser = {
      id: '01K2GY3VEVJWKZDVH5HMNXEVR3',
      first_name: 'Alice',
      last_name: 'Johnson',
      roles: [RoleName.INSTRUCTOR],
      has_profile_picture: true,
    };

    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: instructorUser,
        logout: mockLogout,
        isLoading: false,
      });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: true,
          services: [{ id: 'svc-1', name: 'Piano' }],
          stripe_connect_enabled: true,
          identity_verified_at: '2024-01-01T00:00:00Z',
        },
      });
    });

    it('shows Dashboard option when onboarding complete', async () => {
      const user = userEvent.setup();
      render(<UserProfileDropdown />);

      await user.click(screen.getByRole('button', { name: /open user menu/i }));

      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });

    it('navigates to instructor dashboard when Dashboard is clicked', async () => {
      const user = userEvent.setup();
      render(<UserProfileDropdown />);

      await user.click(screen.getByRole('button', { name: /open user menu/i }));
      await user.click(screen.getByText('Dashboard'));

      expect(mockPush).toHaveBeenCalledWith('/instructor/dashboard');
    });

    it('hides Dashboard when hideDashboardItem prop is true', async () => {
      const user = userEvent.setup();
      render(<UserProfileDropdown hideDashboardItem />);

      await user.click(screen.getByRole('button', { name: /open user menu/i }));

      expect(screen.queryByText('Dashboard')).not.toBeInTheDocument();
      expect(screen.getByText('Sign Out')).toBeInTheDocument();
    });
  });

  describe('Instructor with partial onboarding', () => {
    const instructorUser = {
      id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
      first_name: 'Bob',
      last_name: 'Wilson',
      roles: [RoleName.INSTRUCTOR],
      has_profile_picture: false,
    };

    it('shows Dashboard when is_live is true regardless of other flags', async () => {
      const user = userEvent.setup();
      mockUseAuth.mockReturnValue({
        user: instructorUser,
        logout: mockLogout,
        isLoading: false,
      });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: true,
          services: [],
          stripe_connect_enabled: false,
        },
      });

      render(<UserProfileDropdown />);
      await user.click(screen.getByRole('button', { name: /open user menu/i }));

      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });

    it('shows Dashboard when stripe + identity + services complete but not live', async () => {
      const user = userEvent.setup();
      mockUseAuth.mockReturnValue({
        user: instructorUser,
        logout: mockLogout,
        isLoading: false,
      });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{ id: 'svc-1' }],
          stripe_connect_enabled: true,
          identity_verified_at: '2024-01-01T00:00:00Z',
        },
      });

      render(<UserProfileDropdown />);
      await user.click(screen.getByRole('button', { name: /open user menu/i }));

      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });

    it('checks identity_verification_session_id as fallback for identity verification', async () => {
      const user = userEvent.setup();
      mockUseAuth.mockReturnValue({
        user: instructorUser,
        logout: mockLogout,
        isLoading: false,
      });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: [{ id: 'svc-1' }],
          stripe_connect_enabled: true,
          identity_verified_at: null,
          identity_verification_session_id: 'vs_session123',
        },
      });

      render(<UserProfileDropdown />);
      await user.click(screen.getByRole('button', { name: /open user menu/i }));

      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });
  });

  describe('Click outside handling', () => {
    it('closes dropdown when clicking outside', async () => {
      const user = userEvent.setup();
      mockUseAuth.mockReturnValue({
        user: {
          id: '01K2GY3VEVJWKZDVH5HMNXEVR5',
          first_name: 'Test',
          last_name: 'User',
          roles: [RoleName.STUDENT],
        },
        logout: mockLogout,
        isLoading: false,
      });

      render(
        <div>
          <UserProfileDropdown />
          <div data-testid="outside">Outside area</div>
        </div>
      );

      // Open dropdown
      await user.click(screen.getByRole('button', { name: /open user menu/i }));
      expect(screen.getByText('My Account')).toBeInTheDocument();

      // Click outside
      fireEvent.mouseDown(screen.getByTestId('outside'));

      await waitFor(() => {
        expect(screen.queryByText('My Account')).not.toBeInTheDocument();
      });
    });
  });

  describe('Onboarding page behavior', () => {
    it('skips instructor profile fetch on onboarding pages', () => {
      mockUsePathname.mockReturnValue('/instructor/onboarding/skill-selection');
      mockUseAuth.mockReturnValue({
        user: {
          id: '01K2GY3VEVJWKZDVH5HMNXEVR6',
          first_name: 'New',
          last_name: 'Instructor',
          roles: [RoleName.INSTRUCTOR],
        },
        logout: mockLogout,
        isLoading: false,
      });

      render(<UserProfileDropdown />);

      // The hook should be called with false to disable fetching on onboarding pages
      expect(mockUseInstructorProfileMe).toHaveBeenCalledWith(false);
    });
  });

  describe('Accessibility', () => {
    it('has correct aria attributes on dropdown button', async () => {
      const user = userEvent.setup();
      mockUseAuth.mockReturnValue({
        user: {
          id: '01K2GY3VEVJWKZDVH5HMNXEVR7',
          first_name: 'Test',
          last_name: 'User',
          roles: [RoleName.STUDENT],
        },
        logout: mockLogout,
        isLoading: false,
      });

      render(<UserProfileDropdown />);

      const button = screen.getByRole('button', { name: /open user menu/i });
      expect(button).toHaveAttribute('aria-haspopup', 'menu');
      expect(button).toHaveAttribute('aria-expanded', 'false');

      await user.click(button);

      expect(button).toHaveAttribute('aria-expanded', 'true');
    });
  });

  describe('Dropdown positioning', () => {
    it('updates dropdown position when opened', async () => {
      const user = userEvent.setup();
      mockUseAuth.mockReturnValue({
        user: {
          id: '01K2GY3VEVJWKZDVH5HMNXEVR8',
          first_name: 'Test',
          last_name: 'User',
          roles: [RoleName.STUDENT],
        },
        logout: mockLogout,
        isLoading: false,
      });

      // Mock getBoundingClientRect
      const originalGetBoundingClientRect = Element.prototype.getBoundingClientRect;
      Element.prototype.getBoundingClientRect = jest.fn(() => ({
        top: 100,
        left: 900,
        right: 950,
        bottom: 150,
        width: 50,
        height: 50,
        x: 900,
        y: 100,
        toJSON: jest.fn(),
      }));

      render(<UserProfileDropdown />);

      await user.click(screen.getByRole('button', { name: /open user menu/i }));

      // Dropdown should be rendered
      expect(screen.getByText('My Account')).toBeInTheDocument();

      // Restore original
      Element.prototype.getBoundingClientRect = originalGetBoundingClientRect;
    });
  });

  describe('Edge cases', () => {
    it('handles user with empty roles array', () => {
      mockUseAuth.mockReturnValue({
        user: {
          id: '01K2GY3VEVJWKZDVH5HMNXEVR9',
          first_name: 'Test',
          last_name: 'User',
          roles: [],
        },
        logout: mockLogout,
        isLoading: false,
      });

      render(<UserProfileDropdown />);

      // Should render without crashing
      expect(screen.getByRole('button', { name: /open user menu/i })).toBeInTheDocument();
    });

    it('handles user with undefined roles', async () => {
      const user = userEvent.setup();
      mockUseAuth.mockReturnValue({
        user: {
          id: '01K2GY3VEVJWKZDVH5HMNXEVRZ',
          first_name: 'Test',
          last_name: 'User',
          roles: undefined,
        },
        logout: mockLogout,
        isLoading: false,
      });

      render(<UserProfileDropdown />);

      // Should render student menu by default
      await user.click(screen.getByRole('button', { name: /open user menu/i }));
      expect(screen.getByText('My Account')).toBeInTheDocument();
    });

    it('handles instructor profile without services array', async () => {
      const user = userEvent.setup();
      mockUseAuth.mockReturnValue({
        user: {
          id: '01K2GY3VEVJWKZDVH5HMNXEVRX',
          first_name: 'Test',
          last_name: 'Instructor',
          roles: [RoleName.INSTRUCTOR],
        },
        logout: mockLogout,
        isLoading: false,
      });
      mockUseInstructorProfileMe.mockReturnValue({
        data: {
          is_live: false,
          services: undefined, // undefined services
          stripe_connect_enabled: true,
        },
      });

      render(<UserProfileDropdown />);

      await user.click(screen.getByRole('button', { name: /open user menu/i }));
      expect(screen.getByText('Finish Onboarding')).toBeInTheDocument();
    });
  });
});
