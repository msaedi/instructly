import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import BookingDetailsPage from '../page';
import { useBooking, useCompleteBooking, useMarkBookingNoShow } from '@/src/api/services/bookings';

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useParams: () => ({ id: '01ABC123456789DEFGHIJKLMN' }),
}));

// Mock react-query client
const mockInvalidateQueries = jest.fn();
jest.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({
    invalidateQueries: mockInvalidateQueries,
  }),
}));

// Mock sonner toast
const mockToastSuccess = jest.fn();
const mockToastError = jest.fn();
jest.mock('sonner', () => ({
  toast: {
    success: (msg: string, opts?: object) => mockToastSuccess(msg, opts),
    error: (msg: string, opts?: object) => mockToastError(msg, opts),
  },
}));

// Mock booking service hooks
jest.mock('@/src/api/services/bookings');

const mockUseBooking = useBooking as jest.MockedFunction<typeof useBooking>;
const mockUseCompleteBooking = useCompleteBooking as jest.MockedFunction<typeof useCompleteBooking>;
const mockUseMarkBookingNoShow = useMarkBookingNoShow as jest.MockedFunction<typeof useMarkBookingNoShow>;

// Helper to create a mock booking
const createMockBooking = (overrides = {}) => ({
  id: '01ABC123456789DEFGHIJKLMN',
  status: 'CONFIRMED',
  booking_date: '2025-01-01',
  start_time: '10:00:00',
  end_time: '11:00:00',
  service_name: 'Piano Lesson',
  duration_minutes: 60,
  hourly_rate: 50,
  total_price: 56,
  location_type: 'student_location',
  meeting_location: '123 Main St',
  service_area: 'Manhattan',
  student_id: '01STUDENT123456789DEFGHI',
  student: {
    first_name: 'John',
    last_name: 'Doe',
    email: 'john@example.com',
  },
  student_note: null,
  instructor_note: null,
  cancellation_reason: null,
  cancelled_at: null,
  created_at: '2025-01-01T08:00:00Z',
  ...overrides,
});

describe('Instructor Booking Details Page', () => {
  const mockMutateAsync = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();

    // Default mutation mock
    const defaultMutationMock = {
      mutateAsync: mockMutateAsync.mockResolvedValue({}),
      isPending: false,
    };

    mockUseCompleteBooking.mockReturnValue(defaultMutationMock as unknown as ReturnType<typeof useCompleteBooking>);
    mockUseMarkBookingNoShow.mockReturnValue(defaultMutationMock as unknown as ReturnType<typeof useMarkBookingNoShow>);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('loading state', () => {
    it('shows loading spinner when loading', () => {
      mockUseBooking.mockReturnValue({
        data: undefined,
        isLoading: true,
        error: null,
      } as unknown as ReturnType<typeof useBooking>);

      const { container } = render(<BookingDetailsPage />);
      // Look for the spinner by class
      expect(container.querySelector('.animate-spin')).toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('shows error message when booking fails to load', () => {
      mockUseBooking.mockReturnValue({
        data: undefined,
        isLoading: false,
        error: new Error('Failed'),
      } as unknown as ReturnType<typeof useBooking>);

      render(<BookingDetailsPage />);
      expect(screen.getByText('Failed to load booking details')).toBeInTheDocument();
    });
  });

  describe('booking details display', () => {
    it('renders booking details correctly', () => {
      const booking = createMockBooking();
      mockUseBooking.mockReturnValue({
        data: booking,
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useBooking>);

      render(<BookingDetailsPage />);

      expect(screen.getByText('Piano Lesson')).toBeInTheDocument();
      expect(screen.getByText('John Doe')).toBeInTheDocument();
      expect(screen.getByText('CONFIRMED')).toBeInTheDocument();
      expect(screen.getByText('Duration: 60 minutes')).toBeInTheDocument();
    });
  });

  describe('action buttons for past confirmed bookings', () => {
    it('shows action buttons for past CONFIRMED bookings', () => {
      // Create a booking that ended yesterday
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      const booking = createMockBooking({
        status: 'CONFIRMED',
        booking_date: yesterday.toISOString().split('T')[0],
        start_time: '10:00:00',
        end_time: '11:00:00',
      });

      mockUseBooking.mockReturnValue({
        data: booking,
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useBooking>);

      render(<BookingDetailsPage />);

      expect(screen.getByText('Action Required')).toBeInTheDocument();
      expect(screen.getByText('Mark Complete')).toBeInTheDocument();
      expect(screen.getByText('Report No-Show')).toBeInTheDocument();
    });

    it('hides action buttons for future CONFIRMED bookings', () => {
      // Create a booking for tomorrow
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);
      const booking = createMockBooking({
        status: 'CONFIRMED',
        booking_date: tomorrow.toISOString().split('T')[0],
        start_time: '10:00:00',
        end_time: '11:00:00',
      });

      mockUseBooking.mockReturnValue({
        data: booking,
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useBooking>);

      render(<BookingDetailsPage />);

      expect(screen.queryByText('Action Required')).not.toBeInTheDocument();
      expect(screen.queryByText('Mark Complete')).not.toBeInTheDocument();
      expect(screen.queryByText('Report No-Show')).not.toBeInTheDocument();
    });

    it('hides action buttons for COMPLETED bookings', () => {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      const booking = createMockBooking({
        status: 'COMPLETED',
        booking_date: yesterday.toISOString().split('T')[0],
      });

      mockUseBooking.mockReturnValue({
        data: booking,
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useBooking>);

      render(<BookingDetailsPage />);

      expect(screen.queryByText('Action Required')).not.toBeInTheDocument();
      expect(screen.queryByText('Mark Complete')).not.toBeInTheDocument();
    });

    it('hides action buttons for CANCELLED bookings', () => {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      const booking = createMockBooking({
        status: 'CANCELLED',
        booking_date: yesterday.toISOString().split('T')[0],
        cancellation_reason: 'Student cancelled',
        cancelled_at: yesterday.toISOString(),
      });

      mockUseBooking.mockReturnValue({
        data: booking,
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useBooking>);

      render(<BookingDetailsPage />);

      expect(screen.queryByText('Action Required')).not.toBeInTheDocument();
      expect(screen.queryByText('Mark Complete')).not.toBeInTheDocument();
    });
  });

  describe('mark complete action', () => {
    it('calls complete mutation when Mark Complete is clicked', async () => {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      const booking = createMockBooking({
        status: 'CONFIRMED',
        booking_date: yesterday.toISOString().split('T')[0],
      });

      mockUseBooking.mockReturnValue({
        data: booking,
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useBooking>);

      render(<BookingDetailsPage />);

      const completeButton = screen.getByText('Mark Complete');
      fireEvent.click(completeButton);

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({ bookingId: '01ABC123456789DEFGHIJKLMN' });
      });

      expect(mockToastSuccess).toHaveBeenCalledWith('Lesson marked as complete', expect.any(Object));
      expect(mockInvalidateQueries).toHaveBeenCalled();
    });

    it('shows error toast when complete mutation fails', async () => {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      const booking = createMockBooking({
        status: 'CONFIRMED',
        booking_date: yesterday.toISOString().split('T')[0],
      });

      mockUseBooking.mockReturnValue({
        data: booking,
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useBooking>);

      mockMutateAsync.mockRejectedValueOnce(new Error('Server error'));

      render(<BookingDetailsPage />);

      const completeButton = screen.getByText('Mark Complete');
      fireEvent.click(completeButton);

      await waitFor(() => {
        expect(mockToastError).toHaveBeenCalledWith('Failed to mark lesson as complete', expect.any(Object));
      });
    });
  });

  describe('no-show confirmation modal', () => {
    it('opens no-show modal when Report No-Show is clicked', async () => {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      const booking = createMockBooking({
        status: 'CONFIRMED',
        booking_date: yesterday.toISOString().split('T')[0],
      });

      mockUseBooking.mockReturnValue({
        data: booking,
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useBooking>);

      render(<BookingDetailsPage />);

      const noShowButton = screen.getByText('Report No-Show');
      fireEvent.click(noShowButton);

      await waitFor(() => {
        expect(screen.getByText(/Are you sure you want to mark this lesson as a no-show/)).toBeInTheDocument();
      });

      // Modal should show student name and buttons
      expect(screen.getByText(/did not attend the scheduled lesson/)).toBeInTheDocument();
      expect(screen.getByText('Confirm No-Show')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    });

    it('closes modal when Cancel is clicked', async () => {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      const booking = createMockBooking({
        status: 'CONFIRMED',
        booking_date: yesterday.toISOString().split('T')[0],
      });

      mockUseBooking.mockReturnValue({
        data: booking,
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useBooking>);

      render(<BookingDetailsPage />);

      // Open modal
      fireEvent.click(screen.getByText('Report No-Show'));
      await waitFor(() => {
        expect(screen.getByText('Confirm No-Show')).toBeInTheDocument();
      });

      // Close modal - use getByRole to be more specific
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
      await waitFor(() => {
        expect(screen.queryByText('Confirm No-Show')).not.toBeInTheDocument();
      });
    });

    it('calls no-show mutation when confirmed', async () => {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      const booking = createMockBooking({
        status: 'CONFIRMED',
        booking_date: yesterday.toISOString().split('T')[0],
      });

      mockUseBooking.mockReturnValue({
        data: booking,
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useBooking>);

      render(<BookingDetailsPage />);

      // Open modal
      fireEvent.click(screen.getByText('Report No-Show'));
      await waitFor(() => {
        expect(screen.getByText('Confirm No-Show')).toBeInTheDocument();
      });

      // Confirm no-show
      fireEvent.click(screen.getByText('Confirm No-Show'));

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({
          bookingId: '01ABC123456789DEFGHIJKLMN',
          data: { no_show_type: 'student' },
        });
      });

      expect(mockToastSuccess).toHaveBeenCalledWith('Lesson marked as no-show', expect.any(Object));
    });

    it('shows error toast when no-show mutation fails', async () => {
      const yesterday = new Date();
      yesterday.setDate(yesterday.getDate() - 1);
      const booking = createMockBooking({
        status: 'CONFIRMED',
        booking_date: yesterday.toISOString().split('T')[0],
      });

      mockUseBooking.mockReturnValue({
        data: booking,
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useBooking>);

      mockMutateAsync.mockRejectedValueOnce(new Error('Server error'));

      render(<BookingDetailsPage />);

      // Open modal
      fireEvent.click(screen.getByText('Report No-Show'));
      await waitFor(() => {
        expect(screen.getByText('Confirm No-Show')).toBeInTheDocument();
      });

      // Confirm no-show
      fireEvent.click(screen.getByText('Confirm No-Show'));

      await waitFor(() => {
        expect(mockToastError).toHaveBeenCalledWith('Failed to mark lesson as no-show', expect.any(Object));
      });
    });
  });

  describe('NO_SHOW status display', () => {
    it('displays NO_SHOW status with correct styling', () => {
      const booking = createMockBooking({
        status: 'NO_SHOW',
      });

      mockUseBooking.mockReturnValue({
        data: booking,
        isLoading: false,
        error: null,
      } as unknown as ReturnType<typeof useBooking>);

      render(<BookingDetailsPage />);

      const statusBadge = screen.getByText('NO_SHOW');
      expect(statusBadge).toBeInTheDocument();
      expect(statusBadge).toHaveClass('bg-yellow-100', 'text-yellow-800');
    });
  });
});
