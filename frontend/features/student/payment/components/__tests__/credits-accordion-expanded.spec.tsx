import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { PaymentSection } from '../PaymentSection';
import { BookingPayment, PaymentStatus } from '../../types';
import { BookingType } from '@/features/shared/types/booking';
import {
  fetchPricingPreview,
  fetchPricingPreviewQuote,
  type PricingPreviewResponse,
} from '@/lib/api/pricing';

let mockStudentFeePct = 0.12;

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingFloors: () => ({ floors: null }),
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
    listPaymentMethods: jest.fn(),
    getCreditBalance: jest.fn(),
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

const fetchPricingPreviewMock = fetchPricingPreview as jest.MockedFunction<typeof fetchPricingPreview>;
const fetchPricingPreviewQuoteMock = fetchPricingPreviewQuote as jest.MockedFunction<typeof fetchPricingPreviewQuote>;

const { paymentService } = jest.requireMock('@/services/api/payments') as {
  paymentService: {
    listPaymentMethods: jest.Mock;
    getCreditBalance: jest.Mock;
  };
};

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
  endTime: '03:00 PM',
  duration: 60,
  location: 'Online',
  basePrice: 100,
  totalAmount: 120,
  bookingType: BookingType.STANDARD,
  paymentStatus: PaymentStatus.PENDING,
  serviceId: 'svc-1',
  metadata: {
    serviceId: 'svc-1',
    modality: 'remote',
  },
};

const renderPaymentSection = (overrides: Partial<typeof BASE_BOOKING> = {}) => {
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

const buildPreview = (base: number, fee: number, credit: number): PricingPreviewResponse => ({
  base_price_cents: base,
  student_fee_cents: fee,
  instructor_commission_cents: 0,
  credit_applied_cents: credit,
  student_pay_cents: base + fee - credit,
  application_fee_cents: 0,
  top_up_transfer_cents: 0,
  instructor_tier_pct: null,
  line_items: [
    { label: `Service & Support fee (${Math.round((fee / base) * 100)}%)`, amount_cents: fee },
    ...(credit > 0 ? [{ label: 'Credit applied', amount_cents: -credit }] : []),
  ],
});

const STORAGE_KEY = 'insta:credits:last:booking-1';

const getPositiveCommitCount = () =>
  fetchPricingPreviewMock.mock.calls.filter(([, credit]) => Number(credit) > 0).length;

const waitForCreditsAppliedAmount = async (amountCents: number) => {
  const dollarsPattern = (amountCents / 100).toFixed(2).replace('.', '\\.');
  const rows = await screen.findAllByText('Credits applied');
  const row = rows[0]!;
  await waitFor(() => {
    expect(row.closest('div')).toHaveTextContent(new RegExp(`\\$${dollarsPattern}`));
  });
};

describe('Credits accordion expansion & persistence', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    sessionStorage.clear();
    mockStudentFeePct = 0.12;
    paymentService.listPaymentMethods.mockResolvedValue([
      { id: 'card-1', last4: '4242', brand: 'visa', is_default: true, created_at: '2024-01-01' },
    ]);
    paymentService.getCreditBalance.mockResolvedValue({ available: 0, pending: 0, expires_at: null });
    fetchPricingPreviewQuoteMock.mockImplementation(() => {
      throw new Error('fetchPricingPreviewQuote should not be called in these tests');
    });
  });

  it('auto-expands and persists when credits are applied', async () => {
    const previewsByCredit: Record<number, PricingPreviewResponse> = {
      0: buildPreview(10_000, 2_000, 0),
      4_500: buildPreview(10_000, 2_000, 4_500),
    };

    fetchPricingPreviewMock.mockImplementation(async (_bookingId, creditCents = 0) => {
      const normalized = Math.max(0, Math.round(creditCents));
      const preview = previewsByCredit[normalized];
      if (!preview) {
        throw new Error(`Unexpected preview request for credit ${normalized}`);
      }
      return preview;
    });

    paymentService.getCreditBalance.mockResolvedValue({ available: 45, pending: 0, expires_at: null });

    renderPaymentSection();

    await waitFor(() => expect(screen.queryByText(/Loading payment methods/i)).not.toBeInTheDocument());

    await waitFor(() => {
      expect(getPositiveCommitCount()).toBe(1);
    }, { timeout: 5000 });

    await waitForCreditsAppliedAmount(4_500);

    const slider = await screen.findByRole('slider');
    expect(slider).toBeVisible();
    expect((slider as HTMLInputElement).value).toBe('45');

    const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? 'null');
    expect(stored).toEqual({ lastCreditCents: 4500, explicitlyRemoved: false });

    const accordionToggle = screen.getByRole('button', { name: /Available Credits/i });
    expect(accordionToggle).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(accordionToggle);
    expect(accordionToggle).toHaveAttribute('aria-expanded', 'true');
  });

  it('remembers explicit removal across refresh', async () => {
    const previewsByCredit: Record<number, PricingPreviewResponse> = {
      0: buildPreview(10_000, 2_000, 0),
      4_500: buildPreview(10_000, 2_000, 4_500),
    };

    fetchPricingPreviewMock.mockImplementation(async (_bookingId, creditCents = 0) => {
      const normalized = Math.max(0, Math.round(creditCents));
      const preview = previewsByCredit[normalized];
      if (!preview) {
        throw new Error(`Unexpected preview request for credit ${normalized}`);
      }
      return preview;
    });

    paymentService.getCreditBalance.mockResolvedValue({ available: 45, pending: 0, expires_at: null });

    const { unmount } = renderPaymentSection();

    await waitFor(() => expect(screen.queryByText(/Loading payment methods/i)).not.toBeInTheDocument());

    await waitFor(() => {
      expect(getPositiveCommitCount()).toBe(1);
    }, { timeout: 5000 });

    await waitForCreditsAppliedAmount(4_500);

    fireEvent.click(screen.getByRole('button', { name: /Remove credits/i }));

    await waitFor(() => {
      expect(screen.getByText('Using $0.00')).toBeInTheDocument();
    });

    await waitFor(() => {
      const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? 'null');
      expect(stored).toEqual({ lastCreditCents: 0, explicitlyRemoved: true });
    });

    const commitsBeforeRefresh = getPositiveCommitCount();

    unmount();

    renderPaymentSection();

    await waitFor(() => expect(screen.queryByText(/Loading payment methods/i)).not.toBeInTheDocument());

    const accordionToggle = await screen.findByRole('button', { name: /Available Credits/i });
    expect(accordionToggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('slider')).not.toBeInTheDocument();

    await waitFor(() => {
      expect(getPositiveCommitCount()).toBe(commitsBeforeRefresh);
    }, { timeout: 5000 });
  });

  it('restores stored credit amount on refresh, clamped to wallet/subtotal', async () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ lastCreditCents: 5_000, explicitlyRemoved: false }));

    const previewsByCredit: Record<number, PricingPreviewResponse> = {
      0: buildPreview(10_000, 2_000, 0),
      3_000: buildPreview(10_000, 2_000, 3_000),
    };

    fetchPricingPreviewMock.mockImplementation(async (_bookingId, creditCents = 0) => {
      const normalized = Math.max(0, Math.round(creditCents));
      const preview = previewsByCredit[normalized];
      if (!preview) {
        throw new Error(`Unexpected preview request for credit ${normalized}`);
      }
      return preview;
    });

    paymentService.getCreditBalance.mockResolvedValue({ available: 30, pending: 0, expires_at: null });

    renderPaymentSection();

    await waitFor(() => expect(screen.queryByText(/Loading payment methods/i)).not.toBeInTheDocument());

    await waitFor(() => {
      expect(getPositiveCommitCount()).toBe(1);
    }, { timeout: 5000 });

    await waitForCreditsAppliedAmount(3_000);
    await waitFor(() => expect(screen.getByText('Using $30.00')).toBeInTheDocument());
    const slider = screen.getByRole('slider') as HTMLInputElement;
    expect(slider.value).toBe('30');

    const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? 'null');
    expect(stored).toEqual({ lastCreditCents: 3000, explicitlyRemoved: false });
  });
});
