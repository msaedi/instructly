import React from 'react';
import { act, screen, waitFor } from '@testing-library/react';
import { PaymentSection } from '../PaymentSection';
import { BookingPayment, PaymentStatus } from '../../types';
import { BookingType } from '@/features/shared/types/booking';
import {
  fetchPricingPreview,
  fetchPricingPreviewQuote,
  type PricingPreviewResponse,
} from '@/lib/api/pricing';
import { renderWithQueryClient } from '../testUtils';
import { usePricingPreview } from '../../hooks/usePricingPreview';

type BookingWithOptionalService = BookingPayment & {
  serviceId?: string;
  metadata?: Record<string, unknown>;
};

const bookingUpdateHandlerRef: {
  current: ((updater: (prev: BookingWithOptionalService) => BookingWithOptionalService) => void) | null;
} = { current: null };

const CREDIT_STORAGE_KEY = 'insta:credits:last:booking-1';

jest.mock('../PaymentConfirmation', () => {
  function MockPaymentConfirmation(
    props: {
      onBookingUpdate?: (updater: (prev: BookingWithOptionalService) => BookingWithOptionalService) => void;
    },
  ) {
    bookingUpdateHandlerRef.current = props.onBookingUpdate ?? null;
    const controller = usePricingPreview(true);
    const loading = controller?.loading ?? false;
    const preview = controller?.preview ?? null;
    const creditApplied = preview ? preview.credit_applied_cents : 0;

    const creditDisplay = (creditApplied / 100).toFixed(2);

    return (
      <div>
        <div data-testid="credits-applied">Credits applied ${creditDisplay}</div>
        {loading && <span data-testid="pricing-preview-skeleton" />}
      </div>
    );
  }
  MockPaymentConfirmation.displayName = 'MockPaymentConfirmation';

  return {
    __esModule: true,
    default: MockPaymentConfirmation,
  };
});

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingFloors: () => ({ floors: null, config: { student_fee_pct: 0.12 }, isLoading: false, error: null }),
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
    getCreditBalance: jest.fn().mockResolvedValue({ available: 100, pending: 0, expires_at: null }),
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
    onSelectSuggestion?: (suggestion: unknown) => void;
    inputClassName?: string;
    containerClassName?: string;
    suggestionScope?: 'default' | 'us' | 'global';
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
        suggestionScope: _suggestionScope,
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

const fetchPricingPreviewMock = fetchPricingPreview as jest.MockedFunction<typeof fetchPricingPreview>;
const fetchPricingPreviewQuoteMock = fetchPricingPreviewQuote as jest.MockedFunction<typeof fetchPricingPreviewQuote>;

const BASE_PREVIEW_WITH_CREDIT: PricingPreviewResponse = {
  base_price_cents: 22500,
  student_fee_cents: 2700,
  instructor_platform_fee_cents: 0,
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

const BASE_BOOKING: BookingWithOptionalService = {
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

const renderPaymentSection = (overrides: Partial<BookingWithOptionalService> = {}) => {
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

const createDeferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

describe('PaymentSection optimistic preview handling', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    bookingUpdateHandlerRef.current = null;
    sessionStorage.clear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('keeps credit applied and skips skeleton for date/time-only changes', async () => {
    const deferred = createDeferred<PricingPreviewResponse>();
    fetchPricingPreviewMock
      .mockResolvedValueOnce(BASE_PREVIEW_WITH_CREDIT)
      .mockImplementationOnce(() => deferred.promise);
    fetchPricingPreviewQuoteMock.mockImplementation(() => {
      throw new Error('fetchPricingPreviewQuote should not be called');
    });

    renderPaymentSection();

    await waitFor(() => {
      expect(fetchPricingPreviewMock).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(bookingUpdateHandlerRef.current).toBeTruthy();
    });
    const bookingUpdateHandler = bookingUpdateHandlerRef.current;
    expect(bookingUpdateHandler).toBeTruthy();

    const creditDisplay = await screen.findByTestId('credits-applied');
    expect(creditDisplay).toHaveTextContent(/Credits applied\s+\$45\.00/i);

    await act(async () => {
      bookingUpdateHandler?.((prev) => ({
        ...prev,
        date: new Date('2025-05-07T12:00:00Z'),
        startTime: '03:00 PM',
      }));
    });

    await waitFor(() => {
      expect(fetchPricingPreviewMock).toHaveBeenCalledTimes(2);
    });

    const secondCall = fetchPricingPreviewMock.mock.calls[1];
    expect(secondCall).toBeDefined();
    const appliedCreditCents = secondCall ? secondCall[1] : undefined;
    expect(appliedCreditCents).toBe(4500);

    expect(screen.queryByTestId('pricing-preview-skeleton')).not.toBeInTheDocument();
    expect(screen.getByTestId('credits-applied')).toHaveTextContent(/Credits applied\s+\$45\.00/i);

    await act(async () => {
      deferred.resolve({ ...BASE_PREVIEW_WITH_CREDIT });
    });

    await waitFor(() => {
      expect(screen.getByTestId('credits-applied')).toHaveTextContent(/Credits applied\s+\$45\.00/i);
    });
    expect(fetchPricingPreviewMock).toHaveBeenCalledTimes(2);
  });

  it('shows skeleton but keeps credit applied when duration changes', async () => {
    const deferred = createDeferred<PricingPreviewResponse>();
    const durationPreview: PricingPreviewResponse = {
      ...BASE_PREVIEW_WITH_CREDIT,
    };

    fetchPricingPreviewMock
      .mockResolvedValueOnce(BASE_PREVIEW_WITH_CREDIT)
      .mockImplementationOnce(() => deferred.promise);
    fetchPricingPreviewQuoteMock.mockImplementation(() => {
      throw new Error('fetchPricingPreviewQuote should not be called');
    });

    renderPaymentSection();

    await waitFor(() => {
      expect(fetchPricingPreviewMock).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(bookingUpdateHandlerRef.current).toBeTruthy();
    });
    const bookingUpdateHandler = bookingUpdateHandlerRef.current;
    expect(bookingUpdateHandler).toBeTruthy();

    await act(async () => {
      bookingUpdateHandler?.((prev) => ({
        ...prev,
        duration: 120,
      }));
    });

    await waitFor(() => {
      expect(fetchPricingPreviewMock).toHaveBeenCalledTimes(2);
    });

    await screen.findByText(/Credits applied\s+\$45\.00/i);
    const storedDecision = JSON.parse(sessionStorage.getItem(CREDIT_STORAGE_KEY)!);
    expect(storedDecision).toMatchObject({ lastCreditCents: 4500, explicitlyRemoved: false });

    expect(screen.getAllByTestId('pricing-preview-skeleton').length).toBeGreaterThan(0);

    await act(async () => {
      deferred.resolve(durationPreview);
    });

    await waitFor(() => {
      expect(screen.queryByTestId('pricing-preview-skeleton')).not.toBeInTheDocument();
    });

    const creditNode = await screen.findByTestId('credits-applied');
    expect(creditNode).toHaveTextContent(/Credits applied\s+\$45\.00/i);

    const persistedDecision = JSON.parse(sessionStorage.getItem(CREDIT_STORAGE_KEY)!);
    expect(persistedDecision).toMatchObject({ lastCreditCents: 4500, explicitlyRemoved: false });
  });
});
