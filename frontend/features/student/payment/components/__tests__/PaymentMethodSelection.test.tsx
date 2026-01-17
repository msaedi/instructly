import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PaymentMethodSelection from '../PaymentMethodSelection';
import { BookingType, PAYMENT_STATUS, PaymentMethod, type BookingPayment, type PaymentCard } from '../../types';
import { paymentService } from '@/services/api/payments';

const createPaymentMethodMock = jest.fn();
const getElementMock = jest.fn();

jest.mock('@stripe/stripe-js', () => ({
  loadStripe: jest.fn(() => Promise.resolve({})),
}));

jest.mock('@stripe/react-stripe-js', () => ({
  Elements: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardElement: () => <div data-testid="card-element" />,
  useStripe: () => ({ createPaymentMethod: createPaymentMethodMock }),
  useElements: () => ({ getElement: getElementMock }),
}));

jest.mock('@/services/api/payments', () => ({
  paymentService: {
    savePaymentMethod: jest.fn(),
  },
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
  },
}));

const paymentServiceMock = paymentService.savePaymentMethod as jest.Mock;

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
    createPaymentMethodMock.mockReset();
    getElementMock.mockReset();
    paymentServiceMock.mockReset();
    getElementMock.mockReturnValue({});
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

  it('adds a new card successfully', async () => {
    createPaymentMethodMock.mockResolvedValueOnce({ paymentMethod: { id: 'pm_123' } });
    paymentServiceMock.mockResolvedValueOnce({
      id: 'card-new',
      last4: '9999',
      brand: 'visa',
      is_default: true,
    });

    const { onCardAdded } = renderComponent();

    await userEvent.click(screen.getByRole('button', { name: 'Add New Card' }));
    await userEvent.click(screen.getByRole('button', { name: 'Add Card' }));

    await waitFor(() => expect(onCardAdded).toHaveBeenCalled());
  });

  it('shows error when Stripe returns an error', async () => {
    createPaymentMethodMock.mockResolvedValueOnce({ error: { message: 'Card error' } });

    renderComponent();

    await userEvent.click(screen.getByRole('button', { name: 'Add New Card' }));
    await userEvent.click(screen.getByRole('button', { name: 'Add Card' }));

    await waitFor(() => {
      expect(screen.getByText('Card error')).toBeInTheDocument();
    });
  });
});
