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

  it('handles missing stripe instance gracefully', async () => {
    // Line 71: Early return when stripe or elements is null
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });
    mockUseStripe.mockReturnValue(null); // Stripe not loaded

    render(<PaymentMethods userId="user-1" />);

    await user.click(screen.getByRole('button', { name: /add your first card/i }));

    // Form should render but submission should be prevented
    expect(screen.getByText(/add new card/i)).toBeInTheDocument();

    // Try to submit - should return early without error
    await user.click(screen.getByRole('button', { name: /add card/i }));

    // Should still be on the add card form (no submission happened)
    expect(screen.getByText(/add new card/i)).toBeInTheDocument();
  });

  it('handles missing elements instance gracefully', async () => {
    // Line 71: Early return when elements is null
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });
    mockUseElements.mockReturnValue(null); // Elements not loaded

    render(<PaymentMethods userId="user-1" />);

    await user.click(screen.getByRole('button', { name: /add your first card/i }));

    // Form should render but submission should be prevented
    expect(screen.getByText(/add new card/i)).toBeInTheDocument();

    // Try to submit - should return early
    await user.click(screen.getByRole('button', { name: /add card/i }));

    // Should still be on the add card form
    expect(screen.getByText(/add new card/i)).toBeInTheDocument();
  });

  it('handles missing card element error', async () => {
    // Lines 79-81: Error when cardElement is null
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });
    mockUseElements.mockReturnValue({
      getElement: jest.fn().mockReturnValue(null), // CardElement not found
    });

    render(<PaymentMethods userId="user-1" />);

    await user.click(screen.getByRole('button', { name: /add your first card/i }));

    await user.click(screen.getByRole('button', { name: /add card/i }));

    // Should show error message
    await waitFor(() => {
      expect(screen.getByText(/card element not found/i)).toBeInTheDocument();
    });
  });

  it('handles save payment method API error', async () => {
    // Lines 106-107: Error handling when save fails
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });
    (paymentService.savePaymentMethod as jest.Mock).mockRejectedValue(new Error('Network error'));

    render(<PaymentMethods userId="user-1" />);

    await user.click(screen.getByRole('button', { name: /add your first card/i }));
    await user.click(screen.getByRole('button', { name: /add card/i }));

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

    render(<PaymentMethods userId="user-1" />);

    await user.click(screen.getByRole('button', { name: /set default/i }));

    await waitFor(() => {
      expect(screen.getByText(/failed to update default payment method/i)).toBeInTheDocument();
    });
  });

  it('handles cancel button in add card form', async () => {
    // Line 277: onCancel callback
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });

    render(<PaymentMethods userId="user-1" />);

    // Open add card form
    await user.click(screen.getByRole('button', { name: /add your first card/i }));
    expect(screen.getByText(/add new card/i)).toBeInTheDocument();

    // Click cancel
    await user.click(screen.getByRole('button', { name: /cancel/i }));

    // Add card form should be closed
    expect(screen.queryByText(/add new card/i)).not.toBeInTheDocument();
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

    const { container } = render(<PaymentMethods userId="user-1" />);

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

  it('handles save for future toggle', async () => {
    // Line 141: setSaveForFuture checkbox
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });

    render(<PaymentMethods userId="user-1" />);

    await user.click(screen.getByRole('button', { name: /add your first card/i }));

    // Save for future should be checked by default
    const saveForFutureCheckbox = screen.getByLabelText(/save for future use/i);
    expect(saveForFutureCheckbox).toBeChecked();

    // Uncheck it
    await user.click(saveForFutureCheckbox);
    expect(saveForFutureCheckbox).not.toBeChecked();

    // Set as default should be hidden when save for future is unchecked
    expect(screen.queryByLabelText(/set as default payment method/i)).not.toBeInTheDocument();

    // Check it again
    await user.click(saveForFutureCheckbox);
    expect(saveForFutureCheckbox).toBeChecked();

    // Set as default should be visible again
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

    render(<PaymentMethods userId="user-1" />);

    // Top-level add button should be visible
    const addButton = screen.getByRole('button', { name: /add payment method/i });
    expect(addButton).toBeInTheDocument();

    await user.click(addButton);

    // Add card form should be visible
    expect(screen.getByText(/add new card/i)).toBeInTheDocument();
  });

  it('displays query error message', async () => {
    mockUsePaymentMethods.mockReturnValue({
      data: [],
      isLoading: false,
      error: new Error('Query failed'),
    });

    render(<PaymentMethods userId="user-1" />);

    expect(screen.getByText(/failed to load payment methods/i)).toBeInTheDocument();
  });

  it('shows fallback error when Stripe error has no message', async () => {
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });
    mockUseStripe.mockReturnValue({
      createPaymentMethod: jest.fn().mockResolvedValue({ error: {} }),
    });

    render(<PaymentMethods userId="user-1" />);

    await user.click(screen.getByRole('button', { name: /add your first card/i }));
    await user.click(screen.getByRole('button', { name: /add card/i }));

    expect(await screen.findByText(/failed to add card/i)).toBeInTheDocument();
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

    render(<PaymentMethods userId="user-1" />);

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

    render(<PaymentMethods userId="user-1" />);

    // The getCardBrandDisplay fallback returns 'Card'
    expect(screen.getByText('Card')).toBeInTheDocument();
  });

  it('hides "Add Your First Card" button when add form is open with empty list', async () => {
    const user = userEvent.setup();
    mockUsePaymentMethods.mockReturnValue({ data: [], isLoading: false, error: null });

    render(<PaymentMethods userId="user-1" />);

    // Click "Add Your First Card" to open form
    await user.click(screen.getByRole('button', { name: /add your first card/i }));

    // The "Add Your First Card" button within the empty state should disappear
    expect(screen.queryByRole('button', { name: /add your first card/i })).not.toBeInTheDocument();
    // The top "Add Payment Method" button should also be hidden
    expect(screen.queryByRole('button', { name: /add payment method/i })).not.toBeInTheDocument();
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

    render(<PaymentMethods userId="user-1" />);

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

    render(<PaymentMethods userId="user-1" />);

    // Check that the "Added" date is formatted
    expect(screen.getByText(/added/i)).toBeInTheDocument();
  });
});
