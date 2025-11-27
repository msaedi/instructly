import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import type { BookingResponse } from '@/src/api/generated/instructly.schemas';
import { BookingType, PaymentMethod, PaymentStatus } from '../../types';

// Mock v1 bookings service
const mockFetchBookingDetails = jest.fn();
const mockCancelBookingImperative = jest.fn();

jest.mock('@/src/api/services/bookings', () => ({
  fetchBookingDetails: (...args: unknown[]) => mockFetchBookingDetails(...args),
  cancelBookingImperative: (...args: unknown[]) => mockCancelBookingImperative(...args),
}));

// Type alias for backward compatibility
type Booking = BookingResponse;

const mockQueryClient = {
  invalidateQueries: jest.fn().mockResolvedValue(undefined),
};

jest.mock('@tanstack/react-query', () => {
  const actual = jest.requireActual('@tanstack/react-query');
  return {
    ...actual,
    useQueryClient: () => mockQueryClient,
  };
});

const mockCreateBooking = jest.fn();

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
    createBooking: mockCreateBooking,
    error: null,
    reset: jest.fn(),
  }),
}));

jest.mock('../../hooks/usePaymentFlow', () => {
  const actual = jest.requireActual('../../hooks/usePaymentFlow');
  return {
    ...actual,
    usePaymentFlow: jest.fn(),
  };
});

jest.mock('@/services/api/payments', () => ({
  paymentService: {
    listPaymentMethods: jest.fn(),
    getCreditBalance: jest.fn(),
    createCheckout: jest.fn(),
  },
}));

const mockRefetchCredits = jest.fn().mockResolvedValue(undefined);

function buildPreviewResponse(creditCents = 0) {
  return {
    base_price_cents: 4500,
    student_fee_cents: 0,
    instructor_commission_cents: 0,
    credit_applied_cents: creditCents,
    student_pay_cents: Math.max(0, 4500 - creditCents),
    application_fee_cents: 0,
    top_up_transfer_cents: 0,
    instructor_tier_pct: null,
    line_items: [],
  };
}

jest.mock('../../hooks/usePricingPreview', () => {
  const controller = {
    preview: buildPreviewResponse(0),
    loading: false,
    error: null,
    lastAppliedCreditCents: 0,
    requestPricingPreview: jest.fn().mockResolvedValue(buildPreviewResponse(0)),
    applyCredit: jest.fn().mockImplementation(async (creditCents?: number) =>
      buildPreviewResponse(Math.max(0, Math.round(creditCents ?? 0))),
    ),
    reset: jest.fn(),
    bookingId: null,
  };
  return {
    __esModule: true,
    PricingPreviewContext: React.createContext(null),
    usePricingPreviewController: () => controller,
    mockPreviewController: controller,
  };
});

type MockPreviewController = {
  preview: ReturnType<typeof buildPreviewResponse>;
  loading: boolean;
  error: string | null;
  lastAppliedCreditCents: number;
  requestPricingPreview: jest.Mock;
  applyCredit: jest.Mock;
  reset: jest.Mock;
  bookingId: string | null;
};

const { mockPreviewController } = jest.requireMock('../../hooks/usePricingPreview') as {
  mockPreviewController: MockPreviewController;
};

jest.mock('@/features/shared/payment/hooks/useCredits', () => ({
  useCredits: jest.fn(() => ({
    data: { available: 45, expires_at: null, pending: 0 },
    isLoading: false,
    refetch: mockRefetchCredits,
  })),
}));

import { PaymentSection } from '../PaymentSection';

const mockUsePaymentFlow = jest.requireMock('../../hooks/usePaymentFlow')
  .usePaymentFlow as jest.Mock;
const mockPaymentService = jest.requireMock('@/services/api/payments')
  .paymentService as {
  listPaymentMethods: jest.Mock;
  getCreditBalance: jest.Mock;
  createCheckout: jest.Mock;
};

beforeEach(() => {
  jest.clearAllMocks();
  mockRefetchCredits.mockClear();
  mockQueryClient.invalidateQueries.mockClear();
  mockQueryClient.invalidateQueries.mockResolvedValue(undefined);
  mockCreateBooking.mockReset();
  mockCreateBooking.mockResolvedValue(undefined);
  mockFetchBookingDetails.mockReset();
  mockCancelBookingImperative.mockReset();
  mockPaymentService.listPaymentMethods.mockResolvedValue([
    { id: 'card-1', last4: '1111', brand: 'visa', is_default: true, created_at: '2024-01-01' },
  ]);
  mockPaymentService.getCreditBalance.mockResolvedValue({ available: 0, pending: 0, expires_at: null });
  mockPaymentService.createCheckout.mockResolvedValue({
    success: true,
    payment_intent_id: 'pi_test',
    status: 'succeeded',
    amount: 0,
    application_fee: 0,
    requires_action: false,
  });
  mockUsePaymentFlow.mockReset();
  mockUsePaymentFlow.mockReturnValue({
    currentStep: 'confirmation',
    paymentMethod: PaymentMethod.CREDIT_CARD,
    creditsToUse: 0,
    error: null,
    goToStep: jest.fn(),
    selectPaymentMethod: jest.fn(),
    reset: jest.fn(),
  });
  mockPreviewController.applyCredit.mockClear();
  mockPreviewController.requestPricingPreview.mockClear();
  mockPreviewController.reset.mockClear();
  mockPreviewController.preview = buildPreviewResponse(0);
  mockPreviewController.lastAppliedCreditCents = 0;
});

describe('PaymentSection referral integration', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  afterEach(() => {
    latestReferralProps.current = null;
    latestPaymentConfirmationProps.current = null;
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

    // Mock v1 bookings service to return server booking
    mockFetchBookingDetails.mockResolvedValue(serverBooking);

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
      expect(mockFetchBookingDetails).toHaveBeenCalledWith('order-123');
      expect(latestPaymentConfirmationProps.current).not.toBeNull();
    });

    const confirmationProps = latestPaymentConfirmationProps.current ?? {};

    expect(confirmationProps).toMatchObject({
      referralAppliedCents: 2000,
      referralActive: true,
    });

    const booking = confirmationProps['booking'] as { totalAmount?: number } | undefined;
    expect(booking?.totalAmount).toBeCloseTo(130, 5);
  });
});

describe('PaymentSection credits behavior', () => {
  it('sends checkout for credit-only bookings and refreshes credit balance', async () => {
    mockUsePaymentFlow.mockReturnValue({
      currentStep: 'confirmation',
      paymentMethod: PaymentMethod.CREDITS,
      creditsToUse: 45,
      error: null,
      goToStep: jest.fn(),
      selectPaymentMethod: jest.fn(),
      reset: jest.fn(),
    });

    const createdBooking = {
      id: 'order-credit',
      booking_date: '2024-05-10',
      start_time: '10:00',
      end_time: '11:00',
      duration_minutes: 60,
      total_price: 45,
      hourly_rate: 45,
      instructor_id: 'instructor-1',
      instructor: { first_name: 'Jane', last_initial: 'D' },
      service_name: 'Lesson',
      meeting_location: 'Online',
      student: { id: 'student-1', first_name: 'Stu', last_initial: 'S' },
      status: 'PENDING',
    } as unknown as Booking;

    mockCreateBooking.mockResolvedValue(createdBooking);

    const bookingData = {
      bookingId: 'order-credit',
      instructorId: 'instructor-1',
      instructorName: 'Jane D.',
      lessonType: 'Lesson',
      date: new Date('2024-05-10'),
      startTime: '10:00',
      endTime: '11:00',
      duration: 60,
      location: 'Online',
      basePrice: 45,
      totalAmount: 45,
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
      expect(latestPaymentConfirmationProps.current).not.toBeNull();
    });

    const onConfirm = latestPaymentConfirmationProps.current?.['onConfirm'] as (() => Promise<void>) | undefined;
    const onCreditAmountChange = latestPaymentConfirmationProps.current?.['onCreditAmountChange'] as
      | ((amount: number) => void)
      | undefined;
    expect(typeof onConfirm).toBe('function');
    expect(typeof onCreditAmountChange).toBe('function');

    act(() => {
      onCreditAmountChange?.(45);
    });

    await act(async () => {
      await (onConfirm?.() ?? Promise.resolve());
    });

    expect(mockPaymentService.createCheckout).toHaveBeenCalledWith({
      booking_id: createdBooking.id,
      payment_method_id: undefined,
      save_payment_method: false,
      requested_credit_cents: 4500,
    });
    // Verify credits are refreshed after checkout via React Query
    expect(mockQueryClient.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['payments', 'credits'] });
    expect(mockRefetchCredits).toHaveBeenCalled();
  });

  it('applies slider credits even when payment flow reports zero usage', async () => {
    mockUsePaymentFlow.mockReturnValue({
      currentStep: 'confirmation',
      paymentMethod: PaymentMethod.MIXED,
      creditsToUse: 0,
      error: null,
      goToStep: jest.fn(),
      selectPaymentMethod: jest.fn(),
      reset: jest.fn(),
    });

    const createdBooking = {
      id: 'order-slider',
      booking_date: '2024-06-01',
      start_time: '09:00',
      end_time: '10:00',
      duration_minutes: 60,
      total_price: 45,
      hourly_rate: 45,
      instructor_id: 'instructor-2',
      instructor: { first_name: 'Sam', last_initial: 'K' },
      service_name: 'Lesson',
      meeting_location: 'Online',
      student: { id: 'student-2', first_name: 'Casey', last_initial: 'W' },
      status: 'PENDING',
    } as unknown as Booking;

    mockCreateBooking.mockResolvedValue(createdBooking);

    const bookingData = {
      bookingId: 'order-slider',
      instructorId: 'instructor-2',
      instructorName: 'Sam K.',
      lessonType: 'Lesson',
      date: new Date('2024-06-01'),
      startTime: '09:00',
      endTime: '10:00',
      duration: 60,
      location: 'Online',
      basePrice: 45,
      totalAmount: 45,
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
      expect(latestPaymentConfirmationProps.current).not.toBeNull();
    });

    const confirmationProps = latestPaymentConfirmationProps.current ?? {};
    const onConfirm = confirmationProps['onConfirm'] as (() => Promise<void>) | undefined;
    const onCreditAmountChange = confirmationProps['onCreditAmountChange'] as ((amount: number) => void) | undefined;

    act(() => {
      onCreditAmountChange?.(45);
    });

    await act(async () => {
      await (onConfirm?.() ?? Promise.resolve());
    });

    expect(mockPaymentService.createCheckout).toHaveBeenCalledWith({
      booking_id: createdBooking.id,
      payment_method_id: undefined,
      save_payment_method: false,
      requested_credit_cents: 4500,
    });
    expect(mockQueryClient.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['payments', 'credits'] });
    expect(mockRefetchCredits).toHaveBeenCalled();
  });
});
