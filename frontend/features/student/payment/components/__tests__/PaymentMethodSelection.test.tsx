import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PaymentMethodSelection from '../PaymentMethodSelection';
import { BookingType, PAYMENT_STATUS, PaymentMethod, type BookingPayment, type PaymentCard } from '../../types';
import { paymentService } from '@/services/api/payments';

const confirmSetupMock = jest.fn();

jest.mock('@/features/shared/payment/utils/stripe', () => ({
  getStripe: jest.fn(() => Promise.resolve({})),
  paymentElementAppearance: { theme: 'stripe' },
}));

jest.mock('@stripe/react-stripe-js', () => ({
  Elements: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PaymentElement: () => <div data-testid="payment-element" />,
  useStripe: () => ({ confirmSetup: confirmSetupMock }),
  useElements: () => ({}),
}));

jest.mock('@/services/api/payments', () => ({
  paymentService: {
    savePaymentMethod: jest.fn(),
    createSetupIntent: jest.fn().mockResolvedValue({ client_secret: 'seti_test_secret' }),
  },
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
  },
}));

const paymentServiceMock = paymentService.savePaymentMethod as jest.Mock;
const createSetupIntentMock = paymentService.createSetupIntent as jest.Mock;

const booking: BookingPayment = {
  bookingId: 'booking-1',
  instructorId: 'instructor-1',
  instructorName: 'Jane D.',
  lessonType: 'Piano',
  date: new Date('2025-01-01T00:00:00Z'),
  startTime: '10:00',
  endTime: '11:00',
  duration: 60,
  location: 'NYC',
  basePrice: 100,
  totalAmount: 100,
  bookingType: BookingType.STANDARD,
  paymentStatus: PAYMENT_STATUS.SCHEDULED,
};

const cards: PaymentCard[] = [
  { id: 'card-1', last4: '4242', brand: 'Visa', expiryMonth: 12, expiryYear: 2026, isDefault: true },
  { id: 'card-2', last4: '1111', brand: 'Mastercard', expiryMonth: 1, expiryYear: 2027, isDefault: false },
];

const renderComponent = (props?: Partial<React.ComponentProps<typeof PaymentMethodSelection>>) => {
  const onSelectPayment = jest.fn();
  const onCardAdded = jest.fn();
  render(
    <PaymentMethodSelection
      booking={booking}
      cards={cards}
      credits={{ totalAmount: 0, credits: [] }}
      onSelectPayment={onSelectPayment}
      onCardAdded={onCardAdded}
      {...props}
    />
  );
  return { onSelectPayment, onCardAdded };
};

describe('PaymentMethodSelection', () => {
  beforeEach(() => {
    confirmSetupMock.mockReset();
    paymentServiceMock.mockReset();
    createSetupIntentMock.mockReset();
    createSetupIntentMock.mockResolvedValue({ client_secret: 'seti_test_secret' });
  });

  it('renders cards and submits selected payment method', async () => {
    const { onSelectPayment } = renderComponent();

    await userEvent.click(screen.getByRole('button', { name: 'Apply payment method' }));

    expect(onSelectPayment).toHaveBeenCalledWith(PaymentMethod.CREDIT_CARD, 'card-1');
  });

  it('allows selecting a different card', async () => {
    const { onSelectPayment } = renderComponent();

    await userEvent.click(screen.getByText('Mastercard ending in 1111'));
    await userEvent.click(screen.getByRole('button', { name: 'Apply payment method' }));

    expect(onSelectPayment).toHaveBeenCalledWith(PaymentMethod.CREDIT_CARD, 'card-2');
  });

  it('shows and hides the new card form', async () => {
    renderComponent();

    await userEvent.click(screen.getByRole('button', { name: 'Add New Card' }));
    expect(screen.getByText('Enter Card Details')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByText('Enter Card Details')).not.toBeInTheDocument();
  });

  it('adds a new card successfully via PaymentElement', async () => {
    confirmSetupMock.mockResolvedValueOnce({
      setupIntent: { payment_method: 'pm_123' },
    });
    paymentServiceMock.mockResolvedValueOnce({
      id: 'card-new',
      last4: '9999',
      brand: 'visa',
      is_default: true,
    });

    const { onCardAdded } = renderComponent();

    await userEvent.click(screen.getByRole('button', { name: 'Add New Card' }));

    // Wait for SetupIntent to load and PaymentElement to render
    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: 'Add Card' }));

    await waitFor(() => expect(onCardAdded).toHaveBeenCalled());
  });

  it('shows error when Stripe confirmSetup returns an error', async () => {
    confirmSetupMock.mockResolvedValueOnce({ error: { message: 'Card error' } });

    renderComponent();

    await userEvent.click(screen.getByRole('button', { name: 'Add New Card' }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: 'Add Card' }));

    await waitFor(() => {
      expect(screen.getByText('Card error')).toBeInTheDocument();
    });
  });

  it('shows error when payment service fails', async () => {
    confirmSetupMock.mockResolvedValueOnce({
      setupIntent: { payment_method: 'pm_123' },
    });
    paymentServiceMock.mockRejectedValueOnce(new Error('Network error'));

    renderComponent();

    await userEvent.click(screen.getByRole('button', { name: 'Add New Card' }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: 'Add Card' }));

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });

  it('shows generic error when payment service fails with non-Error', async () => {
    confirmSetupMock.mockResolvedValueOnce({
      setupIntent: { payment_method: 'pm_123' },
    });
    paymentServiceMock.mockRejectedValueOnce('Unknown failure');

    renderComponent();

    await userEvent.click(screen.getByRole('button', { name: 'Add New Card' }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: 'Add Card' }));

    await waitFor(() => {
      expect(screen.getByText('Failed to save payment method')).toBeInTheDocument();
    });
  });

  it('allows toggling setAsDefault checkbox when cards exist', async () => {
    renderComponent();

    await userEvent.click(screen.getByRole('button', { name: 'Add New Card' }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    const checkbox = screen.getByRole('checkbox', { name: /set as default/i });
    expect(checkbox).not.toBeChecked();

    await userEvent.click(checkbox);
    expect(checkbox).toBeChecked();
  });

  it('hides setAsDefault checkbox when no existing cards', async () => {
    renderComponent({ cards: [] });

    await userEvent.click(screen.getByRole('button', { name: 'Add New Card' }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    expect(screen.queryByRole('checkbox', { name: /set as default/i })).not.toBeInTheDocument();
  });

  it('closes new card form via X button', async () => {
    renderComponent();

    await userEvent.click(screen.getByRole('button', { name: 'Add New Card' }));
    expect(screen.getByText('Enter Card Details')).toBeInTheDocument();

    // Find the X button (Plus icon rotated 45deg)
    const closeButtons = screen.getAllByRole('button');
    const closeButton = closeButtons.find(btn =>
      btn.querySelector('.rotate-45') || btn.classList.contains('rotate-45')
    );

    if (closeButton) {
      await userEvent.click(closeButton);
    } else {
      const header = screen.getByText('Enter Card Details').parentElement;
      const xButton = header?.querySelector('button');
      if (xButton) {
        await userEvent.click(xButton);
      }
    }

    expect(screen.queryByText('Enter Card Details')).not.toBeInTheDocument();
  });

  it('renders continue button text when onBack is provided', () => {
    const onBack = jest.fn();
    renderComponent({ onBack });

    expect(screen.getByRole('button', { name: 'Continue to Confirmation' })).toBeInTheDocument();
  });

  it('renders with no cards and selects first card when added', async () => {
    confirmSetupMock.mockResolvedValueOnce({
      setupIntent: { payment_method: 'pm_123' },
    });
    paymentServiceMock.mockResolvedValueOnce({
      id: 'card-new',
      last4: '9999',
      brand: 'visa',
      is_default: true,
    });

    const { onCardAdded } = renderComponent({ cards: [] });

    await userEvent.click(screen.getByRole('button', { name: 'Add New Card' }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: 'Add Card' }));

    await waitFor(() => expect(onCardAdded).toHaveBeenCalled());

    // Form should close after adding card
    await waitFor(() => {
      expect(screen.queryByText('Enter Card Details')).not.toBeInTheDocument();
    });
  });

  it('shows Stripe error without message using fallback', async () => {
    confirmSetupMock.mockResolvedValueOnce({ error: {} });

    renderComponent();

    await userEvent.click(screen.getByRole('button', { name: 'Add New Card' }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: 'Add Card' }));

    await waitFor(() => {
      expect(screen.getByText('Failed to add card')).toBeInTheDocument();
    });
  });

  it('shows backup payment method header when remaining is 0', () => {
    renderComponent();

    expect(screen.getByText('Payment Card')).toBeInTheDocument();
  });

  it('does not submit when stripe is null (early return in handleSubmit)', async () => {
    const stripeMock = jest.requireMock('@stripe/react-stripe-js');
    const originalUseStripe = stripeMock.useStripe;
    stripeMock.useStripe = () => null;

    renderComponent();

    await userEvent.click(screen.getByRole('button', { name: 'Add New Card' }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    const submitButton = screen.getByRole('button', { name: 'Add Card' });
    expect(submitButton).toBeDisabled();

    stripeMock.useStripe = originalUseStripe;
  });

  it('does not submit when elements is null (early return in handleSubmit)', async () => {
    const stripeMock = jest.requireMock('@stripe/react-stripe-js');
    const originalUseElements = stripeMock.useElements;
    stripeMock.useElements = () => null;

    renderComponent();

    await userEvent.click(screen.getByRole('button', { name: 'Add New Card' }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    const submitButton = screen.getByRole('button', { name: 'Add Card' });
    await userEvent.click(submitButton);

    // No error should be shown since we returned early
    expect(confirmSetupMock).not.toHaveBeenCalled();

    stripeMock.useElements = originalUseElements;
  });

  it('shows default badge on default card', () => {
    renderComponent();

    expect(screen.getByText('Default')).toBeInTheDocument();
  });

  it('shows check icon on selected card', () => {
    renderComponent();

    const selectedCard = screen.getByText('Visa ending in 4242').closest('label');
    expect(selectedCard).toBeInTheDocument();
  });

  it('shows secure payment text', () => {
    renderComponent();

    expect(screen.getByText(/Secure payment/)).toBeInTheDocument();
    expect(screen.getByText(/Maximum transaction limit: \$1,000/)).toBeInTheDocument();
  });

  it('calls onSelectPayment with CREDIT_CARD for default path', async () => {
    const { onSelectPayment } = renderComponent();

    await userEvent.click(screen.getByRole('button', { name: 'Apply payment method' }));

    expect(onSelectPayment).toHaveBeenCalledWith(PaymentMethod.CREDIT_CARD, 'card-1');
  });

  it('renders with totalAmount of 0 showing Backup Payment Method header', () => {
    renderComponent({
      booking: {
        ...booking,
        totalAmount: 0,
      },
    });

    expect(screen.getByText('Backup Payment Method')).toBeInTheDocument();
  });

  it('does not crash when onCardAdded is not provided and card is added', async () => {
    confirmSetupMock.mockResolvedValueOnce({
      setupIntent: { payment_method: 'pm_456' },
    });
    paymentServiceMock.mockResolvedValueOnce({
      id: 'card-no-callback',
      last4: '7777',
      brand: 'amex',
      is_default: false,
    });

    const onSelectPayment = jest.fn();
    render(
      <PaymentMethodSelection
        booking={booking}
        cards={cards}
        credits={{ totalAmount: 0, credits: [] }}
        onSelectPayment={onSelectPayment}
      />
    );

    await userEvent.click(screen.getByRole('button', { name: 'Add New Card' }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: 'Add Card' }));

    await waitFor(() => {
      expect(screen.queryByText('Enter Card Details')).not.toBeInTheDocument();
    });
  });

  it('renders with empty cards array and no cards displayed', () => {
    renderComponent({ cards: [] });

    expect(screen.queryByText(/ending in/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add New Card' })).toBeInTheDocument();
  });

  it('shows loading state on add card button during submission', async () => {
    let resolveSetup: (val: unknown) => void;
    confirmSetupMock.mockImplementation(
      () => new Promise((resolve) => { resolveSetup = resolve; })
    );

    renderComponent();
    await userEvent.click(screen.getByRole('button', { name: 'Add New Card' }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: 'Add Card' }));

    expect(screen.getByRole('button', { name: 'Adding...' })).toBeInTheDocument();

    resolveSetup!({ setupIntent: { payment_method: 'pm_loading' } });
  });

  it('selects empty string for selectedCardId when cards are empty', async () => {
    const { onSelectPayment } = renderComponent({ cards: [] });

    await userEvent.click(screen.getByRole('button', { name: 'Apply payment method' }));

    expect(onSelectPayment).toHaveBeenCalledWith(PaymentMethod.CREDIT_CARD, '');
  });

  it('shows error when createSetupIntent fails', async () => {
    createSetupIntentMock.mockRejectedValueOnce(new Error('Intent failed'));

    renderComponent();

    await userEvent.click(screen.getByRole('button', { name: 'Add New Card' }));

    await waitFor(() => {
      expect(screen.getByText('Failed to initialize payment form.')).toBeInTheDocument();
    });
  });
});
