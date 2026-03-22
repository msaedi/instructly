import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import BookingDetailsPage from '../page';
import { useCreateConversation } from '@/hooks/useCreateConversation';
import {
  useBooking,
  useCompleteBooking,
  useMarkBookingNoShow,
} from '@/src/api/services/bookings';

jest.mock('next/navigation', () => ({
  useParams: () => ({ id: '01KKQKWD9V9QF0J2T0AB3124' }),
}));

jest.mock('@/components/UserProfileDropdown', () => {
  const MockUserProfileDropdown = () => <div data-testid="user-dropdown" />;
  MockUserProfileDropdown.displayName = 'MockUserProfileDropdown';
  return {
    __esModule: true,
    default: MockUserProfileDropdown,
  };
});

const mockInvalidateQueries = jest.fn();
jest.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({
    invalidateQueries: mockInvalidateQueries,
  }),
}));

const mockToastSuccess = jest.fn();
const mockToastError = jest.fn();
jest.mock('sonner', () => ({
  toast: {
    success: (msg: string, opts?: object) => mockToastSuccess(msg, opts),
    error: (msg: string, opts?: object) => mockToastError(msg, opts),
  },
}));

jest.mock('@/src/api/services/bookings');
jest.mock('@/hooks/useCreateConversation');

const mockUseBooking = useBooking as jest.MockedFunction<typeof useBooking>;
const mockUseCompleteBooking = useCompleteBooking as jest.MockedFunction<typeof useCompleteBooking>;
const mockUseMarkBookingNoShow = useMarkBookingNoShow as jest.MockedFunction<
  typeof useMarkBookingNoShow
>;
const mockUseCreateConversation = useCreateConversation as jest.MockedFunction<
  typeof useCreateConversation
>;

const completeMutateAsyncMock = jest.fn();
const markNoShowMutateAsyncMock = jest.fn();
const createConversationMock = jest.fn();

const createMockBooking = (overrides = {}) => ({
  id: '01KKQKWD9V9QF0J2T0AB3124',
  status: 'CONFIRMED',
  booking_date: '2026-03-16',
  start_time: '16:30:00',
  end_time: '17:15:00',
  service_name: 'Piano',
  duration_minutes: 45,
  hourly_rate: 110,
  total_price: 82.5,
  location_type: 'instructor_location',
  meeting_location: 'Manhattan',
  service_area: 'Upper East Side',
  student_id: '01STUDENT123456789ABCDEFGH',
  student: {
    id: '01STUDENT123456789ABCDEFGH',
    first_name: 'John',
    last_initial: 'S',
    last_name: 'Smith',
    email: 'john@example.com',
  },
  student_note: null,
  instructor_note: null,
  cancellation_reason: null,
  cancelled_at: null,
  created_at: '2026-03-14T08:00:00Z',
  settlement_outcome: null,
  instructor_payout_amount: null,
  video_session_duration_seconds: null,
  video_instructor_joined_at: null,
  video_student_joined_at: null,
  ...overrides,
});

describe('Instructor Booking Details Page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useRealTimers();

    mockUseCompleteBooking.mockReturnValue({
      mutateAsync: completeMutateAsyncMock.mockResolvedValue({}),
      isPending: false,
    } as unknown as ReturnType<typeof useCompleteBooking>);
    mockUseMarkBookingNoShow.mockReturnValue({
      mutateAsync: markNoShowMutateAsyncMock.mockResolvedValue({}),
      isPending: false,
    } as unknown as ReturnType<typeof useMarkBookingNoShow>);
    mockUseCreateConversation.mockReturnValue({
      createConversation: createConversationMock,
      isCreating: false,
      error: null,
    });
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('shows the loading spinner inside the dashboard shell', () => {
    mockUseBooking.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as unknown as ReturnType<typeof useBooking>);

    const { container } = render(<BookingDetailsPage />);

    expect(screen.getByTestId('instructor-dashboard-shell')).toBeInTheDocument();
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('shows an error message when the booking fails to load', () => {
    mockUseBooking.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Failed'),
    } as unknown as ReturnType<typeof useBooking>);

    render(<BookingDetailsPage />);

    expect(screen.getByText('Failed to load booking details')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Bookings' })).toHaveAttribute(
      'href',
      '/instructor/dashboard?panel=bookings'
    );
  });

  it('renders the redesigned detail page inside the instructor dashboard shell', () => {
    mockUseBooking.mockReturnValue({
      data: createMockBooking(),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useBooking>);

    render(<BookingDetailsPage />);

    expect(screen.getByTestId('instructor-dashboard-shell')).toBeInTheDocument();
    expect(screen.getByTestId('instructor-dashboard-sidebar')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Bookings' })).toBeInTheDocument();
    expect(
      screen.getByText('Track upcoming sessions and review completed lessons all in one place.')
    ).toBeInTheDocument();
    expect(screen.getByText('Booking #KWD-3124')).toBeInTheDocument();
    expect(screen.queryByText('Back to Bookings')).not.toBeInTheDocument();
    expect(screen.queryByText('01KKQKWD9V9QF0J2T0AB3124')).not.toBeInTheDocument();
    expect(screen.getByText('Created on 3/14/2026')).toBeInTheDocument();
    expect(screen.getByText('John S.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Message' })).toBeInTheDocument();
    expect(screen.getByText('Monday, March 16')).toBeInTheDocument();
    expect(screen.getByText('4:30 PM – 5:15 PM')).toBeInTheDocument();
    expect(screen.getByText("At instructor's location · Manhattan")).toBeInTheDocument();
    expect(screen.getByText('$110.00/hr')).toBeInTheDocument();
    expect(screen.getByText('45 min')).toBeInTheDocument();
    expect(screen.getByText('$82.50')).toBeInTheDocument();
    expect(screen.queryByText('john@example.com')).not.toBeInTheDocument();
    expect(screen.queryByText('John Smith')).not.toBeInTheDocument();
  });

  it('opens messaging for the student when Message is clicked', async () => {
    mockUseBooking.mockReturnValue({
      data: createMockBooking(),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useBooking>);

    render(<BookingDetailsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'Message' }));

    await waitFor(() => {
      expect(createConversationMock).toHaveBeenCalledWith('01STUDENT123456789ABCDEFGH', {
        navigateToMessages: true,
      });
    });
  });

  it('renders completed payout status when payout data is available', () => {
    mockUseBooking.mockReturnValue({
      data: createMockBooking({
        status: 'COMPLETED',
        settlement_outcome: 'paid_out',
        instructor_payout_amount: 80,
      }),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useBooking>);

    render(<BookingDetailsPage />);

    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('Payout status')).toBeInTheDocument();
    expect(screen.getByText('Paid Out · $80.00 payout')).toBeInTheDocument();
  });

  it('shows action buttons for past confirmed bookings and marks them complete', async () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-03-21T12:00:00Z'));
    mockUseBooking.mockReturnValue({
      data: createMockBooking(),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useBooking>);

    render(<BookingDetailsPage />);

    expect(screen.getByText('Action Required')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Mark Complete' }));

    await waitFor(() => {
      expect(completeMutateAsyncMock).toHaveBeenCalledWith({
        bookingId: '01KKQKWD9V9QF0J2T0AB3124',
      });
    });

    expect(mockToastSuccess).toHaveBeenCalledWith(
      'Lesson marked as complete',
      expect.any(Object)
    );
    expect(mockInvalidateQueries).toHaveBeenCalledTimes(2);
  });

  it('shows an error toast when marking complete fails', async () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-03-21T12:00:00Z'));
    completeMutateAsyncMock.mockRejectedValueOnce(new Error('Server error'));
    mockUseBooking.mockReturnValue({
      data: createMockBooking(),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useBooking>);

    render(<BookingDetailsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'Mark Complete' }));

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith(
        'Failed to mark lesson as complete',
        expect.any(Object)
      );
    });
  });

  it('opens and closes the no-show modal, then submits a no-show', async () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-03-21T12:00:00Z'));
    mockUseBooking.mockReturnValue({
      data: createMockBooking(),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useBooking>);

    render(<BookingDetailsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'Report No-Show' }));
    expect(
      screen.getByText(/Are you sure you want to mark this lesson as a no-show/i)
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => {
      expect(screen.queryByText('Confirm No-Show')).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Report No-Show' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm No-Show' }));

    await waitFor(() => {
      expect(markNoShowMutateAsyncMock).toHaveBeenCalledWith({
        bookingId: '01KKQKWD9V9QF0J2T0AB3124',
        data: { no_show_type: 'student' },
      });
    });

    expect(mockToastSuccess).toHaveBeenCalledWith(
      'Lesson marked as no-show',
      expect.any(Object)
    );
  });

  it('shows an error toast when reporting a no-show fails', async () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-03-21T12:00:00Z'));
    markNoShowMutateAsyncMock.mockRejectedValueOnce(new Error('Server error'));
    mockUseBooking.mockReturnValue({
      data: createMockBooking(),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useBooking>);

    render(<BookingDetailsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'Report No-Show' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm No-Show' }));

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith(
        'Failed to mark lesson as no-show',
        expect.any(Object)
      );
    });
  });

  it('hides action buttons for future, completed, and cancelled bookings', () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-03-10T12:00:00Z'));
    mockUseBooking.mockReturnValue({
      data: createMockBooking({
        booking_date: '2026-03-25',
      }),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useBooking>);

    const { rerender } = render(<BookingDetailsPage />);

    expect(screen.queryByText('Action Required')).not.toBeInTheDocument();

    mockUseBooking.mockReturnValue({
      data: createMockBooking({
        status: 'COMPLETED',
      }),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useBooking>);
    rerender(<BookingDetailsPage />);

    expect(screen.queryByText('Action Required')).not.toBeInTheDocument();

    mockUseBooking.mockReturnValue({
      data: createMockBooking({
        status: 'CANCELLED',
        cancellation_reason: 'Student cancelled',
        cancelled_at: '2026-03-15T12:00:00Z',
      }),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useBooking>);
    rerender(<BookingDetailsPage />);

    expect(screen.queryByText('Action Required')).not.toBeInTheDocument();
  });

  it('renders preserved video, notes, and no-show states', () => {
    mockUseBooking.mockReturnValue({
      data: createMockBooking({
        status: 'NO_SHOW',
        video_session_duration_seconds: 2100,
        video_instructor_joined_at: '2026-03-16T16:30:00Z',
        video_student_joined_at: '2026-03-16T16:32:00Z',
        student_note: 'Please focus on scales.',
        instructor_note: 'Great left-hand posture.',
        cancellation_reason: 'Weather',
        cancelled_at: '2026-03-16T12:00:00Z',
      }),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useBooking>);

    render(<BookingDetailsPage />);

    expect(screen.getByText('No-show')).toHaveClass('bg-amber-50', 'text-amber-800');
    expect(screen.getByText('Video Session')).toBeInTheDocument();
    expect(screen.getByText('35m')).toBeInTheDocument();
    expect(screen.getByText('Note from student')).toBeInTheDocument();
    expect(screen.getByText('"Please focus on scales."')).toBeInTheDocument();
    expect(screen.getByText('Instructor notes')).toBeInTheDocument();
    expect(screen.getByText('Great left-hand posture.')).toBeInTheDocument();
  });

  it('renders cancellation details for cancelled bookings', () => {
    mockUseBooking.mockReturnValue({
      data: createMockBooking({
        status: 'CANCELLED',
        cancellation_reason: 'Student cancelled',
        cancelled_at: '2026-03-15T12:00:00Z',
      }),
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useBooking>);

    render(<BookingDetailsPage />);

    expect(screen.getByText('Cancellation Details')).toBeInTheDocument();
    expect(screen.getByText(/Reason:/)).toBeInTheDocument();
    expect(screen.getByText('Student cancelled')).toBeInTheDocument();
    expect(screen.getByText('Cancelled on 3/15/2026')).toBeInTheDocument();
  });
});
