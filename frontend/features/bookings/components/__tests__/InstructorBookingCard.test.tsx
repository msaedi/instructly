import { render, screen } from '@testing-library/react';
import { InstructorBookingCard } from '../InstructorBookingCard';

describe('InstructorBookingCard', () => {
  it('renders the redesigned instructor booking card', () => {
    render(
      <InstructorBookingCard
        booking={{
          id: '01KKQKWD9V9QF0J2T0AB3124',
          booking_date: '2026-03-14',
          start_time: '14:45:00',
          end_time: '15:30:00',
          status: 'CONFIRMED',
          service_name: 'Piano',
          duration_minutes: 45,
          location_type: 'student_location',
          student: {
            id: '01STUDENT123456789ABCDEFGH',
            first_name: 'David',
            last_initial: 'M',
          },
        }}
      />
    );

    const badge = screen.getByText('Confirmed');
    expect(badge).toHaveClass('bg-emerald-50', 'text-emerald-700');
    expect(screen.getByText('David M.')).toBeInTheDocument();
    expect(screen.queryByText(/^Piano$/)).not.toBeInTheDocument();
    expect(screen.getByText('Sat, Mar 14')).toBeInTheDocument();
    expect(screen.getByText('2:45 PM – 3:30 PM')).toBeInTheDocument();
    expect(screen.getByText('45 min · Piano')).toBeInTheDocument();
    expect(screen.getByText("At student's location")).toBeInTheDocument();

    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/instructor/bookings/01KKQKWD9V9QF0J2T0AB3124');
    expect(screen.getByText('View lesson ›')).toBeInTheDocument();
  });

  it('falls back to first name only when the last initial is blank', () => {
    render(
      <InstructorBookingCard
        booking={{
          id: 'booking-first-name',
          booking_date: '2026-03-14',
          start_time: '14:45:00',
          end_time: '15:30:00',
          status: 'CONFIRMED',
          service_name: 'Voice',
          duration_minutes: 45,
          location_type: 'online',
          student: {
            id: 'student-first-name',
            first_name: 'Alice',
            last_initial: '',
          },
        }}
      />
    );

    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.queryByText('Alice .')).not.toBeInTheDocument();
  });

  it('falls back to Student when the student first name is blank', () => {
    render(
      <InstructorBookingCard
        booking={{
          id: 'booking-student-fallback',
          booking_date: '2026-03-14',
          start_time: '14:45:00',
          end_time: '15:30:00',
          status: 'CONFIRMED',
          service_name: 'Drums',
          duration_minutes: 45,
          location_type: 'neutral_location',
          student: {
            id: 'student-fallback',
            first_name: '',
            last_initial: '',
          },
        }}
      />
    );

    expect(screen.getByText('Student')).toBeInTheDocument();
  });

  it('falls back to raw date and time strings when parsing fails', () => {
    render(
      <InstructorBookingCard
        booking={{
          id: 'booking-invalid-date',
          booking_date: 'not-a-date',
          start_time: 'bad-start',
          end_time: 'bad-end',
          status: 'CONFIRMED',
          service_name: 'Piano',
          duration_minutes: 45,
          location_type: 'online',
          student: {
            id: 'student-invalid-date',
            first_name: 'Alex',
            last_initial: 'P',
          },
        }}
      />
    );

    expect(screen.getByText('not-a-date')).toBeInTheDocument();
    expect(screen.getByText('bad-start – bad-end')).toBeInTheDocument();
  });
});
