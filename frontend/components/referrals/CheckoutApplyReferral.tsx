'use client';

import { useMemo, useState } from 'react';
import { AlertCircle, CheckCircle, Gift, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { applyReferralCredit, type ApplyReferralErrorType } from '@/features/referrals/api';

export interface CheckoutApplyReferralProps {
  orderId: string;
  subtotalCents: number;
  promoApplied: boolean;
  onApplied?: (appliedCents: number) => void;
}

const MIN_BASKET_CENTS = 75_00;
const CREDIT_VALUE_CENTS = 20_00;

const errorMessages: Record<ApplyReferralErrorType, string> = {
  promo_conflict: 'Referral credit can’t be combined with other promotions.',
  below_min_basket: 'Spend $75+ to use your $20 credit.',
  no_unlocked_credit: 'You don’t have unlocked referral credit yet.',
  disabled: 'Referral credits are unavailable right now. Please try again later.',
};

const formatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 0,
});

const formatCents = (amount: number) => formatter.format(amount / 100);

export function CheckoutApplyReferral({ orderId, subtotalCents, promoApplied, onApplied }: CheckoutApplyReferralProps) {
  const [appliedCents, setAppliedCents] = useState<number | null>(null);
  const [error, setError] = useState<ApplyReferralErrorType | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const subtotalDisplay = formatCents(subtotalCents);
  const creditDisplay = formatCents(CREDIT_VALUE_CENTS);

  const isEligibleSubtotal = subtotalCents >= MIN_BASKET_CENTS;
  const hasOrder = Boolean(orderId);

  const primaryNote = useMemo(() => {
    if (!hasOrder) return 'We’re finalizing your order details. Referral credit will be available in a moment.';
    if (promoApplied) return errorMessages.promo_conflict;
    if (!isEligibleSubtotal) return errorMessages.below_min_basket;
    if (error) return errorMessages[error];
    return null;
  }, [error, hasOrder, isEligibleSubtotal, promoApplied]);

  const canApply = hasOrder && !promoApplied && isEligibleSubtotal && appliedCents === null && !isLoading;

  const handleApply = async () => {
    if (!canApply) return;

    setIsLoading(true);
    setError(null);

    const result = await applyReferralCredit(orderId);

    if ('applied_cents' in result) {
      setAppliedCents(result.applied_cents ?? CREDIT_VALUE_CENTS);
      onApplied?.(result.applied_cents ?? CREDIT_VALUE_CENTS);
      toast.success('Referral credit applied');
    } else {
      setError(result.type);
      if (result.message) {
        toast.error(result.message);
      } else {
        toast.error(errorMessages[result.type]);
      }
    }

    setIsLoading(false);
  };

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-3">
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-[#7E22CE]/10 text-[#7E22CE]">
          <Gift className="h-5 w-5" aria-hidden="true" />
        </span>
        <div>
          <h3 className="text-base font-semibold text-gray-900">Referral credit</h3>
          <p className="text-sm text-gray-600">
            Apply {creditDisplay} to this booking when your subtotal is {formatCents(MIN_BASKET_CENTS)} or more.
          </p>
        </div>
      </div>

      <div className="mt-4 space-y-3">
        {appliedCents !== null ? (
          <div className="flex items-start gap-2 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
            <CheckCircle className="mt-0.5 h-4 w-4" aria-hidden="true" />
            <div>
              <p className="font-medium">Referral credit applied</p>
              <p>{formatCents(appliedCents)} will automatically deduct from checkout.</p>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-between rounded-lg border border-gray-200 px-3 py-2">
            <div>
              <p className="text-sm font-medium text-gray-800">Subtotal</p>
              <p className="text-xs text-gray-500">{subtotalDisplay}</p>
            </div>
            <button
              type="button"
              onClick={handleApply}
              disabled={!canApply}
              aria-label="Apply referral credit"
              className="inline-flex items-center gap-2 rounded-lg bg-[#7E22CE] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#6b1fb8] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Applying…
                </>
              ) : (
                <>Apply {creditDisplay} credit</>
              )}
            </button>
          </div>
        )}

        {primaryNote && (
          <div className="flex items-start gap-2 rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-600">
            <AlertCircle className="mt-0.5 h-4 w-4 text-gray-400" aria-hidden="true" />
            <p>{primaryNote}</p>
          </div>
        )}

        <p className="text-xs text-gray-500">
          One referral credit per order. FTC disclosure: when your friend books their first $75+ lesson, you both receive Theta credits.
        </p>
      </div>
    </section>
  );
}

export default CheckoutApplyReferral;
