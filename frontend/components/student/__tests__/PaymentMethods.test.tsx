import React from 'react';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PaymentMethods from '../PaymentMethods';
import { paymentService } from '@/services/api/payments';
import { usePaymentMethods, useInvalidatePaymentMethods } from '@/hooks/queries/usePaymentMethods';
import { useStripe, useElements } from '@stripe/react-stripe-js';

jest.mock('@stripe/stripe-js', () => ({
  loadStripe: jest.fn(() => Promise.resolve({})),
}));

jest.mock('@/features/shared/payment/utils/stripe', () => ({
  getStripe: jest.fn(() => Promise.resolve({})),
  paymentElementAppearance: { theme: 'stripe' },
}));

jest.mock('@stripe/react-stripe-js', () => ({
  Elements: ({ children }: { children: React.ReactNode }) => <div data-testid="stripe-elements">{children}</div>,
  PaymentElement: () => <div data-testid="payment-element" />,
  useStripe: jest.fn(),
  useElements: jest.fn(),
}));

jest.mock('@/services/api/payments', () => ({
  paymentService: {
    savePaymentMethod: jest.fn(),
    setDefaultPaymentMethod: jest.fn(),
    deletePaymentMethod: jest.fn(),
    createSetupIntent: jest.fn().mockResolvedValue({ client_secret: 'seti_test_secret' }),
  },
}));

jest.mock('@/hooks/queries/usePaymentMethods', () => ({
  usePaymentMethods: jest.fn(),
  useInvalidatePaymentMethods: jest.fn(),
}));

let latestDeleteModalProps:
  | {
      isOpen: boolean;
      onConfirm: () => Promise<void>;
      paymentMethod: { id?: string } | undefined;
    }
  | null = null;

jest.mock('@/components/modals/DeletePaymentMethodModal', () => ({
  __esModule: true,
  default: ({ isOpen, onClose, onConfirm, paymentMethod }: { isOpen: boolean; onClose: () => void; onConfirm: () => Promise<void>; paymentMethod?: { id?: string } }) => {
    latestDeleteModalProps = { isOpen, onConfirm, paymentMethod };
    return isOpen ? (
      <div data-testid="delete-modal">
        <div>{paymentMethod?.id}</div>
        <button type="button" onClick={() => onConfirm().catch(() => {})}>Confirm Delete</button>
        <button type="button" onClick={onClose}>Close</button>
      </div>
    ) : null;
  },
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
    latestDeleteModalProps = null;
    mockUseInvalidatePaymentMethods.mockReturnValue(jest.fn());
    mockUseStripe.mockReturnValue({
      confirmSetup: jest.fn().mockResolvedValue({
        setupIntent: { payment_method: 'pm_1' },
      }),
    });
    mockUseElements.mockReturnValue({});
  });

  it('shows a loading state while payment methods are fetched', () => {
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: true, error: null });

    const { container } = render(<PaymentMethods />);

    expect(screen.queryByRole('button', { name: /add payment method/i })).not.toBeInTheDocument();
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('renders an empty state when no payment methods exist', () => {
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });

    render(<PaymentMethods />);

    expect(screen.getByText(/no payment methods saved/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /add your first card/i })).toBeInTheDocument();
  });

  it('adds a payment method successfully', async () => {
    const invalidate = jest.fn();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });
    mockUseInvalidatePaymentMethods.mockReturnValue(invalidate);
    (paymentService.savePaymentMethod as jest.Mock).mockResolvedValue({});
    (paymentService.createSetupIntent as jest.Mock).mockResolvedValue({ client_secret: 'seti_test_secret' });

    render(<PaymentMethods />);

    // Open the add form
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /add your first card/i }));
    });

    // Wait for createSetupIntent and PaymentElement to render
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });

    // PaymentElement should be visible
    expect(screen.getByTestId('payment-element')).toBeInTheDocument();

    // Click submit button
    const submitButton = screen.getByRole('button', { name: /^add payment method$/i });
    fireEvent.click(submitButton);

    // Wait for confirmSetup → savePaymentMethod chain to complete
    await waitFor(() => {
      const stripe = mockUseStripe();
      expect(stripe.confirmSetup).toHaveBeenCalled();
    });

    // savePaymentMethod is called after confirmSetup resolves — need to flush promises
    await act(async () => {
      // Multiple flushes for chained async calls:
      // confirmSetup (microtask) → savePaymentMethod (microtask) → onSuccess (setState)
      for (let i = 0; i < 5; i++) {
        await new Promise(resolve => setTimeout(resolve, 0));
      }
    });

    expect(paymentService.savePaymentMethod).toHaveBeenCalledWith({
      payment_method_id: 'pm_1',
      set_as_default: true, // First card defaults to default
    });
    expect(invalidate).toHaveBeenCalled();
  });

  it('shows a Stripe error when confirmSetup fails', async () => {
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });
    mockUseStripe.mockReturnValue({
      confirmSetup: jest.fn().mockResolvedValue({ error: { message: 'Bad card' } }),
    });

    render(<PaymentMethods />);

    await user.click(screen.getByRole('button', { name: /add your first card/i }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /add payment method/i }));

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

    render(<PaymentMethods />);

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

    render(<PaymentMethods />);

    const deleteButton = screen.getByRole('button', { name: /delete payment method ending in 1111/i });
    await user.click(deleteButton);
    expect(screen.getByTestId('delete-modal')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /confirm delete/i }));

    await waitFor(() => {
      expect(paymentService.deletePaymentMethod).toHaveBeenCalledWith('pm_2');
    });
    expect(invalidate).toHaveBeenCalled();
  });

  it('ignores a stale confirm callback when no payment method is selected for deletion', async () => {
    mockUsePaymentMethods.mockReturnValue({
      data: [
        { id: 'pm_4', last4: '3333', brand: 'visa', is_default: false, created_at: '2024-02-01T00:00:00Z' },
      ],
      isLoading: false,
      error: null,
    });

    render(<PaymentMethods />);

    expect(latestDeleteModalProps?.isOpen).toBe(false);

    await latestDeleteModalProps?.onConfirm();

    expect(paymentService.deletePaymentMethod).not.toHaveBeenCalled();
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

    render(<PaymentMethods />);

    const deleteButton = screen.getByRole('button', { name: /delete payment method ending in 2222/i });
    await user.click(deleteButton);
    await user.click(screen.getByRole('button', { name: /confirm delete/i }));

    expect(await screen.findByText(/failed to delete payment method/i)).toBeInTheDocument();
    expect(screen.getByText(/card/i)).toBeInTheDocument();
  });

  it('handles null stripe instance gracefully', async () => {
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });
    mockUseStripe.mockReturnValue(null);

    render(<PaymentMethods />);

    await user.click(screen.getByRole('button', { name: /add your first card/i }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    // Submit button should be disabled when stripe is null
    const submitButton = screen.getByRole('button', { name: /add payment method/i });
    expect(submitButton).toBeDisabled();
  });

  it('handles missing elements instance gracefully', async () => {
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });
    mockUseElements.mockReturnValue(null);

    render(<PaymentMethods />);

    await user.click(screen.getByRole('button', { name: /add your first card/i }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    // Try to submit - should return early without calling confirmSetup
    await user.click(screen.getByRole('button', { name: /add payment method/i }));

    // Form should still be visible (no submission happened)
    expect(screen.getByText(/add new payment method/i)).toBeInTheDocument();
  });

  it('handles SetupIntent creation error', async () => {
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });
    (paymentService.createSetupIntent as jest.Mock).mockRejectedValueOnce(new Error('Intent failed'));

    render(<PaymentMethods />);

    await user.click(screen.getByRole('button', { name: /add your first card/i }));

    await waitFor(() => {
      expect(screen.getByText(/failed to initialize payment form/i)).toBeInTheDocument();
    });
  });

  it('handles save payment method API error', async () => {
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });
    mockUseStripe.mockReturnValue({
      confirmSetup: jest.fn().mockResolvedValue({
        setupIntent: { payment_method: 'pm_fail' },
      }),
    });
    (paymentService.savePaymentMethod as jest.Mock).mockRejectedValue(new Error('Network error'));

    render(<PaymentMethods />);

    await user.click(screen.getByRole('button', { name: /add your first card/i }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /add payment method/i }));

    await waitFor(() => {
      expect(screen.getByText(/failed to add payment method/i)).toBeInTheDocument();
    });
  });

  it('handles set default payment method error', async () => {
    // Lines 218-219: Error in setDefaultMethod
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({
      data: [
        { id: 'pm_error', last4: '9999', brand: 'visa', is_default: false, created_at: '2024-01-01T00:00:00Z' },
      ],
      isLoading: false,
      error: null,
    });
    (paymentService.setDefaultPaymentMethod as jest.Mock).mockRejectedValue(new Error('Server error'));

    render(<PaymentMethods />);

    await user.click(screen.getByRole('button', { name: /set default/i }));

    await waitFor(() => {
      expect(screen.getByText(/failed to update default payment method/i)).toBeInTheDocument();
    });
  });

  it('handles cancel button in add payment method form', async () => {
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });

    render(<PaymentMethods />);

    // Open form
    await user.click(screen.getByRole('button', { name: /add your first card/i }));
    expect(screen.getByText(/add new payment method/i)).toBeInTheDocument();

    // Click cancel
    await user.click(screen.getByRole('button', { name: /cancel/i }));

    // Form should be closed
    expect(screen.queryByText(/add new payment method/i)).not.toBeInTheDocument();
    // Should show empty state again
    expect(screen.getByText(/no payment methods saved/i)).toBeInTheDocument();
  });

  it('closes delete modal when close button is clicked', async () => {
    // Lines 357-358: setDeleteModalOpen(false) and setMethodToDelete(null)
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({
      data: [
        { id: 'pm_close', last4: '5555', brand: 'mastercard', is_default: false, created_at: '2024-02-01T00:00:00Z' },
      ],
      isLoading: false,
      error: null,
    });

    const { container } = render(<PaymentMethods />);

    const deleteButton = container.querySelector('button.text-red-600') as HTMLButtonElement | null;
    expect(deleteButton).toBeInTheDocument();
    await user.click(deleteButton!);

    // Modal should be open
    expect(screen.getByTestId('delete-modal')).toBeInTheDocument();

    // Click close button
    await user.click(screen.getByRole('button', { name: /close/i }));

    // Modal should be closed
    expect(screen.queryByTestId('delete-modal')).not.toBeInTheDocument();
  });

  it('shows set as default checkbox when existing cards present', async () => {
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({
      data: [
        { id: 'pm_existing', last4: '1234', brand: 'visa', is_default: true, created_at: '2024-01-01T00:00:00Z' },
      ],
      isLoading: false,
      error: null,
    });

    render(<PaymentMethods />);

    await user.click(screen.getByRole('button', { name: /add payment method/i }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    // Set as default checkbox should be visible when cards exist
    expect(screen.getByLabelText(/set as default payment method/i)).toBeInTheDocument();
  });

  it('shows top add payment method button when cards exist', async () => {
    // Line 253: Button onClick for setAddingCard(true)
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({
      data: [
        { id: 'pm_existing', last4: '1234', brand: 'visa', is_default: true, created_at: '2024-01-01T00:00:00Z' },
      ],
      isLoading: false,
      error: null,
    });

    render(<PaymentMethods />);

    // Top-level add button should be visible
    const addButton = screen.getByRole('button', { name: /add payment method/i });
    expect(addButton).toBeInTheDocument();

    await user.click(addButton);

    // Add card form should be visible
    expect(screen.getByText(/add new payment method/i)).toBeInTheDocument();
  });

  it('displays query error message', async () => {
    mockUsePaymentMethods.mockReturnValue({
      data: [],
      isLoading: false,
      error: new Error('Query failed'),
    });

    render(<PaymentMethods />);

    expect(screen.getByText(/failed to load payment methods/i)).toBeInTheDocument();
  });

  it('shows fallback error when Stripe error has no message', async () => {
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });
    mockUseStripe.mockReturnValue({
      confirmSetup: jest.fn().mockResolvedValue({ error: {} }),
    });

    render(<PaymentMethods />);

    await user.click(screen.getByRole('button', { name: /add your first card/i }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /add payment method/i }));

    expect(await screen.findByText(/failed to add payment method/i)).toBeInTheDocument();
  });

  it('displays recognized brand names correctly', () => {
    mockUsePaymentMethods.mockReturnValue({
      data: [
        { id: 'pm_amex', last4: '0001', brand: 'amex', is_default: false, created_at: '2024-01-01T00:00:00Z' },
        { id: 'pm_discover', last4: '0002', brand: 'discover', is_default: false, created_at: '2024-01-02T00:00:00Z' },
      ],
      isLoading: false,
      error: null,
    });

    render(<PaymentMethods />);

    expect(screen.getByText('American Express')).toBeInTheDocument();
    expect(screen.getByText('Discover')).toBeInTheDocument();
  });

  it('falls back to "Card" for unrecognized brand', () => {
    mockUsePaymentMethods.mockReturnValue({
      data: [
        { id: 'pm_weird', last4: '0003', brand: 'obscure_brand', is_default: false, created_at: '2024-01-01T00:00:00Z' },
      ],
      isLoading: false,
      error: null,
    });

    render(<PaymentMethods />);

    // The getCardBrandDisplay fallback returns 'Card'
    expect(screen.getByText('Card')).toBeInTheDocument();
  });

  it('hides "Add Your First Card" button when add form is open with empty list', async () => {
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });

    render(<PaymentMethods />);

    // Click "Add Your First Card" to open form
    await user.click(screen.getByRole('button', { name: /add your first card/i }));

    // The "Add Your First Card" button within the empty state should disappear
    expect(screen.queryByRole('button', { name: /add your first card/i })).not.toBeInTheDocument();
    // The form heading should be visible
    expect(screen.getByText(/add new payment method/i)).toBeInTheDocument();
  });

  it('does not show "Set Default" button for the default card', () => {
    mockUsePaymentMethods.mockReturnValue({
      data: [
        { id: 'pm_default', last4: '8888', brand: 'visa', is_default: true, created_at: '2024-01-01T00:00:00Z' },
        { id: 'pm_other', last4: '9999', brand: 'mastercard', is_default: false, created_at: '2024-01-02T00:00:00Z' },
      ],
      isLoading: false,
      error: null,
    });

    render(<PaymentMethods />);

    // Default badge should appear for the default card
    expect(screen.getByText('Default')).toBeInTheDocument();
    // Only one "Set Default" button should exist (for the non-default card)
    const setDefaultButtons = screen.getAllByRole('button', { name: /set default/i });
    expect(setDefaultButtons).toHaveLength(1);
  });

  it('shows formatted date for card creation', () => {
    mockUsePaymentMethods.mockReturnValue({
      data: [
        { id: 'pm_dated', last4: '4444', brand: 'visa', is_default: false, created_at: '2024-06-15T12:00:00Z' },
      ],
      isLoading: false,
      error: null,
    });

    render(<PaymentMethods />);

    // Check that the "Added" date is formatted
    expect(screen.getByText(/added/i)).toBeInTheDocument();
  });

  it('toggles set as default checkbox in add payment method form', async () => {
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({
      data: [
        { id: 'pm_existing', last4: '1234', brand: 'visa', is_default: true, created_at: '2024-01-01T00:00:00Z' },
      ],
      isLoading: false,
      error: null,
    });

    render(<PaymentMethods />);

    await user.click(screen.getByRole('button', { name: /add payment method/i }));

    await waitFor(() => {
      expect(screen.getByTestId('payment-element')).toBeInTheDocument();
    });

    const checkbox = screen.getByLabelText(/set as default payment method/i);
    expect(checkbox).not.toBeChecked();

    await user.click(checkbox);
    expect(checkbox).toBeChecked();

    await user.click(checkbox);
    expect(checkbox).not.toBeChecked();
  });

  it('handles confirmSetup returning no payment_method', async () => {
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });
    mockUseStripe.mockReturnValue({
      confirmSetup: jest.fn().mockResolvedValue({
        setupIntent: { payment_method: null },
      }),
    });

    render(<PaymentMethods />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /add your first card/i }));
    });

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });

    const form = screen.getByTestId('payment-element').closest('form')!;
    await act(async () => {
      fireEvent.submit(form);
    });

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });

    // savePaymentMethod should NOT be called when payment_method is null
    expect(paymentService.savePaymentMethod).not.toHaveBeenCalled();
  });

  it('handles payment_method as object with id property', async () => {
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });
    const invalidate = jest.fn();
    mockUseInvalidatePaymentMethods.mockReturnValue(invalidate);
    mockUseStripe.mockReturnValue({
      confirmSetup: jest.fn().mockResolvedValue({
        setupIntent: { payment_method: { id: 'pm_obj_123', card: { last4: '9999' } } },
      }),
    });
    (paymentService.savePaymentMethod as jest.Mock).mockResolvedValue({});

    render(<PaymentMethods />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /add your first card/i }));
    });

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });

    const form = screen.getByTestId('payment-element').closest('form')!;
    await act(async () => {
      fireEvent.submit(form);
    });

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 50));
    });

    // Should extract id from object
    expect(paymentService.savePaymentMethod).toHaveBeenCalledWith({
      payment_method_id: 'pm_obj_123',
      set_as_default: true, // First card defaults to default
    });
  });

  it('handles cleanup when component unmounts during SetupIntent fetch', async () => {
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });

    let resolveSetupIntent: (val: { client_secret: string }) => void;
    (paymentService.createSetupIntent as jest.Mock).mockImplementation(
      () => new Promise((resolve) => { resolveSetupIntent = resolve; })
    );

    const { unmount } = render(<PaymentMethods />);

    fireEvent.click(screen.getByRole('button', { name: /add your first card/i }));

    // Unmount before the SetupIntent resolves
    unmount();

    // Resolve after unmount — should not cause state update error
    await act(async () => {
      resolveSetupIntent!({ client_secret: 'seti_late' });
    });

    // No error thrown — cancelled flag prevented state update
  });

  it('uses empty array default when usePaymentMethods returns undefined data', () => {
    mockUsePaymentMethods.mockReturnValue({ data: undefined, isLoading: false, error: null });

    render(<PaymentMethods />);

    // Should render empty state (default [] kicks in)
    expect(screen.getByText(/no payment methods saved/i)).toBeInTheDocument();
  });

  it('handles cleanup when component unmounts during SetupIntent error', async () => {
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });

    let rejectSetupIntent: (err: Error) => void;
    (paymentService.createSetupIntent as jest.Mock).mockImplementation(
      () => new Promise((_resolve, reject) => { rejectSetupIntent = reject; })
    );

    const { unmount } = render(<PaymentMethods />);

    fireEvent.click(screen.getByRole('button', { name: /add your first card/i }));

    // Unmount before the SetupIntent rejects
    unmount();

    // Reject after unmount — should not cause state update error
    await act(async () => {
      rejectSetupIntent!(new Error('Too late'));
    });

    // No error thrown — cancelled flag prevented state update
  });
});
