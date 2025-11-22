import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import BillingTab from '../BillingTab';

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
  },
}));

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

jest.mock('@/features/shared/payment/hooks/useCredits', () => ({
  useCredits: () => ({
    data: { available: 0, expires_at: null, pending: 0 },
    isLoading: false,
    refetch: jest.fn(),
  }),
}));

type MockTransaction = {
  id: string;
  service_name: string;
  instructor_name: string;
  booking_date: string;
  duration_minutes: number;
  hourly_rate: number;
  total_price: number;
  platform_fee: number;
  credit_applied: number;
  final_amount: number;
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
  total_price: 120,
  platform_fee: 28.8,
  credit_applied: 0,
  final_amount: 134.4,
  status: 'succeeded',
  created_at: '2025-01-09T00:00:00.000Z',
  ...overrides,
});

const { paymentService } = jest.requireMock('@/services/api/payments') as {
  paymentService: {
    getTransactionHistory: jest.Mock;
  };
};

const renderComponent = async (transactions: MockTransaction[]) => {
  paymentService.getTransactionHistory.mockResolvedValueOnce(transactions);

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <BillingTab userId="student-1" />
    </QueryClientProvider>,
  );

  await waitFor(() => {
    expect(paymentService.getTransactionHistory).toHaveBeenCalled();
  });
};

describe('BillingTab service fee display', () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  it('shows computed 12% service fee for bookings with and without credits', async () => {
    const transactions = [
      createTransaction({ id: 'tx-no-credit' }),
      createTransaction({
        id: 'tx-credit',
        final_amount: 89.4,
        credit_applied: 45,
        platform_fee: 0,
      }),
    ];

    await renderComponent(transactions);

    const serviceFeeLabels = await screen.findAllByText('Service fee');
    serviceFeeLabels.forEach((label) => {
      expect(label.nextElementSibling?.textContent).toBe('$14.40');
    });

    expect(screen.getByText('Credit Applied')).toBeInTheDocument();
    expect(screen.getByText('-$45.00')).toBeInTheDocument();
    expect(screen.getByText('$134.40')).toBeInTheDocument();
    expect(screen.getByText('$89.40')).toBeInTheDocument();
  });
});
