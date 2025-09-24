'use client';

export const dynamic = 'force-dynamic';

import { Suspense, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import CheckoutApplyReferral from '@/components/referrals/CheckoutApplyReferral';

function CheckoutContent() {
  const params = useSearchParams();
  const orderId = params.get('orderId') ?? '';
  const subtotalParam = params.get('subtotalCents') ?? params.get('subtotal') ?? '0';
  const subtotalCents = useMemo(() => {
    const parsed = Number(subtotalParam);
    return Number.isFinite(parsed) ? parsed : 0;
  }, [subtotalParam]);
  const promoApplied = (params.get('promo') ?? params.get('promoApplied')) === '1';

  return (
    <main className="mx-auto flex min-h-[70vh] w-full max-w-3xl flex-col gap-6 px-4 py-12 sm:px-6 lg:px-8">
      <header className="space-y-2">
        <p className="text-sm font-medium uppercase tracking-[0.18em] text-gray-500">Checkout</p>
        <h1 className="text-3xl font-bold text-gray-900">Apply referral credit</h1>
        <p className="text-sm text-gray-600">
          Use referral credits when your subtotal meets the minimum and no other promotions are active.
        </p>
      </header>

      <CheckoutApplyReferral
        orderId={orderId}
        subtotalCents={subtotalCents}
        promoApplied={promoApplied}
        onApplied={() => {}}
      />

      <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-xs text-gray-500">
        <p className="font-semibold text-gray-700">Developer note</p>
        <p className="mt-2">
          Pass <code>orderId</code>, <code>subtotalCents</code>, and optional <code>promo=1</code> query parameters to exercise different states. Example:
        </p>
        <p className="mt-1 font-mono text-[11px] text-gray-600">/checkout?orderId=ORDER123&subtotalCents=8200</p>
      </div>
    </main>
  );
}

export default function CheckoutPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto flex min-h-[70vh] w-full max-w-3xl items-center justify-center px-4 py-12 sm:px-6 lg:px-8">
          <p className="text-sm text-gray-500">Loading checkout preview…</p>
        </main>
      }
    >
      <CheckoutContent />
    </Suspense>
  );
}
