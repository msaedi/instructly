import React, { useMemo, useState } from 'react';
import { screen, fireEvent, waitFor, within, act } from '@testing-library/react';
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
import { renderWithQueryClient } from '../testUtils';

let mockStudentFeePct = 0.12;

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingFloors: () => ({ floors: null, config: { student_fee_pct: mockStudentFeePct }, isLoading: false, error: null }),
  usePricingConfig: () => ({ config: { student_fee_pct: mockStudentFeePct }, isLoading: false, error: null }),
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

let latestTimeSelectionModalProps: {
  isOpen?: boolean;
  onTimeSelected?: (selection: { date: string; time: string; duration: number }) => void;
} | null = null;

jest.mock('@/features/student/booking/components/TimeSelectionModal', () => ({
  __esModule: true,
  default: (props: unknown) => {
    latestTimeSelectionModalProps = props as typeof latestTimeSelectionModalProps;
    return null;
  },
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

const { paymentService } = jest.requireMock('@/services/api/payments') as {
  paymentService: {
    listPaymentMethods: jest.Mock;
    getCreditBalance: jest.Mock;
  };
};

const CREDIT_STORAGE_KEY = 'insta:credits:last:booking-1';

const buildPreview = (baseCents: number, feeCents: number, creditCents: number): PricingPreviewResponse => ({
  base_price_cents: baseCents,
  student_fee_cents: feeCents,
  instructor_commission_cents: 0,
  credit_applied_cents: creditCents,
  student_pay_cents: baseCents + feeCents - creditCents,
  application_fee_cents: 0,
  top_up_transfer_cents: 0,
  instructor_tier_pct: null,
  line_items: [
    { label: `Service & Support fee (12%)`, amount_cents: feeCents },
    ...(creditCents > 0 ? [{ label: 'Credit applied', amount_cents: -creditCents }] : []),
  ],
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
    { label: 'Service & Support fee (12%)', amount_cents: 2700 },
    { label: 'Credit', amount_cents: -4500 },
  ],
};

const PREVIEW_NO_CREDIT: PricingPreviewResponse = {
  ...PREVIEW_WITH_CREDIT,
  credit_applied_cents: 0,
  student_pay_cents: 25200,
  line_items: [{ label: 'Service & Support fee (12%)', amount_cents: 2700 }],
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

  return renderWithQueryClient(
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
    mockStudentFeePct = 0.12;
    sessionStorage.clear();
    latestTimeSelectionModalProps = null;
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
      line_items: [{ label: 'Service & Support fee (12%)', amount_cents: 900 }],
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
    expect(scoped.getByText('Service & Support fee (12%)')).toBeInTheDocument();
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
      line_items: [{ label: 'Service & Support fee (12%)', amount_cents: 1092 }],
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
    expect(scoped.getByText('Service & Support fee (12%)')).toBeInTheDocument();
    expect(scoped.getByText('$10.92')).toBeInTheDocument();
    expect(scoped.getByText('Total')).toBeInTheDocument();
    expect(scoped.getByText('$101.92')).toBeInTheDocument();
  });

  it('keeps applied credits when duration increases and sends the credit amount with the preview request', async () => {
    paymentService.getCreditBalance.mockResolvedValue({ available: 100, pending: 0, expires_at: null });

    let durationIncreaseTriggered = false;

    fetchPricingPreviewMock.mockImplementation(async (_bookingId, creditCents = 0) => {
      const normalized = Math.max(0, Math.round(creditCents));
      if (durationIncreaseTriggered) {
        return buildPreview(15_000, 1_800, normalized);
      }
      return buildPreview(12_000, 1_500, normalized);
    });

    renderPaymentSectionForSummary({
      duration: 45,
      endTime: '02:45 PM',
      totalAmount: 135,
      basePrice: 120,
    });

    await waitFor(() => expect(screen.queryByText(/Loading payment methods/i)).not.toBeInTheDocument());

    const creditsToggle = await screen.findByRole('button', { name: /Available Credits/i });
    if (creditsToggle.getAttribute('aria-expanded') === 'false') {
      fireEvent.click(creditsToggle);
    }

    const slider = await screen.findByRole('slider');
    fireEvent.change(slider, { target: { value: '27' } });
    fireEvent.mouseUp(slider);

    await waitFor(() => expect((screen.getByRole('slider') as HTMLInputElement).value).toBe('27'));
    await screen.findByText(/Using \$27\.00/i);
    expect(JSON.parse(sessionStorage.getItem(CREDIT_STORAGE_KEY)!)).toMatchObject({
      lastCreditCents: 2700,
      explicitlyRemoved: false,
    });

    fireEvent.click(screen.getByRole('button', { name: /Edit lesson/i }));

    expect(latestTimeSelectionModalProps?.onTimeSelected).toBeDefined();

    act(() => {
      durationIncreaseTriggered = true;
      latestTimeSelectionModalProps?.onTimeSelected?.({ date: '2025-05-06', time: '14:00', duration: 60 });
    });

    await waitFor(() => {
      expect((screen.getByRole('slider') as HTMLInputElement).value).toBe('27');
    });
    await screen.findByText(/Using \$27\.00/i);
    expect(JSON.parse(sessionStorage.getItem(CREDIT_STORAGE_KEY)!)).toMatchObject({
      lastCreditCents: 2700,
      explicitlyRemoved: false,
    });
  });

  it('clamps applied credits when duration decreases and persists the server amount', async () => {
    paymentService.getCreditBalance.mockResolvedValue({ available: 100, pending: 0, expires_at: null });

    let durationDecreaseTriggered = false;

    fetchPricingPreviewMock.mockImplementation(async (_bookingId, creditCents = 0) => {
      const normalized = Math.max(0, Math.round(creditCents));
      if (durationDecreaseTriggered) {
        const clamped = Math.min(normalized, 3_000);
        return buildPreview(2_400, 600, clamped);
      }
      return buildPreview(16_000, 1_920, normalized);
    });

    renderPaymentSectionForSummary({
      duration: 60,
      endTime: '03:00 PM',
      totalAmount: 198,
      basePrice: 176,
    });

    await waitFor(() => expect(screen.queryByText(/Loading payment methods/i)).not.toBeInTheDocument());

    const creditsToggle = await screen.findByRole('button', { name: /Available Credits/i });
    if (creditsToggle.getAttribute('aria-expanded') === 'false') {
      fireEvent.click(creditsToggle);
    }

    const slider = await screen.findByRole('slider');
    fireEvent.change(slider, { target: { value: '40' } });
    fireEvent.mouseUp(slider);

    await waitFor(() => expect((screen.getByRole('slider') as HTMLInputElement).value).toBe('40'));
    expect(JSON.parse(sessionStorage.getItem(CREDIT_STORAGE_KEY)!)).toMatchObject({
      lastCreditCents: 4000,
      explicitlyRemoved: false,
    });

    fireEvent.click(screen.getByRole('button', { name: /Edit lesson/i }));

    expect(latestTimeSelectionModalProps?.onTimeSelected).toBeDefined();

    act(() => {
      durationDecreaseTriggered = true;
      latestTimeSelectionModalProps?.onTimeSelected?.({ date: '2025-05-06', time: '14:00', duration: 45 });
    });

    await waitFor(() => expect((screen.getByRole('slider') as HTMLInputElement).value).toBe('30'));
    await screen.findByText(/Using \$30\.00/i);
    expect(JSON.parse(sessionStorage.getItem(CREDIT_STORAGE_KEY)!)).toMatchObject({
      lastCreditCents: 3000,
      explicitlyRemoved: false,
    });
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
  it('reflects updated booking protection percent from admin config', async () => {
    mockStudentFeePct = 0.14;
    const preview: PricingPreviewResponse = {
      base_price_cents: 15000,
      student_fee_cents: 2100,
      instructor_commission_cents: 0,
      credit_applied_cents: 0,
      student_pay_cents: 17100,
      application_fee_cents: 2100,
      top_up_transfer_cents: 0,
      instructor_tier_pct: 0.12,
      line_items: [{ label: 'Service & Support fee (14%)', amount_cents: 2100 }],
    };

    const controller = {
      preview,
      loading: false,
      error: null,
      lastAppliedCreditCents: preview.credit_applied_cents,
      requestPricingPreview: async () => preview,
      applyCredit: async () => preview,
      reset: () => undefined,
      bookingId: 'booking-1',
    };

    renderWithQueryClient(
      <PricingPreviewContext.Provider value={controller}>
        <PaymentConfirmation
          booking={BASE_BOOKING}
          paymentMethod={PaymentMethod.CREDIT_CARD}
          cardLast4="4242"
          onConfirm={jest.fn()}
          onBack={jest.fn()}
          onChangePaymentMethod={jest.fn()}
          onCreditToggle={jest.fn()}
          onCreditAmountChange={jest.fn()}
          availableCredits={0}
          creditsUsed={0}
          creditEarliestExpiry={null}
          referralAppliedCents={0}
          referralActive={false}
          floorViolationMessage={null}
          onClearFloorViolation={jest.fn()}
        />
      </PricingPreviewContext.Provider>
    );

    expect(await screen.findByText('Service & Support fee (14%)')).toBeInTheDocument();
  });

  it('renders preview line items and updates totals when credits are removed', async () => {
    renderWithQueryClient(<PaymentSummaryHarness />);

    expect(await screen.findByText('Lesson (90 min)')).toBeInTheDocument();
    expect(screen.getByText('$225.00')).toBeInTheDocument();
    expect(screen.getByText('Service & Support fee (12%)')).toBeInTheDocument();
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
    expect(screen.getByText('Service & Support fee (12%)')).toBeInTheDocument();
  });
});
