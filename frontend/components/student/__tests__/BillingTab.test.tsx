import React from 'react';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import BillingTab from '../BillingTab';

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
  },
}));

const { toast: mockToast } = jest.requireMock('sonner') as {
  toast: {
    success: jest.Mock;
    error: jest.Mock;
    info: jest.Mock;
  };
};

jest.mock('@/components/student/PaymentMethods', () => ({
  __esModule: true,
  default: () => <div data-testid="payment-methods" />,
}));

jest.mock('@/services/api/payments', () => ({
  paymentService: {
    getTransactionHistory: jest.fn(),
    applyPromoCode: jest.fn(),
  },
}));

// Use a module-level object to allow dynamic mock values
const creditsMockState = {
  data: { available: 0, expires_at: null as string | null, pending: 0 },
  isLoading: false,
  refetch: jest.fn().mockResolvedValue(undefined),
};

jest.mock('@/features/shared/payment/hooks/useCredits', () => ({
  useCredits: () => ({
    data: creditsMockState.data,
    isLoading: creditsMockState.isLoading,
    refetch: creditsMockState.refetch,
  }),
}));

jest.mock('@/hooks/queries/useTransactionHistory', () => ({
  useTransactionHistory: jest.fn(),
}));

const { useTransactionHistory } = jest.requireMock('@/hooks/queries/useTransactionHistory') as {
  useTransactionHistory: jest.Mock;
};

type MockTransaction = {
  id: string;
  service_name: string;
  instructor_name: string;
  booking_date: string;
  duration_minutes: number;
  hourly_rate: number;
  lesson_amount: number;
  service_fee: number;
  credit_applied: number;
  tip_amount: number;
  tip_paid: number;
  tip_status?: string | null;
  total_paid: number;
  status: string;
  created_at: string;
};

const createTransaction = (overrides: Partial<MockTransaction> = {}): MockTransaction => ({
  id: 'transaction-1',
  service_name: 'Lesson',
  instructor_name: 'Sarah C.',
  booking_date: '2025-01-10T00:00:00.000Z',
  duration_minutes: 60,
  hourly_rate: 120,
  lesson_amount: 120,
  service_fee: 14.4,
  credit_applied: 0,
  tip_amount: 0,
  tip_paid: 0,
  tip_status: null,
  total_paid: 134.4,
  status: 'succeeded',
  created_at: '2025-01-09T00:00:00.000Z',
  ...overrides,
});

const { paymentService } = jest.requireMock('@/services/api/payments') as {
  paymentService: {
    getTransactionHistory: jest.Mock;
    applyPromoCode: jest.Mock;
  };
};

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

const renderComponent = (transactions: MockTransaction[] = []) => {
  useTransactionHistory.mockReturnValue({
    data: transactions,
    isLoading: false,
  });

  const queryClient = createQueryClient();

  const result = render(
    <QueryClientProvider client={queryClient}>
      <BillingTab userId="student-1" />
    </QueryClientProvider>,
  );

  return { ...result, queryClient };
};

const renderComponentWithLoadingTransactions = () => {
  useTransactionHistory.mockReturnValue({
    data: undefined,
    isLoading: true,
  });

  const queryClient = createQueryClient();

  return render(
    <QueryClientProvider client={queryClient}>
      <BillingTab userId="student-1" />
    </QueryClientProvider>,
  );
};

describe('BillingTab', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    creditsMockState.data = { available: 0, expires_at: null, pending: 0 };
    creditsMockState.isLoading = false;
    creditsMockState.refetch.mockResolvedValue(undefined);
  });

  describe('service fee display', () => {
    it('shows service fee, credits, and totals for bookings with and without credits', () => {
      const transactions = [
        createTransaction({ id: 'tx-no-credit' }),
        createTransaction({
          id: 'tx-credit',
          total_paid: 89.4,
          credit_applied: 45,
          service_fee: 14.4,
        }),
      ];

      renderComponent(transactions);

      const serviceFeeLabels = screen.getAllByText('Platform fee');
      serviceFeeLabels.forEach((label) => {
        expect(label.nextElementSibling?.textContent).toBe('$14.40');
      });

      expect(screen.getByText('Credit Applied')).toBeInTheDocument();
      expect(screen.getByText('-$45.00')).toBeInTheDocument();
      expect(screen.getByText('$134.40')).toBeInTheDocument();
      expect(screen.getByText('$89.40')).toBeInTheDocument();
    });

    it('displays tip rows with pending state when applicable', () => {
      const transactions = [
        createTransaction({
          id: 'tx-tip-paid',
          tip_amount: 15,
          tip_paid: 15,
          total_paid: 149.4,
        }),
        createTransaction({
          id: 'tx-tip-pending',
          tip_amount: 20,
          tip_paid: 0,
          total_paid: 134.4,
        }),
      ];

      renderComponent(transactions);

      expect(screen.getByText(/^Tip$/)).toBeInTheDocument();
      expect(screen.getByText('$15.00')).toBeInTheDocument();
      expect(screen.getByText('$20.00')).toBeInTheDocument();
      expect(screen.getByText(/Tip \(pending\)/)).toBeInTheDocument();
    });

    it('shows tip pending message when tip not fully paid', () => {
      const transactions = [
        createTransaction({
          id: 'tx-partial-tip',
          tip_amount: 20,
          tip_paid: 5,
          total_paid: 139.4,
        }),
      ];

      renderComponent(transactions);

      expect(screen.getByText(/Tip will be charged once payment method is confirmed/)).toBeInTheDocument();
    });
  });

  describe('promo code functionality', () => {
    it('shows error toast when applying empty promo code', async () => {
      renderComponent([]);

      const applyButton = screen.getByRole('button', { name: /Apply/i });
      expect(applyButton).toBeDisabled();
    });

    it('shows error toast for whitespace-only promo code', async () => {
      renderComponent([]);

      const input = screen.getByPlaceholderText('Enter code');
      await userEvent.type(input, '   ');

      const applyButton = screen.getByRole('button', { name: /Apply/i });
      expect(applyButton).toBeDisabled();
    });

    it('applies valid promo code successfully', async () => {
      paymentService.applyPromoCode.mockResolvedValueOnce({ credit_added: 25 });

      renderComponent([]);

      const input = screen.getByPlaceholderText('Enter code');
      await userEvent.type(input, 'SAVE25');

      const applyButton = screen.getByRole('button', { name: /Apply/i });
      expect(applyButton).not.toBeDisabled();

      await act(async () => {
        fireEvent.click(applyButton);
      });

      await waitFor(() => {
        expect(paymentService.applyPromoCode).toHaveBeenCalledWith('SAVE25');
      });

      await waitFor(() => {
        expect(mockToast.success).toHaveBeenCalledWith(
          'Promo code applied! $25 added to your balance.',
          expect.any(Object)
        );
      });

      await waitFor(() => {
        expect(input).toHaveValue('');
      });
    });

    it('converts promo code to uppercase', async () => {
      renderComponent([]);

      const input = screen.getByPlaceholderText('Enter code');
      await userEvent.type(input, 'lowercase');

      expect(input).toHaveValue('LOWERCASE');
    });

    it('shows error toast for invalid promo code', async () => {
      paymentService.applyPromoCode.mockRejectedValueOnce(new Error('Invalid code'));

      renderComponent([]);

      const input = screen.getByPlaceholderText('Enter code');
      await userEvent.type(input, 'BADCODE');

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /Apply/i }));
      });

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith(
          'Invalid or expired promo code',
          expect.any(Object)
        );
      });
    });

    it('submits promo code on Enter key press', async () => {
      paymentService.applyPromoCode.mockResolvedValueOnce({ credit_added: 10 });

      renderComponent([]);

      const input = screen.getByPlaceholderText('Enter code');
      await userEvent.type(input, 'ENTER10');

      await act(async () => {
        fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
      });

      await waitFor(() => {
        expect(paymentService.applyPromoCode).toHaveBeenCalledWith('ENTER10');
      });
    });

    it('shows error toast when Enter pressed with empty input', async () => {
      renderComponent([]);

      const input = screen.getByPlaceholderText('Enter code');
      // Press Enter without entering any value
      await act(async () => {
        fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
      });

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith(
          'Please enter a promo code',
          expect.any(Object)
        );
      });

      // Verify applyPromoCode was NOT called
      expect(paymentService.applyPromoCode).not.toHaveBeenCalled();
    });

    it('shows loading state while applying promo code', async () => {
      let resolvePromo: (value: { credit_added: number }) => void;
      paymentService.applyPromoCode.mockReturnValueOnce(
        new Promise((resolve) => {
          resolvePromo = resolve;
        })
      );

      renderComponent([]);

      const input = screen.getByPlaceholderText('Enter code');
      await userEvent.type(input, 'LOADING');

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /Apply/i }));
      });

      expect(screen.getByText(/Applying\.\.\./i)).toBeInTheDocument();

      await act(async () => {
        resolvePromo!({ credit_added: 15 });
      });

      await waitFor(() => {
        expect(screen.queryByText(/Applying\.\.\./i)).not.toBeInTheDocument();
      });
    });
  });

  describe('download history functionality', () => {
    it('shows info toast when no transactions to download', async () => {
      renderComponent([]);

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /Download History/i }));
      });

      expect(mockToast.info).toHaveBeenCalledWith(
        'No transactions to download',
        expect.any(Object)
      );
    });

    it('downloads CSV when transactions exist', async () => {
      const mockCreateObjectURL = jest.fn(() => 'blob:test-url');
      const mockRevokeObjectURL = jest.fn();
      const clickSpy = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
      const originalCreateObjectURL = URL.createObjectURL;
      const originalRevokeObjectURL = URL.revokeObjectURL;

      URL.createObjectURL = mockCreateObjectURL;
      URL.revokeObjectURL = mockRevokeObjectURL;

      const transactions = [
        createTransaction({ id: 'tx-1' }),
        createTransaction({ id: 'tx-2', service_name: 'Guitar Lesson' }),
      ];

      renderComponent(transactions);

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /Download History/i }));
      });

      expect(mockCreateObjectURL).toHaveBeenCalled();
      expect(clickSpy).toHaveBeenCalled();
      expect(mockRevokeObjectURL).toHaveBeenCalledWith('blob:test-url');
      expect(mockToast.success).toHaveBeenCalledWith(
        'Transaction history downloaded',
        expect.any(Object)
      );

      clickSpy.mockRestore();
      URL.createObjectURL = originalCreateObjectURL;
      URL.revokeObjectURL = originalRevokeObjectURL;
    });

    it('shows info toast when download throws error', async () => {
      const originalCreateObjectURL = URL.createObjectURL;
      URL.createObjectURL = jest.fn(() => {
        throw new Error('Blob creation failed');
      });

      const transactions = [createTransaction({ id: 'tx-1' })];

      renderComponent(transactions);

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /Download History/i }));
      });

      expect(mockToast.info).toHaveBeenCalledWith(
        'Download feature coming soon!',
        expect.any(Object)
      );

      URL.createObjectURL = originalCreateObjectURL;
    });
  });

  describe('credit balance display', () => {
    it('shows loading state while credits are loading', () => {
      creditsMockState.isLoading = true;

      renderComponent([]);

      const creditSection = screen.getByText('Credit Balance').parentElement;
      expect(creditSection?.querySelector('.animate-spin')).toBeInTheDocument();
    });

    it('shows available credits with formatted amount', () => {
      creditsMockState.data = { available: 75.5, expires_at: null, pending: 0 };

      renderComponent([]);

      expect(screen.getByText('$75.50')).toBeInTheDocument();
      expect(screen.getByText('Available balance')).toBeInTheDocument();
      expect(screen.getByText('No expiry on current credits')).toBeInTheDocument();
    });

    it('shows credits with expiry date', () => {
      creditsMockState.data = { available: 100, expires_at: '2025-06-15T00:00:00.000', pending: 0 };

      renderComponent([]);

      expect(screen.getByText('$100.00')).toBeInTheDocument();
      expect(screen.getByText('Earliest expiry: Jun 15, 2025')).toBeInTheDocument();
    });

    it('shows no credits message when balance is zero', () => {
      creditsMockState.data = { available: 0, expires_at: null, pending: 0 };

      renderComponent([]);

      expect(screen.getByText('No credits available')).toBeInTheDocument();
    });

    it('shows automatic credit application note', () => {
      creditsMockState.data = { available: 50, expires_at: null, pending: 0 };

      renderComponent([]);

      expect(screen.getByText('*Credits are automatically applied at checkout')).toBeInTheDocument();
    });
  });

  describe('purchase credit package button', () => {
    it('shows coming soon toast when clicked', async () => {
      renderComponent([]);

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /Purchase Credit Package/i }));
      });

      expect(mockToast.info).toHaveBeenCalledWith(
        'Credit packages coming soon!',
        expect.any(Object)
      );
    });
  });

  describe('transaction history', () => {
    it('shows loading state while transactions are loading', () => {
      renderComponentWithLoadingTransactions();

      expect(document.querySelector('.animate-spin')).toBeInTheDocument();
    });

    it('shows empty state when no transactions', () => {
      renderComponent([]);

      expect(screen.getByText('No transactions yet')).toBeInTheDocument();
    });

    it('shows first 5 transactions by default', () => {
      const transactions = Array.from({ length: 8 }, (_, i) =>
        createTransaction({ id: `tx-${i}`, service_name: `Service ${i}` })
      );

      renderComponent(transactions);

      expect(screen.getByText('Service 0')).toBeInTheDocument();
      expect(screen.getByText('Service 4')).toBeInTheDocument();
      expect(screen.queryByText('Service 5')).not.toBeInTheDocument();
    });

    it('shows Load More button when more than 5 transactions', () => {
      const transactions = Array.from({ length: 8 }, (_, i) =>
        createTransaction({ id: `tx-${i}`, service_name: `Service ${i}` })
      );

      renderComponent(transactions);

      expect(screen.getByRole('button', { name: /Load More Transactions/i })).toBeInTheDocument();
    });

    it('shows all transactions after clicking Load More', async () => {
      const transactions = Array.from({ length: 8 }, (_, i) =>
        createTransaction({ id: `tx-${i}`, service_name: `Service ${i}` })
      );

      renderComponent(transactions);

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /Load More Transactions/i }));
      });

      expect(screen.getByText('Service 5')).toBeInTheDocument();
      expect(screen.getByText('Service 7')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Load More Transactions/i })).not.toBeInTheDocument();
    });

    it('does not show Load More button when 5 or fewer transactions', () => {
      const transactions = Array.from({ length: 5 }, (_, i) =>
        createTransaction({ id: `tx-${i}`, service_name: `Service ${i}` })
      );

      renderComponent(transactions);

      expect(screen.queryByRole('button', { name: /Load More Transactions/i })).not.toBeInTheDocument();
    });
  });

  describe('formatDate edge cases', () => {
    it('handles invalid date string gracefully', () => {
      const transactions = [
        createTransaction({ id: 'tx-invalid', booking_date: 'invalid-date' }),
      ];

      renderComponent(transactions);

      expect(screen.getByText('invalid-date')).toBeInTheDocument();
    });
  });

  describe('component structure', () => {
    it('renders PaymentMethods component', () => {
      renderComponent([]);

      expect(screen.getByTestId('payment-methods')).toBeInTheDocument();
    });

    it('renders all main sections', () => {
      renderComponent([]);

      expect(screen.getByText('Payment Methods')).toBeInTheDocument();
      expect(screen.getByText('Credit Balance')).toBeInTheDocument();
      expect(screen.getByText('Transaction History')).toBeInTheDocument();
    });
  });
});
