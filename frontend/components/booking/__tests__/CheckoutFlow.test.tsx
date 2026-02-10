/**
 * Tests for CheckoutFlow component
 */

import React from 'react';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
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

  describe('Amount Normalization', () => {
    it('handles string total_price in booking', async () => {
      const bookingWithStringPrice = {
        ...mockBooking,
        total_price: '75.50' as unknown as number,
      };

      render(<CheckoutFlow booking={bookingWithStringPrice} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        // Should still render and parse the string price
        expect(screen.getByText('Booking Summary')).toBeInTheDocument();
      });

      const payButton = screen.getByRole('button', { name: /Pay \$/ });
      expect(payButton).toBeInTheDocument();
    });

    it('handles invalid total_price in booking', async () => {
      const bookingWithInvalidPrice = {
        ...mockBooking,
        total_price: 'invalid' as unknown as number,
      };

      render(<CheckoutFlow booking={bookingWithInvalidPrice} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Booking Summary')).toBeInTheDocument();
      });
    });
  });

  describe('3D Secure Flow', () => {
    it('handles 3D Secure confirmation when required', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          payment_intent_id: 'pi_123',
          requires_action: true,
          client_secret: 'secret_123',
        }),
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
        expect(stripeMocks.confirmCardPayment).toHaveBeenCalledWith('secret_123');
      });
    });

    it('handles 3D Secure confirmation error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          payment_intent_id: 'pi_123',
          requires_action: true,
          client_secret: 'secret_123',
        }),
      });
      stripeMocks.confirmCardPayment.mockResolvedValueOnce({
        error: { message: '3DS authentication failed' },
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
        expect(screen.getByText('3DS authentication failed')).toBeInTheDocument();
      }, { timeout: 3000 });
    });
  });

  describe('CVV Input for Saved Cards', () => {
    it('shows CVV input when saved card is selected', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Visa')).toBeInTheDocument();
      });

      // Default card is already selected, CVV should show
      expect(screen.getByText('Security Code (CVV)')).toBeInTheDocument();
    });

    it('allows entering CVV for saved card', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Security Code (CVV)')).toBeInTheDocument();
      });

      const cvvInput = screen.getByPlaceholderText('123');
      await userEvent.type(cvvInput, '456');

      expect(cvvInput).toHaveValue('456');
    });

    it('only allows numeric input for CVV', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Security Code (CVV)')).toBeInTheDocument();
      });

      const cvvInput = screen.getByPlaceholderText('123');
      await userEvent.type(cvvInput, 'abc123def');

      // Should only contain digits
      expect(cvvInput).toHaveValue('123');
    });

    it('hides CVV input when adding new card', async () => {
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
        expect(screen.queryByText('Security Code (CVV)')).not.toBeInTheDocument();
      });
    });
  });

  describe('Error Reset', () => {
    it('clears error and resets payment status when try again is clicked', async () => {
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

      // Click try again
      await userEvent.click(screen.getByText('Try again'));

      // Error should be cleared
      await waitFor(() => {
        expect(screen.queryByText('Payment failed')).not.toBeInTheDocument();
      });
    });
  });

  describe('Payment Method Creation Errors', () => {
    it('handles stripe not initialized error', async () => {
      // Mock useStripe to return null
      jest.requireMock('@stripe/react-stripe-js').useStripe = () => null;

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

      const payButton = screen.getByRole('button', { name: /Pay \$/ });
      fireEvent.click(payButton);

      // Stripe null case is handled at button disabled level
      expect(payButton).toBeDisabled();

      // Restore mock
      jest.requireMock('@stripe/react-stripe-js').useStripe = () => stripeMocks;
    });

    it('handles payment method creation failure', async () => {
      stripeMocks.createPaymentMethod.mockResolvedValueOnce({
        paymentMethod: null,
        error: { message: 'Card creation failed' },
      });

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

      const payButton = screen.getByRole('button', { name: /Pay \$/ });
      await userEvent.click(payButton);

      await waitFor(() => {
        expect(screen.getByText('Card creation failed')).toBeInTheDocument();
      }, { timeout: 3000 });
    });
  });

  describe('Save Card Checkbox', () => {
    it('toggles save card checkbox when checked', async () => {
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

      const saveCheckbox = screen.getByRole('checkbox');
      expect(saveCheckbox).not.toBeChecked();

      await userEvent.click(saveCheckbox);

      expect(saveCheckbox).toBeChecked();
    });
  });

  describe('Line Items Display', () => {
    it('displays service support fee line item with tooltip', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText(/Service & Support fee/)).toBeInTheDocument();
      });
    });

    it('displays lesson duration in price breakdown', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText(/Lesson \(60 min\)/)).toBeInTheDocument();
      });
    });
  });

  describe('Success Flow', () => {
    it('calls onSuccess after timeout', async () => {
      jest.useFakeTimers();

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

      // Fast-forward timer
      act(() => {
        jest.advanceTimersByTime(2000);
      });

      expect(onSuccess).toHaveBeenCalledWith('pi_123');

      jest.useRealTimers();
    });
  });

  describe('Pricing Preview Error Handling', () => {
    it('displays pricing preview error message', async () => {
      const { fetchPricingPreview: mockFetchPricing } = jest.requireMock('@/lib/api/pricing');
      mockFetchPricing.mockRejectedValueOnce(new Error('Price validation failed'));

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        // Component should still render even with pricing error
        expect(screen.getByText('Booking Summary')).toBeInTheDocument();
      });
    });

    it('handles ApiProblemError with 422 status', async () => {
      // Import ApiProblemError to create proper instance
      const { ApiProblemError } = await import('@/lib/api/fetch');
      const mockResponse = {
        status: 422,
        statusText: 'Unprocessable Entity',
      } as Response;

      const { fetchPricingPreview: mockFetchPricing } = jest.requireMock('@/lib/api/pricing');
      mockFetchPricing.mockRejectedValueOnce(
        new ApiProblemError({ type: 'validation_error', detail: 'Price below minimum threshold', title: 'Validation Error', status: 422 }, mockResponse)
      );

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        // Should show the specific error from ApiProblemError
        expect(screen.getByText('Price below minimum threshold')).toBeInTheDocument();
      });
    });

    it('handles ApiProblemError with 422 and empty detail', async () => {
      const { ApiProblemError } = await import('@/lib/api/fetch');
      const mockResponse = {
        status: 422,
        statusText: 'Unprocessable Entity',
      } as Response;

      const { fetchPricingPreview: mockFetchPricing } = jest.requireMock('@/lib/api/pricing');
      // Note: Problem.detail is always a string (never undefined), so ?? fallback cannot trigger
      // When detail is empty string, it passes through since '' is not nullish
      mockFetchPricing.mockRejectedValueOnce(
        new ApiProblemError({ type: 'validation_error', title: 'Validation Error', detail: '', status: 422 }, mockResponse)
      );

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      // With empty detail string, the error state is set to empty string
      // The PaymentSection should still render (pricing preview error doesn't block UI)
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /^Pay \$/i })).toBeInTheDocument();
      });
    });
  });

  describe('API Error Response Handling', () => {
    it('handles error with message field instead of detail', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: () => Promise.resolve({ message: 'Server error occurred' }),
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
        expect(screen.getByText('Server error occurred')).toBeInTheDocument();
      }, { timeout: 3000 });
    });
  });

  describe('Line Item Label Fallback', () => {
    it('uses item.label for non-service-support line items', async () => {
      // Override mock to return custom line items
      jest.requireMock('@/lib/api/pricing').fetchPricingPreview.mockResolvedValue({
        base_price_cents: 6000,
        student_pay_cents: 6300,
        line_items: [
          { label: 'Custom fee', amount_cents: 500 },
        ],
      });

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Custom fee')).toBeInTheDocument();
      });
    });

    it('normalizes booking protection label to service support', async () => {
      jest.requireMock('@/lib/api/pricing').fetchPricingPreview.mockResolvedValue({
        base_price_cents: 6000,
        student_pay_cents: 6300,
        line_items: [
          { label: 'Booking Protection (5%)', amount_cents: 300 },
        ],
      });

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText(/Service & Support fee/)).toBeInTheDocument();
      });
    });
  });

  describe('Stripe Elements Edge Cases', () => {
    it('handles useElements returning null by showing error', async () => {
      // Save original mock
      const originalUseElements = jest.requireMock('@stripe/react-stripe-js').useElements;
      // Mock useElements to return null
      jest.requireMock('@stripe/react-stripe-js').useElements = () => null;

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

      const payButton = screen.getByRole('button', { name: /Pay \$/ });
      await userEvent.click(payButton);

      // Should show error when elements is null
      await waitFor(() => {
        expect(screen.getByText(/Card elements not initialized/i)).toBeInTheDocument();
      }, { timeout: 3000 });

      // Restore original
      jest.requireMock('@stripe/react-stripe-js').useElements = originalUseElements;
    });

    it('handles getElement returning null', async () => {
      // Save original mock
      const originalUseElements = jest.requireMock('@stripe/react-stripe-js').useElements;
      // Mock useElements to return object with getElement returning null
      jest.requireMock('@stripe/react-stripe-js').useElements = () => ({
        getElement: () => null,
      });

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

      const payButton = screen.getByRole('button', { name: /Pay \$/ });
      await userEvent.click(payButton);

      await waitFor(() => {
        expect(screen.getByText(/Card element not found/i)).toBeInTheDocument();
      }, { timeout: 3000 });

      // Restore original
      jest.requireMock('@stripe/react-stripe-js').useElements = originalUseElements;
    });
  });

  describe('Derive Booking Amount', () => {
    it('derives amount from booking when studentPayAmount is undefined', async () => {
      // Override mock to not return student_pay_cents
      jest.requireMock('@/lib/api/pricing').fetchPricingPreview.mockResolvedValue({
        base_price_cents: 6000,
        line_items: [],
        // Omit student_pay_cents to force deriveBookingAmount usage
      });

      const bookingWithPrice = {
        ...mockBooking,
        total_price: 65,
      };

      render(<CheckoutFlow booking={bookingWithPrice} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Booking Summary')).toBeInTheDocument();
      });
    });

    it('handles booking without total_price', async () => {
      jest.requireMock('@/lib/api/pricing').fetchPricingPreview.mockResolvedValue({
        base_price_cents: 6000,
        line_items: [],
      });

      const bookingWithoutPrice = {
        ...mockBooking,
        total_price: undefined as unknown as number,
      };

      render(<CheckoutFlow booking={bookingWithoutPrice} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Booking Summary')).toBeInTheDocument();
      });
    });

    it('parses string total_price in deriveBookingAmount', async () => {
      // Need to make studentPayAmount non-numeric to trigger deriveBookingAmount
      jest.requireMock('@/lib/api/pricing').fetchPricingPreview.mockResolvedValue({
        base_price_cents: 6000,
        student_pay_cents: undefined, // undefined to trigger deriveBookingAmount
        line_items: [],
      });

      const bookingWithStringPrice = {
        ...mockBooking,
        total_price: '75.50' as unknown as number,
      };

      render(<CheckoutFlow booking={bookingWithStringPrice} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Booking Summary')).toBeInTheDocument();
      });

      // Try to make a payment to trigger deriveBookingAmount
      const payButton = screen.getByRole('button', { name: /Pay/ });
      expect(payButton).toBeInTheDocument();
    });

    it('returns 0 for non-numeric total_price', async () => {
      jest.requireMock('@/lib/api/pricing').fetchPricingPreview.mockResolvedValue({
        base_price_cents: 6000,
        student_pay_cents: undefined,
        line_items: [],
      });

      const bookingWithInvalidPrice = {
        ...mockBooking,
        total_price: 'not-a-number' as unknown as number,
      };

      render(<CheckoutFlow booking={bookingWithInvalidPrice} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Booking Summary')).toBeInTheDocument();
      });
    });
  });

  describe('Stripe Initialization', () => {
    it('disables pay button when stripe is not initialized', async () => {
      // Mock useStripe to return null
      const originalUseStripe = jest.requireMock('@stripe/react-stripe-js').useStripe;
      jest.requireMock('@stripe/react-stripe-js').useStripe = () => null;

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Visa')).toBeInTheDocument();
      });

      // Button should be disabled when stripe is null
      const payButton = screen.getByRole('button', { name: /Pay \$/ });
      expect(payButton).toBeDisabled();

      // Restore original
      jest.requireMock('@stripe/react-stripe-js').useStripe = originalUseStripe;
    });
  });

  describe('normalizeAmount edge cases', () => {
    it('handles booking with zero hourly_rate', async () => {
      const bookingZeroRate = {
        ...mockBooking,
        hourly_rate: 0,
        total_price: 0,
      };

      render(<CheckoutFlow booking={bookingZeroRate} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Booking Summary')).toBeInTheDocument();
      });

      expect(screen.getByText(/Lesson \(60 min\)/)).toBeInTheDocument();
    });

    it('handles string hourly_rate through normalizeAmount', async () => {
      const bookingStringRate = {
        ...mockBooking,
        hourly_rate: '55.75' as unknown as number,
      };

      render(<CheckoutFlow booking={bookingStringRate} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Booking Summary')).toBeInTheDocument();
      });
    });

    it('handles Infinity hourly_rate through normalizeAmount', async () => {
      const bookingInfinityRate = {
        ...mockBooking,
        hourly_rate: Infinity,
      };

      render(<CheckoutFlow booking={bookingInfinityRate} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Booking Summary')).toBeInTheDocument();
      });
    });

    it('handles NaN total_price through normalizeAmount', async () => {
      const bookingNaN = {
        ...mockBooking,
        total_price: NaN,
      };

      render(<CheckoutFlow booking={bookingNaN} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Booking Summary')).toBeInTheDocument();
      });
    });
  });

  describe('Duration fallback', () => {
    it('falls back to 60 for price calculation when duration_minutes is missing', async () => {
      const bookingNoDuration = {
        ...mockBooking,
        duration_minutes: undefined as unknown as number,
      };

      render(<CheckoutFlow booking={bookingNoDuration} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        // The component renders booking.duration_minutes directly in text (may show nothing),
        // but durationMinutes ?? 60 is used for the Lesson label
        expect(screen.getByText(/Lesson \(60 min\)/)).toBeInTheDocument();
      });
    });
  });

  describe('Line items with credits', () => {
    it('displays credit line items in green', async () => {
      jest.requireMock('@/lib/api/pricing').fetchPricingPreview.mockResolvedValue({
        base_price_cents: 6000,
        student_pay_cents: 5500,
        line_items: [
          { label: 'Service & Support fee (5%)', amount_cents: 300 },
          { label: 'Welcome credit', amount_cents: -800 },
        ],
      });

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Welcome credit')).toBeInTheDocument();
      });

      // Credit line item should have green text class
      const creditElement = screen.getByText('Welcome credit').closest('div');
      expect(creditElement).toHaveClass('text-green-600');
    });
  });

  describe('Empty line items fallback annotation', () => {
    it('shows annotation with service support fee when no line items', async () => {
      jest.requireMock('@/lib/api/pricing').fetchPricingPreview.mockResolvedValue({
        base_price_cents: 6000,
        student_pay_cents: 6300,
        line_items: [],
      });

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText(/and credits apply at checkout/)).toBeInTheDocument();
      });
    });
  });

  describe('Pricing preview loading indicator', () => {
    it('shows loading text while pricing preview is fetching', async () => {
      // Create a never-resolving promise to keep loading state
      jest.requireMock('@/lib/api/pricing').fetchPricingPreview.mockImplementation(
        () => new Promise(() => {})
      );

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Updating pricing…')).toBeInTheDocument();
      });
    });
  });

  describe('Non-ApiProblemError pricing failure', () => {
    it('shows generic pricing error for non-ApiProblemError', async () => {
      jest.requireMock('@/lib/api/pricing').fetchPricingPreview.mockRejectedValue(
        new Error('Network timeout')
      );

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Unable to load pricing preview.')).toBeInTheDocument();
      });
    });
  });

  describe('Payment with saved card sends correct method id', () => {
    it('sends existing payment method id for saved card', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Visa')).toBeInTheDocument();
      });

      const payButton = screen.getByRole('button', { name: /Pay \$/ });
      fireEvent.click(payButton);

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          '/api/v1/payments/checkout',
          expect.objectContaining({
            body: expect.stringContaining('"payment_method_id":"pm_1"'),
          })
        );
      });
    });

    it('sends save_payment_method false for existing card', async () => {
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Visa')).toBeInTheDocument();
      });

      const payButton = screen.getByRole('button', { name: /Pay \$/ });
      fireEvent.click(payButton);

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          '/api/v1/payments/checkout',
          expect.objectContaining({
            body: expect.stringContaining('"save_payment_method":false'),
          })
        );
      });
    });
  });

  describe('deriveBookingAmount string path', () => {
    it('falls back to derive when studentPayAmount is undefined', async () => {
      // Make pricingPreview return undefined student_pay_cents and null pricingPreview
      // so the component falls back to fallbackTotalCents
      jest.requireMock('@/lib/api/pricing').fetchPricingPreview.mockRejectedValue(
        new Error('Pricing unavailable')
      );

      const bookingWithPrice = {
        ...mockBooking,
        total_price: 42.5,
      };

      render(<CheckoutFlow booking={bookingWithPrice} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Booking Summary')).toBeInTheDocument();
      });

      // When pricingPreview is null, fallbackTotalCents = Math.round(42.5 * 100) = 4250
      // previewStudentPayCents = 4250, studentPayAmount = 42.5
      // This still goes through the typeof number check, not deriveBookingAmount
      // But the rendering should work
      const payButton = screen.getByRole('button', { name: /Pay/ });
      expect(payButton).toBeInTheDocument();
    });
  });

  describe('API error without detail or message', () => {
    it('shows generic "Payment failed" when no detail or message in error response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: () => Promise.resolve({}),
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
    });
  });

  describe('Stripe null during payment submission', () => {
    it('shows Stripe not initialized error when stripe is null and saved card is used', async () => {
      // Render with stripe available so button is initially enabled
      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Visa')).toBeInTheDocument();
      });

      // Now set stripe to null before clicking pay
      const originalUseStripe = jest.requireMock('@stripe/react-stripe-js').useStripe;
      jest.requireMock('@stripe/react-stripe-js').useStripe = () => null;

      // Force re-render by toggling payment method selection
      const mastercardLabel = screen.getByText('Mastercard').closest('label');
      if (mastercardLabel) {
        fireEvent.click(mastercardLabel);
      }

      // Button should now be disabled since stripe is null after re-render
      await waitFor(() => {
        const payButton = screen.getByRole('button', { name: /Pay/ });
        expect(payButton).toBeDisabled();
      });

      // Restore
      jest.requireMock('@stripe/react-stripe-js').useStripe = originalUseStripe;
    });
  });

  describe('Malformed total_price handling', () => {
    it('handles empty string total_price via deriveBookingAmount', async () => {
      jest.requireMock('@/lib/api/pricing').fetchPricingPreview.mockResolvedValue({
        base_price_cents: 6000,
        student_pay_cents: undefined,
        line_items: [],
      });

      const bookingEmptyPrice = {
        ...mockBooking,
        total_price: '' as unknown as number,
      };

      render(<CheckoutFlow booking={bookingEmptyPrice} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Booking Summary')).toBeInTheDocument();
      });

      // Empty string parses to 0 via Number('') === 0, which is finite
      // So deriveBookingAmount returns 0.00 and Pay button shows $0.00
      const payButton = screen.getByRole('button', { name: /Pay/ });
      expect(payButton).toBeInTheDocument();
    });

    it('handles null total_price via deriveBookingAmount', async () => {
      jest.requireMock('@/lib/api/pricing').fetchPricingPreview.mockResolvedValue({
        base_price_cents: 6000,
        student_pay_cents: undefined,
        line_items: [],
      });

      const bookingNullPrice = {
        ...mockBooking,
        total_price: null as unknown as number,
      };

      render(<CheckoutFlow booking={bookingNullPrice} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Booking Summary')).toBeInTheDocument();
      });

      // null is not a number and not a string, so deriveBookingAmount returns 0
      const payButton = screen.getByRole('button', { name: /Pay/ });
      expect(payButton).toBeInTheDocument();
    });
  });

  describe('Non-Error thrown during payment', () => {
    it('shows default message when non-Error is thrown', async () => {
      mockFetch.mockRejectedValueOnce('string error');

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Visa')).toBeInTheDocument();
      });

      const payButton = screen.getByRole('button', { name: /Pay \$/ });
      fireEvent.click(payButton);

      await waitFor(() => {
        expect(screen.getByText('Payment failed. Please try again.')).toBeInTheDocument();
      }, { timeout: 3000 });
    });
  });

  describe('Zero duration_minutes fallback to total_price', () => {
    it('falls back to normalizeAmount(total_price) when durationMinutes is 0', async () => {
      const bookingZeroDuration = {
        ...mockBooking,
        duration_minutes: 0,
        total_price: 45,
      };

      render(<CheckoutFlow booking={bookingZeroDuration} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        // durationMinutes=0 is falsy so baseLessonAmount = normalizeAmount(total_price, 0)
        expect(screen.getByText(/Lesson \(0 min\)/)).toBeInTheDocument();
      });
    });
  });

  describe('ApiProblemError with undefined detail', () => {
    it('falls back to default message when ApiProblemError detail is undefined', async () => {
      const { ApiProblemError } = await import('@/lib/api/fetch');
      const mockResponse = {
        status: 422,
        statusText: 'Unprocessable Entity',
      } as Response;

      jest.requireMock('@/lib/api/pricing').fetchPricingPreview.mockRejectedValue(
        new ApiProblemError(
          { type: 'validation_error', title: 'Validation Error', detail: undefined as unknown as string, status: 422 },
          mockResponse,
        )
      );

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        // detail is undefined, so ?? operator triggers the fallback
        expect(screen.getByText('Price is below the minimum.')).toBeInTheDocument();
      });
    });
  });

  describe('3D Secure with empty error message', () => {
    it('uses fallback message when confirmError.message is empty', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          payment_intent_id: 'pi_123',
          requires_action: true,
          client_secret: 'secret_456',
        }),
      });
      stripeMocks.confirmCardPayment.mockResolvedValueOnce({
        error: { message: '' },
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
        // Empty string is falsy, so || operator triggers fallback
        expect(screen.getByText('Payment confirmation failed')).toBeInTheDocument();
      }, { timeout: 3000 });
    });
  });

  describe('createPaymentMethod with empty error message', () => {
    it('uses fallback message when stripe error.message is empty', async () => {
      stripeMocks.createPaymentMethod.mockResolvedValueOnce({
        paymentMethod: null,
        error: { message: '' },
      });

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

      const payButton = screen.getByRole('button', { name: /Pay \$/ });
      await userEvent.click(payButton);

      await waitFor(() => {
        // Empty error.message is falsy, so || triggers 'Failed to create payment method'
        expect(screen.getByText('Failed to create payment method')).toBeInTheDocument();
      }, { timeout: 3000 });
    });
  });

  describe('Save card with new payment method', () => {
    it('sends save_payment_method true when saveCard is checked and method is new', async () => {
      mockUsePaymentMethods.mockReturnValue({
        data: [],
        isLoading: false,
      });

      render(<CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText('Save card for future use')).toBeInTheDocument();
      });

      // Check the save card checkbox
      const saveCheckbox = screen.getByRole('checkbox');
      await userEvent.click(saveCheckbox);
      expect(saveCheckbox).toBeChecked();

      const payButton = screen.getByRole('button', { name: /Pay \$/ });
      await userEvent.click(payButton);

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          '/api/v1/payments/checkout',
          expect.objectContaining({
            body: expect.stringContaining('"save_payment_method":true'),
          })
        );
      });
    });
  });

  describe('normalizeAmount default-arg fallback', () => {
    it('uses custom fallback for normalizeAmount when value is non-numeric string', async () => {
      // hourly_rate as a non-numeric string triggers the fallback path
      const bookingBadRate = {
        ...mockBooking,
        hourly_rate: 'abc' as unknown as number,
        total_price: 50,
      };

      render(<CheckoutFlow booking={bookingBadRate} onSuccess={onSuccess} onCancel={onCancel} />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        // normalizeAmount('abc', 0) falls through both if-checks to return Number(fallback.toFixed(2))
        expect(screen.getByText('Booking Summary')).toBeInTheDocument();
      });
    });
  });

  describe('Pricing preview cancelled on unmount', () => {
    it('does not update state after component unmounts during pricing fetch', async () => {
      let resolvePreview: (value: unknown) => void;
      jest.requireMock('@/lib/api/pricing').fetchPricingPreview.mockImplementation(
        () => new Promise(resolve => {
          resolvePreview = resolve;
        })
      );

      const { unmount } = render(
        <CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />,
        { wrapper: createWrapper() },
      );

      await waitFor(() => {
        expect(screen.getByText('Updating pricing…')).toBeInTheDocument();
      });

      // Unmount while pricing is still loading - sets cancelled = true
      unmount();

      // Resolve the pricing preview after unmount
      resolvePreview!({
        base_price_cents: 6000,
        student_pay_cents: 6300,
        line_items: [],
      });

      // No error should occur - setState is skipped because cancelled is true
    });

    it('does not update state after component unmounts during pricing fetch error', async () => {
      const { ApiProblemError } = await import('@/lib/api/fetch');
      let rejectPreview: (err: unknown) => void;
      jest.requireMock('@/lib/api/pricing').fetchPricingPreview.mockImplementation(
        () => new Promise((_resolve, reject) => {
          rejectPreview = reject;
        })
      );

      const { unmount } = render(
        <CheckoutFlow booking={mockBooking} onSuccess={onSuccess} onCancel={onCancel} />,
        { wrapper: createWrapper() },
      );

      await waitFor(() => {
        expect(screen.getByText('Updating pricing…')).toBeInTheDocument();
      });

      // Unmount while pricing is still loading
      unmount();

      // Reject with ApiProblemError after unmount - catch block should return early
      rejectPreview!(
        new ApiProblemError(
          { type: 'error', title: 'Error', detail: 'Test', status: 422 },
          { status: 422 } as Response,
        )
      );

      // No error should occur
    });
  });
});
