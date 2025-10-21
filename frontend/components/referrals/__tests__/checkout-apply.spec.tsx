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

    expect(inviteLink).toHaveAttribute('href', '/rewards');
  });
});
