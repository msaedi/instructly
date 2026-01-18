import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import PayoutsDashboard from '../PayoutsDashboard';
import { paymentService } from '@/services/api/payments';
import { useInstructorEarnings } from '@/hooks/queries/useInstructorEarnings';
import { usePricingConfig } from '@/lib/pricing/usePricingFloors';
import type { ReactNode } from 'react';

// Mock dependencies
jest.mock('@/services/api/payments', () => ({
  paymentService: {
    getDashboardLink: jest.fn(),
  },
}));

jest.mock('@/hooks/queries/useInstructorEarnings', () => ({
  useInstructorEarnings: jest.fn(),
}));

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingConfig: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
  },
}));

const paymentServiceMock = paymentService as jest.Mocked<typeof paymentService>;
const useInstructorEarningsMock = useInstructorEarnings as jest.Mock;
const usePricingConfigMock = usePricingConfig as jest.Mock;

// Create wrapper
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

describe('PayoutsDashboard', () => {
  const mockEarnings = {
    total_earned: 1500.0,
    total_fees: 225.0,
    booking_count: 15,
    average_earning: 100.0,
    period_start: '2025-01-01',
    period_end: '2025-01-31',
  };

  const mockPricingConfig = {
    instructor_tiers: [
      { min: 0, pct: 0.15 },
      { min: 10000, pct: 0.12 },
    ],
  };

  beforeEach(() => {
    jest.clearAllMocks();

    useInstructorEarningsMock.mockReturnValue({
      data: mockEarnings,
      isLoading: false,
      error: null,
    });

    usePricingConfigMock.mockReturnValue({
      config: mockPricingConfig,
    });
  });

  describe('loading state', () => {
    it('shows loading spinner when loading', () => {
      useInstructorEarningsMock.mockReturnValue({
        data: null,
        isLoading: true,
        error: null,
      });

      const { container } = render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(container.querySelector('.animate-spin')).toBeInTheDocument();
    });
  });

  describe('earnings overview', () => {
    it('displays page title', () => {
      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText('Payouts & Earnings')).toBeInTheDocument();
    });

    it('displays total earnings', () => {
      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText('Total Earnings')).toBeInTheDocument();
      expect(screen.getByText('$1,500.00')).toBeInTheDocument();
    });

    it('displays booking count', () => {
      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText('Total Bookings')).toBeInTheDocument();
      expect(screen.getByText('15')).toBeInTheDocument();
    });

    it('displays average earning per session', () => {
      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText(/Avg\. \$100\.00 per session/)).toBeInTheDocument();
    });

    it('displays platform fees', () => {
      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText('Platform Fees')).toBeInTheDocument();
      expect(screen.getByText('$225.00')).toBeInTheDocument();
    });

    it('displays platform fee percentage from config', () => {
      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText('15% service fee')).toBeInTheDocument();
    });

    it('displays date range', () => {
      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText(/This month/)).toBeInTheDocument();
    });
  });

  describe('quick actions', () => {
    it('renders View Stripe Dashboard button', () => {
      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByRole('button', { name: /view stripe dashboard/i })).toBeInTheDocument();
    });

    it('renders Update Banking Info button', () => {
      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByRole('button', { name: /update banking info/i })).toBeInTheDocument();
    });

    it('renders Tax Documents button', () => {
      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByRole('button', { name: /tax documents/i })).toBeInTheDocument();
    });

    it('opens Stripe dashboard when clicking button', async () => {
      const mockOpen = jest.fn();
      window.open = mockOpen;

      paymentServiceMock.getDashboardLink.mockResolvedValue({
        dashboard_url: 'https://dashboard.stripe.com',
        expires_in_minutes: 15,
      });

      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      fireEvent.click(screen.getByRole('button', { name: /view stripe dashboard/i }));

      await waitFor(() => {
        expect(mockOpen).toHaveBeenCalledWith('https://dashboard.stripe.com', '_blank');
      });
    });

    it('shows error message when dashboard link fails', async () => {
      paymentServiceMock.getDashboardLink.mockRejectedValue(new Error('Failed'));

      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      fireEvent.click(screen.getByRole('button', { name: /view stripe dashboard/i }));

      await waitFor(() => {
        expect(screen.getByText(/failed to open stripe dashboard/i)).toBeInTheDocument();
      });
    });
  });

  describe('payout information', () => {
    it('displays payout schedule info', () => {
      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText('Payout Schedule')).toBeInTheDocument();
      expect(screen.getByText(/2-day rolling basis/)).toBeInTheDocument();
    });

    it('displays platform fee structure info', () => {
      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText('Platform Fee Structure')).toBeInTheDocument();
    });

    it('displays tax documents info', () => {
      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      // "Tax Documents" appears as both a button and section heading
      const taxDocElements = screen.getAllByText('Tax Documents');
      expect(taxDocElements.length).toBeGreaterThan(0);
      expect(screen.getByText(/1099 forms/)).toBeInTheDocument();
    });

    it('displays support contact information', () => {
      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText(/payments@instainstru.com/)).toBeInTheDocument();
    });
  });

  describe('earnings breakdown', () => {
    it('displays earnings breakdown section', () => {
      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText('Earnings Breakdown')).toBeInTheDocument();
    });

    it('shows call to action for Stripe analytics', () => {
      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText('Detailed earnings analytics')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /open analytics/i })).toBeInTheDocument();
    });
  });

  describe('error handling', () => {
    it('displays error when earnings fetch fails', () => {
      useInstructorEarningsMock.mockReturnValue({
        data: null,
        isLoading: false,
        error: new Error('Failed to load'),
      });

      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText('Failed to load earnings data')).toBeInTheDocument();
    });
  });

  describe('pricing config edge cases', () => {
    it('handles missing pricing config gracefully', () => {
      usePricingConfigMock.mockReturnValue({
        config: null,
      });

      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      // Should not show percentage, but show fallback
      expect(screen.getByText('Platform fees withheld')).toBeInTheDocument();
    });

    it('handles empty tiers array', () => {
      usePricingConfigMock.mockReturnValue({
        config: { instructor_tiers: [] },
      });

      render(<PayoutsDashboard instructorId="inst-123" />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByText('Platform fees withheld')).toBeInTheDocument();
    });
  });
});
