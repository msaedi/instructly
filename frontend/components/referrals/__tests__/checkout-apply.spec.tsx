import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CheckoutApplyReferral from '../CheckoutApplyReferral';

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

const mockApplyReferralCredit = jest.fn();
jest.mock('@/features/shared/referrals/api', () => ({
  applyReferralCredit: (...args: unknown[]) => mockApplyReferralCredit(...args),
}));

describe('CheckoutApplyReferral', () => {
  beforeEach(() => {
    mockApplyReferralCredit.mockReset();
  });

  it('hides CTA and shows non-stacking message when a promo is already applied', () => {
    render(
      <CheckoutApplyReferral
        orderId="order-1"
        subtotalCents={9000}
        promoApplied
        onApplied={jest.fn()}
      />
    );

    expect(screen.getAllByText('Referral credit can’t be combined with other promotions.')[0]).toBeVisible();
    expect(screen.queryByRole('button', { name: /apply referral credit/i })).not.toBeInTheDocument();
  });

  it('shows applied banner and refreshes order summary after success', async () => {
    mockApplyReferralCredit.mockResolvedValue({ applied_cents: 2000 });
    const onApplied = jest.fn();
    const onRefreshOrderSummary = jest.fn();

    render(
      <CheckoutApplyReferral
        orderId="order-2"
        subtotalCents={12000}
        promoApplied={false}
        onApplied={onApplied}
        onRefreshOrderSummary={onRefreshOrderSummary}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /apply referral credit/i }));

    await waitFor(() => {
      expect(screen.getByText('Referral credit applied')).toBeInTheDocument();
      expect(screen.getAllByText('Referral credit applied — promotions can’t be combined.').length).toBeGreaterThan(0);
    });

    expect(onApplied).toHaveBeenCalledWith(2000);
    expect(onRefreshOrderSummary).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: /apply referral credit/i })).not.toBeInTheDocument();
  });

  it('surfaces promo conflict banner and keeps referral unapplied', async () => {
    mockApplyReferralCredit.mockResolvedValue({ type: 'promo_conflict' });
    const onApplied = jest.fn();

    render(
      <CheckoutApplyReferral
        orderId="order-3"
        subtotalCents={9000}
        promoApplied={false}
        onApplied={onApplied}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /apply referral credit/i }));

    await waitFor(() => {
      expect(screen.getAllByText('Referral credit can’t be combined with other promotions.').length).toBeGreaterThan(0);
    });

    expect(onApplied).not.toHaveBeenCalled();
    expect(screen.queryByText('Referral credit applied')).not.toBeInTheDocument();
  });

  it('alerts when subtotal is below the eligibility threshold', () => {
    render(
      <CheckoutApplyReferral
        orderId="order-4"
        subtotalCents={5000}
        promoApplied={false}
        onApplied={jest.fn()}
      />
    );

    expect(screen.getByText('Spend $75+ to use your $20 credit.')).toBeInTheDocument();
  });

  it('links to rewards page when user has no unlocked credit', async () => {
    mockApplyReferralCredit.mockResolvedValue({ type: 'no_unlocked_credit' });

    render(
      <CheckoutApplyReferral
        orderId="order-5"
        subtotalCents={9000}
        promoApplied={false}
        onApplied={jest.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /apply referral credit/i }));

    const inviteLink = await screen.findByRole('link', { name: /invite friends/i });

    expect(inviteLink).toHaveAttribute('href', '/student/dashboard?tab=rewards');
  });

  // Line 50: When hasOrder is false (orderId is empty)
  it('shows order loading message when orderId is empty', () => {
    render(
      <CheckoutApplyReferral
        orderId=""
        subtotalCents={9000}
        promoApplied={false}
        onApplied={jest.fn()}
      />
    );

    expect(screen.getByText(/finalizing your order details/i)).toBeInTheDocument();
    // Button is visible but disabled when orderId is empty
    expect(screen.getByRole('button', { name: /apply referral credit/i })).toBeDisabled();
  });

  // Line 56: When error === 'disabled' or featureDisabled
  it('shows disabled message when referral credits are unavailable', async () => {
    mockApplyReferralCredit.mockResolvedValue({ type: 'disabled' });

    render(
      <CheckoutApplyReferral
        orderId="order-6"
        subtotalCents={9000}
        promoApplied={false}
        onApplied={jest.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /apply referral credit/i }));

    await waitFor(() => {
      expect(screen.getByText(/referral credits are unavailable right now/i)).toBeInTheDocument();
    });
  });

  // Lines 102-103: Error handling when onRefreshOrderSummary fails
  it('shows error toast when refresh order summary fails', async () => {
    const { toast } = jest.requireMock('sonner') as { toast: { success: jest.Mock; error: jest.Mock } };
    mockApplyReferralCredit.mockResolvedValue({ applied_cents: 2000 });
    const onRefreshOrderSummary = jest.fn().mockRejectedValue(new Error('Refresh failed'));

    render(
      <CheckoutApplyReferral
        orderId="order-7"
        subtotalCents={12000}
        promoApplied={false}
        onApplied={jest.fn()}
        onRefreshOrderSummary={onRefreshOrderSummary}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /apply referral credit/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Referral credit applied');
      expect(toast.error).toHaveBeenCalledWith('Applied credit, but failed to refresh totals. Please review your order.');
    });
  });

  // Line 109: Setting featureDisabled when error type is 'disabled'
  it('disables button after receiving disabled error', async () => {
    mockApplyReferralCredit.mockResolvedValue({ type: 'disabled' });

    render(
      <CheckoutApplyReferral
        orderId="order-8"
        subtotalCents={9000}
        promoApplied={false}
        onApplied={jest.fn()}
      />
    );

    // First click should work
    fireEvent.click(screen.getByRole('button', { name: /apply referral credit/i }));

    await waitFor(() => {
      expect(screen.getByText(/referral credits are unavailable right now/i)).toBeInTheDocument();
    });

    // Button should no longer be present after disabled error
    expect(screen.queryByRole('button', { name: /apply referral credit/i })).not.toBeInTheDocument();
  });

  // Line 115: When result.message is truthy (custom error message from API)
  it('shows custom error message from API response', async () => {
    const { toast } = jest.requireMock('sonner') as { toast: { success: jest.Mock; error: jest.Mock } };
    mockApplyReferralCredit.mockResolvedValue({
      type: 'below_min_basket',
      message: 'Custom error: Your order is too small for referral credits.',
    });

    render(
      <CheckoutApplyReferral
        orderId="order-9"
        subtotalCents={9000}
        promoApplied={false}
        onApplied={jest.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /apply referral credit/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Custom error: Your order is too small for referral credits.');
    });
  });

  // Test default error message when result.message is not provided
  it('shows default error message when API does not provide custom message', async () => {
    const { toast } = jest.requireMock('sonner') as { toast: { success: jest.Mock; error: jest.Mock } };
    mockApplyReferralCredit.mockResolvedValue({ type: 'below_min_basket' });

    render(
      <CheckoutApplyReferral
        orderId="order-10"
        subtotalCents={9000}
        promoApplied={false}
        onApplied={jest.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /apply referral credit/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Spend $75+ to use your $20 credit.');
    });
  });

  // Test default applied_cents when not provided
  it('uses default credit amount when applied_cents is not provided', async () => {
    mockApplyReferralCredit.mockResolvedValue({ applied_cents: null });
    const onApplied = jest.fn();

    render(
      <CheckoutApplyReferral
        orderId="order-11"
        subtotalCents={12000}
        promoApplied={false}
        onApplied={onApplied}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /apply referral credit/i }));

    await waitFor(() => {
      expect(onApplied).toHaveBeenCalledWith(2000); // Default CREDIT_VALUE_CENTS
    });
  });

  // Test loading state
  it('shows loading state while applying credit', async () => {
    let resolveApply: (value: { applied_cents: number }) => void;
    mockApplyReferralCredit.mockImplementation(() => new Promise((resolve) => {
      resolveApply = resolve;
    }));

    render(
      <CheckoutApplyReferral
        orderId="order-12"
        subtotalCents={12000}
        promoApplied={false}
        onApplied={jest.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /apply referral credit/i }));

    // Button shows "Applying…" text but still has the same aria-label
    expect(screen.getByText(/applying/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /apply referral credit/i })).toBeDisabled();

    // Resolve to complete the test
    resolveApply!({ applied_cents: 2000 });

    await waitFor(() => {
      expect(screen.queryByText(/applying/i)).not.toBeInTheDocument();
    });
  });

  // Test canApply is false when already applied
  it('does not allow applying when credit is already applied', async () => {
    mockApplyReferralCredit.mockResolvedValue({ applied_cents: 2000 });

    render(
      <CheckoutApplyReferral
        orderId="order-13"
        subtotalCents={12000}
        promoApplied={false}
        onApplied={jest.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /apply referral credit/i }));

    await waitFor(() => {
      expect(screen.getByText('Referral credit applied')).toBeInTheDocument();
    });

    // Button should be gone after successful apply
    expect(screen.queryByRole('button', { name: /apply referral credit/i })).not.toBeInTheDocument();
  });

  // Test promo_conflict resets appliedCents to null
  it('resets appliedCents on promo_conflict error', async () => {
    mockApplyReferralCredit.mockResolvedValue({ type: 'promo_conflict' });

    render(
      <CheckoutApplyReferral
        orderId="order-14"
        subtotalCents={9000}
        promoApplied={false}
        onApplied={jest.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /apply referral credit/i }));

    await waitFor(() => {
      expect(screen.getAllByText(/Referral credit can.t be combined with other promotions/i).length).toBeGreaterThan(0);
    });

    // Applied credit state should remain null, button should still be present (for retry if promo removed)
    expect(screen.queryByText('Referral credit applied')).not.toBeInTheDocument();
  });

  // Test FTC disclosure is shown
  it('shows FTC disclosure text', () => {
    render(
      <CheckoutApplyReferral
        orderId="order-15"
        subtotalCents={9000}
        promoApplied={false}
        onApplied={jest.fn()}
      />
    );

    expect(screen.getByText(/ftc disclosure/i)).toBeInTheDocument();
    expect(screen.getByText(/one referral credit per order/i)).toBeInTheDocument();
  });

  // Test subtotal and credit display
  it('displays formatted subtotal and credit amount', () => {
    render(
      <CheckoutApplyReferral
        orderId="order-16"
        subtotalCents={8500}
        promoApplied={false}
        onApplied={jest.fn()}
      />
    );

    expect(screen.getByText('$85')).toBeInTheDocument(); // subtotalDisplay
    expect(screen.getByText(/apply \$20 credit/i)).toBeInTheDocument(); // creditDisplay
  });
});
