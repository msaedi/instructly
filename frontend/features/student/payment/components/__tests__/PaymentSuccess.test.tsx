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

  it('renders standard view when isPackage is true but packageDetails is missing', () => {
    render(
      <PaymentSuccess
        booking={baseBooking}
        confirmationNumber="STD456"
        cardLast4="5555"
        isPackage
      />
    );

    // Should fall through to standard booking view, not package view
    expect(screen.getByText('Lesson Reserved!')).toBeInTheDocument();
    expect(screen.queryByText('Package Purchased!')).not.toBeInTheDocument();
  });

  it('hides free cancellation section when freeCancellationUntil is not provided on standard booking', () => {
    render(
      <PaymentSuccess
        booking={{ ...baseBooking, freeCancellationUntil: undefined }}
        confirmationNumber="NOCANCEL"
        cardLast4="3333"
      />
    );

    expect(screen.queryByText(/Free cancellation until/)).not.toBeInTheDocument();
  });

  it('uses fallback date when freeCancellationUntil is undefined in non-last-minute charge text', () => {
    // When freeCancellationUntil is undefined on a non-last-minute booking, the
    // payment info section uses `new Date()` as fallback for the charge date.
    render(
      <PaymentSuccess
        booking={{ ...baseBooking, freeCancellationUntil: undefined }}
        confirmationNumber="FALLBACK1"
        cardLast4="6666"
      />
    );

    // Should still show "will be charged" text (non-last-minute)
    expect(screen.getByText(/will be charged/)).toBeInTheDocument();
    // Should show a date and time (using new Date() fallback)
    expect(screen.getByText(/24hrs before/)).toBeInTheDocument();
  });

  it('renders package flow links correctly', () => {
    render(
      <PaymentSuccess
        booking={baseBooking}
        confirmationNumber="PKG2"
        cardLast4="7777"
        isPackage
        packageDetails={{ lessonsCount: 3, expiryDate: new Date('2025-07-15T00:00:00Z') }}
      />
    );

    expect(screen.getByRole('link', { name: /Book First Lesson/i })).toHaveAttribute(
      'href',
      `/instructors/${baseBooking.instructorId}/book`
    );
    expect(screen.getByRole('link', { name: /View All Credits/i })).toHaveAttribute(
      'href',
      '/student/dashboard/credits'
    );
  });

  it('renders package details with correct lesson count and expiry', () => {
    render(
      <PaymentSuccess
        booking={{ ...baseBooking, lessonType: 'Violin', instructorName: 'Bob S.' }}
        confirmationNumber="PKG3"
        cardLast4="8888"
        isPackage
        packageDetails={{ lessonsCount: 10, expiryDate: new Date('2025-12-01T00:00:00Z') }}
      />
    );

    expect(screen.getByText(/10 Violin Credits/)).toBeInTheDocument();
    expect(screen.getByText(/with Bob S./)).toBeInTheDocument();
    expect(screen.getByText(/December 1, 2025/)).toBeInTheDocument();
  });

  it('shows email confirmation message', () => {
    render(
      <PaymentSuccess
        booking={baseBooking}
        confirmationNumber="EMAIL1"
        cardLast4="1212"
      />
    );

    expect(screen.getByText('Confirmation email sent')).toBeInTheDocument();
  });

  it('displays booking details correctly', () => {
    render(
      <PaymentSuccess
        booking={baseBooking}
        confirmationNumber="DET1"
        cardLast4="9090"
      />
    );

    // Instructor and lesson type
    expect(screen.getByText(/Jane D\. - Piano/)).toBeInTheDocument();
    // Time range
    expect(screen.getByText(/10:00 - 11:00/)).toBeInTheDocument();
    // Location
    expect(screen.getByText('NYC')).toBeInTheDocument();
  });
});
