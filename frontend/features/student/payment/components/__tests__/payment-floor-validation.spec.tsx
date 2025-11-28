import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React, { useState } from 'react';
import PaymentConfirmation from '../PaymentConfirmation';
import { PaymentMethod, PaymentStatus, BookingType, type BookingPayment } from '../../types';

jest.mock('@/features/shared/api/client', () => ({
  protectedApi: {
    getBookings: jest.fn().mockResolvedValue({ status: 200, data: { items: [] } }),
  },
}));

jest.mock('@/features/shared/api/http', () => ({
  httpJson: jest.fn().mockResolvedValue({ services: [] }),
}));

jest.mock('@/features/shared/api/schemas/instructorProfile', () => ({
  loadInstructorProfileSchema: jest.fn(),
}));

jest.mock('@/lib/apiBase', () => ({
  withApiBase: (url: string) => url,
}));

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingFloors: () => ({
    floors: { private_in_person: 8000, private_remote: 6500 },
    config: {
      student_fee_pct: 0.12,
      instructor_tiers: [{ min: 1, max: 4, pct: 0.15 }],
      price_floor_cents: { private_in_person: 8000, private_remote: 6500 },
    },
    isLoading: false,
    error: null,
  }),
  usePricingConfig: () => ({
    config: {
      student_fee_pct: 0.12,
      instructor_tiers: [{ min: 1, max: 4, pct: 0.15 }],
      price_floor_cents: { private_in_person: 8000, private_remote: 6500 },
    },
    isLoading: false,
    error: null,
  }),
}));

jest.mock('@/features/student/booking/components/TimeSelectionModal', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

const baseBooking: BookingPayment & { metadata?: Record<string, unknown> } = {
  bookingId: 'booking-123',
  instructorId: 'inst-1',
  instructorName: 'Jane D.',
  lessonType: 'Piano',
  date: new Date('2025-01-01'),
  startTime: '10:00',
  endTime: '11:00',
  duration: 60,
  location: '',
  basePrice: 90,
  totalAmount: 100,
  bookingType: BookingType.STANDARD,
  paymentStatus: PaymentStatus.PENDING,
  metadata: { modality: 'in_person' },
};

function PaymentConfirmationHarness() {
  const [floorMessage, setFloorMessage] = useState<string | null>(
    'Minimum price for in-person 60-minute private session is $80.00 (current $60.00).'
  );

  return (
    <PaymentConfirmation
      booking={baseBooking}
      paymentMethod={PaymentMethod.CREDIT_CARD}
      floorViolationMessage={floorMessage}
      onClearFloorViolation={() => setFloorMessage(null)}
      onConfirm={jest.fn()}
      onBack={jest.fn()}
    />
  );
}

describe('PaymentConfirmation price floor handling', () => {
  it('shows server-provided price floor message and clears after correction', async () => {
    render(<PaymentConfirmationHarness />);

    await waitFor(() => {
      expect(
        screen.getByText(/Minimum price for in-person 60-minute private session/i)
      ).toBeInTheDocument();
    });

    const submitButton = screen.getByRole('button', { name: /Price must meet minimum/i });
    expect(submitButton).toBeDisabled();

    fireEvent.click(screen.getByLabelText(/Online/i));

    await waitFor(() => {
      expect(
        screen.queryByText(/Minimum price for in-person 60-minute private session/i)
      ).not.toBeInTheDocument();
    });

    const enabledButton = screen.getByRole('button', { name: /Book now!/i });
    expect(enabledButton).not.toBeDisabled();
  });
});
