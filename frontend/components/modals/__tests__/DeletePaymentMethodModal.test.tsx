import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DeletePaymentMethodModal from '../DeletePaymentMethodModal';

// Mock the logger
jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
  },
}));

describe('DeletePaymentMethodModal', () => {
  const mockPaymentMethod = {
    id: 'pm_test123',
    last4: '4242',
    brand: 'visa',
    is_default: false,
  };

  const defaultProps = {
    paymentMethod: mockPaymentMethod,
    isOpen: true,
    onClose: jest.fn(),
    onConfirm: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders when open with payment method', () => {
    render(<DeletePaymentMethodModal {...defaultProps} />);

    expect(screen.getByText('Remove Payment Method?')).toBeInTheDocument();
    expect(screen.getByText('Visa ending in 4242')).toBeInTheDocument();
  });

  it('does not render when isOpen is false', () => {
    render(<DeletePaymentMethodModal {...defaultProps} isOpen={false} />);

    expect(screen.queryByText('Remove Payment Method?')).not.toBeInTheDocument();
  });

  it('does not render when paymentMethod is null', () => {
    render(<DeletePaymentMethodModal {...defaultProps} paymentMethod={null} />);

    expect(screen.queryByText('Remove Payment Method?')).not.toBeInTheDocument();
  });

  it('shows default payment method warning when is_default is true', () => {
    const defaultPaymentMethod = { ...mockPaymentMethod, is_default: true };
    render(
      <DeletePaymentMethodModal {...defaultProps} paymentMethod={defaultPaymentMethod} />
    );

    expect(
      screen.getByText(/This is your default payment method/i)
    ).toBeInTheDocument();
  });

  it('does not show default warning for non-default methods', () => {
    render(<DeletePaymentMethodModal {...defaultProps} />);

    expect(
      screen.queryByText(/This is your default payment method/i)
    ).not.toBeInTheDocument();
  });

  it('calls onClose when Cancel button is clicked', async () => {
    const user = userEvent.setup();
    render(<DeletePaymentMethodModal {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onConfirm and onClose on successful deletion', async () => {
    const user = userEvent.setup();
    const onConfirm = jest.fn().mockResolvedValue(undefined);
    const onClose = jest.fn();
    render(
      <DeletePaymentMethodModal
        {...defaultProps}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    await user.click(screen.getByRole('button', { name: /remove card/i }));

    await waitFor(() => {
      expect(onConfirm).toHaveBeenCalledTimes(1);
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  it('shows loading state during deletion', async () => {
    const user = userEvent.setup();
    let resolveDelete: () => void;
    const onConfirm = jest.fn(
      () => new Promise<void>((resolve) => (resolveDelete = resolve))
    );
    render(<DeletePaymentMethodModal {...defaultProps} onConfirm={onConfirm} />);

    await user.click(screen.getByRole('button', { name: /remove card/i }));

    expect(screen.getByText(/removing/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancel/i })).toBeDisabled();

    resolveDelete!();
  });

  it('shows error message on deletion failure', async () => {
    const user = userEvent.setup();
    const onConfirm = jest.fn().mockRejectedValue(new Error('Network error'));
    render(<DeletePaymentMethodModal {...defaultProps} onConfirm={onConfirm} />);

    await user.click(screen.getByRole('button', { name: /remove card/i }));

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });

    expect(defaultProps.onClose).not.toHaveBeenCalled();
  });

  it('shows default error message when error has no message', async () => {
    const user = userEvent.setup();
    const onConfirm = jest.fn().mockRejectedValue('unknown error');
    render(<DeletePaymentMethodModal {...defaultProps} onConfirm={onConfirm} />);

    await user.click(screen.getByRole('button', { name: /remove card/i }));

    await waitFor(() => {
      expect(screen.getByText(/failed to delete payment method/i)).toBeInTheDocument();
    });
  });

  it('formats brand name with capital first letter', () => {
    const amexMethod = { ...mockPaymentMethod, brand: 'amex', last4: '1234' };
    render(<DeletePaymentMethodModal {...defaultProps} paymentMethod={amexMethod} />);

    expect(screen.getByText('Amex ending in 1234')).toBeInTheDocument();
  });

  it('prevents closing modal while deletion is in progress', async () => {
    const user = userEvent.setup();
    let resolveDelete: () => void;
    const onConfirm = jest.fn(
      () => new Promise<void>((resolve) => (resolveDelete = resolve))
    );
    const onClose = jest.fn();
    render(
      <DeletePaymentMethodModal
        {...defaultProps}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    await user.click(screen.getByRole('button', { name: /remove card/i }));

    const cancelButton = screen.getByRole('button', { name: /cancel/i });
    await user.click(cancelButton);

    expect(onClose).not.toHaveBeenCalled();

    resolveDelete!();
  });
});
