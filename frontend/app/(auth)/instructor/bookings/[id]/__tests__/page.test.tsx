import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

import BookingDetailsPage from '../page';
import { useCreateConversation } from '@/hooks/useCreateConversation';
import { logger } from '@/lib/logger';
import { useBooking, useMarkBookingNoShow } from '@/src/api/services/bookings';
import { useMarkLessonComplete } from '@/src/api/services/instructor-bookings';

const mockPush = jest.fn();

jest.mock('next/navigation', () => ({
  useParams: () => ({ id: '01KKQKWD9V9QF0J2T0AB3124' }),
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('@/components/UserProfileDropdown', () => {
  const MockUserProfileDropdown = () => <div data-testid="user-dropdown" />;
  MockUserProfileDropdown.displayName = 'MockUserProfileDropdown';
  return {
    __esModule: true,
    default: MockUserProfileDropdown,
  };
});

jest.mock('@/components/notifications/NotificationBell', () => ({
  NotificationBell: () => <div data-testid="notification-bell" />,
}));

jest.mock('@/lib/auth/sessionRefresh', () => ({
  fetchWithSessionRefresh: jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ conversations: [] }),
  }),
}));

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

jest.mock('@/lib/logger', () => ({
  logger: {
    error: jest.fn(),
  },
}));

jest.mock('@/src/api/services/bookings');
jest.mock('@/src/api/services/instructor-bookings');
jest.mock('@/hooks/useCreateConversation');

const mockUseBooking = useBooking as jest.MockedFunction<typeof useBooking>;
const mockUseMarkBookingNoShow = useMarkBookingNoShow as jest.MockedFunction<
  typeof useMarkBookingNoShow
>;
const mockUseMarkLessonComplete = useMarkLessonComplete as jest.MockedFunction<
  typeof useMarkLessonComplete
>;
const mockUseCreateConversation = useCreateConversation as jest.MockedFunction<
  typeof useCreateConversation
>;
const mockLoggerError = logger.error as jest.MockedFunction<typeof logger.error>;

const completeMutateAsyncMock = jest.fn();
const markNoShowMutateAsyncMock = jest.fn();
const createConversationMock = jest.fn();

  const createMockBooking = (overrides = {}) => ({
  id: '01KKQKWD9V9QF0J2T0AB3124',
  status: 'CONFIRMED',
  booking_date: '2026-03-16',
  start_time: '16:30:00',
  end_time: '17:15:00',
  booking_start_utc: null,
  booking_end_utc: null,
  service_name: 'Piano',
  duration_minutes: 45,
  lesson_timezone: null,
  hourly_rate: 110,
  total_price: 82.5,
  location_type: 'instructor_location',
  location_address: '129 W 67th St, New York, NY 10023',
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
  join_opens_at: null,
  join_closes_at: null,
  no_show_reported_at: null,
  no_show_type: null,
  ...overrides,
});

function mockBookingData(overrides = {}) {
  mockUseBooking.mockReturnValue({
    data: createMockBooking(overrides),
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useBooking>);
}

describe('Instructor Booking Details Page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useRealTimers();

    completeMutateAsyncMock.mockReset().mockResolvedValue({});
    markNoShowMutateAsyncMock.mockReset().mockResolvedValue({});
    createConversationMock.mockReset().mockResolvedValue({ id: 'conv_123', created: true });

    mockUseMarkLessonComplete.mockReturnValue({
      mutateAsync: completeMutateAsyncMock,
      isPending: false,
    } as unknown as ReturnType<typeof useMarkLessonComplete>);
    mockUseMarkBookingNoShow.mockReturnValue({
      mutateAsync: markNoShowMutateAsyncMock,
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

  it('renders lavender pricing tiles with a disabled join button and countdown before join opens', () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-03-16T16:20:00Z'));
    mockBookingData({
      location_type: 'online',
      location_address: null,
      meeting_location: 'Online',
      service_area: null,
      join_opens_at: '2026-03-16T16:25:00Z',
      join_closes_at: '2026-03-16T17:10:00Z',
    });

    render(<BookingDetailsPage />);

    expect(screen.getByTestId('pricing-tile-rate')).toHaveStyle({ backgroundColor: '#FAF5FF' });
    expect(screen.getByTestId('pricing-tile-duration')).toHaveStyle({
      backgroundColor: '#FAF5FF',
    });
    expect(screen.getByTestId('pricing-tile-lesson-price')).toHaveStyle({
      backgroundColor: '#FAF5FF',
    });

    expect(screen.getByRole('button', { name: 'Join lesson' })).toBeDisabled();
    expect(screen.getByTestId('join-lesson-countdown')).toHaveTextContent(
      'Join opens in 05:00'
    );
    expect(screen.getByText('Online lesson')).not.toHaveClass('text-(--color-brand)');
    expect(screen.getByTestId('report-issue-link')).toBeInTheDocument();
    expect(screen.getByTestId('cancel-lesson-link')).toBeInTheDocument();

    const actions = screen.getByTestId('booking-card-actions');
    expect(actions.firstElementChild).toHaveTextContent('Join lesson');
    expect(actions.lastElementChild).toHaveTextContent('Message');
  });

  it('transitions the join button from disabled to active when the countdown expires and highlights the online row', async () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-03-16T16:24:45Z'));
    mockBookingData({
      location_type: 'online',
      location_address: null,
      meeting_location: 'Online',
      service_area: null,
      join_opens_at: '2026-03-16T16:25:00Z',
      join_closes_at: '2026-03-16T17:10:00Z',
    });

    render(<BookingDetailsPage />);

    expect(screen.getByRole('button', { name: 'Join lesson' })).toBeDisabled();
    expect(screen.getByTestId('join-lesson-countdown')).toHaveTextContent(
      'Join opens in 00:15'
    );

    act(() => {
      jest.advanceTimersByTime(15_000);
    });

    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'Join lesson' })).toHaveAttribute(
        'href',
        '/lessons/01KKQKWD9V9QF0J2T0AB3124'
      );
    });

    expect(screen.getByText('Online lesson')).toHaveClass('text-(--color-brand)');
  });

  it('hides the join button after the scheduled session ends', () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-03-16T17:11:00Z'));
    mockBookingData({
      location_type: 'online',
      location_address: null,
      meeting_location: 'Online',
      service_area: null,
      join_opens_at: '2026-03-16T16:25:00Z',
      join_closes_at: '2026-03-16T17:10:00Z',
    });

    render(<BookingDetailsPage />);

    expect(screen.queryByTestId('join-lesson-button')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Message' })).toBeInTheDocument();
  });

  it('shows In Progress while a confirmed lesson is live', () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-03-16T16:40:00Z'));
    mockBookingData({
      booking_start_utc: '2026-03-16T16:30:00Z',
      booking_end_utc: '2026-03-16T17:15:00Z',
      location_type: 'online',
      location_address: null,
      meeting_location: 'Online',
      service_area: null,
    });

    render(<BookingDetailsPage />);

    const badge = screen.getByText('In Progress');
    expect(badge).toHaveClass('bg-purple-50', 'text-purple-700');
    expect(screen.queryByText('Confirmed')).not.toBeInTheDocument();
  });

  it('opens standard messaging from the Message button without a prefilled message', async () => {
    mockBookingData();

    render(<BookingDetailsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'Message' }));

    await waitFor(() => {
      expect(createConversationMock).toHaveBeenCalledWith('01STUDENT123456789ABCDEFGH', {
        navigateToMessages: true,
      });
    });
  });

  it('opens messages with the exact prefilled copy for the report and cancel links', async () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-03-15T12:00:00Z'));
    mockBookingData();

    render(<BookingDetailsPage />);

    fireEvent.click(screen.getByTestId('report-issue-link'));

    await waitFor(() => {
      expect(createConversationMock).toHaveBeenNthCalledWith(
        1,
        '01STUDENT123456789ABCDEFGH',
        {
          navigateToMessages: true,
          initialMessage:
            'Hi John, I need to report an issue with our Piano lesson on Monday, March 16. ',
        }
      );
    });

    fireEvent.click(screen.getByTestId('cancel-lesson-link'));

    await waitFor(() => {
      expect(createConversationMock).toHaveBeenNthCalledWith(
        2,
        '01STUDENT123456789ABCDEFGH',
        {
          navigateToMessages: true,
          initialMessage:
            'Hi John, I need to discuss cancelling our Piano lesson on Monday, March 16. ',
        }
      );
    });
  });

  it('shows report issue but hides the cancel link once the booking is no longer a future confirmed lesson', () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-03-15T12:00:00Z'));
    mockBookingData({
      status: 'COMPLETED',
      settlement_outcome: 'paid_out',
      instructor_payout_amount: 80,
    });

    const { rerender } = render(<BookingDetailsPage />);

    expect(screen.getByTestId('report-issue-link')).toBeInTheDocument();
    expect(screen.queryByTestId('cancel-lesson-link')).not.toBeInTheDocument();
    expect(screen.getByText('Payout status')).toBeInTheDocument();
    expect(screen.getByText('Paid Out · $80.00 payout')).toBeInTheDocument();

    mockBookingData({
      status: 'PAYMENT_FAILED',
    });
    rerender(<BookingDetailsPage />);

    expect(screen.queryByTestId('report-issue-link')).not.toBeInTheDocument();
    expect(screen.queryByTestId('cancel-lesson-link')).not.toBeInTheDocument();

    mockBookingData({
      status: 'CANCELLED',
      cancellation_reason: 'Student cancelled',
      cancelled_at: '2026-03-15T12:00:00Z',
    });
    rerender(<BookingDetailsPage />);

    expect(screen.queryByTestId('report-issue-link')).not.toBeInTheDocument();
    expect(screen.queryByTestId('cancel-lesson-link')).not.toBeInTheDocument();
    expect(screen.getByText('Cancellation Details')).toBeInTheDocument();
  });

  it('renders the redesigned action row and uses the instructor-specific complete mutation', async () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-03-21T12:00:00Z'));
    mockBookingData({
      booking_end_utc: '2026-03-20T10:00:00Z',
    });

    render(<BookingDetailsPage />);

    expect(screen.queryByText('In Progress')).not.toBeInTheDocument();
    expect(screen.getByTestId('booking-action-row')).toBeInTheDocument();
    expect(screen.getByText('Action required · Did the lesson occur?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mark complete' })).toHaveClass(
      'bg-(--color-brand)'
    );
    expect(screen.getByRole('button', { name: 'Report no-show' })).toHaveClass(
      'border-red-600',
      'text-red-600'
    );
    expect(screen.getByRole('button', { name: 'Report no-show' })).toBeDisabled();
    expect(
      screen.queryByText('No-show window has passed (24 hours after lesson end).')
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Mark complete' }));

    await waitFor(() => {
      expect(mockUseMarkLessonComplete).toHaveBeenCalled();
      expect(completeMutateAsyncMock).toHaveBeenCalledWith({
        bookingId: '01KKQKWD9V9QF0J2T0AB3124',
        data: {},
      });
    });

    expect(mockToastSuccess).toHaveBeenCalledWith(
      'Lesson marked as complete',
      expect.any(Object)
    );
    expect(mockInvalidateQueries).toHaveBeenCalledTimes(2);
  });

  it('shows the action required row when booking_end_utc is null but the lesson has ended in lesson_timezone', () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-04-03T01:00:00Z'));
    mockBookingData({
      booking_date: '2026-04-02',
      start_time: '18:15:00',
      end_time: '19:15:00',
      booking_start_utc: null,
      booking_end_utc: null,
      lesson_timezone: 'America/New_York',
      location_type: 'online',
      location_address: null,
      meeting_location: 'Online',
      service_area: null,
    });

    render(<BookingDetailsPage />);

    expect(screen.getByTestId('booking-action-row')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mark complete' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Report no-show' })).toBeInTheDocument();
  });

  it('hides the action required row once a no-show has already been reported', () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-03-21T12:00:00Z'));
    mockBookingData({
      booking_end_utc: '2026-03-20T10:00:00Z',
      no_show_reported_at: '2026-03-20T12:00:00Z',
    });

    render(<BookingDetailsPage />);

    expect(screen.queryByTestId('booking-action-row')).not.toBeInTheDocument();
  });

  it('renders the redesigned no-show modal, focuses the X dismiss button, and closes via X', async () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-03-17T12:00:00Z'));
    mockBookingData({
      booking_end_utc: '2026-03-16T17:15:00Z',
    });

    render(<BookingDetailsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'Report no-show' }));

    const dialog = screen.getByRole('dialog');
    const heading = screen.getByRole('heading', { name: 'Report no-show' });

    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby', heading.getAttribute('id'));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Close report no-show modal' })).toHaveFocus();
    });
    expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
    expect(
      screen.getByText(
        (_content, node) =>
          node?.textContent ===
          'Confirm that JOHN S. was a no-show. They will still be charged for the lesson.'
      )
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Close report no-show modal' }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('submits the redesigned no-show flow and preserves existing video and note sections', async () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-03-17T12:00:00Z'));
    mockBookingData({
      booking_end_utc: '2026-03-16T17:15:00Z',
      video_session_duration_seconds: 2100,
      video_instructor_joined_at: '2026-03-16T16:30:00Z',
      video_student_joined_at: '2026-03-16T16:32:00Z',
      student_note: 'Please focus on scales.',
      instructor_note: 'Great left-hand posture.',
    });

    render(<BookingDetailsPage />);

    expect(screen.getByText('Video Session')).toBeInTheDocument();
    expect(screen.getByText('35m')).toBeInTheDocument();
    expect(screen.getByText('Note from student')).toBeInTheDocument();
    expect(screen.getByText('Instructor notes')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Report no-show' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm no-show' }));

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

  it('shows an error toast when opening messages fails', async () => {
    createConversationMock.mockRejectedValueOnce(new Error('Conversation failed'));
    mockBookingData();

    render(<BookingDetailsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'Message' }));

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith('Failed to open messages', expect.any(Object));
    });
    expect(mockLoggerError).toHaveBeenCalledWith('Failed to open messages', expect.any(Error));
  });

  it('shows an error toast when reporting a no-show fails', async () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-03-17T12:00:00Z'));
    markNoShowMutateAsyncMock.mockRejectedValueOnce(
      new Error('No-show can only be reported between lesson start and 24 hours after lesson end')
    );
    mockBookingData({
      booking_end_utc: '2026-03-16T17:15:00Z',
    });

    render(<BookingDetailsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'Report no-show' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm no-show' }));

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith(
        'No-show can only be reported between lesson start and 24 hours after lesson end',
        expect.any(Object)
      );
    });
    expect(mockLoggerError).toHaveBeenCalledWith(
      'Failed to mark lesson as no-show',
      expect.any(Error)
    );
  });
});
