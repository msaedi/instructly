import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { fetchPricingPreview } from '@/lib/api/pricing';
import { PaymentSection } from '../PaymentSection';
import { BookingType, PaymentStatus } from '../../types';

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
    getCreditBalance: jest.fn().mockResolvedValue({ available: 200, pending: 0, expires_at: null }),
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
  };
});

const fetchPricingPreviewMock = fetchPricingPreview as jest.MockedFunction<typeof fetchPricingPreview>;

const baseBookingData = {
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
  paymentStatus: PaymentStatus.PENDING,
} as const;

const renderPaymentSection = () =>
  render(
    <PaymentSection
      bookingData={baseBookingData}
      onSuccess={jest.fn()}
      onError={jest.fn()}
      showPaymentMethodInline
    />
  );

describe('PaymentSection pricing preview integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders server line items and updates totals when credit slider changes', async () => {
    fetchPricingPreviewMock.mockImplementation((_bookingId, creditCents = 0) => {
      if (creditCents === 0) {
        return Promise.resolve({
          base_price_cents: 10000,
          student_fee_cents: 1200,
          instructor_commission_cents: 0,
          credit_applied_cents: 0,
          student_pay_cents: 11200,
          application_fee_cents: 0,
          top_up_transfer_cents: 0,
          instructor_tier_pct: null,
          line_items: [
            { label: 'Booking Protection (12%)', amount_cents: 1200 },
          ],
        });
      }
      if (creditCents === 2000) {
        return Promise.resolve({
          base_price_cents: 10000,
          student_fee_cents: 1200,
          instructor_commission_cents: 0,
          credit_applied_cents: 2000,
          student_pay_cents: 9200,
          application_fee_cents: 0,
          top_up_transfer_cents: 0,
          instructor_tier_pct: null,
          line_items: [
            { label: 'Booking Protection (12%)', amount_cents: 1200 },
            { label: 'Credit', amount_cents: -2000 },
          ],
        });
      }
      return Promise.reject(new Error(`Unexpected credit cents ${creditCents}`));
    });

    renderPaymentSection();

    await screen.findByText('Booking Protection (12%)');
    fireEvent.click(screen.getByText('Available Credits'));

    await waitFor(() => {
      expect(document.querySelector('input[type="range"]')).toBeTruthy();
    });
    const creditSlider = document.querySelector('input[type="range"]') as HTMLInputElement;

    expect(screen.getByText('$100.00')).toBeInTheDocument();
    expect(screen.queryByText('-$20.00')).not.toBeInTheDocument();
    expect(screen.getByText('$112.00')).toBeInTheDocument();

    fireEvent.change(creditSlider, { target: { value: '20' } });

    await new Promise((resolve) => setTimeout(resolve, 250));

    await waitFor(() => {
      expect(fetchPricingPreviewMock).toHaveBeenCalledWith('booking-123', 2000, expect.anything());
      expect(screen.getByText('-$20.00')).toBeInTheDocument();
      expect(screen.getByText('$92.00')).toBeInTheDocument();
      expect(screen.getByText('Credits to apply:')).toBeInTheDocument();
      expect(screen.getByText('$20.00', { selector: 'span.font-medium' })).toBeInTheDocument();
    });
  });

  it('shows floor violation banner and disables confirm when preview returns 422', async () => {
    fetchPricingPreviewMock.mockImplementation((_bookingId, creditCents = 0) => {
      if (creditCents === 0) {
        return Promise.resolve({
          base_price_cents: 10000,
          student_fee_cents: 1200,
          instructor_commission_cents: 0,
          credit_applied_cents: 0,
          student_pay_cents: 11200,
          application_fee_cents: 0,
          top_up_transfer_cents: 0,
          instructor_tier_pct: null,
          line_items: [
            { label: 'Booking Protection (12%)', amount_cents: 1200 },
          ],
        });
      }
      if (creditCents === 2000) {
        return Promise.resolve({
          base_price_cents: 10000,
          student_fee_cents: 1200,
          instructor_commission_cents: 0,
          credit_applied_cents: 2000,
          student_pay_cents: 9200,
          application_fee_cents: 0,
          top_up_transfer_cents: 0,
          instructor_tier_pct: null,
          line_items: [
            { label: 'Booking Protection (12%)', amount_cents: 1200 },
            { label: 'Credit', amount_cents: -2000 },
          ],
        });
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

    renderPaymentSection();

    await screen.findByText('Booking Protection (12%)');
    fireEvent.click(screen.getByText('Available Credits'));

    await waitFor(() => {
      expect(document.querySelector('input[type="range"]')).toBeTruthy();
    });
    const creditSlider = document.querySelector('input[type="range"]') as HTMLInputElement;
    fireEvent.change(creditSlider, { target: { value: '20' } });
    await new Promise((resolve) => setTimeout(resolve, 250));
    await screen.findByText('-$20.00');

    fireEvent.change(creditSlider, { target: { value: '112' } });
    await new Promise((resolve) => setTimeout(resolve, 250));

    await waitFor(() => {
      expect(fetchPricingPreviewMock).toHaveBeenCalledWith('booking-123', 11200, expect.anything());
    });

    await screen.findByText('Test floor error');

    await waitFor(() => {
      const confirmButton = screen.queryByRole('button', { name: /price must meet minimum/i });
      expect(confirmButton).toBeDisabled();
    });
  });
});
