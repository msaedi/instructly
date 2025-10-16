import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
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
    { label: `Booking Protection (${Math.round((fee / base) * 100)}%)`, amount_cents: fee },
    ...(credit > 0 ? [{ label: 'Credit applied', amount_cents: -credit }] : []),
  ],
});

describe('PaymentSection auto credit application', () => {
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

  it('auto-applies partial wallet credit once and updates totals', async () => {
    const previewsByCredit: Record<number, PricingPreviewResponse> = {
      0: buildPreview(10_000, 2_000, 0),
      4_500: buildPreview(10_000, 2_000, 4_500),
    };

    fetchPricingPreviewMock.mockImplementation(async (_bookingId, creditCents) => {
      const normalized = Math.max(0, Math.round(creditCents));
      const preview = previewsByCredit[normalized];
      if (!preview) {
        throw new Error(`Unexpected preview request for credit ${normalized}`);
      }
      return preview;
    });

    paymentService.getCreditBalance.mockResolvedValue({ available: 45, pending: 0, expires_at: null });

    renderPaymentSection();

    await waitFor(() => {
      expect(screen.queryByText(/Loading payment methods/i)).not.toBeInTheDocument();
    });

    await waitFor(() => {
      const commitCalls = fetchPricingPreviewMock.mock.calls.filter(([, credit]) => Math.round(credit) === 4_500);
      expect(commitCalls).toHaveLength(1);
    });

    await screen.findAllByText(/Available Credits/i);
    await waitFor(() => expect(screen.getAllByText(/Using \$45\.00/)[0]).toBeInTheDocument());

    await waitFor(() => {
      expect(screen.getByText('$75.00')).toBeInTheDocument();
      expect(screen.getByText('-$45.00')).toBeInTheDocument();
    });
  });

  it('auto-applies credit up to subtotal and results in zero due', async () => {
    const previewsByCredit: Record<number, PricingPreviewResponse> = {
      0: buildPreview(7_000, 1_400, 0),
      8_400: buildPreview(7_000, 1_400, 8_400),
    };

    fetchPricingPreviewMock.mockImplementation(async (_bookingId, creditCents) => {
      const normalized = Math.max(0, Math.round(creditCents));
      const preview = previewsByCredit[normalized];
      if (!preview) {
        throw new Error(`Unexpected preview request for credit ${normalized}`);
      }
      return preview;
    });

    paymentService.getCreditBalance.mockResolvedValue({ available: 200, pending: 0, expires_at: null });

    renderPaymentSection({
      basePrice: 70,
      totalAmount: 84,
    });

    await waitFor(() => {
      expect(screen.queryByText(/Loading payment methods/i)).not.toBeInTheDocument();
    });

    await waitFor(() => {
      const commitCalls = fetchPricingPreviewMock.mock.calls.filter(([, credit]) => Math.round(credit) === 8_400);
      expect(commitCalls).toHaveLength(1);
    });

    await screen.findAllByText(/Available Credits/i);
    await waitFor(() => expect(screen.getAllByText(/Using \$84\.00/)[0]).toBeInTheDocument());

    await waitFor(() => {
      expect(screen.getByText('$0.00')).toBeInTheDocument();
      expect(screen.getByText('-$84.00')).toBeInTheDocument();
    });
  });
});
