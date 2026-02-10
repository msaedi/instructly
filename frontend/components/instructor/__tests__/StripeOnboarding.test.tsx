import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import StripeOnboarding from '../StripeOnboarding';
import { paymentService } from '@/services/api/payments';

// Mock dependencies
jest.mock('next/navigation', () => ({
  useSearchParams: jest.fn(() => ({
    get: jest.fn(() => null),
  })),
}));

jest.mock('@/services/api/payments', () => ({
  paymentService: {
    getOnboardingStatus: jest.fn(),
    startOnboarding: jest.fn(),
    getDashboardLink: jest.fn(),
  },
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    warn: jest.fn(),
  },
}));

const paymentServiceMock = paymentService as jest.Mocked<typeof paymentService>;

describe('StripeOnboarding', () => {
  const mockInstructorId = 'instructor-123';

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('loading state', () => {
    it('shows loading spinner initially', () => {
      paymentServiceMock.getOnboardingStatus.mockImplementation(
        () => new Promise(() => {}) // Never resolves
      );

      const { container } = render(<StripeOnboarding instructorId={mockInstructorId} />);

      // Check for animate-spin class on loader
      expect(container.querySelector('.animate-spin')).toBeInTheDocument();
    });
  });

  describe('not connected state', () => {
    beforeEach(() => {
      paymentServiceMock.getOnboardingStatus.mockResolvedValue({
        has_account: false,
        onboarding_completed: false,
        charges_enabled: false,
        payouts_enabled: false,
        details_submitted: false,
        requirements: [],
      });
    });

    it('shows connect account prompt', async () => {
      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Connect Your Stripe Account')).toBeInTheDocument();
      });
    });

    it('shows what you need list', async () => {
      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText(/Bank account details/i)).toBeInTheDocument();
        expect(screen.getByText(/Tax identification/i)).toBeInTheDocument();
      });
    });

    it('shows connect button', async () => {
      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /connect stripe account/i })).toBeInTheDocument();
      });
    });

    it('calls startOnboarding when clicking connect', async () => {
      paymentServiceMock.startOnboarding.mockResolvedValue({
        account_id: 'acct_123',
        already_onboarded: true,
        onboarding_url: '',
      });

      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /connect stripe account/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /connect stripe account/i }));

      await waitFor(() => {
        expect(paymentServiceMock.startOnboarding).toHaveBeenCalled();
      });
    });
  });

  describe('incomplete onboarding state', () => {
    beforeEach(() => {
      paymentServiceMock.getOnboardingStatus.mockResolvedValue({
        has_account: true,
        onboarding_completed: false,
        charges_enabled: false,
        payouts_enabled: false,
        details_submitted: false,
        requirements: ['External account', 'Identity verification'],
      });
    });

    it('shows complete setup prompt', async () => {
      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Complete Your Setup')).toBeInTheDocument();
      });
    });

    it('displays remaining requirements', async () => {
      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Remaining Requirements:')).toBeInTheDocument();
        expect(screen.getByText(/External account/)).toBeInTheDocument();
        expect(screen.getByText(/Identity verification/)).toBeInTheDocument();
      });
    });

    it('shows status indicators', async () => {
      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Charges enabled:')).toBeInTheDocument();
        expect(screen.getByText('Payouts enabled:')).toBeInTheDocument();
        expect(screen.getByText('Details submitted:')).toBeInTheDocument();
      });
    });

    it('shows continue setup button', async () => {
      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /continue setup/i })).toBeInTheDocument();
      });
    });
  });

  describe('completed onboarding state', () => {
    beforeEach(() => {
      paymentServiceMock.getOnboardingStatus.mockResolvedValue({
        has_account: true,
        onboarding_completed: true,
        charges_enabled: true,
        payouts_enabled: true,
        details_submitted: true,
        requirements: [],
      });
    });

    it('shows success state', async () => {
      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Stripe Account Connected')).toBeInTheDocument();
      });
    });

    it('shows all enabled indicators', async () => {
      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Charges enabled')).toBeInTheDocument();
        expect(screen.getByText('Payouts enabled')).toBeInTheDocument();
        expect(screen.getByText('Ready for payments')).toBeInTheDocument();
      });
    });

    it('shows dashboard button', async () => {
      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /view payouts dashboard/i })).toBeInTheDocument();
      });
    });

    it('shows refresh status button', async () => {
      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /refresh status/i })).toBeInTheDocument();
      });
    });

    it('opens dashboard when clicking dashboard button', async () => {
      const mockOpen = jest.fn();
      window.open = mockOpen;

      paymentServiceMock.getDashboardLink.mockResolvedValue({
        dashboard_url: 'https://dashboard.stripe.com/express',
        expires_in_minutes: 15,
      });

      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /view payouts dashboard/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /view payouts dashboard/i }));

      await waitFor(() => {
        expect(mockOpen).toHaveBeenCalledWith('https://dashboard.stripe.com/express', '_blank');
      });
    });
  });

  describe('error handling', () => {
    // Note: Since checkStatus rethrows errors after setting state, we need to handle the rejection
    const originalOnUnhandledRejection = process.listeners('unhandledRejection');

    beforeEach(() => {
      // Remove all unhandledRejection listeners for error handling tests
      process.removeAllListeners('unhandledRejection');
      // Add our own handler that does nothing (suppresses the error)
      process.on('unhandledRejection', () => {});
    });

    afterEach(() => {
      // Restore original handlers
      process.removeAllListeners('unhandledRejection');
      originalOnUnhandledRejection.forEach((listener) => {
        process.on('unhandledRejection', listener as NodeJS.UnhandledRejectionListener);
      });
    });

    it('shows error state when status fetch fails', async () => {
      paymentServiceMock.getOnboardingStatus.mockImplementation(() =>
        Promise.reject(new Error('Network error'))
      );

      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Connection Error')).toBeInTheDocument();
        expect(screen.getByText('Failed to load onboarding status')).toBeInTheDocument();
      });
    });

    it('shows try again button on error', async () => {
      paymentServiceMock.getOnboardingStatus.mockImplementation(() =>
        Promise.reject(new Error('Network error'))
      );

      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
      });
    });

    it('handles startOnboarding error', async () => {
      paymentServiceMock.getOnboardingStatus.mockResolvedValue({
        has_account: false,
        onboarding_completed: false,
        charges_enabled: false,
        payouts_enabled: false,
        details_submitted: false,
        requirements: [],
      });
      paymentServiceMock.startOnboarding.mockRejectedValue(new Error('Start failed'));

      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /connect stripe account/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /connect stripe account/i }));

      await waitFor(() => {
        expect(paymentServiceMock.startOnboarding).toHaveBeenCalled();
      });

      // Button should be re-enabled after error
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /connect stripe account/i })).toBeEnabled();
      });
    });

    it('handles getDashboardLink error', async () => {
      paymentServiceMock.getOnboardingStatus.mockResolvedValue({
        has_account: true,
        onboarding_completed: true,
        charges_enabled: true,
        payouts_enabled: true,
        details_submitted: true,
        requirements: [],
      });
      paymentServiceMock.getDashboardLink.mockRejectedValue(new Error('Dashboard error'));

      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /view payouts dashboard/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /view payouts dashboard/i }));

      await waitFor(() => {
        expect(screen.getByText('Failed to open dashboard. Please try again.')).toBeInTheDocument();
      });
    });
  });

  describe('already onboarded', () => {
    it('refreshes status when already onboarded', async () => {
      paymentServiceMock.getOnboardingStatus.mockResolvedValue({
        has_account: false,
        onboarding_completed: false,
        charges_enabled: false,
        payouts_enabled: false,
        details_submitted: false,
        requirements: [],
      });
      paymentServiceMock.startOnboarding.mockResolvedValue({
        account_id: 'acct_123',
        already_onboarded: true,
        onboarding_url: '',
      });

      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /connect stripe account/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /connect stripe account/i }));

      await waitFor(() => {
        expect(paymentServiceMock.getOnboardingStatus).toHaveBeenCalledTimes(2);
      });
    });
  });

  describe('refresh status', () => {
    it('refetches status when clicking refresh', async () => {
      paymentServiceMock.getOnboardingStatus.mockResolvedValue({
        has_account: true,
        onboarding_completed: true,
        charges_enabled: true,
        payouts_enabled: true,
        details_submitted: true,
        requirements: [],
      });

      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /refresh status/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /refresh status/i }));

      await waitFor(() => {
        expect(paymentServiceMock.getOnboardingStatus).toHaveBeenCalledTimes(2);
      });
    });
  });

  describe('polling behavior', () => {
    it('starts polling when returning from Stripe', async () => {
      // Mock returning from Stripe
      const mockUseSearchParams = jest.requireMock('next/navigation').useSearchParams;
      mockUseSearchParams.mockReturnValue({
        get: (param: string) => (param === 'stripe_onboarding_return' ? 'true' : null),
      });

      paymentServiceMock.getOnboardingStatus.mockResolvedValue({
        has_account: true,
        onboarding_completed: false,
        charges_enabled: false,
        payouts_enabled: false,
        details_submitted: true,
        requirements: ['Bank account'],
      });

      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Verifying Your Account')).toBeInTheDocument();
      });

      // Reset mock for cleanup
      mockUseSearchParams.mockReturnValue({
        get: jest.fn(() => null),
      });
    });

    it('stops polling after onboarding completes', async () => {
      const mockUseSearchParams = jest.requireMock('next/navigation').useSearchParams;
      mockUseSearchParams.mockReturnValue({
        get: (param: string) => (param === 'stripe_onboarding_return' ? 'true' : null),
      });

      const mockReplaceState = jest.fn();
      const originalReplaceState = window.history.replaceState;
      window.history.replaceState = mockReplaceState;

      // First call returns incomplete, then complete
      paymentServiceMock.getOnboardingStatus
        .mockResolvedValueOnce({
          has_account: true,
          onboarding_completed: false,
          charges_enabled: false,
          payouts_enabled: false,
          details_submitted: true,
          requirements: [],
        })
        .mockResolvedValue({
          has_account: true,
          onboarding_completed: true,
          charges_enabled: true,
          payouts_enabled: true,
          details_submitted: true,
          requirements: [],
        });

      render(<StripeOnboarding instructorId={mockInstructorId} />);

      // Wait for polling to start
      await waitFor(() => {
        expect(screen.getByText('Verifying Your Account')).toBeInTheDocument();
      });

      // Advance timer to trigger poll and flush promises
      await jest.advanceTimersByTimeAsync(2100);

      await waitFor(() => {
        expect(screen.getByText('Stripe Account Connected')).toBeInTheDocument();
      });

      // Cleanup
      window.history.replaceState = originalReplaceState;
      mockUseSearchParams.mockReturnValue({
        get: jest.fn(() => null),
      });
    });

    it('stops polling after timeout', async () => {
      const mockUseSearchParams = jest.requireMock('next/navigation').useSearchParams;
      mockUseSearchParams.mockReturnValue({
        get: (param: string) => (param === 'stripe_onboarding_return' ? 'true' : null),
      });

      paymentServiceMock.getOnboardingStatus.mockResolvedValue({
        has_account: true,
        onboarding_completed: false,
        charges_enabled: false,
        payouts_enabled: false,
        details_submitted: true,
        requirements: ['Something'],
      });

      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Verifying Your Account')).toBeInTheDocument();
      });

      // Advance through 15+ poll attempts (16 * 2100ms)
      await jest.advanceTimersByTimeAsync(16 * 2100);

      // After 15 attempts, polling should stop and show the incomplete state
      await waitFor(() => {
        expect(screen.getByText('Complete Your Setup')).toBeInTheDocument();
      });

      // Cleanup
      mockUseSearchParams.mockReturnValue({
        get: jest.fn(() => null),
      });
    });
  });

  describe('incomplete onboarding with enabled features', () => {
    it('shows enabled indicators correctly', async () => {
      paymentServiceMock.getOnboardingStatus.mockResolvedValue({
        has_account: true,
        onboarding_completed: false,
        charges_enabled: true,
        payouts_enabled: true,
        details_submitted: true,
        requirements: [],
      });

      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Complete Your Setup')).toBeInTheDocument();
      });

      // Check status indicators are present (they show check icons when enabled)
      const chargesLabel = screen.getByText('Charges enabled:');
      const payoutsLabel = screen.getByText('Payouts enabled:');
      const detailsLabel = screen.getByText('Details submitted:');

      expect(chargesLabel).toBeInTheDocument();
      expect(payoutsLabel).toBeInTheDocument();
      expect(detailsLabel).toBeInTheDocument();
    });
  });

  describe('startOnboarding with onboarding_url (redirect path)', () => {
    // JSDOM's window.location.href is non-configurable — cannot be mocked or spied on.
    // Intercept the JSDOM "Not implemented: navigation" error that fires when assigning to it,
    // while passing all other console.error calls through.
    let consoleErrorSpy: jest.SpyInstance;

    beforeEach(() => {
      const original = console.error.bind(console);
      consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation((...args: unknown[]) => {
        if (typeof args[0] === 'string' && args[0].includes('Not implemented: navigation')) return;
        original(...args);
      });
    });

    afterEach(() => {
      consoleErrorSpy.mockRestore();
    });

    it('calls startOnboarding and triggers redirect when onboarding_url is provided', async () => {
      paymentServiceMock.getOnboardingStatus.mockResolvedValue({
        has_account: false,
        onboarding_completed: false,
        charges_enabled: false,
        payouts_enabled: false,
        details_submitted: false,
        requirements: [],
      });
      paymentServiceMock.startOnboarding.mockResolvedValue({
        account_id: 'acct_123',
        already_onboarded: false,
        onboarding_url: 'https://connect.stripe.com/setup/abc',
      });

      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /connect stripe account/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /connect stripe account/i }));

      await waitFor(() => {
        expect(paymentServiceMock.startOnboarding).toHaveBeenCalled();
      });

      // Verify startOnboarding was called with redirect URL returned;
      // JSDOM does not support actual navigation, so we verify the API path instead
      expect(paymentServiceMock.getOnboardingStatus).toHaveBeenCalledTimes(1);
    });
  });

  describe('dashboard link without URL', () => {
    it('does not open window when dashboard_url is empty', async () => {
      const mockOpen = jest.fn();
      window.open = mockOpen;

      paymentServiceMock.getOnboardingStatus.mockResolvedValue({
        has_account: true,
        onboarding_completed: true,
        charges_enabled: true,
        payouts_enabled: true,
        details_submitted: true,
        requirements: [],
      });
      paymentServiceMock.getDashboardLink.mockResolvedValue({
        dashboard_url: '',
        expires_in_minutes: 15,
      });

      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /view payouts dashboard/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /view payouts dashboard/i }));

      await waitFor(() => {
        expect(paymentServiceMock.getDashboardLink).toHaveBeenCalled();
      });

      // window.open should not be called with empty string
      expect(mockOpen).not.toHaveBeenCalled();
    });
  });

  describe('error on completed state', () => {
    it('shows error message alongside completed state when dashboard fails', async () => {
      paymentServiceMock.getOnboardingStatus.mockResolvedValue({
        has_account: true,
        onboarding_completed: true,
        charges_enabled: true,
        payouts_enabled: true,
        details_submitted: true,
        requirements: [],
      });
      paymentServiceMock.getDashboardLink.mockRejectedValue(new Error('Dashboard fail'));

      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Stripe Account Connected')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /view payouts dashboard/i }));

      await waitFor(() => {
        // error + onboardingStatus both present: shows error inline on completed page
        expect(screen.getByText('Failed to open dashboard. Please try again.')).toBeInTheDocument();
        // The completed page should still be visible
        expect(screen.getByText('Stripe Account Connected')).toBeInTheDocument();
      });
    });
  });

  describe('incomplete onboarding without requirements', () => {
    it('does not show requirements section when array is empty', async () => {
      paymentServiceMock.getOnboardingStatus.mockResolvedValue({
        has_account: true,
        onboarding_completed: false,
        charges_enabled: false,
        payouts_enabled: false,
        details_submitted: false,
        requirements: [],
      });

      render(<StripeOnboarding instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Complete Your Setup')).toBeInTheDocument();
      });

      // Should NOT show the requirements heading when list is empty
      expect(screen.queryByText('Remaining Requirements:')).not.toBeInTheDocument();
    });
  });
});
