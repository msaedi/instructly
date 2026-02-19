import { render, screen } from '@testing-library/react';
import { LessonEnded } from '../LessonEnded';
import type { Booking, VideoSessionStatusResponse } from '@/features/shared/api/types';

const baseBooking = {
  service_name: 'Guitar Lesson',
  instructor_id: 'inst_123',
  video_session_duration_seconds: 1800,
} as unknown as Booking;

const sessionData = {
  instructor_joined_at: '2025-01-01T10:00:00Z',
  student_joined_at: '2025-01-01T10:01:00Z',
} as unknown as VideoSessionStatusResponse;

describe('LessonEnded', () => {
  it('shows "Lesson Complete" heading', () => {
    render(<LessonEnded booking={baseBooking} userRole="student" />);
    expect(screen.getByRole('heading', { name: 'Lesson Complete' })).toBeInTheDocument();
  });

  it('shows booking service name', () => {
    render(<LessonEnded booking={baseBooking} userRole="student" />);
    expect(screen.getByText('Guitar Lesson')).toBeInTheDocument();
  });

  it('shows session details when sessionData is provided', () => {
    render(<LessonEnded booking={baseBooking} sessionData={sessionData} userRole="student" />);
    expect(screen.getByText('30m')).toBeInTheDocument();
    expect(screen.getByText(/Instructor joined:/)).toBeInTheDocument();
    expect(screen.getByText(/Student joined:/)).toBeInTheDocument();
  });

  it('does NOT show session details when sessionData is null', () => {
    render(<LessonEnded booking={baseBooking} sessionData={null} userRole="student" />);
    expect(screen.queryByText(/Duration:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Instructor joined:/)).not.toBeInTheDocument();
  });

  it('student role: links to /student/lessons and shows Book Again', () => {
    render(<LessonEnded booking={baseBooking} userRole="student" />);
    const backLink = screen.getByRole('link', { name: 'Back to My Lessons' });
    expect(backLink).toHaveAttribute('href', '/student/lessons');
    const bookAgain = screen.getByRole('link', { name: 'Book Again' });
    expect(bookAgain).toHaveAttribute('href', '/instructors/inst_123');
  });

  it('instructor role: links to /instructor/bookings, no Book Again', () => {
    render(<LessonEnded booking={baseBooking} userRole="instructor" />);
    const backLink = screen.getByRole('link', { name: 'Back to My Lessons' });
    expect(backLink).toHaveAttribute('href', '/instructor/bookings');
    expect(screen.queryByRole('link', { name: 'Book Again' })).not.toBeInTheDocument();
  });

  it('formats 1800s as "30m"', () => {
    render(<LessonEnded booking={baseBooking} sessionData={sessionData} userRole="student" />);
    expect(screen.getByText('30m')).toBeInTheDocument();
  });

  it('formats 95s as "1m 35s"', () => {
    const booking = { ...baseBooking, video_session_duration_seconds: 95 } as unknown as Booking;
    render(<LessonEnded booking={booking} sessionData={sessionData} userRole="student" />);
    expect(screen.getByText('1m 35s')).toBeInTheDocument();
  });

  it('formats null duration as "--"', () => {
    const booking = { ...baseBooking, video_session_duration_seconds: null } as unknown as Booking;
    render(<LessonEnded booking={booking} sessionData={sessionData} userRole="student" />);
    expect(screen.getByText('--')).toBeInTheDocument();
  });

  it('formats duration >= 3600s in hours and minutes', () => {
    // 3660 seconds = 61 minutes = 1h 1m (exercises lines 15-16: m >= 60 branch)
    const booking = { ...baseBooking, video_session_duration_seconds: 3660 } as unknown as Booking;
    render(<LessonEnded booking={booking} sessionData={sessionData} userRole="student" />);
    expect(screen.getByText('1h 1m')).toBeInTheDocument();
  });

  it('formats exactly 1 hour (3600s) as "1h 0m"', () => {
    const booking = { ...baseBooking, video_session_duration_seconds: 3600 } as unknown as Booking;
    render(<LessonEnded booking={booking} sessionData={sessionData} userRole="student" />);
    expect(screen.getByText('1h 0m')).toBeInTheDocument();
  });

  it('formats multi-hour duration correctly', () => {
    // 7380 seconds = 123 minutes = 2h 3m
    const booking = { ...baseBooking, video_session_duration_seconds: 7380 } as unknown as Booking;
    render(<LessonEnded booking={booking} sessionData={sessionData} userRole="student" />);
    expect(screen.getByText('2h 3m')).toBeInTheDocument();
  });

  it('returns "--" for formatTime when toLocaleTimeString throws', () => {
    // Stub Date.prototype.toLocaleTimeString to throw, exercising line 26 (catch branch)
    const original = Date.prototype.toLocaleTimeString;
    Date.prototype.toLocaleTimeString = () => { throw new Error('locale not supported'); };

    const session = {
      instructor_joined_at: '2025-01-01T10:00:00Z',
      student_joined_at: '2025-01-01T10:01:00Z',
    } as unknown as VideoSessionStatusResponse;

    render(<LessonEnded booking={baseBooking} sessionData={session} userRole="student" />);

    // Both time fields should show "--" because toLocaleTimeString throws
    const dashes = screen.getAllByText('--');
    expect(dashes.length).toBeGreaterThanOrEqual(2);

    Date.prototype.toLocaleTimeString = original;
  });

  it('does not show Book Again when student has no instructor_id', () => {
    const bookingNoInstructor = { ...baseBooking, instructor_id: undefined } as unknown as Booking;
    render(<LessonEnded booking={bookingNoInstructor} userRole="student" />);
    expect(screen.queryByRole('link', { name: 'Book Again' })).not.toBeInTheDocument();
  });
});
