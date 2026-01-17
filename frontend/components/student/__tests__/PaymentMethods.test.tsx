import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PaymentMethods from '../PaymentMethods';
import { paymentService } from '@/services/api/payments';
import { usePaymentMethods, useInvalidatePaymentMethods } from '@/hooks/queries/usePaymentMethods';
import { useStripe, useElements } from '@stripe/react-stripe-js';

jest.mock('@stripe/stripe-js', () => ({
  loadStripe: jest.fn(() => Promise.resolve({})),
}));

jest.mock('@stripe/react-stripe-js', () => ({
  Elements: ({ children }: { children: React.ReactNode }) => <div data-testid="stripe-elements">{children}</div>,
  CardElement: () => <div data-testid="card-element" />,
  useStripe: jest.fn(),
  useElements: jest.fn(),
}));

jest.mock('@/services/api/payments', () => ({
  paymentService: {
    savePaymentMethod: jest.fn(),
    setDefaultPaymentMethod: jest.fn(),
    deletePaymentMethod: jest.fn(),
  },
}));

jest.mock('@/hooks/queries/usePaymentMethods', () => ({
  usePaymentMethods: jest.fn(),
  useInvalidatePaymentMethods: jest.fn(),
}));

jest.mock('@/components/modals/DeletePaymentMethodModal', () => ({
  __esModule: true,
  default: ({ isOpen, onClose, onConfirm, paymentMethod }: { isOpen: boolean; onClose: () => void; onConfirm: () => Promise<void>; paymentMethod?: { id?: string } }) => (
    isOpen ? (
      <div data-testid="delete-modal">
        <div>{paymentMethod?.id}</div>
        <button type="button" onClick={() => onConfirm().catch(() => {})}>Confirm Delete</button>
        <button type="button" onClick={onClose}>Close</button>
      </div>
    ) : null
  ),
}));

jest.mock('@/lib/logger', () => ({
  logger: { info: jest.fn(), error: jest.fn() },
}));

const mockUsePaymentMethods = usePaymentMethods as jest.Mock;
const mockUseInvalidatePaymentMethods = useInvalidatePaymentMethods as jest.Mock;
const mockUseStripe = useStripe as jest.Mock;
const mockUseElements = useElements as jest.Mock;

describe('PaymentMethods', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseInvalidatePaymentMethods.mockReturnValue(jest.fn());
    mockUseStripe.mockReturnValue({
      createPaymentMethod: jest.fn().mockResolvedValue({ paymentMethod: { id: 'pm_1' } }),
    });
    mockUseElements.mockReturnValue({
      getElement: jest.fn().mockReturnValue({}),
    });
  });

  it('shows a loading state while payment methods are fetched', () => {
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: true, error: null });

    const { container } = render(<PaymentMethods userId="user-1" />);

    expect(screen.queryByRole('button', { name: /add payment method/i })).not.toBeInTheDocument();
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('renders an empty state when no payment methods exist', () => {
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });

    render(<PaymentMethods userId="user-1" />);

    expect(screen.getByText(/no payment methods saved/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /add your first card/i })).toBeInTheDocument();
  });

  it('adds a payment method successfully', async () => {
    const user = userEvent.setup();
    const invalidate = jest.fn();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });
    mockUseInvalidatePaymentMethods.mockReturnValue(invalidate);
    (paymentService.savePaymentMethod as jest.Mock).mockResolvedValue({});

    render(<PaymentMethods userId="user-1" />);

    await user.click(screen.getByRole('button', { name: /add your first card/i }));
    await user.click(screen.getByLabelText(/set as default payment method/i));
    await user.click(screen.getByRole('button', { name: /add card/i }));

    await waitFor(() => {
      expect(paymentService.savePaymentMethod).toHaveBeenCalledWith({
        payment_method_id: 'pm_1',
        set_as_default: true,
      });
    });
    expect(invalidate).toHaveBeenCalled();
    expect(screen.queryByText(/add new card/i)).not.toBeInTheDocument();
  });

  it('shows a Stripe error when createPaymentMethod fails', async () => {
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });
    mockUseStripe.mockReturnValue({
      createPaymentMethod: jest.fn().mockResolvedValue({ error: { message: 'Bad card' } }),
    });

    render(<PaymentMethods userId="user-1" />);

    await user.click(screen.getByRole('button', { name: /add your first card/i }));
    await user.click(screen.getByRole('button', { name: /add card/i }));

    expect(await screen.findByText(/bad card/i)).toBeInTheDocument();
  });

  it('sets a payment method as default and refreshes data', async () => {
    const user = userEvent.setup();
    const invalidate = jest.fn();
    mockUsePaymentMethods.mockReturnValue({
      data: [
        { id: 'pm_1', last4: '4242', brand: 'visa', is_default: false, created_at: '2024-01-01T00:00:00Z' },
      ],
      isLoading: false,
      error: null,
    });
    mockUseInvalidatePaymentMethods.mockReturnValue(invalidate);
    (paymentService.setDefaultPaymentMethod as jest.Mock).mockResolvedValue({});

    render(<PaymentMethods userId="user-1" />);

    await user.click(screen.getByRole('button', { name: /set default/i }));

    await waitFor(() => {
      expect(paymentService.setDefaultPaymentMethod).toHaveBeenCalledWith('pm_1');
    });
    expect(invalidate).toHaveBeenCalled();
  });

  it('deletes a payment method from the modal flow', async () => {
    const user = userEvent.setup();
    const invalidate = jest.fn();
    mockUsePaymentMethods.mockReturnValue({
      data: [
        { id: 'pm_2', last4: '1111', brand: 'mastercard', is_default: true, created_at: '2024-02-01T00:00:00Z' },
      ],
      isLoading: false,
      error: null,
    });
    mockUseInvalidatePaymentMethods.mockReturnValue(invalidate);
    (paymentService.deletePaymentMethod as jest.Mock).mockResolvedValue({});

    const { container } = render(<PaymentMethods userId="user-1" />);

    const deleteButton = container.querySelector('button.text-red-600') as HTMLButtonElement | null;
    expect(deleteButton).toBeInTheDocument();
    await user.click(deleteButton!);
    expect(screen.getByTestId('delete-modal')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /confirm delete/i }));

    await waitFor(() => {
      expect(paymentService.deletePaymentMethod).toHaveBeenCalledWith('pm_2');
    });
    expect(invalidate).toHaveBeenCalled();
  });

  it('surfaces delete errors in the UI', async () => {
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({
      data: [
        { id: 'pm_3', last4: '2222', brand: 'unknown', is_default: false, created_at: '2024-02-01T00:00:00Z' },
      ],
      isLoading: false,
      error: null,
    });
    (paymentService.deletePaymentMethod as jest.Mock).mockRejectedValue(new Error('fail'));

    const { container } = render(<PaymentMethods userId="user-1" />);

    const deleteButton = container.querySelector('button.text-red-600') as HTMLButtonElement | null;
    expect(deleteButton).toBeInTheDocument();
    await user.click(deleteButton!);
    await user.click(screen.getByRole('button', { name: /confirm delete/i }));

    expect(await screen.findByText(/failed to delete payment method/i)).toBeInTheDocument();
    expect(screen.getByText(/card/i)).toBeInTheDocument();
  });
});
