import React, { useMemo, useState } from 'react';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import PaymentConfirmation from '../PaymentConfirmation';
import { PaymentSection } from '../PaymentSection';
import { BookingPayment, PaymentMethod, PaymentStatus } from '../../types';
import { BookingType } from '@/features/shared/types/booking';
import { PricingPreviewContext } from '../../hooks/usePricingPreview';
import {
  fetchPricingPreview,
  fetchPricingPreviewQuote,
  type PricingPreviewResponse,
} from '@/lib/api/pricing';

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingFloors: () => ({ floors: null }),
  usePricingConfig: () => ({ config: { student_fee_pct: 0.12 }, isLoading: false, error: null }),
}));

jest.mock('@/features/shared/api/client', () => ({
  protectedApi: {
    getBooking: jest.fn().mockResolvedValue({ data: null, status: 200 }),
    getBookings: jest.fn().mockResolvedValue({ data: { items: [] }, status: 200 }),
    cancelBooking: jest.fn().mockResolvedValue({ data: null, status: 200 }),
  },
}));

jest.mock('@/features/shared/api/http', () => ({
  httpJson: jest.fn().mockResolvedValue({}),
}));

jest.mock('@/lib/apiBase', () => ({
  withApiBase: (path: string) => path,
}));

jest.mock('@/features/shared/api/schemas/instructorProfile', () => ({
  loadInstructorProfileSchema: jest.fn().mockResolvedValue({ services: [] }),
}));

jest.mock('@/features/student/booking/components/TimeSelectionModal', () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock('@/components/referrals/CheckoutApplyReferral', () => ({
  __esModule: true,
  default: () => <div data-testid="mock-referral" />,
}));

jest.mock('../PaymentMethodSelection', () => ({
  __esModule: true,
  default: () => <div data-testid="mock-method-selection" />,
}));

jest.mock('../PaymentProcessing', () => ({
  __esModule: true,
  default: () => <div data-testid="mock-processing" />,
}));

jest.mock('../PaymentSuccess', () => ({
  __esModule: true,
  default: () => <div data-testid="mock-success" />,
}));

jest.mock('@/services/api/payments', () => ({
  paymentService: {
    listPaymentMethods: jest.fn().mockResolvedValue([
      { id: 'card-1', last4: '4242', brand: 'visa', is_default: true, created_at: '2024-01-01' },
    ]),
    getCreditBalance: jest.fn().mockResolvedValue({ available: 0, pending: 0, expires_at: null }),
  },
}));

jest.mock('@/lib/api/pricing', () => {
  const actual = jest.requireActual('@/lib/api/pricing');
  return {
    ...actual,
    fetchPricingPreview: jest.fn(),
    fetchPricingPreviewQuote: jest.fn(),
  };
});

jest.mock('@/components/forms/PlacesAutocompleteInput', () => {
  type MockProps = React.ComponentPropsWithoutRef<'input'> & {
    value?: string;
    onValueChange?: (value: string) => void;
    inputClassName?: string;
    onSelectSuggestion?: (value: string) => void;
    containerClassName?: string;
    inputProps?: unknown;
  };

  const MockPlacesAutocompleteInput = React.forwardRef<HTMLInputElement, MockProps>(
    (
      {
        onValueChange,
        value,
        inputClassName,
        className,
        onChange,
        onSelectSuggestion: _ignored,
        containerClassName: _containerClassName,
        inputProps: _inputProps,
        ...rest
      },
      ref,
    ) => (
      <input
        ref={ref}
        {...rest}
        className={inputClassName ?? className}
        value={value ?? ''}
        onChange={(event) => {
          onValueChange?.(event.target.value);
          onChange?.(event);
        }}
      />
    ),
  );
  MockPlacesAutocompleteInput.displayName = 'MockPlacesAutocompleteInput';

  return { PlacesAutocompleteInput: MockPlacesAutocompleteInput };
});

const PREVIEW_WITH_CREDIT: PricingPreviewResponse = {
  base_price_cents: 22500,
  student_fee_cents: 2700,
  instructor_commission_cents: 0,
  credit_applied_cents: 4500,
  student_pay_cents: 20700,
  application_fee_cents: 0,
  top_up_transfer_cents: 0,
  instructor_tier_pct: null,
  line_items: [
    { label: 'Booking Protection (12%)', amount_cents: 2700 },
    { label: 'Credit', amount_cents: -4500 },
  ],
};

const PREVIEW_NO_CREDIT: PricingPreviewResponse = {
  ...PREVIEW_WITH_CREDIT,
  credit_applied_cents: 0,
  student_pay_cents: 25200,
  line_items: [{ label: 'Booking Protection (12%)', amount_cents: 2700 }],
};

const PREVIEW_BY_CREDIT: Record<number, PricingPreviewResponse> = {
  0: PREVIEW_NO_CREDIT,
  4500: PREVIEW_WITH_CREDIT,
};

const fetchPricingPreviewMock = fetchPricingPreview as jest.MockedFunction<typeof fetchPricingPreview>;
const fetchPricingPreviewQuoteMock = fetchPricingPreviewQuote as jest.MockedFunction<typeof fetchPricingPreviewQuote>;

const BASE_BOOKING: BookingPayment & {
  serviceId?: string;
  metadata?: Record<string, unknown>;
} = {
  bookingId: 'booking-1',
  instructorId: 'inst-1',
  instructorName: 'Jordan Instructor',
  lessonType: 'Lesson',
  date: new Date('2025-05-06T12:00:00Z'),
  startTime: '02:00 PM',
  endTime: '03:30 PM',
  duration: 90,
  location: 'Online',
  basePrice: 225,
  totalAmount: 252,
  bookingType: BookingType.STANDARD,
  paymentStatus: PaymentStatus.PENDING,
  serviceId: 'svc-1',
  metadata: {
    serviceId: 'svc-1',
    modality: 'remote',
  },
};

const renderPaymentSectionForSummary = (overrides: Partial<typeof BASE_BOOKING> = {}) => {
  const mergedMetadata = {
    ...(BASE_BOOKING.metadata ?? {}),
    ...(overrides.metadata ?? {}),
  };

  return render(
    <PaymentSection
      bookingData={{
        ...BASE_BOOKING,
        ...overrides,
        metadata: mergedMetadata,
      }}
      onSuccess={jest.fn()}
      onError={jest.fn()}
      showPaymentMethodInline
    />
  );
};

describe('Payment summary integration with pricing preview', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('renders server totals when quoting without a booking id', async () => {
    fetchPricingPreviewMock.mockImplementation(() => {
      throw new Error('fetchPricingPreview should not be called');
    });
    fetchPricingPreviewQuoteMock.mockResolvedValue({
      base_price_cents: 7500,
      student_fee_cents: 900,
      instructor_commission_cents: 0,
      credit_applied_cents: 0,
      student_pay_cents: 8400,
      application_fee_cents: 0,
      top_up_transfer_cents: 0,
      instructor_tier_pct: null,
      line_items: [{ label: 'Booking Protection (12%)', amount_cents: 900 }],
    });

    renderPaymentSectionForSummary({ bookingId: '' });

    await waitFor(() => {
      expect(fetchPricingPreviewQuoteMock).toHaveBeenCalledTimes(1);
    });

    const paymentDetailsHeading = await screen.findByText('Payment details');
    const paymentDetails = paymentDetailsHeading.closest('div');
    expect(paymentDetails).toBeTruthy();
    const scoped = within(paymentDetails as HTMLElement);
    expect(scoped.getByText('Lesson (90 min)')).toBeInTheDocument();
    expect(scoped.getByText('$75.00')).toBeInTheDocument();
    expect(scoped.getByText('Booking Protection (12%)')).toBeInTheDocument();
    expect(scoped.getByText('$9.00')).toBeInTheDocument();
    expect(scoped.getByText('Total')).toBeInTheDocument();
    expect(scoped.getByText('$84.00')).toBeInTheDocument();
  });

  it('renders server totals when a booking id is available', async () => {
    fetchPricingPreviewQuoteMock.mockImplementation(() => {
      throw new Error('fetchPricingPreviewQuote should not be called');
    });
    fetchPricingPreviewMock.mockResolvedValue({
      base_price_cents: 9100,
      student_fee_cents: 1092,
      instructor_commission_cents: 0,
      credit_applied_cents: 0,
      student_pay_cents: 10192,
      application_fee_cents: 0,
      top_up_transfer_cents: 0,
      instructor_tier_pct: null,
      line_items: [{ label: 'Booking Protection (12%)', amount_cents: 1092 }],
    });

    renderPaymentSectionForSummary();

    await waitFor(() => {
      expect(fetchPricingPreviewMock).toHaveBeenCalledTimes(1);
    });

    const paymentDetailsHeading = await screen.findByText('Payment details');
    const paymentDetails = paymentDetailsHeading.closest('div');
    expect(paymentDetails).toBeTruthy();
    const scoped = within(paymentDetails as HTMLElement);
    expect(scoped.getByText('Lesson (90 min)')).toBeInTheDocument();
    expect(scoped.getByText('$91.00')).toBeInTheDocument();
    expect(scoped.getByText('Booking Protection (12%)')).toBeInTheDocument();
    expect(scoped.getByText('$10.92')).toBeInTheDocument();
    expect(scoped.getByText('Total')).toBeInTheDocument();
    expect(scoped.getByText('$101.92')).toBeInTheDocument();
  });

  it('shows a skeleton while pricing preview is loading', async () => {
    jest.useFakeTimers();
    fetchPricingPreviewMock.mockImplementation(
      () => new Promise<PricingPreviewResponse>(() => {
        // Intentionally never resolve to simulate in-flight request
      }),
    );

    renderPaymentSectionForSummary();

    act(() => {
      jest.advanceTimersByTime(250);
    });

    await waitFor(() => {
      expect(fetchPricingPreviewMock).toHaveBeenCalledTimes(1);
    });

    const paymentDetailsHeading = await screen.findByText('Payment details');
    const paymentDetails = paymentDetailsHeading.closest('div');
    expect(paymentDetails).toBeTruthy();
    const scoped = within(paymentDetails as HTMLElement);
    expect(scoped.getAllByTestId('pricing-preview-skeleton').length).toBeGreaterThan(0);
    expect(scoped.queryByText('—')).not.toBeInTheDocument();
  });
});

function PaymentSummaryHarness() {
  const [preview, setPreview] = useState(PREVIEW_WITH_CREDIT);

  const controller = useMemo(() => ({
    preview,
    loading: false,
    error: null,
    lastAppliedCreditCents: preview?.credit_applied_cents ?? 0,
    requestPricingPreview: async () => preview,
    applyCredit: async (creditCents: number) => {
      const normalized = Math.max(0, Math.round(creditCents));
      const next: PricingPreviewResponse = PREVIEW_BY_CREDIT[normalized] ?? PREVIEW_WITH_CREDIT;
      setPreview(next);
      return next;
    },
    reset: () => {
      setPreview(PREVIEW_WITH_CREDIT);
    },
    bookingId: 'booking-1',
  }), [preview]);

  return (
    <PricingPreviewContext.Provider value={controller}>
      <PaymentConfirmation
        booking={BASE_BOOKING}
        paymentMethod={PaymentMethod.MIXED}
        cardLast4="4242"
        onConfirm={jest.fn()}
        onBack={jest.fn()}
        onChangePaymentMethod={jest.fn()}
        onCreditToggle={jest.fn()}
        onCreditAmountChange={(amount) => {
          void controller.applyCredit(Math.round(amount * 100));
        }}
        availableCredits={100}
        creditsUsed={(preview?.credit_applied_cents ?? 0) / 100}
        creditEarliestExpiry={null}
        referralAppliedCents={0}
        referralActive={false}
        floorViolationMessage={null}
        onClearFloorViolation={jest.fn()}
      />
    </PricingPreviewContext.Provider>
  );
}

describe('Payment summary preview', () => {
  it('renders preview line items and updates totals when credits are removed', async () => {
    render(<PaymentSummaryHarness />);

    expect(await screen.findByText('Lesson (90 min)')).toBeInTheDocument();
    expect(screen.getByText('$225.00')).toBeInTheDocument();
    expect(screen.getByText('Booking Protection (12%)')).toBeInTheDocument();
    expect(screen.getByText('$27.00')).toBeInTheDocument();
    expect(screen.getByText('Credits applied')).toBeInTheDocument();
    expect(screen.getByText('-$45.00')).toBeInTheDocument();
    expect(screen.getByText('$207.00')).toBeInTheDocument();

    const slider = screen.getByRole('slider');
    fireEvent.change(slider, { target: { value: '0' } });
    fireEvent.mouseUp(slider);

    await waitFor(() => {
      expect(screen.getByText('$252.00')).toBeInTheDocument();
    });
    expect(screen.queryByText('-$45.00')).not.toBeInTheDocument();
    expect(screen.getByText('Booking Protection (12%)')).toBeInTheDocument();
  });
});
