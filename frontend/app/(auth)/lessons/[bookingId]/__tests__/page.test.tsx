import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useParams } from 'next/navigation';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useLessonDetails } from '@/hooks/useMyLessons';
import { useJoinLesson, useVideoSessionStatus } from '@/hooks/queries/useLessonRoom';
import type { Booking } from '@/features/shared/api/types';
import LessonRoomPage from '../page';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

jest.mock('next/navigation', () => ({
  useParams: jest.fn(() => ({ bookingId: 'booking_123' })),
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(),
}));

jest.mock('@/hooks/useMyLessons', () => ({
  useLessonDetails: jest.fn(),
}));

jest.mock('@/hooks/queries/useLessonRoom', () => ({
  useJoinLesson: jest.fn(),
  useVideoSessionStatus: jest.fn(),
}));

jest.mock('@/components/lessons/video/PreLessonWaiting', () => ({
  PreLessonWaiting: (props: Record<string, unknown>) => (
    <div data-testid="pre-lesson-waiting" data-join-error={props.joinError ?? ''}>
      <button onClick={props.onJoin as () => void}>Join Lesson</button>
    </div>
  ),
}));

jest.mock('@/components/lessons/video/ActiveLesson', () => ({
  ActiveLesson: (props: Record<string, unknown>) => (
    <div data-testid="active-lesson">
      <button onClick={props.onLeave as () => void}>Leave</button>
    </div>
  ),
}));

jest.mock('@/components/lessons/video/NotJoinable', () => ({
  NotJoinable: (props: Record<string, unknown>) => (
    <div data-testid="not-joinable" data-reason={props.reason} />
  ),
}));

jest.mock('@/components/lessons/video/LessonEnded', () => ({
  LessonEnded: () => <div data-testid="lesson-ended" />,
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const onlineConfirmedBooking = {
  id: 'booking_123',
  location_type: 'online',
  status: 'CONFIRMED',
  join_opens_at: '2025-01-01T10:00:00Z',
  join_closes_at: '2025-01-01T10:30:00Z',
  video_session_ended_at: null,
  service_name: 'Guitar Lesson',
  instructor_id: 'inst_456',
  instructor: { first_name: 'Sarah' },
  student: { first_name: 'John' },
} as unknown as Booking;

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

const mockRedirectToLogin = jest.fn();
const mockJoinLesson = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();

  (useParams as jest.Mock).mockReturnValue({ bookingId: 'booking_123' });

  (useAuth as jest.Mock).mockReturnValue({
    user: { id: 'user_1', first_name: 'John', last_name: 'Doe' },
    isLoading: false,
    isAuthenticated: true,
    redirectToLogin: mockRedirectToLogin,
  });

  (useLessonDetails as jest.Mock).mockReturnValue({
    data: onlineConfirmedBooking,
    isLoading: false,
    error: null,
  });

  (useJoinLesson as jest.Mock).mockReturnValue({
    joinLesson: mockJoinLesson,
    isPending: false,
  });

  (useVideoSessionStatus as jest.Mock).mockReturnValue({
    sessionData: null,
  });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('LessonRoomPage', () => {
  it('shows a loading spinner while auth is loading', () => {
    (useAuth as jest.Mock).mockReturnValue({
      user: null,
      isLoading: true,
      isAuthenticated: false,
      redirectToLogin: mockRedirectToLogin,
    });

    render(<LessonRoomPage />);

    // The spinner is rendered; none of the phase-specific components should appear
    expect(screen.queryByTestId('pre-lesson-waiting')).not.toBeInTheDocument();
    expect(screen.queryByTestId('active-lesson')).not.toBeInTheDocument();
    expect(screen.queryByTestId('not-joinable')).not.toBeInTheDocument();
    expect(screen.queryByTestId('lesson-ended')).not.toBeInTheDocument();
  });

  it('redirects to login when not authenticated', () => {
    (useAuth as jest.Mock).mockReturnValue({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      redirectToLogin: mockRedirectToLogin,
    });

    render(<LessonRoomPage />);

    expect(mockRedirectToLogin).toHaveBeenCalled();
  });

  it('shows error message when booking fails to load', () => {
    // First render with valid data so phase advances past 'loading'
    const { rerender } = render(<LessonRoomPage />);
    expect(screen.getByTestId('pre-lesson-waiting')).toBeInTheDocument();

    // Simulate a refetch that returns an error (data becomes null)
    (useLessonDetails as jest.Mock).mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('Network error'),
    });
    rerender(<LessonRoomPage />);

    expect(screen.getByText('Failed to load lesson details.')).toBeInTheDocument();
    expect(screen.getByText('Back to My Lessons')).toBeInTheDocument();
  });

  it('shows "Lesson not found." when booking data is null with no error', () => {
    // First render with valid data so phase advances past 'loading'
    const { rerender } = render(<LessonRoomPage />);
    expect(screen.getByTestId('pre-lesson-waiting')).toBeInTheDocument();

    // Simulate data disappearing (e.g., cache eviction)
    (useLessonDetails as jest.Mock).mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    });
    rerender(<LessonRoomPage />);

    expect(screen.getByText('Lesson not found.')).toBeInTheDocument();
  });

  it('renders NotJoinable with reason "in-person" for non-online bookings', () => {
    const inPersonBooking = {
      ...onlineConfirmedBooking,
      location_type: 'in-person',
    } as unknown as Booking;

    (useLessonDetails as jest.Mock).mockReturnValue({
      data: inPersonBooking,
      isLoading: false,
      error: null,
    });

    render(<LessonRoomPage />);

    const el = screen.getByTestId('not-joinable');
    expect(el).toBeInTheDocument();
    expect(el).toHaveAttribute('data-reason', 'in-person');
  });

  it('renders NotJoinable with reason "cancelled" for cancelled bookings', () => {
    const cancelledBooking = {
      ...onlineConfirmedBooking,
      status: 'CANCELLED',
    } as unknown as Booking;

    (useLessonDetails as jest.Mock).mockReturnValue({
      data: cancelledBooking,
      isLoading: false,
      error: null,
    });

    render(<LessonRoomPage />);

    const el = screen.getByTestId('not-joinable');
    expect(el).toBeInTheDocument();
    expect(el).toHaveAttribute('data-reason', 'cancelled');
  });

  it('renders NotJoinable with reason "not-available" when join window is missing', () => {
    const noJoinWindowBooking = {
      ...onlineConfirmedBooking,
      join_opens_at: null,
    } as unknown as Booking;

    (useLessonDetails as jest.Mock).mockReturnValue({
      data: noJoinWindowBooking,
      isLoading: false,
      error: null,
    });

    render(<LessonRoomPage />);

    const el = screen.getByTestId('not-joinable');
    expect(el).toBeInTheDocument();
    expect(el).toHaveAttribute('data-reason', 'not-available');
  });

  it('renders PreLessonWaiting for an online confirmed booking with a join window', () => {
    render(<LessonRoomPage />);

    expect(screen.getByTestId('pre-lesson-waiting')).toBeInTheDocument();
  });

  it('renders LessonEnded when video session has already ended', () => {
    const endedBooking = {
      ...onlineConfirmedBooking,
      video_session_ended_at: '2025-01-01T11:00:00Z',
    } as unknown as Booking;

    (useLessonDetails as jest.Mock).mockReturnValue({
      data: endedBooking,
      isLoading: false,
      error: null,
    });

    render(<LessonRoomPage />);

    expect(screen.getByTestId('lesson-ended')).toBeInTheDocument();
  });

  it('transitions through join -> active -> leave -> ended', async () => {
    mockJoinLesson.mockResolvedValueOnce({ auth_token: 'tok_123' });

    render(<LessonRoomPage />);

    // Start in pre-lesson
    expect(screen.getByTestId('pre-lesson-waiting')).toBeInTheDocument();

    // Click Join
    fireEvent.click(screen.getByText('Join Lesson'));

    // Should transition to active
    await waitFor(() => {
      expect(screen.getByTestId('active-lesson')).toBeInTheDocument();
    });

    // Click Leave
    fireEvent.click(screen.getByText('Leave'));

    // Should transition to ended
    await waitFor(() => {
      expect(screen.getByTestId('lesson-ended')).toBeInTheDocument();
    });
  });
});
