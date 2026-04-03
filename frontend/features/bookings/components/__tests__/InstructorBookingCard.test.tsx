import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InstructorBookingCard } from '../InstructorBookingCard';

const mockPush = jest.fn();

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

describe('InstructorBookingCard', () => {
  beforeEach(() => {
    mockPush.mockReset();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

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
          location_address: '123 Main St, Brooklyn, NY 11201',
          meeting_location: null,
          booking_end_utc: '2026-04-02T19:15:00Z',
          no_show_reported_at: null,
          student: {
            id: '01STUDENT123456789ABCDEFGH',
            first_name: 'David',
            last_initial: 'M',
          },
        }}
      />
    );

    const header = screen.getByTestId('booking-card-header');
    const badge = within(header).getByText('Confirmed');
    expect(badge).toHaveClass('bg-emerald-50', 'text-emerald-700');
    expect(within(header).getByText('David M.')).toBeInTheDocument();
    expect(screen.queryByText(/^Piano$/)).not.toBeInTheDocument();
    expect(screen.getByText('Sat, Mar 14')).toBeInTheDocument();
    expect(screen.getByText('2:45 PM – 3:30 PM')).toBeInTheDocument();
    expect(screen.getByText('45 min · Piano')).toBeInTheDocument();
    expect(screen.getByTestId('booking-location-link')).toHaveTextContent(
      '123 Main St, Brooklyn, NY 11201'
    );
    expect(screen.getByTestId('booking-location-link')).toHaveAttribute(
      'href',
      'https://www.google.com/maps/search/?api=1&query=123%20Main%20St%2C%20Brooklyn%2C%20NY%2011201'
    );
    expect(screen.getByTestId('booking-location-link')).toHaveAttribute('target', '_blank');
    expect(screen.getByTestId('booking-action-needed-badge')).toHaveTextContent('Action needed');

    expect(
      screen.getByRole('link', { name: 'View lesson details for David M.' })
    ).toBeInTheDocument();
    expect(screen.getByText('Lesson details ›')).toBeInTheDocument();
  });

  it('navigates to the booking detail page when the card surface is clicked', async () => {
    const user = userEvent.setup();

    render(
      <InstructorBookingCard
        booking={{
          id: 'booking-click-target',
          booking_date: '2026-03-14',
          start_time: '14:45:00',
          end_time: '15:30:00',
          status: 'CONFIRMED',
          service_name: 'Piano',
          duration_minutes: 45,
          location_type: 'student_location',
          location_address: '123 Main St, Brooklyn, NY 11201',
          meeting_location: null,
          booking_end_utc: '2026-04-02T19:15:00Z',
          no_show_reported_at: null,
          student: {
            id: 'student-click-target',
            first_name: 'David',
            last_initial: 'M',
          },
        }}
      />
    );

    await user.click(screen.getByTestId('booking-card'));

    expect(mockPush).toHaveBeenCalledWith('/instructor/bookings/booking-click-target');
  });

  it('opens the address link without triggering card navigation', async () => {
    const user = userEvent.setup();

    render(
      <InstructorBookingCard
        booking={{
          id: 'booking-map-target',
          booking_date: '2026-03-14',
          start_time: '14:45:00',
          end_time: '15:30:00',
          status: 'CONFIRMED',
          service_name: 'Piano',
          duration_minutes: 45,
          location_type: 'student_location',
          location_address: '123 Main St, Brooklyn, NY 11201',
          meeting_location: null,
          booking_end_utc: '2026-04-02T19:15:00Z',
          no_show_reported_at: null,
          student: {
            id: 'student-map-target',
            first_name: 'David',
            last_initial: 'M',
          },
        }}
      />
    );

    await user.click(screen.getByTestId('booking-location-link'));

    expect(mockPush).not.toHaveBeenCalled();
    expect(screen.getByTestId('booking-location-link')).toHaveAttribute(
      'href',
      'https://www.google.com/maps/search/?api=1&query=123%20Main%20St%2C%20Brooklyn%2C%20NY%2011201'
    );
  });

  it('navigates to the booking detail page from keyboard activation on the card', () => {
    render(
      <InstructorBookingCard
        booking={{
          id: 'booking-keyboard-target',
          booking_date: '2026-03-14',
          start_time: '14:45:00',
          end_time: '15:30:00',
          status: 'CONFIRMED',
          service_name: 'Piano',
          duration_minutes: 45,
          location_type: 'student_location',
          location_address: '123 Main St, Brooklyn, NY 11201',
          meeting_location: null,
          booking_end_utc: '2026-04-02T19:15:00Z',
          no_show_reported_at: null,
          student: {
            id: 'student-keyboard-target',
            first_name: 'David',
            last_initial: 'M',
          },
        }}
      />
    );

    fireEvent.keyDown(screen.getByRole('link', { name: 'View lesson details for David M.' }), {
      key: 'Enter',
    });

    expect(mockPush).toHaveBeenCalledWith('/instructor/bookings/booking-keyboard-target');
  });

  it('prevents address-link keyboard interaction from triggering card navigation', () => {
    render(
      <InstructorBookingCard
        booking={{
          id: 'booking-map-keyboard-target',
          booking_date: '2026-03-14',
          start_time: '14:45:00',
          end_time: '15:30:00',
          status: 'CONFIRMED',
          service_name: 'Piano',
          duration_minutes: 45,
          location_type: 'student_location',
          location_address: '123 Main St, Brooklyn, NY 11201',
          meeting_location: null,
          booking_end_utc: '2026-04-02T19:15:00Z',
          no_show_reported_at: null,
          student: {
            id: 'student-map-keyboard-target',
            first_name: 'David',
            last_initial: 'M',
          },
        }}
      />
    );

    fireEvent.keyDown(screen.getByTestId('booking-location-link'), { key: 'Enter' });

    expect(mockPush).not.toHaveBeenCalled();
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
          location_address: null,
          meeting_location: null,
          booking_end_utc: null,
          no_show_reported_at: null,
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
    expect(screen.queryByTestId('booking-location-link')).not.toBeInTheDocument();
    expect(screen.getByText('Online')).toBeInTheDocument();
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
          location_address: null,
          meeting_location: null,
          booking_end_utc: null,
          no_show_reported_at: null,
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

  it('falls back to a non-link location label when the stored address is generic', () => {
    render(
      <InstructorBookingCard
        booking={{
          id: 'booking-generic-location',
          booking_date: '2026-03-14',
          start_time: '14:45:00',
          end_time: '15:30:00',
          status: 'CONFIRMED',
          service_name: 'Guitar',
          duration_minutes: 45,
          location_type: 'instructor_location',
          location_address: 'Instructor address shared after booking confirmation',
          meeting_location: null,
          booking_end_utc: null,
          no_show_reported_at: null,
          student: {
            id: 'student-generic-location',
            first_name: 'Sam',
            last_initial: 'R',
          },
        }}
      />
    );

    expect(screen.queryByTestId('booking-location-link')).not.toBeInTheDocument();
    expect(screen.getByText("At instructor's location")).toBeInTheDocument();
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
          location_address: null,
          meeting_location: null,
          booking_end_utc: null,
          no_show_reported_at: null,
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

  it('shows the action-needed badge when booking_end_utc is missing but the local lesson end time has passed', () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-04-02T21:00:00Z'));

    render(
      <InstructorBookingCard
        booking={{
          id: 'booking-local-end-fallback',
          booking_date: '2026-04-02',
          start_time: '18:15:00',
          end_time: '19:15:00',
          status: 'CONFIRMED',
          service_name: 'Piano',
          duration_minutes: 60,
          location_type: 'student_location',
          location_address: '123 Main St, Brooklyn, NY 11201',
          meeting_location: null,
          booking_end_utc: null,
          no_show_reported_at: null,
          student: {
            id: 'student-local-end-fallback',
            first_name: 'Emma',
            last_initial: 'J',
          },
        }}
      />
    );

    expect(screen.getByTestId('booking-action-needed-badge')).toHaveTextContent('Action needed');
  });

  it('hides the action-needed badge once a no-show has already been reported', () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-04-02T21:00:00Z'));

    render(
      <InstructorBookingCard
        booking={{
          id: 'booking-no-show-reported',
          booking_date: '2026-04-02',
          start_time: '18:15:00',
          end_time: '19:15:00',
          status: 'CONFIRMED',
          service_name: 'Piano',
          duration_minutes: 60,
          location_type: 'student_location',
          location_address: '123 Main St, Brooklyn, NY 11201',
          meeting_location: null,
          booking_end_utc: '2026-04-02T19:15:00Z',
          no_show_reported_at: '2026-04-02T20:00:00Z',
          student: {
            id: 'student-no-show-reported',
            first_name: 'Emma',
            last_initial: 'J',
          },
        }}
      />
    );

    expect(screen.queryByTestId('booking-action-needed-badge')).not.toBeInTheDocument();
  });
});
