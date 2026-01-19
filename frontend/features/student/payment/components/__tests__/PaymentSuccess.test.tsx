import { render, screen } from '@testing-library/react';
import PaymentSuccess from '../PaymentSuccess';
import { BookingType, PAYMENT_STATUS, type BookingPayment } from '../../types';

const baseBooking: BookingPayment = {
  bookingId: 'booking-1',
  instructorId: 'instructor-1',
  instructorName: 'Jane D.',
  lessonType: 'Piano',
  date: new Date('2025-01-01T00:00:00Z'),
  startTime: '10:00',
  endTime: '11:00',
  duration: 60,
  location: 'NYC',
  basePrice: 100,
  totalAmount: 100,
  bookingType: BookingType.STANDARD,
  paymentStatus: PAYMENT_STATUS.SCHEDULED,
  freeCancellationUntil: new Date('2024-12-31T10:00:00Z'),
};

describe('PaymentSuccess', () => {
  it('renders standard booking confirmation', () => {
    render(
      <PaymentSuccess
        booking={baseBooking}
        confirmationNumber="ABC123"
        cardLast4="4242"
      />
    );

    expect(screen.getByText('Lesson Reserved!')).toBeInTheDocument();
    expect(screen.getByText('Confirmation #ABC123')).toBeInTheDocument();
    expect(screen.getByText(/will be charged/)).toBeInTheDocument();
  });

  it('renders last-minute booking confirmation', () => {
    render(
      <PaymentSuccess
        booking={{ ...baseBooking, bookingType: BookingType.LAST_MINUTE, freeCancellationUntil: undefined }}
        confirmationNumber="XYZ789"
        cardLast4="1111"
      />
    );

    expect(screen.getByText('Booking Confirmed!')).toBeInTheDocument();
    expect(screen.getByText(/charged \$100.00/)).toBeInTheDocument();
  });

  it('renders cancellation info when provided', () => {
    render(
      <PaymentSuccess
        booking={baseBooking}
        confirmationNumber="ABC123"
        cardLast4="4242"
      />
    );

    expect(screen.getByText(/Free cancellation until/)).toBeInTheDocument();
  });

  it('renders package purchase flow', () => {
    render(
      <PaymentSuccess
        booking={baseBooking}
        confirmationNumber="PKG1"
        cardLast4="4242"
        isPackage
        packageDetails={{ lessonsCount: 5, expiryDate: new Date('2025-06-01T00:00:00Z') }}
      />
    );

    expect(screen.getByText('Package Purchased!')).toBeInTheDocument();
    expect(screen.getByText(/Credits added to account/)).toBeInTheDocument();
  });

  it('renders primary action links', () => {
    render(
      <PaymentSuccess
        booking={baseBooking}
        confirmationNumber="ABC123"
        cardLast4="4242"
      />
    );

    expect(screen.getByRole('link', { name: /View My Lessons/i })).toHaveAttribute('href', '/student/lessons');
    expect(screen.getByRole('link', { name: /Book Another Lesson/i })).toHaveAttribute('href', '/search');
  });
});
