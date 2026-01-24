import React from 'react';
import { screen, fireEvent, waitFor, within } from '@testing-library/react';
import { ApiProblemError } from '@/lib/api/fetch';
import { fetchPricingPreview, fetchPricingPreviewQuote } from '@/lib/api/pricing';
import type { PricingPreviewResponse } from '@/lib/api/pricing';
import { paymentService } from '@/services/api/payments';
import { formatDateForAPI } from '@/lib/availability/dateHelpers';
import { PaymentSection } from '../PaymentSection';
import { BookingPayment, BookingType, PAYMENT_STATUS } from '../../types';
import { renderWithQueryClient } from '../testUtils';

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingFloors: () => ({ floors: null, config: { student_fee_pct: 0.12 }, isLoading: false, error: null }),
  usePricingConfig: () => ({ config: { student_fee_pct: 0.12 }, isLoading: false, error: null }),
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

jest.mock('@/features/shared/api/client', () => ({
  protectedApi: {
    getBooking: jest.fn().mockResolvedValue({ data: null, status: 200 }),
    getBookings: jest.fn().mockResolvedValue({ data: { items: [] }, status: 200 }),
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
const mockedPaymentService = paymentService as jest.Mocked<typeof paymentService>;

const baseBookingData: BookingPayment & {
  serviceId?: string;
  metadata?: Record<string, unknown>;
} = {
  bookingId: 'booking-123',
  instructorId: 'inst-1',
  instructorName: 'Sam Teacher',
  lessonType: 'Piano Lesson',
  date: new Date('2024-06-01T10:00:00Z'),
  startTime: '10:00',
  endTime: '11:00',
  duration: 60,
  location: 'Online',
  basePrice: 100,
  totalAmount: 112,
  bookingType: BookingType.STANDARD,
  paymentStatus: PAYMENT_STATUS.SCHEDULED,
  serviceId: 'svc-1',
  metadata: {
    serviceId: 'svc-1',
    modality: 'remote',
  },
};

const buildPricingPreview = (overrides: Partial<PricingPreviewResponse>): PricingPreviewResponse => ({
  base_price_cents: 0,
  student_fee_cents: 0,
  instructor_platform_fee_cents: 0,
  credit_applied_cents: 0,
  student_pay_cents: 0,
  application_fee_cents: 0,
  top_up_transfer_cents: 0,
  instructor_tier_pct: 0,
  target_instructor_payout_cents: 0,
  line_items: [],
  ...overrides,
});

const renderPaymentSection = (overrides: Partial<typeof baseBookingData> = {}) =>
  renderWithQueryClient(
    <PaymentSection
      bookingData={{
        ...baseBookingData,
        ...overrides,
        metadata: {
          ...(baseBookingData.metadata ?? {}),
          ...(overrides.metadata ?? {}),
        },
      }}
      onSuccess={jest.fn()}
      onError={jest.fn()}
      showPaymentMethodInline
    />
  );

describe('PaymentSection pricing preview integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    sessionStorage.clear();
  });

  it('renders server line items for bookings with an id', async () => {
    fetchPricingPreviewMock.mockResolvedValue(
      buildPricingPreview({
        base_price_cents: 7500,
        student_fee_cents: 900,
        instructor_platform_fee_cents: 0,
        credit_applied_cents: 0,
        student_pay_cents: 8400,
        application_fee_cents: 0,
        top_up_transfer_cents: 0,
        instructor_tier_pct: 0,
        target_instructor_payout_cents: 7500,
        line_items: [{ label: 'Service & Support fee (12%)', amount_cents: 900 }],
      })
    );

    renderPaymentSection();

    await waitFor(() => {
      expect(fetchPricingPreviewMock).toHaveBeenCalledWith('booking-123', 0, expect.anything());
    });

    const paymentDetailsHeading = await screen.findByText('Payment details');
    const paymentDetails = paymentDetailsHeading.closest('div');
    expect(paymentDetails).toBeTruthy();
    const scoped = within(paymentDetails as HTMLElement);
    expect(scoped.getByText('Lesson (60 min)')).toBeInTheDocument();
    expect(scoped.getByText('$75.00')).toBeInTheDocument();
    expect(scoped.getByText('Service & Support fee (12%)')).toBeInTheDocument();
    expect(scoped.getByText('$9.00')).toBeInTheDocument();
    expect(scoped.getByText('Total')).toBeInTheDocument();
    expect(scoped.getByText('$84.00')).toBeInTheDocument();
  });

  it('requests a pricing quote when no booking id is available', async () => {
    fetchPricingPreviewMock.mockImplementation(() => {
      throw new Error('fetchPricingPreview should not be called');
    });
    fetchPricingPreviewQuoteMock.mockResolvedValue(
      buildPricingPreview({
        base_price_cents: 8800,
        student_fee_cents: 1056,
        instructor_platform_fee_cents: 0,
        credit_applied_cents: 0,
        student_pay_cents: 9856,
        application_fee_cents: 0,
        top_up_transfer_cents: 0,
        instructor_tier_pct: 0,
        target_instructor_payout_cents: 8800,
        line_items: [{ label: 'Service & Support fee (12%)', amount_cents: 1056 }],
      })
    );

    renderPaymentSection({
      bookingId: '',
    });

    await waitFor(() => {
      expect(fetchPricingPreviewQuoteMock).toHaveBeenCalledTimes(1);
    });

    const expectedBookingDate = formatDateForAPI(baseBookingData.date);

    expect(fetchPricingPreviewQuoteMock).toHaveBeenCalledWith(
      expect.objectContaining({
        instructor_id: 'inst-1',
        instructor_service_id: 'svc-1',
        booking_date: expectedBookingDate,
        start_time: '10:00',
        selected_duration: 60,
        location_type: 'online',
        meeting_location: 'Online',
        applied_credit_cents: 0,
      }),
      expect.any(Object)
    );

    const paymentDetailsHeading = await screen.findByText('Payment details');
    const paymentDetails = paymentDetailsHeading.closest('div');
    expect(paymentDetails).toBeTruthy();
    const scoped = within(paymentDetails as HTMLElement);
    expect(scoped.getByText('$88.00')).toBeInTheDocument();
    expect(scoped.getByText('$10.56')).toBeInTheDocument();
    expect(scoped.getByText('$98.56')).toBeInTheDocument();
  });

  it('shows floor violation banner and disables confirm when preview returns 422', async () => {
    mockedPaymentService.getCreditBalance.mockResolvedValueOnce({
      available: 200,
      pending: 0,
      expires_at: null,
    });

    fetchPricingPreviewMock.mockImplementation((_bookingId, creditCents = 0) => {
      if (creditCents === 0) {
        return Promise.resolve(
          buildPricingPreview({
            base_price_cents: 10000,
            student_fee_cents: 1200,
            instructor_platform_fee_cents: 0,
            credit_applied_cents: 0,
            student_pay_cents: 11200,
            application_fee_cents: 0,
            top_up_transfer_cents: 0,
            instructor_tier_pct: 0,
            target_instructor_payout_cents: 10000,
            line_items: [{ label: 'Service & Support fee (12%)', amount_cents: 1200 }],
          })
        );
      }
      if (creditCents === 2000) {
        return Promise.resolve(
          buildPricingPreview({
            base_price_cents: 10000,
            student_fee_cents: 1200,
            instructor_platform_fee_cents: 0,
            credit_applied_cents: 2000,
            student_pay_cents: 9200,
            application_fee_cents: 0,
            top_up_transfer_cents: 0,
            instructor_tier_pct: 0,
            target_instructor_payout_cents: 8000,
            line_items: [
              { label: 'Service & Support fee (12%)', amount_cents: 1200 },
              { label: 'Credit', amount_cents: -2000 },
            ],
          })
        );
      }
      if (creditCents === 11200) {
        return Promise.reject({
          problem: {
            title: 'Price floor',
            detail: 'Test floor error',
            status: 422,
            type: 'about:blank',
          },
          response: { status: 422 },
        });
      }
      return Promise.reject(new Error(`Unexpected credit cents ${creditCents}`));
    });

    mockedPaymentService.getCreditBalance.mockResolvedValue({ available: 200, pending: 0, expires_at: null });

    renderPaymentSection();

    await screen.findByText('Service & Support fee (12%)');

    const creditsToggle = await screen.findByRole('button', { name: /Available Credits/i });
    if (creditsToggle.getAttribute('aria-expanded') === 'false') {
      fireEvent.click(creditsToggle);
    }

    const creditSlider = await screen.findByRole('slider');
    fireEvent.change(creditSlider, { target: { value: '20' } });
    fireEvent.mouseUp(creditSlider);
    await new Promise((resolve) => setTimeout(resolve, 250));
    await screen.findByText('-$20.00');

    fireEvent.change(creditSlider, { target: { value: '112' } });
    fireEvent.mouseUp(creditSlider);
    await new Promise((resolve) => setTimeout(resolve, 250));

    const messages = await screen.findAllByText((content) => /Test floor error|Price must meet minimum/i.test(content));
    expect(messages.length).toBeGreaterThan(0);

    await waitFor(() => {
      const confirmButton = screen.queryByRole('button', { name: /price must meet minimum/i });
      expect(confirmButton).toBeDisabled();
    });
  });

  it('surfaces preview errors in the payment summary when the request fails', async () => {
    const mockResponse = { status: 422 } as Response;
    fetchPricingPreviewMock.mockRejectedValueOnce(
      new ApiProblemError(
        {
          title: 'Price floor',
          detail: 'Below minimum',
          status: 422,
          type: 'about:blank',
        },
        mockResponse,
      ),
    );

    renderPaymentSection();

    await waitFor(() => {
      expect(fetchPricingPreviewMock).toHaveBeenCalledTimes(1);
    });

    const errorMessage = await screen.findByText('Unable to load pricing preview. Please try again.');
    expect(errorMessage).toBeInTheDocument();
    expect(screen.getByText('Service & Support fee (12%)')).toBeInTheDocument();
    expect(screen.queryByTestId('pricing-preview-skeleton')).not.toBeInTheDocument();
  });
});
