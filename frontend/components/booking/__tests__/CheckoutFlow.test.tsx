/**
 * Tests for CheckoutFlow component
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Shared mock implementations
const stripeMocks = {
  createPaymentMethod: jest.fn(),
  confirmCardPayment: jest.fn(),
};

jest.mock('@stripe/stripe-js', () => ({
  loadStripe: jest.fn(() => Promise.resolve({})),
}));

jest.mock('@stripe/react-stripe-js', () => ({
  Elements: ({ children }: { children: React.ReactNode }) => <div data-testid="stripe-elements">{children}</div>,
  CardElement: () => <div data-testid="card-element" />,
  useStripe: () => stripeMocks,
  useElements: () => ({ getElement: () => ({}) }),
}));

// Mock logger
jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

// Mock API pricing
jest.mock('@/lib/api/pricing', () => ({
  fetchPricingPreview: jest.fn().mockResolvedValue({
    base_price_cents: 6000,
    student_pay_cents: 6300,
    line_items: [
      { label: 'Service & Support fee (5%)', amount_cents: 300 },
    ],
  }),
  formatCentsToDisplay: jest.fn((cents: number) => `$${(cents / 100).toFixed(2)}`),
}));

// Mock pricing config
jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingConfig: () => ({
    config: { studentFeePercent: 5 },
    isLoading: false,
  }),
}));

// Mock student fee utilities
jest.mock('@/lib/pricing/studentFee', () => ({
  computeStudentFeePercent: jest.fn(() => 5),
  formatServiceSupportLabel: jest.fn((percent: number, opts?: { includeFeeWord?: boolean }) =>
    opts?.includeFeeWord === false ? `${percent}%` : `Service & Support fee (${percent}%)`
  ),
  formatServiceSupportTooltip: jest.fn(() => 'This fee helps cover platform costs and support.'),
}));

// Mock timezone formatting
jest.mock('@/lib/timezone/formatBookingTime', () => ({
  formatBookingDate: jest.fn(() => 'January 15, 2026'),
  formatBookingTimeRange: jest.fn(() => '10:00 AM - 11:00 AM'),
}));

// Mock usePaymentMethods hook
const mockPaymentMethods = [
  { id: 'pm_1', last4: '4242', brand: 'Visa', is_default: true },
  { id: 'pm_2', last4: '5555', brand: 'Mastercard', is_default: false },
];

const mockUsePaymentMethods = jest.fn(() => ({
  data: mockPaymentMethods,
  isLoading: false,
}));

jest.mock('@/hooks/queries/usePaymentMethods', () => ({
  usePaymentMethods: () => mockUsePaymentMethods(),
}));

// Mock fetch for checkout API
const mockFetch = jest.fn();
global.fetch = mockFetch;

// Import after mocks
import CheckoutFlow from '../CheckoutFlow';
import { fetchPricingPreview } from '@/lib/api/pricing';

const mockBooking = {
  id: 'booking-123',
  service_name: 'Piano Lesson',
  instructor_name: 'Sarah C.',
  instructor_id: 'inst-1',
  booking_date: '2026-01-15',
  start_time: '10:00',
  end_time: '11:00',
  booking_start_utc: '2026-01-15T15:00:00Z',
  booking_end_utc: '2026-01-15T16:00:00Z',
  lesson_timezone: 'America/New_York',
  duration_minutes: 60,
  hourly_rate: 60,
  total_price: 60,
};

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'TestQueryClientWrapper';
  return Wrapper;
};

describe('CheckoutFlow', () => {
  const onSuccess = jest.fn();
  const onCancel = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    mockFetch.mockReset();
    mockUsePaymentMethods.mockReturnValue({
      data: mockPaymentMethods,
      isLoading: false,
    });
    stripeMocks.createPaymentMethod.mockResolvedValue({
      paymentMethod: { id: 'pm_new' },
      error: null,
    });
    stripeMocks.confirmCardPayment.mockResolvedValue({ error: null });
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ payment_intent_id: 'pi_123', requires_action: false }),
    });
  });

  describe('Basic Rendering', () => {
    it('renders booking summary', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Booking Summary')).toBeInTheDocument();
      });
      expect(screen.getByText('Piano Lesson')).toBeInTheDocument();
      expect(screen.getByText(/Sarah C./)).toBeInTheDocument();
    });

    it('renders date and time', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('January 15, 2026')).toBeInTheDocument();
      });
      expect(screen.getByText('10:00 AM - 11:00 AM')).toBeInTheDocument();
      expect(screen.getByText('60 minutes')).toBeInTheDocument();
    });

    it('renders payment section with Stripe elements', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Payment')).toBeInTheDocument();
      });
      expect(screen.getByTestId('stripe-elements')).toBeInTheDocument();
    });

    it('renders cancel button', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Cancel and go back')).toBeInTheDocument();
      });
    });

    it('renders security badge', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText(/encrypted and secure/)).toBeInTheDocument();
      });
    });
  });

  describe('Saved Payment Methods', () => {
    it('renders saved payment methods', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Visa')).toBeInTheDocument();
        expect(screen.getByText('•••• 4242')).toBeInTheDocument();
        expect(screen.getByText('Mastercard')).toBeInTheDocument();
        expect(screen.getByText('•••• 5555')).toBeInTheDocument();
      });
    });

    it('marks default payment method', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Default')).toBeInTheDocument();
      });
    });

    it('renders add new card option', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Add New Card')).toBeInTheDocument();
      });
    });
  });

  describe('New Card Entry', () => {
    it('shows card element when add new card is selected', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Add New Card')).toBeInTheDocument();
      });

      const labels = screen.getAllByText('Add New Card');
      const newCardLabel = labels.find(el => el.closest('label'));
      if (newCardLabel) {
        fireEvent.click(newCardLabel);
      }

      await waitFor(() => {
        expect(screen.getByTestId('card-element')).toBeInTheDocument();
      });
    });

    it('shows save card checkbox when adding new card', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Add New Card')).toBeInTheDocument();
      });

      const labels = screen.getAllByText('Add New Card');
      const newCardLabel = labels.find(el => el.closest('label'));
      if (newCardLabel) {
        fireEvent.click(newCardLabel);
      }

      await waitFor(() => {
        expect(screen.getByText('Save card for future use')).toBeInTheDocument();
      });
    });
  });

  describe('Pricing Display', () => {
    it('fetches pricing preview on mount', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(fetchPricingPreview).toHaveBeenCalledWith('booking-123', 0);
      });
    });

    it('displays booking summary with pricing', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Booking Summary')).toBeInTheDocument();
        expect(screen.getByText('Total')).toBeInTheDocument();
      });
    });
  });

  describe('Payment Processing', () => {
    it('calls checkout API when pay button clicked', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Visa')).toBeInTheDocument();
      });

      const payButton = screen.getByRole('button', { name: /Pay \$/ });
      await userEvent.click(payButton);

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          '/api/v1/payments/checkout',
          expect.objectContaining({
            method: 'POST',
          })
        );
      });
    });

    it('creates new payment method when adding new card', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Add New Card')).toBeInTheDocument();
      });

      const labels = screen.getAllByText('Add New Card');
      const newCardLabel = labels.find(el => el.closest('label'));
      if (newCardLabel) {
        fireEvent.click(newCardLabel);
      }

      await waitFor(() => {
        expect(screen.getByTestId('card-element')).toBeInTheDocument();
      });

      const payButton = screen.getByRole('button', { name: /Pay \$/ });
      await userEvent.click(payButton);

      await waitFor(() => {
        expect(stripeMocks.createPaymentMethod).toHaveBeenCalled();
      });
    });

    it('shows processing state while payment in progress', async () => {
      // Make fetch hang
      mockFetch.mockImplementation(() => new Promise(() => {}));

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Visa')).toBeInTheDocument();
      });

      const payButton = screen.getByRole('button', { name: /Pay \$/ });
      fireEvent.click(payButton);

      await waitFor(() => {
        expect(screen.getByText('Processing...')).toBeInTheDocument();
      });
    });

    it('shows success state after payment completion', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Visa')).toBeInTheDocument();
      });

      const payButton = screen.getByRole('button', { name: /Pay \$/ });
      fireEvent.click(payButton);

      await waitFor(() => {
        expect(screen.getByText('Payment Successful!')).toBeInTheDocument();
      }, { timeout: 3000 });
    });

    it('handles payment error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: () => Promise.resolve({ detail: 'Card declined' }),
      });

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Visa')).toBeInTheDocument();
      });

      const payButton = screen.getByRole('button', { name: /Pay \$/ });
      fireEvent.click(payButton);

      await waitFor(() => {
        expect(screen.getByText('Card declined')).toBeInTheDocument();
      }, { timeout: 3000 });
    });
  });

  describe('Cancel Flow', () => {
    it('calls onCancel when cancel button clicked', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Cancel and go back')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('Cancel and go back'));

      expect(onCancel).toHaveBeenCalled();
    });
  });

  describe('Loading State', () => {
    it('shows loading spinner when payment methods loading', () => {
      mockUsePaymentMethods.mockReturnValue({
        data: [],
        isLoading: true,
      });

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      // Should not show booking summary when loading
      expect(screen.queryByText('Booking Summary')).not.toBeInTheDocument();
    });
  });

  describe('No Saved Payment Methods', () => {
    it('shows add new card when no saved methods exist', async () => {
      mockUsePaymentMethods.mockReturnValue({
        data: [],
        isLoading: false,
      });

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Add New Card')).toBeInTheDocument();
      });

      // No default badge should be shown
      expect(screen.queryByText('Default')).not.toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('displays error and allows retry', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: () => Promise.resolve({ detail: 'Payment failed' }),
      });

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Visa')).toBeInTheDocument();
      });

      const payButton = screen.getByRole('button', { name: /Pay \$/ });
      fireEvent.click(payButton);

      await waitFor(() => {
        expect(screen.getByText('Payment failed')).toBeInTheDocument();
      }, { timeout: 3000 });

      // Try again button should be available
      expect(screen.getByText('Try again')).toBeInTheDocument();
    });
  });

  describe('Payment Method Selection', () => {
    it('allows selecting different saved payment methods', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Mastercard')).toBeInTheDocument();
      });

      // Click on Mastercard option
      const mastercardLabel = screen.getByText('Mastercard').closest('label');
      if (mastercardLabel) {
        fireEvent.click(mastercardLabel);
      }

      // The radio should be selected
      const mastercardRadio = mastercardLabel?.querySelector('input[type="radio"]');
      expect(mastercardRadio).toBeChecked();
    });

    it('shows Payment Method header', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Payment Method')).toBeInTheDocument();
      });
    });
  });

  describe('Booking Details Display', () => {
    it('displays service name', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Piano Lesson')).toBeInTheDocument();
      });
    });

    it('displays instructor name', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText(/Sarah C./)).toBeInTheDocument();
      });
    });

    it('displays Service header', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Service')).toBeInTheDocument();
      });
    });

    it('displays Date header', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Date')).toBeInTheDocument();
      });
    });

    it('displays Time header', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Time')).toBeInTheDocument();
      });
    });

    it('displays duration in minutes', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('60 minutes')).toBeInTheDocument();
      });
    });
  });
});
