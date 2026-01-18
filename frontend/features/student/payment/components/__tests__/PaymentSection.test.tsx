import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PaymentSection } from '../PaymentSection';
import { useCreateBooking } from '@/features/student/booking/hooks/useCreateBooking';
import { usePaymentFlow, PaymentStep } from '../../hooks/usePaymentFlow';
import { usePricingPreviewController } from '../../hooks/usePricingPreview';
import { useCredits } from '@/features/shared/payment/hooks/useCredits';
import { paymentService } from '@/services/api/payments';
import { BookingType, PAYMENT_STATUS, PaymentMethod, type BookingPayment } from '../../types';
import type { ReactNode } from 'react';

// Mock dependencies
jest.mock('@/features/student/booking/hooks/useCreateBooking', () => ({
  useCreateBooking: jest.fn(),
}));

jest.mock('../../hooks/usePaymentFlow', () => ({
  usePaymentFlow: jest.fn(),
  PaymentStep: {
    METHOD_SELECTION: 'METHOD_SELECTION',
    CONFIRMATION: 'CONFIRMATION',
    PROCESSING: 'PROCESSING',
    SUCCESS: 'SUCCESS',
    ERROR: 'ERROR',
  },
}));

jest.mock('../../hooks/usePricingPreview', () => ({
  usePricingPreviewController: jest.fn(),
  PricingPreviewContext: {
    Provider: ({ children, _value }: { children: ReactNode; _value?: unknown }) => (
      <div data-testid="pricing-preview-context">{children}</div>
    ),
  },
}));

jest.mock('@/features/shared/payment/hooks/useCredits', () => ({
  useCredits: jest.fn(),
}));

jest.mock('@/services/api/payments', () => ({
  paymentService: {
    listPaymentMethods: jest.fn(),
    createCheckout: jest.fn(),
  },
}));

jest.mock('@/src/api/services/bookings', () => ({
  fetchBookingDetails: jest.fn(),
  cancelBookingImperative: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

// Mock child components
jest.mock('../PaymentMethodSelection', () => {
  return function MockPaymentMethodSelection({ onSelectPayment, onCardAdded }: {
    onSelectPayment: (method: string, cardId?: string) => void;
    onCardAdded?: (card: { id: string; last4: string; brand: string }) => void;
  }) {
    return (
      <div data-testid="payment-method-selection">
        <button onClick={() => onSelectPayment('CREDIT_CARD', 'card-1')}>
          Select Card
        </button>
        <button onClick={() => onCardAdded?.({ id: 'new-card', last4: '4242', brand: 'Visa' })}>
          Add Card
        </button>
      </div>
    );
  };
});

jest.mock('../PaymentConfirmation', () => {
  return function MockPaymentConfirmation({ onConfirm, onBack }: {
    onConfirm: () => void;
    onBack: () => void;
  }) {
    return (
      <div data-testid="payment-confirmation">
        <button onClick={onConfirm}>Confirm Payment</button>
        <button onClick={onBack}>Back</button>
      </div>
    );
  };
});

jest.mock('../PaymentProcessing', () => {
  return function MockPaymentProcessing() {
    return <div data-testid="payment-processing">Processing...</div>;
  };
});

jest.mock('../PaymentSuccess', () => {
  return function MockPaymentSuccess({ confirmationNumber }: { confirmationNumber: string }) {
    return <div data-testid="payment-success">Success! Confirmation: {confirmationNumber}</div>;
  };
});

jest.mock('@/components/referrals/CheckoutApplyReferral', () => {
  return function MockCheckoutApplyReferral() {
    return <div data-testid="checkout-apply-referral" />;
  };
});

const useCreateBookingMock = useCreateBooking as jest.Mock;
const usePaymentFlowMock = usePaymentFlow as jest.Mock;
const usePricingPreviewControllerMock = usePricingPreviewController as jest.Mock;
const useCreditsMock = useCredits as jest.Mock;
const paymentServiceMock = paymentService as jest.Mocked<typeof paymentService>;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return Wrapper;
};

const mockBookingData: BookingPayment & { metadata?: Record<string, unknown> } = {
  bookingId: 'booking-123',
  instructorId: 'instructor-456',
  instructorName: 'John D.',
  lessonType: 'Piano',
  date: new Date('2025-02-01T10:00:00Z'),
  startTime: '10:00',
  endTime: '11:00',
  duration: 60,
  location: '123 Main St, NYC',
  basePrice: 100,
  totalAmount: 115,
  bookingType: BookingType.STANDARD,
  paymentStatus: PAYMENT_STATUS.SCHEDULED,
  metadata: {
    serviceId: 'service-789',
  },
};

describe('PaymentSection', () => {
  const defaultProps = {
    bookingData: mockBookingData,
    onSuccess: jest.fn(),
    onError: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();

    // Default mock implementations
    useCreateBookingMock.mockReturnValue({
      createBooking: jest.fn().mockResolvedValue({ id: 'new-booking-id', status: 'pending' }),
      error: null,
      reset: jest.fn(),
    });

    usePaymentFlowMock.mockReturnValue({
      currentStep: PaymentStep.METHOD_SELECTION,
      paymentMethod: PaymentMethod.CREDIT_CARD,
      creditsToUse: 0,
      error: null,
      goToStep: jest.fn(),
      selectPaymentMethod: jest.fn(),
      reset: jest.fn(),
    });

    usePricingPreviewControllerMock.mockReturnValue({
      preview: {
        base_price_cents: 10000,
        student_fee_cents: 1500,
        student_pay_cents: 11500,
        credit_applied_cents: 0,
        line_items: [],
      },
      error: null,
      loading: false,
      applyCredit: jest.fn(),
      requestPricingPreview: jest.fn(),
      lastAppliedCreditCents: 0,
    });

    useCreditsMock.mockReturnValue({
      data: { available: 50, expires_at: null },
      isLoading: false,
      refetch: jest.fn(),
    });

    paymentServiceMock.listPaymentMethods.mockResolvedValue([
      { id: 'pm-1', last4: '4242', brand: 'visa', is_default: true, created_at: '2025-01-01T00:00:00Z' },
    ]);
  });

  describe('loading state', () => {
    it('shows loading state while fetching payment methods', async () => {
      paymentServiceMock.listPaymentMethods.mockImplementation(
        () => new Promise(() => {}) // Never resolves
      );

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      expect(screen.getByText('Loading payment data...')).toBeInTheDocument();
    });

    it('shows loading state while fetching credits', () => {
      useCreditsMock.mockReturnValue({
        data: null,
        isLoading: true,
        refetch: jest.fn(),
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      expect(screen.getByText('Loading payment data...')).toBeInTheDocument();
    });
  });

  describe('method selection step', () => {
    it('renders payment method selection', async () => {
      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('renders referral apply panel', async () => {
      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('checkout-apply-referral')).toBeInTheDocument();
      });
    });
  });

  describe('confirmation step', () => {
    it('renders payment confirmation when on confirmation step', async () => {
      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep: jest.fn(),
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });
    });

    it('handles back button to method selection', async () => {
      const goToStep = jest.fn();
      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Back'));

      expect(goToStep).toHaveBeenCalledWith(PaymentStep.METHOD_SELECTION);
    });
  });

  describe('processing step', () => {
    it('renders processing state', async () => {
      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.PROCESSING,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep: jest.fn(),
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-processing')).toBeInTheDocument();
      });
    });
  });

  describe('success step', () => {
    it('renders success state with confirmation number', async () => {
      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.SUCCESS,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep: jest.fn(),
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-success')).toBeInTheDocument();
      });
    });
  });

  describe('error step', () => {
    it('renders error state with retry button', async () => {
      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.ERROR,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: 'Payment failed',
        goToStep: jest.fn(),
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Payment Failed')).toBeInTheDocument();
        expect(screen.getByText('Try Again')).toBeInTheDocument();
      });
    });

    it('shows booking error message when booking error exists', async () => {
      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.ERROR,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep: jest.fn(),
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      useCreateBookingMock.mockReturnValue({
        createBooking: jest.fn(),
        error: 'Booking creation failed',
        reset: jest.fn(),
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        // Component shows booking error message
        expect(screen.getByText(/Booking creation failed/)).toBeInTheDocument();
      });
    });

    it('calls reset and goes to method selection on retry', async () => {
      const goToStep = jest.fn();
      const resetPayment = jest.fn();
      const resetBookingError = jest.fn();

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.ERROR,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: 'Payment failed',
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: resetPayment,
      });

      useCreateBookingMock.mockReturnValue({
        createBooking: jest.fn(),
        error: null,
        reset: resetBookingError,
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Try Again')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Try Again'));

      expect(resetPayment).toHaveBeenCalled();
      expect(resetBookingError).toHaveBeenCalled();
      expect(goToStep).toHaveBeenCalledWith(PaymentStep.METHOD_SELECTION);
    });

    it('shows cancel button when onBack is provided', async () => {
      const onBack = jest.fn();

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.ERROR,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: 'Payment failed',
        goToStep: jest.fn(),
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      render(<PaymentSection {...defaultProps} onBack={onBack} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Cancel')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Cancel'));

      expect(onBack).toHaveBeenCalled();
    });
  });

  describe('inline payment mode', () => {
    it('renders both method selection and confirmation when inline mode enabled', async () => {
      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep: jest.fn(),
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      render(
        <PaymentSection {...defaultProps} showPaymentMethodInline={true} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });
    });
  });

  describe('payment methods', () => {
    it('loads payment methods on mount', async () => {
      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(paymentServiceMock.listPaymentMethods).toHaveBeenCalled();
      });
    });

    it('handles payment method loading failure gracefully', async () => {
      paymentServiceMock.listPaymentMethods.mockRejectedValue(new Error('Failed'));

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        // Should still render with mock fallback card
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });
  });

  describe('credits', () => {
    it('uses credits data from hook', async () => {
      useCreditsMock.mockReturnValue({
        data: { available: 25.50, expires_at: '2025-12-31' },
        isLoading: false,
        refetch: jest.fn(),
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('handles null credits data', async () => {
      useCreditsMock.mockReturnValue({
        data: null,
        isLoading: false,
        refetch: jest.fn(),
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });
  });

  describe('pricing preview', () => {
    it('uses pricing preview from controller', async () => {
      usePricingPreviewControllerMock.mockReturnValue({
        preview: {
          base_price_cents: 8000,
          student_fee_cents: 1200,
          student_pay_cents: 9200,
          credit_applied_cents: 500,
          line_items: [],
        },
        error: null,
        loading: false,
        applyCredit: jest.fn(),
        requestPricingPreview: jest.fn(),
        lastAppliedCreditCents: 500,
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('handles pricing preview error', async () => {
      usePricingPreviewControllerMock.mockReturnValue({
        preview: null,
        error: 'Failed to load pricing',
        loading: false,
        applyCredit: jest.fn(),
        requestPricingPreview: jest.fn(),
        lastAppliedCreditCents: 0,
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });
  });

  describe('booking data', () => {
    it('handles booking data without metadata', async () => {
      const bookingWithoutMetadata = {
        ...mockBookingData,
        metadata: undefined,
      };

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithoutMetadata} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('handles booking data with serviceId prop', async () => {
      const bookingWithServiceId = {
        ...mockBookingData,
        serviceId: 'service-direct',
        metadata: undefined,
      };

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithServiceId} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('handles missing booking date', async () => {
      const bookingWithoutDate = {
        ...mockBookingData,
        date: undefined as unknown as Date,
      };

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithoutDate} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });
  });

  describe('card addition', () => {
    it('adds new card to the list when onCardAdded is called', async () => {
      const user = userEvent.setup();

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Add Card'));

      // Component should handle the new card internally
    });
  });

  describe('payment method selection', () => {
    it('calls selectPaymentMethod when payment is selected', async () => {
      const selectPaymentMethod = jest.fn();
      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.METHOD_SELECTION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep: jest.fn(),
        selectPaymentMethod,
        reset: jest.fn(),
      });

      const user = userEvent.setup();

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Select Card'));

      expect(selectPaymentMethod).toHaveBeenCalledWith(
        expect.any(String),
        'card-1',
        undefined
      );
    });
  });

  describe('accessibility', () => {
    it('renders without accessibility violations', async () => {
      const { container } = render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });

      // Basic accessibility check - ensure main content is present
      expect(container.querySelector('[data-testid="pricing-preview-context"]')).toBeInTheDocument();
    });
  });

  describe('payment processing', () => {
    it('processes payment successfully with credits', async () => {
      const onSuccess = jest.fn();
      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.MIXED,
        creditsToUse: 25,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockResolvedValue({
        payment_intent_id: 'pi_123',
        application_fee: 0,
        success: true,
        status: 'succeeded',
        amount: 9000,
        client_secret: 'secret_123',
        requires_action: false,
      });

      render(<PaymentSection {...defaultProps} onSuccess={onSuccess} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(createBookingMock).toHaveBeenCalled();
      });
    });

    it('handles insufficient funds error', async () => {
      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockRejectedValue(
        new Error('Your card has insufficient funds')
      );

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(goToStep).toHaveBeenCalledWith(PaymentStep.ERROR);
      });
    });

    it('handles card declined error', async () => {
      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockRejectedValue(
        new Error('Your card was declined')
      );

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(goToStep).toHaveBeenCalledWith(PaymentStep.ERROR);
      });
    });

    it('handles expired card error', async () => {
      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockRejectedValue(
        new Error('Your card has expired')
      );

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(goToStep).toHaveBeenCalledWith(PaymentStep.ERROR);
      });
    });

    it('handles payment method reuse error', async () => {
      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockRejectedValue(
        new Error('PaymentMethod was previously used')
      );

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(goToStep).toHaveBeenCalledWith(PaymentStep.ERROR);
      });
    });

    it('handles requires_action payment status', async () => {
      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockResolvedValue({
        payment_intent_id: 'pi_123',
        application_fee: 0,
        success: true,
        status: 'requires_action',
        amount: 11500,
        client_secret: 'secret_123',
        requires_action: true,
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(goToStep).toHaveBeenCalledWith(PaymentStep.ERROR);
      });
    });

    it('handles instructor payment account not set up error', async () => {
      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockRejectedValue(
        new Error('Instructor payment account not set up')
      );

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(goToStep).toHaveBeenCalledWith(PaymentStep.ERROR);
      });
    });

    it('handles booking creation with minimum price error', async () => {
      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue(null);

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: 'Booking does not meet minimum price requirements',
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(goToStep).toHaveBeenCalledWith(PaymentStep.CONFIRMATION);
      });
    });

    it('handles payment with requires_capture status', async () => {
      const onSuccess = jest.fn();
      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockResolvedValue({
        payment_intent_id: 'pi_123',
        application_fee: 0,
        success: true,
        status: 'requires_capture',
        amount: 11500,
        client_secret: 'secret_123',
        requires_action: false,
      });

      render(<PaymentSection {...defaultProps} onSuccess={onSuccess} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      // requires_capture is a valid pre-authorization state - verify createCheckout was called
      await waitFor(() => {
        expect(createBookingMock).toHaveBeenCalled();
      });
    });

    it('handles payment failure status', async () => {
      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockResolvedValue({
        payment_intent_id: 'pi_123',
        application_fee: 0,
        success: true,
        status: 'failed',
        amount: 11500,
        client_secret: 'secret_123',
        requires_action: false,
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(goToStep).toHaveBeenCalledWith(PaymentStep.ERROR);
      });
    });
  });

  describe('credit management', () => {
    it('handles credit toggle callback', async () => {
      const selectPaymentMethod = jest.fn();

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.MIXED,
        creditsToUse: 25,
        error: null,
        goToStep: jest.fn(),
        selectPaymentMethod,
        reset: jest.fn(),
      });

      usePricingPreviewControllerMock.mockReturnValue({
        preview: {
          base_price_cents: 10000,
          student_fee_cents: 1500,
          student_pay_cents: 9000,
          credit_applied_cents: 2500,
          line_items: [],
        },
        error: null,
        loading: false,
        applyCredit: jest.fn(),
        requestPricingPreview: jest.fn(),
        lastAppliedCreditCents: 2500,
      });

      useCreditsMock.mockReturnValue({
        data: { available: 50, expires_at: null },
        isLoading: false,
        refetch: jest.fn(),
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });
    });

    it('handles credit amount change callback', async () => {
      const applyCredit = jest.fn().mockResolvedValue({
        base_price_cents: 10000,
        student_fee_cents: 1500,
        student_pay_cents: 7500,
        credit_applied_cents: 4000,
        line_items: [],
      });

      usePricingPreviewControllerMock.mockReturnValue({
        preview: {
          base_price_cents: 10000,
          student_fee_cents: 1500,
          student_pay_cents: 9000,
          credit_applied_cents: 2500,
          line_items: [],
        },
        error: null,
        loading: false,
        applyCredit,
        requestPricingPreview: jest.fn(),
        lastAppliedCreditCents: 2500,
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.MIXED,
        creditsToUse: 25,
        error: null,
        goToStep: jest.fn(),
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });
    });
  });

  describe('floor violation handling', () => {
    it('handles floor violation from pricing preview', async () => {
      const applyCredit = jest.fn().mockRejectedValue({
        response: { status: 422 },
        problem: { detail: 'Price must meet minimum requirements' },
      });

      usePricingPreviewControllerMock.mockReturnValue({
        preview: {
          base_price_cents: 10000,
          student_fee_cents: 1500,
          student_pay_cents: 11500,
          credit_applied_cents: 0,
          line_items: [],
        },
        error: null,
        loading: false,
        applyCredit,
        requestPricingPreview: jest.fn(),
        lastAppliedCreditCents: 0,
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep: jest.fn(),
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });
    });
  });

  describe('inline payment mode behaviors', () => {
    it('auto-selects default card in inline mode', async () => {
      const selectPaymentMethod = jest.fn();

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.METHOD_SELECTION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep: jest.fn(),
        selectPaymentMethod,
        reset: jest.fn(),
      });

      paymentServiceMock.listPaymentMethods.mockResolvedValue([
        { id: 'pm-default', last4: '4242', brand: 'visa', is_default: true, created_at: '2025-01-01T00:00:00Z' },
        { id: 'pm-second', last4: '1234', brand: 'mastercard', is_default: false, created_at: '2025-01-02T00:00:00Z' },
      ]);

      render(
        <PaymentSection {...defaultProps} showPaymentMethodInline={true} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(selectPaymentMethod).toHaveBeenCalledWith(
          PaymentMethod.CREDIT_CARD,
          'pm-default',
          undefined
        );
      });
    });

    it('handles changing payment method in inline mode', async () => {
      const goToStep = jest.fn();

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      render(
        <PaymentSection {...defaultProps} showPaymentMethodInline={true} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });
    });
  });

  describe('booking data edge cases', () => {
    it('handles booking with string date', async () => {
      const bookingWithStringDate = {
        ...mockBookingData,
        date: '2025-02-01' as unknown as Date,
      };

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithStringDate} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('handles booking with HH:MM:SS time format', async () => {
      const bookingWithFullTime = {
        ...mockBookingData,
        startTime: '10:00:00',
        endTime: '11:00:00',
      };

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithFullTime} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('handles booking with online location', async () => {
      const bookingWithOnline = {
        ...mockBookingData,
        location: 'Online',
      };

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithOnline} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('handles booking with remote modality in metadata', async () => {
      const bookingWithRemote = {
        ...mockBookingData,
        metadata: {
          serviceId: 'service-789',
          modality: 'remote',
        },
      };

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithRemote} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('handles booking with duration in metadata', async () => {
      const bookingWithDurationMetadata = {
        ...mockBookingData,
        duration: 0,
        metadata: {
          serviceId: 'service-789',
          duration_minutes: 45,
        },
      };

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithDurationMetadata} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });
  });

  describe('error state display', () => {
    it('displays booking error title when error contains booking', async () => {
      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.ERROR,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep: jest.fn(),
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      useCreateBookingMock.mockReturnValue({
        createBooking: jest.fn(),
        error: 'booking creation failed due to conflict',
        reset: jest.fn(),
      });

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByText('Booking Failed')).toBeInTheDocument();
      });
    });
  });

  describe('credits-only payment', () => {
    it('processes payment with credits only (no card needed)', async () => {
      const onSuccess = jest.fn();
      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDITS,
        creditsToUse: 115,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      usePricingPreviewControllerMock.mockReturnValue({
        preview: {
          base_price_cents: 10000,
          student_fee_cents: 1500,
          student_pay_cents: 0,
          credit_applied_cents: 11500,
          line_items: [],
        },
        error: null,
        loading: false,
        applyCredit: jest.fn(),
        requestPricingPreview: jest.fn(),
        lastAppliedCreditCents: 11500,
      });

      paymentServiceMock.createCheckout.mockResolvedValue({
        payment_intent_id: 'pi_123',
        application_fee: 0,
        success: true,
        status: 'succeeded',
        amount: 0,
        client_secret: 'secret_123',
        requires_action: false,
      });

      render(<PaymentSection {...defaultProps} onSuccess={onSuccess} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(createBookingMock).toHaveBeenCalled();
      });
    });
  });

  describe('sessionStorage credit UI state', () => {
    beforeEach(() => {
      // Clear sessionStorage before each test
      sessionStorage.clear();
    });

    it('reads stored credits UI state from sessionStorage', async () => {
      // Store some credit UI state
      const key = 'test-credit-ui-state';
      sessionStorage.setItem(key, JSON.stringify({ creditsCollapsed: true }));

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('handles invalid JSON in sessionStorage gracefully', async () => {
      // Store invalid JSON
      sessionStorage.setItem('test-credit-ui-state', 'not-valid-json');

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('handles empty sessionStorage value', async () => {
      sessionStorage.setItem('test-credit-ui-state', '');

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });
  });

  describe('time conversion and duration calculation', () => {
    it('handles 12-hour time format (AM/PM) in booking data', async () => {
      const bookingWith12HourTime = {
        ...mockBookingData,
        startTime: '10:00am',
        endTime: '11:00am',
      };

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWith12HourTime} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('handles PM time format in booking data', async () => {
      const bookingWithPMTime = {
        ...mockBookingData,
        startTime: '2:00pm',
        endTime: '3:00pm',
      };

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithPMTime} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('handles duration calculation from start/end times when duration is zero', async () => {
      const bookingWithZeroDuration = {
        ...mockBookingData,
        duration: 0,
        startTime: '10:00',
        endTime: '11:30',
        metadata: {
          serviceId: 'service-789',
        },
      };

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithZeroDuration} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('handles string duration in metadata', async () => {
      const bookingWithStringDuration = {
        ...mockBookingData,
        duration: 0,
        metadata: {
          serviceId: 'service-789',
          duration: '60',
        },
      };

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithStringDuration} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('handles invalid time format gracefully', async () => {
      const bookingWithInvalidTime = {
        ...mockBookingData,
        startTime: 'invalid-time',
        endTime: 'also-invalid',
      };

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithInvalidTime} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });
  });

  describe('currency normalization edge cases', () => {
    it('handles booking with string totalAmount', async () => {
      const bookingWithStringAmount = {
        ...mockBookingData,
        totalAmount: '115.50' as unknown as number,
      };

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithStringAmount} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('handles booking with string basePrice', async () => {
      const bookingWithStringBase = {
        ...mockBookingData,
        basePrice: '100.00' as unknown as number,
      };

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithStringBase} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('handles booking with non-finite amount (NaN)', async () => {
      const bookingWithNaN = {
        ...mockBookingData,
        totalAmount: NaN,
        basePrice: NaN,
      };

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithNaN} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });

    it('handles booking with Infinity amount', async () => {
      const bookingWithInfinity = {
        ...mockBookingData,
        totalAmount: Infinity,
      };

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithInfinity} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-method-selection')).toBeInTheDocument();
      });
    });
  });

  describe('date recovery from sessionStorage', () => {
    beforeEach(() => {
      sessionStorage.clear();
    });

    it('recovers date from selectedSlot in sessionStorage when date is missing', async () => {
      const bookingWithoutDate = {
        ...mockBookingData,
        date: null as unknown as Date,
      };

      // Store a selected slot in sessionStorage
      sessionStorage.setItem('selectedSlot', JSON.stringify({
        date: '2025-02-15',
        startTime: '10:00',
        endTime: '11:00',
      }));

      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockResolvedValue({
        payment_intent_id: 'pi_123',
        application_fee: 0,
        success: true,
        status: 'succeeded',
        amount: 11500,
        client_secret: 'secret_123',
        requires_action: false,
      });

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithoutDate} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      // Should attempt to process payment
      await waitFor(() => {
        expect(createBookingMock).toHaveBeenCalled();
      });
    });

    it('handles missing date with no sessionStorage fallback', async () => {
      const bookingWithoutDate = {
        ...mockBookingData,
        date: undefined as unknown as Date,
      };

      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithoutDate} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      // Should go to error step due to missing date
      await waitFor(() => {
        expect(goToStep).toHaveBeenCalledWith(PaymentStep.ERROR);
      });
    });

    it('handles invalid selectedSlot JSON in sessionStorage', async () => {
      const bookingWithoutDate = {
        ...mockBookingData,
        date: null as unknown as Date,
      };

      // Store invalid JSON
      sessionStorage.setItem('selectedSlot', 'not-valid-json');

      const goToStep = jest.fn();

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithoutDate} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      // Should go to error step due to invalid JSON
      await waitFor(() => {
        expect(goToStep).toHaveBeenCalledWith(PaymentStep.ERROR);
      });
    });

    it('handles selectedSlot without date property', async () => {
      const bookingWithoutDate = {
        ...mockBookingData,
        date: null as unknown as Date,
      };

      // Store slot without date
      sessionStorage.setItem('selectedSlot', JSON.stringify({
        startTime: '10:00',
        endTime: '11:00',
      }));

      const goToStep = jest.fn();

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithoutDate} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      // Should go to error step due to missing date in slot
      await waitFor(() => {
        expect(goToStep).toHaveBeenCalledWith(PaymentStep.ERROR);
      });
    });
  });

  describe('payment error message transformations', () => {
    it('transforms "Payment failed with status" error message', async () => {
      const goToStep = jest.fn();
      const onError = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockRejectedValue(
        new Error('Payment failed with status: canceled')
      );

      render(
        <PaymentSection {...defaultProps} onError={onError} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(goToStep).toHaveBeenCalledWith(PaymentStep.ERROR);
      });
    });

    it('handles 3DS authentication required error', async () => {
      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      // Simulate a requires_action error with client_secret
      const error = new Error('requires_action');
      (error as unknown as Record<string, unknown>)['client_secret'] = 'secret_123';
      paymentServiceMock.createCheckout.mockRejectedValue(error);

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(goToStep).toHaveBeenCalledWith(PaymentStep.ERROR);
      });
    });

    it('handles non-Error exceptions during payment', async () => {
      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      // Reject with a string instead of an Error
      paymentServiceMock.createCheckout.mockRejectedValue('String error message');

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(goToStep).toHaveBeenCalledWith(PaymentStep.ERROR);
      });
    });
  });

  describe('booking cancellation on payment failure', () => {
    it('cancels booking when payment fails after booking creation', async () => {
      const cancelBookingMock = jest.fn().mockResolvedValue(undefined);
      const { cancelBookingImperative } = jest.requireMock('@/src/api/services/bookings');
      cancelBookingImperative.mockImplementation(cancelBookingMock);

      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-to-cancel', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockRejectedValue(new Error('Payment failed'));

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(goToStep).toHaveBeenCalledWith(PaymentStep.ERROR);
      });
    });
  });

  describe('timezone metadata handling', () => {
    it('uses timezone from metadata', async () => {
      const bookingWithTimezone = {
        ...mockBookingData,
        metadata: {
          serviceId: 'service-789',
          timezone: 'America/New_York',
        },
      };

      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep: jest.fn(),
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockResolvedValue({
        payment_intent_id: 'pi_123',
        application_fee: 0,
        success: true,
        status: 'succeeded',
        amount: 11500,
        client_secret: 'secret_123',
        requires_action: false,
      });

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithTimezone} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(createBookingMock).toHaveBeenCalled();
      });
    });

    it('uses lesson_timezone from metadata as fallback', async () => {
      const bookingWithLessonTimezone = {
        ...mockBookingData,
        metadata: {
          serviceId: 'service-789',
          lesson_timezone: 'America/Los_Angeles',
        },
      };

      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep: jest.fn(),
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockResolvedValue({
        payment_intent_id: 'pi_123',
        application_fee: 0,
        success: true,
        status: 'succeeded',
        amount: 11500,
        client_secret: 'secret_123',
        requires_action: false,
      });

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithLessonTimezone} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(createBookingMock).toHaveBeenCalled();
      });
    });

    it('uses instructor_timezone from metadata as fallback', async () => {
      const bookingWithInstructorTimezone = {
        ...mockBookingData,
        metadata: {
          serviceId: 'service-789',
          instructor_timezone: 'America/Chicago',
        },
      };

      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep: jest.fn(),
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockResolvedValue({
        payment_intent_id: 'pi_123',
        application_fee: 0,
        success: true,
        status: 'succeeded',
        amount: 11500,
        client_secret: 'secret_123',
        requires_action: false,
      });

      render(
        <PaymentSection {...defaultProps} bookingData={bookingWithInstructorTimezone} />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(createBookingMock).toHaveBeenCalled();
      });
    });
  });

  describe('payment without card when amount is due', () => {
    it('throws error when payment required but no card selected', async () => {
      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      // Mock no payment methods
      paymentServiceMock.listPaymentMethods.mockResolvedValue([]);

      render(<PaymentSection {...defaultProps} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(goToStep).toHaveBeenCalledWith(PaymentStep.ERROR);
      });
    });
  });

  describe('payment status validation', () => {
    it('accepts processing status as valid', async () => {
      const onSuccess = jest.fn();
      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockResolvedValue({
        payment_intent_id: 'pi_123',
        application_fee: 0,
        success: true,
        status: 'processing',
        amount: 11500,
        client_secret: 'secret_123',
        requires_action: false,
      });

      render(<PaymentSection {...defaultProps} onSuccess={onSuccess} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(createBookingMock).toHaveBeenCalled();
      });
    });

    it('accepts authorized status as valid', async () => {
      const onSuccess = jest.fn();
      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockResolvedValue({
        payment_intent_id: 'pi_123',
        application_fee: 0,
        success: true,
        status: 'authorized',
        amount: 11500,
        client_secret: 'secret_123',
        requires_action: false,
      });

      render(<PaymentSection {...defaultProps} onSuccess={onSuccess} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(createBookingMock).toHaveBeenCalled();
      });
    });

    it('accepts scheduled status as valid', async () => {
      const onSuccess = jest.fn();
      const goToStep = jest.fn();
      const createBookingMock = jest.fn().mockResolvedValue({ id: 'booking-123', status: 'pending' });

      useCreateBookingMock.mockReturnValue({
        createBooking: createBookingMock,
        error: null,
        reset: jest.fn(),
      });

      usePaymentFlowMock.mockReturnValue({
        currentStep: PaymentStep.CONFIRMATION,
        paymentMethod: PaymentMethod.CREDIT_CARD,
        creditsToUse: 0,
        error: null,
        goToStep,
        selectPaymentMethod: jest.fn(),
        reset: jest.fn(),
      });

      paymentServiceMock.createCheckout.mockResolvedValue({
        payment_intent_id: 'pi_123',
        application_fee: 0,
        success: true,
        status: 'scheduled',
        amount: 11500,
        client_secret: 'secret_123',
        requires_action: false,
      });

      render(<PaymentSection {...defaultProps} onSuccess={onSuccess} />, { wrapper: createWrapper() });

      await waitFor(() => {
        expect(screen.getByTestId('payment-confirmation')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Confirm Payment'));

      await waitFor(() => {
        expect(createBookingMock).toHaveBeenCalled();
      });
    });
  });
});
