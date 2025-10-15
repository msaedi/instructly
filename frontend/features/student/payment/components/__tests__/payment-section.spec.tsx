import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import type { Booking } from '@/features/shared/api/client';
import { protectedApi } from '@/features/shared/api/client';
import { BookingType, PaymentMethod, PaymentStatus } from '../../types';

const latestReferralProps: {
  current:
    | null
    | {
      onApplied?: (cents: number) => void;
      onRefreshOrderSummary?: () => Promise<void> | void;
    };
} = { current: null };

const latestPaymentConfirmationProps: { current: Record<string, unknown> | null } = { current: null };

jest.mock('@/components/referrals/CheckoutApplyReferral', () => ({
  __esModule: true,
  default: (props: { onApplied?: (cents: number) => void; onRefreshOrderSummary?: () => Promise<void> | void }) => {
    latestReferralProps.current = props;
    return (
      <button
        type="button"
        data-testid="mock-apply-referral"
        onClick={async () => {
          props.onApplied?.(2000);
          await props.onRefreshOrderSummary?.();
        }}
      >
        apply referral
      </button>
    );
  },
}));

jest.mock('../PaymentMethodSelection', () => ({
  __esModule: true,
  default: () => <div data-testid="mock-payment-method-selection" />,
}));

jest.mock('../PaymentProcessing', () => ({
  __esModule: true,
  default: () => <div data-testid="mock-payment-processing" />,
}));

jest.mock('../PaymentSuccess', () => ({
  __esModule: true,
  default: () => <div data-testid="mock-payment-success" />,
}));

jest.mock('../PaymentConfirmation', () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => {
    latestPaymentConfirmationProps.current = props;
    return <div data-testid="mock-payment-confirmation" />;
  },
}));

jest.mock('@/features/student/booking/hooks/useCreateBooking', () => ({
  useCreateBooking: () => ({
    createBooking: jest.fn(),
    error: null,
    reset: jest.fn(),
  }),
}));

jest.mock('../../hooks/usePaymentFlow', () => {
  const actual = jest.requireActual('../../hooks/usePaymentFlow');
  return {
    ...actual,
    usePaymentFlow: () => ({
      currentStep: actual.PaymentStep.CONFIRMATION,
      paymentMethod: PaymentMethod.CREDIT_CARD,
      creditsToUse: 0,
      error: null,
      goToStep: jest.fn(),
      selectPaymentMethod: jest.fn(),
      reset: jest.fn(),
    }),
  };
});

jest.mock('@/services/api/payments', () => ({
  paymentService: {
    listPaymentMethods: jest.fn().mockResolvedValue([
      { id: 'card-1', last4: '1111', brand: 'visa', is_default: true, created_at: '2024-01-01' },
    ]),
    getCreditBalance: jest.fn().mockResolvedValue({ available: 0, pending: 0, expires_at: null }),
  },
}));

import { PaymentSection } from '../PaymentSection';

describe('PaymentSection referral integration', () => {
  afterEach(() => {
    latestReferralProps.current = null;
    latestPaymentConfirmationProps.current = null;
    jest.clearAllMocks();
  });

  it('refreshes booking totals from the server and disables promo inputs when referral applies', async () => {
    const serverBooking = {
      id: 'order-123',
      booking_date: '2024-05-10',
      start_time: '10:00',
      end_time: '11:00',
      duration_minutes: 60,
      total_price: 130,
      hourly_rate: 100,
      instructor_id: 'instructor-1',
      instructor: { first_name: 'Jane', last_initial: 'D' },
      service_name: 'Guitar Lesson',
      meeting_location: 'Online',
      student: { id: 'student-1', first_name: 'Stu', last_initial: 'S' },
      status: 'CONFIRMED',
      cancellation_reason: null,
      cancelled_at: null,
      cancelled_by_id: null,
      completed_at: null,
      confirmed_at: null,
      created_at: '2024-05-01T00:00:00Z',
      instructor_note: null,
      student_note: null,
      service_area: null,
    } as unknown as Booking;

    const getBookingSpy = jest.spyOn(protectedApi, 'getBooking').mockResolvedValue({ data: serverBooking, status: 200 });

    const bookingData = {
      bookingId: 'order-123',
      instructorId: 'instructor-1',
      instructorName: 'Jane D.',
      lessonType: 'Lesson',
      date: new Date('2024-05-10'),
      startTime: '10:00',
      endTime: '11:00',
      duration: 60,
      location: 'Online',
      basePrice: 100,
      totalAmount: 120,
      bookingType: BookingType.STANDARD,
      paymentStatus: PaymentStatus.PENDING,
    } as const;

    render(
      <PaymentSection
        bookingData={bookingData}
        onSuccess={jest.fn()}
        onError={jest.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('mock-apply-referral')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('mock-apply-referral'));

    await waitFor(() => {
      expect(getBookingSpy).toHaveBeenCalledWith('order-123');
      expect(latestPaymentConfirmationProps.current).not.toBeNull();
    });

    const confirmationProps = latestPaymentConfirmationProps.current ?? {};

    expect(confirmationProps).toMatchObject({
      referralAppliedCents: 2000,
      referralActive: true,
    });

    const booking = confirmationProps['booking'] as { totalAmount?: number } | undefined;
    expect(booking?.totalAmount).toBeCloseTo(130, 5);

    getBookingSpy.mockRestore();
  });
});
