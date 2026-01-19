import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { UpcomingLessons } from '../UpcomingLessons';

jest.mock('next/link', () => {
  const MockLink = ({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>;
  MockLink.displayName = 'MockLink';
  return MockLink;
});

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(() => ({
    isAuthenticated: true,
    user: { roles: [{ name: 'student' }] },
    isLoading: false,
  })),
}));

jest.mock('@/features/shared/hooks/useAuth.helpers', () => ({
  hasRole: jest.fn((_user, role) => role === 'student'),
}));

jest.mock('@/src/api/services/bookings', () => ({
  useUpcomingBookings: jest.fn(() => ({
    data: null,
    isLoading: false,
    error: null,
  })),
}));

jest.mock('@/lib/timezone/formatBookingTime', () => ({
  formatBookingDate: jest.fn(() => 'Monday, January 15'),
  formatBookingTime: jest.fn(() => '10:00 AM'),
}));

import { useAuth } from '@/features/shared/hooks/useAuth';
import { hasRole } from '@/features/shared/hooks/useAuth.helpers';
import { useUpcomingBookings } from '@/src/api/services/bookings';

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;
const mockHasRole = hasRole as jest.MockedFunction<typeof hasRole>;
const mockUseUpcomingBookings = useUpcomingBookings as jest.MockedFunction<
  typeof useUpcomingBookings
>;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'QueryClientWrapper';
  return Wrapper;
};

const createMockBooking = (overrides = {}) => ({
  id: '01K2GY3VEVJWKZDVH5HMNXEVRD',
  booking_date: '2024-01-15',
  booking_start_utc: '2024-01-15T15:00:00Z',
  service_name: 'Piano Lesson',
  instructor_first_name: 'Sarah',
  instructor_last_name: 'C',
  student_first_name: 'John',
  student_last_name: 'D',
  meeting_location: '123 Upper West Side Ave, New York',
  ...overrides,
});

describe('UpcomingLessons', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      user: { roles: ['student'] },
      isLoading: false,
      redirectToLogin: jest.fn(),
    } as unknown as ReturnType<typeof useAuth>);
    mockHasRole.mockImplementation((_user, role) => role === 'student');
    mockUseUpcomingBookings.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useUpcomingBookings>);
  });

  describe('Authentication states', () => {
    it('returns null when auth is loading', () => {
      mockUseAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: true,
        redirectToLogin: jest.fn(),
      } as unknown as ReturnType<typeof useAuth>);

      const { container } = render(<UpcomingLessons />, {
        wrapper: createWrapper(),
      });
      expect(container).toBeEmptyDOMElement();
    });

    it('returns null when not authenticated', () => {
      mockUseAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: false,
        redirectToLogin: jest.fn(),
      } as unknown as ReturnType<typeof useAuth>);

      const { container } = render(<UpcomingLessons />, {
        wrapper: createWrapper(),
      });
      expect(container).toBeEmptyDOMElement();
    });
  });

  describe('Loading state', () => {
    it('shows loading skeleton when loading', async () => {
      mockUseUpcomingBookings.mockReturnValue({
        data: null,
        isLoading: true,
        error: null,
      } as unknown as ReturnType<typeof useUpcomingBookings>);

      render(<UpcomingLessons />, { wrapper: createWrapper() });

      // Wait for client-side hydration
      await waitFor(() => {
        expect(screen.getByText('📅 Your Upcoming Lessons')).toBeInTheDocument();
      });

      // Should show loading skeletons
      const skeletons = document.querySelectorAll('.animate-pulse');
      expect(skeletons.length).toBeGreaterThan(0);
    });
  });

  describe('Empty state', () => {
    it('returns null when no bookings', async () => {
      mockUseUpcomingBookings.mockReturnValue({
        data: { items: [], total: 0 },
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useUpcomingBookings>);

      const { container } = render(<UpcomingLessons />, {
        wrapper: createWrapper(),
      });

      // Wait for any async updates
      await waitFor(() => {
        expect(container).toBeEmptyDOMElement();
      });
    });
  });

  describe('Error state', () => {
    it('returns null on error', async () => {
      mockUseUpcomingBookings.mockReturnValue({
        data: null,
        isLoading: false,
        error: new Error('Network error'),
      } as unknown as ReturnType<typeof useUpcomingBookings>);

      const { container } = render(<UpcomingLessons />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(container).toBeEmptyDOMElement();
      });
    });
  });

  describe('With bookings', () => {
    beforeEach(() => {
      mockUseUpcomingBookings.mockReturnValue({
        data: {
          items: [createMockBooking(), createMockBooking({ id: '02' })],
          total: 2,
        },
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useUpcomingBookings>);
    });

    it('renders heading', async () => {
      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Your Upcoming Lessons')).toBeInTheDocument();
      });
    });

    it('renders booking service name', async () => {
      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getAllByText('Piano Lesson')).toHaveLength(2);
      });
    });

    it('renders instructor name for student user', async () => {
      mockHasRole.mockImplementation((_user, role) => role === 'student');

      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getAllByText('with Sarah C.')).toHaveLength(2);
      });
    });

    it('renders student name for instructor user', async () => {
      mockHasRole.mockImplementation((_user, role) => role === 'instructor');

      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getAllByText('with John D.')).toHaveLength(2);
      });
    });

    it('renders location area when available', async () => {
      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getAllByText('Upper West')).toHaveLength(2);
      });
    });

    it('renders see details link for student', async () => {
      mockHasRole.mockImplementation((_user, role) => role === 'student');

      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        const links = screen.getAllByText('See lesson details');
        expect(links).toHaveLength(2);
        const firstLink = links[0];
        expect(firstLink).toBeDefined();
        expect(firstLink?.closest('a')).toHaveAttribute(
          'href',
          '/student/lessons/01K2GY3VEVJWKZDVH5HMNXEVRD'
        );
      });
    });

    it('renders see details link for instructor', async () => {
      mockHasRole.mockImplementation((_user, role) => role === 'instructor');

      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        const links = screen.getAllByText('See lesson details');
        expect(links).toHaveLength(2);
        const firstLink = links[0];
        expect(firstLink).toBeDefined();
        expect(firstLink?.closest('a')).toHaveAttribute(
          'href',
          '/instructor/bookings/01K2GY3VEVJWKZDVH5HMNXEVRD'
        );
      });
    });

    it('shows only first 2 bookings in display', async () => {
      mockUseUpcomingBookings.mockReturnValue({
        data: {
          items: [
            createMockBooking({ id: '01' }),
            createMockBooking({ id: '02' }),
            createMockBooking({ id: '03' }),
          ],
          total: 3,
        },
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useUpcomingBookings>);

      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getAllByText('Piano Lesson')).toHaveLength(2);
      });
    });

    it('shows view all link when more than 2 bookings', async () => {
      mockUseUpcomingBookings.mockReturnValue({
        data: {
          items: [
            createMockBooking({ id: '01' }),
            createMockBooking({ id: '02' }),
            createMockBooking({ id: '03' }),
          ],
          total: 3,
        },
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useUpcomingBookings>);

      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/View all 3 upcoming lessons/)).toBeInTheDocument();
      });
    });
  });

  describe('Location area extraction', () => {
    it('extracts Upper West from location', async () => {
      mockUseUpcomingBookings.mockReturnValue({
        data: {
          items: [createMockBooking({ meeting_location: '123 Upper West Side Ave' })],
          total: 1,
        },
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useUpcomingBookings>);

      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Upper West')).toBeInTheDocument();
      });
    });

    it('extracts Midtown from location', async () => {
      mockUseUpcomingBookings.mockReturnValue({
        data: {
          items: [createMockBooking({ meeting_location: '456 Midtown Manhattan' })],
          total: 1,
        },
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useUpcomingBookings>);

      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Midtown')).toBeInTheDocument();
      });
    });

    it('extracts Brooklyn from location', async () => {
      mockUseUpcomingBookings.mockReturnValue({
        data: {
          items: [createMockBooking({ meeting_location: '789 Brooklyn Heights' })],
          total: 1,
        },
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useUpcomingBookings>);

      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Brooklyn')).toBeInTheDocument();
      });
    });

    it('does not show location when no area match', async () => {
      mockUseUpcomingBookings.mockReturnValue({
        data: {
          items: [createMockBooking({ meeting_location: '123 Random Street' })],
          total: 1,
        },
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useUpcomingBookings>);

      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.queryByText('Upper West')).not.toBeInTheDocument();
        expect(screen.queryByText('Midtown')).not.toBeInTheDocument();
      });
    });

    it('does not show location when meeting_location is null', async () => {
      mockUseUpcomingBookings.mockReturnValue({
        data: {
          items: [createMockBooking({ meeting_location: null })],
          total: 1,
        },
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useUpcomingBookings>);

      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.queryByText('Upper West')).not.toBeInTheDocument();
      });
    });
  });

  describe('Name formatting', () => {
    it('shows fallback when instructor name not available', async () => {
      mockHasRole.mockImplementation((_user, role) => role === 'student');
      mockUseUpcomingBookings.mockReturnValue({
        data: {
          items: [createMockBooking({ instructor_first_name: null })],
          total: 1,
        },
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useUpcomingBookings>);

      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/with Instructor/)).toBeInTheDocument();
      });
    });

    it('shows fallback when student name not available', async () => {
      mockHasRole.mockImplementation((_user, role) => role === 'instructor');
      mockUseUpcomingBookings.mockReturnValue({
        data: {
          items: [createMockBooking({ student_first_name: null })],
          total: 1,
        },
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useUpcomingBookings>);

      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/with Student/)).toBeInTheDocument();
      });
    });
  });

  describe('Date label formatting', () => {
    it('shows "Today" for bookings today', async () => {
      const now = new Date();
      const todayBooking = createMockBooking({
        booking_start_utc: now.toISOString(),
        booking_date: now.toISOString().split('T')[0],
      });

      mockUseUpcomingBookings.mockReturnValue({
        data: {
          items: [todayBooking],
          total: 1,
        },
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useUpcomingBookings>);

      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/Today/)).toBeInTheDocument();
      });
    });

    it('shows "Tomorrow" for bookings tomorrow', async () => {
      const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000);
      const tomorrowBooking = createMockBooking({
        booking_start_utc: tomorrow.toISOString(),
        booking_date: tomorrow.toISOString().split('T')[0],
      });

      mockUseUpcomingBookings.mockReturnValue({
        data: {
          items: [tomorrowBooking],
          total: 1,
        },
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useUpcomingBookings>);

      render(<UpcomingLessons />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText(/Tomorrow/)).toBeInTheDocument();
      });
    });
  });
});
