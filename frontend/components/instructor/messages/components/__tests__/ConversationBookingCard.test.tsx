import { render, screen, within } from '@testing-library/react';
import { ConversationBookingCard } from '../ConversationBookingCard';
import { shortenBookingId } from '@/lib/bookingId';

describe('ConversationBookingCard', () => {
  const booking = {
    id: '01KKQKWD9V9QF0J2T0AB3124',
    service_name: 'Piano Lesson',
    date: '2025-01-20',
    start_time: '09:00',
    status: 'CONFIRMED',
  };

  it('renders the primary booking card with the highlighted treatment and shortened id', () => {
    render(
      <ConversationBookingCard
        booking={booking}
        href={`/instructor/bookings/${booking.id}`}
        status="CONFIRMED"
        statusLabel="Confirmed"
        variant="primary"
      />
    );

    const card = screen.getByTestId(`chat-header-booking-card-${booking.id}`);
    expect(card).toHaveClass('bg-(--color-brand-lavender)');
    expect(card).toHaveAttribute('href', `/instructor/bookings/${booking.id}`);
    expect(within(card).getByText('Confirmed')).toBeInTheDocument();
    expect(within(card).getByText(`#${shortenBookingId(booking.id)}`)).toBeInTheDocument();
  });

  it('renders completed bookings with the gray surface variant', () => {
    render(
      <ConversationBookingCard
        booking={booking}
        href={`/instructor/bookings/${booking.id}`}
        status="COMPLETED"
        statusLabel="Completed"
        variant="completed"
      />
    );

    expect(screen.getByTestId(`chat-header-booking-card-${booking.id}`)).toHaveClass('bg-gray-100');
  });
});
