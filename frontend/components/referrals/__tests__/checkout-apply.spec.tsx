import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CheckoutApplyReferral from '../CheckoutApplyReferral';
import type { ApplyReferralErrorType } from '@/features/shared/referrals/api';

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

  it('displays non-stacking note when another promotion is active', () => {
    render(
      <CheckoutApplyReferral orderId="order-1" subtotalCents={9000} promoApplied onApplied={jest.fn()} />
    );

    expect(
      screen.getByText("Referral credit can’t be combined with other promotions.")
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /apply referral credit/i })).toBeDisabled();
  });

  it('enforces minimum basket threshold', () => {
    render(
      <CheckoutApplyReferral orderId="order-1" subtotalCents={5000} promoApplied={false} onApplied={jest.fn()} />
    );

    expect(screen.getByText('Spend $75+ to use your $20 credit.')).toBeInTheDocument();
  });

  it.each<ApplyReferralErrorType>([
    'no_unlocked_credit',
    'disabled',
  ])('maps %s error to user-friendly message', async (errorType) => {
    mockApplyReferralCredit.mockResolvedValue({ type: errorType });

    render(
      <CheckoutApplyReferral orderId="order-2" subtotalCents={9000} promoApplied={false} onApplied={jest.fn()} />
    );

    const applyButton = screen.getByRole('button', { name: /apply referral credit/i });
    fireEvent.click(applyButton);

    await waitFor(() => {
      if (errorType === 'no_unlocked_credit') {
        expect(screen.getByText('You don’t have unlocked referral credit yet.')).toBeInTheDocument();
      } else {
        expect(screen.getByText('Referral credits are unavailable right now. Please try again later.')).toBeInTheDocument();
      }
    });

    expect(mockApplyReferralCredit).toHaveBeenCalledWith('order-2');
  });

  it('invokes onApplied callback on success', async () => {
    mockApplyReferralCredit.mockResolvedValue({ applied_cents: 2000 });
    const onApplied = jest.fn();

    render(
      <CheckoutApplyReferral orderId="order-3" subtotalCents={9000} promoApplied={false} onApplied={onApplied} />
    );

    fireEvent.click(screen.getByRole('button', { name: /apply referral credit/i }));

    await waitFor(() => {
      expect(screen.getByText('Referral credit applied')).toBeInTheDocument();
    });

    expect(onApplied).toHaveBeenCalledWith(2000);
  });
});
