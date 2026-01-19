import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BookAgain } from '../BookAgain';

const pushMock = jest.fn();

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(() => ({ isAuthenticated: true })),
}));

jest.mock('@/lib/react-query/queryClient', () => ({
  queryKeys: {
    bookings: {
      history: () => ['bookings', 'history'],
    },
  },
  CACHE_TIMES: {
    SLOW: 15 * 60 * 1000,
  },
}));

jest.mock('@/lib/react-query/api', () => ({
  queryFn: jest.fn(() => () => Promise.resolve({ items: [], total: 0 })),
}));

import { useAuth } from '@/features/shared/hooks/useAuth';
import { queryFn } from '@/lib/react-query/api';

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;
const mockQueryFn = queryFn as jest.MockedFunction<typeof queryFn>;

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

const createMockBookingsResponse = (items: Array<{
  id: string;
  instructor?: {
    id: string;
    first_name: string;
    last_initial: string;
  };
  service_name: string;
  instructor_service_id: string;
  hourly_rate: number;
  booking_date: string;
}>) => ({
  items,
  total: items.length,
  page: 1,
  per_page: 50,
  pages: 1,
});

describe('BookAgain', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    pushMock.mockClear();
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      user: null,
      redirectToLogin: jest.fn(),
    } as unknown as ReturnType<typeof useAuth>);
  });

  describe('When not authenticated', () => {
    it('returns null', () => {
      mockUseAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        redirectToLogin: jest.fn(),
      } as unknown as ReturnType<typeof useAuth>);

      const { container } = render(<BookAgain />, { wrapper: createWrapper() });
      expect(container).toBeEmptyDOMElement();
    });
  });

  describe('When loading', () => {
    it('returns null while loading', () => {
      // Query never resolves = loading state
      mockQueryFn.mockReturnValue(() => new Promise(() => {}));

      const { container } = render(<BookAgain />, { wrapper: createWrapper() });
      expect(container).toBeEmptyDOMElement();
    });
  });

  describe('When no booking history', () => {
    it('returns null when no bookings', async () => {
      mockQueryFn.mockReturnValue(() =>
        Promise.resolve(createMockBookingsResponse([]))
      );

      const { container } = render(<BookAgain />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(container).toBeEmptyDOMElement();
      });
    });

    it('calls onLoadComplete with false when no history', async () => {
      const onLoadComplete = jest.fn();
      mockQueryFn.mockReturnValue(() =>
        Promise.resolve(createMockBookingsResponse([]))
      );

      render(<BookAgain onLoadComplete={onLoadComplete} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(onLoadComplete).toHaveBeenCalledWith(false);
      });
    });
  });

  describe('When has booking history', () => {
    const mockBookings = [
      {
        id: '01K2GY3VEVJWKZDVH5BOOKING1',
        instructor: {
          id: '01K2GY3VEVJWKZDVH5INSTRUC1',
          first_name: 'Sarah',
          last_initial: 'C',
        },
        service_name: 'Piano Lesson',
        instructor_service_id: '01K2GY3VEVJWKZDVH5SERVICE1',
        hourly_rate: 60,
        booking_date: '2024-01-15',
      },
      {
        id: '01K2GY3VEVJWKZDVH5BOOKING2',
        instructor: {
          id: '01K2GY3VEVJWKZDVH5INSTRUC2',
          first_name: 'Mike',
          last_initial: 'B',
        },
        service_name: 'Guitar Lesson',
        instructor_service_id: '01K2GY3VEVJWKZDVH5SERVICE2',
        hourly_rate: 55,
        booking_date: '2024-01-10',
      },
    ];

    beforeEach(() => {
      mockQueryFn.mockReturnValue(() =>
        Promise.resolve(createMockBookingsResponse(mockBookings))
      );
    });

    it('renders Book Again heading', async () => {
      render(<BookAgain />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Book Again' })).toBeInTheDocument();
      });
    });

    it('renders instructor cards', async () => {
      render(<BookAgain />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Piano Lesson')).toBeInTheDocument();
        expect(screen.getByText('Guitar Lesson')).toBeInTheDocument();
      });
    });

    it('renders instructor names with format', async () => {
      render(<BookAgain />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('with Sarah C.')).toBeInTheDocument();
        expect(screen.getByText('with Mike B.')).toBeInTheDocument();
      });
    });

    it('renders hourly rates', async () => {
      render(<BookAgain />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('$60/hour')).toBeInTheDocument();
        expect(screen.getByText('$55/hour')).toBeInTheDocument();
      });
    });

    it('renders rating stars', async () => {
      render(<BookAgain />, { wrapper: createWrapper() });

      await waitFor(() => {
        const ratings = screen.getAllByText('4.8');
        expect(ratings.length).toBe(2);
      });
    });

    it('renders Book Again buttons for each instructor', async () => {
      render(<BookAgain />, { wrapper: createWrapper() });

      await waitFor(() => {
        const buttons = screen.getAllByRole('button', { name: 'Book Again' });
        expect(buttons).toHaveLength(2);
      });
    });

    it('calls onLoadComplete with true when has history', async () => {
      const onLoadComplete = jest.fn();

      render(<BookAgain onLoadComplete={onLoadComplete} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(onLoadComplete).toHaveBeenCalledWith(true);
      });
    });

    it('limits to 3 unique instructors', async () => {
      const manyBookings = [
        ...mockBookings,
        {
          id: '01K2GY3VEVJWKZDVH5BOOKING3',
          instructor: {
            id: '01K2GY3VEVJWKZDVH5INSTRUC3',
            first_name: 'Alice',
            last_initial: 'D',
          },
          service_name: 'Violin Lesson',
          instructor_service_id: '01K2GY3VEVJWKZDVH5SERVICE3',
          hourly_rate: 70,
          booking_date: '2024-01-05',
        },
        {
          id: '01K2GY3VEVJWKZDVH5BOOKING4',
          instructor: {
            id: '01K2GY3VEVJWKZDVH5INSTRUC4',
            first_name: 'Bob',
            last_initial: 'E',
          },
          service_name: 'Drums Lesson',
          instructor_service_id: '01K2GY3VEVJWKZDVH5SERVICE4',
          hourly_rate: 65,
          booking_date: '2024-01-01',
        },
      ];

      mockQueryFn.mockReturnValue(() =>
        Promise.resolve(createMockBookingsResponse(manyBookings))
      );

      render(<BookAgain />, { wrapper: createWrapper() });

      await waitFor(() => {
        const buttons = screen.getAllByRole('button', { name: 'Book Again' });
        expect(buttons).toHaveLength(3);
      });
    });

    it('deduplicates same instructor from multiple bookings', async () => {
      const duplicateInstructorBookings = [
        ...mockBookings,
        {
          id: '01K2GY3VEVJWKZDVH5BOOKING3',
          instructor: {
            id: '01K2GY3VEVJWKZDVH5INSTRUC1', // Same as first instructor
            first_name: 'Sarah',
            last_initial: 'C',
          },
          service_name: 'Piano Lesson', // Same service
          instructor_service_id: '01K2GY3VEVJWKZDVH5SERVICE1',
          hourly_rate: 60,
          booking_date: '2024-01-01',
        },
      ];

      mockQueryFn.mockReturnValue(() =>
        Promise.resolve(createMockBookingsResponse(duplicateInstructorBookings))
      );

      render(<BookAgain />, { wrapper: createWrapper() });

      await waitFor(() => {
        // Should only show 2 unique instructors
        const buttons = screen.getAllByRole('button', { name: 'Book Again' });
        expect(buttons).toHaveLength(2);
      });
    });
  });

  describe('Navigation', () => {
    const mockBookings = [
      {
        id: '01K2GY3VEVJWKZDVH5BOOKING1',
        instructor: {
          id: '01K2GY3VEVJWKZDVH5INSTRUC1',
          first_name: 'Sarah',
          last_initial: 'C',
        },
        service_name: 'Piano Lesson',
        instructor_service_id: '01K2GY3VEVJWKZDVH5SERVICE1',
        hourly_rate: 60,
        booking_date: '2024-01-15',
      },
    ];

    beforeEach(() => {
      mockQueryFn.mockReturnValue(() =>
        Promise.resolve(createMockBookingsResponse(mockBookings))
      );
    });

    it('navigates to instructor profile when button is clicked', async () => {
      render(<BookAgain />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Piano Lesson')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: 'Book Again' }));

      expect(pushMock).toHaveBeenCalledWith(
        '/instructors/01K2GY3VEVJWKZDVH5INSTRUC1?openCalendar=true&serviceId=01K2GY3VEVJWKZDVH5SERVICE1'
      );
    });

    it('navigates when card container is clicked', async () => {
      render(<BookAgain />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Piano Lesson')).toBeInTheDocument();
      });

      // Click on the card container (service name text)
      fireEvent.click(screen.getByText('Piano Lesson'));

      expect(pushMock).toHaveBeenCalledWith(
        '/instructors/01K2GY3VEVJWKZDVH5INSTRUC1?openCalendar=true&serviceId=01K2GY3VEVJWKZDVH5SERVICE1'
      );
    });

    it('stops propagation when button is clicked to prevent double navigation', async () => {
      render(<BookAgain />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Piano Lesson')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: 'Book Again' }));

      // Should only navigate once
      expect(pushMock).toHaveBeenCalledTimes(1);
    });
  });

  describe('Mobile scroll indicators', () => {
    const mockBookings = [
      {
        id: '01K2GY3VEVJWKZDVH5BOOKING1',
        instructor: {
          id: '01K2GY3VEVJWKZDVH5INSTRUC1',
          first_name: 'Sarah',
          last_initial: 'C',
        },
        service_name: 'Piano Lesson',
        instructor_service_id: '01K2GY3VEVJWKZDVH5SERVICE1',
        hourly_rate: 60,
        booking_date: '2024-01-15',
      },
      {
        id: '01K2GY3VEVJWKZDVH5BOOKING2',
        instructor: {
          id: '01K2GY3VEVJWKZDVH5INSTRUC2',
          first_name: 'Mike',
          last_initial: 'B',
        },
        service_name: 'Guitar Lesson',
        instructor_service_id: '01K2GY3VEVJWKZDVH5SERVICE2',
        hourly_rate: 55,
        booking_date: '2024-01-10',
      },
    ];

    beforeEach(() => {
      mockQueryFn.mockReturnValue(() =>
        Promise.resolve(createMockBookingsResponse(mockBookings))
      );
    });

    it('renders scroll indicator dots for each instructor', async () => {
      const { container } = render(<BookAgain />, { wrapper: createWrapper() });

      await waitFor(() => {
        const dots = container.querySelectorAll('.rounded-full.bg-gray-300');
        expect(dots).toHaveLength(2);
      });
    });
  });

  describe('Bookings without instructor', () => {
    it('handles bookings without instructor data', async () => {
      const bookingsWithoutInstructor = [
        {
          id: '01K2GY3VEVJWKZDVH5BOOKING1',
          instructor: undefined,
          service_name: 'Piano Lesson',
          instructor_service_id: '01K2GY3VEVJWKZDVH5SERVICE1',
          hourly_rate: 60,
          booking_date: '2024-01-15',
        },
        {
          id: '01K2GY3VEVJWKZDVH5BOOKING2',
          instructor: {
            id: '01K2GY3VEVJWKZDVH5INSTRUC2',
            first_name: 'Mike',
            last_initial: 'B',
          },
          service_name: 'Guitar Lesson',
          instructor_service_id: '01K2GY3VEVJWKZDVH5SERVICE2',
          hourly_rate: 55,
          booking_date: '2024-01-10',
        },
      ];

      mockQueryFn.mockReturnValue(() =>
        Promise.resolve(createMockBookingsResponse(bookingsWithoutInstructor))
      );

      render(<BookAgain />, { wrapper: createWrapper() });

      await waitFor(() => {
        // Should only show the booking with instructor
        expect(screen.getByText('Guitar Lesson')).toBeInTheDocument();
        expect(screen.queryByText('Piano Lesson')).not.toBeInTheDocument();
      });
    });
  });
});
