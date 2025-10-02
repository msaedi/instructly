'use client';

import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { toast } from 'sonner';

import { API_ENDPOINTS, fetchWithAuth } from '@/lib/api';
import { logger } from '@/lib/logger';
import type { OnboardingStatusResponse } from '@/services/api/payments';

const delay = (ms: number) =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, ms);
  });

const determineTargetPath = (fromParam: string | null) => {
  const slug = (fromParam || '').toLowerCase();

  if (!slug) {
    return '/instructor/onboarding/verification';
  }

  if (slug === 'dashboard') {
    return '/instructor/dashboard';
  }

  if (slug === 'profile') {
    return '/instructor/profile';
  }

  const onboardingSlugs = new Set([
    'status',
    'verification',
    'payment-setup',
    'skill-selection',
    'welcome',
  ]);

  if (onboardingSlugs.has(slug)) {
    return `/instructor/onboarding/${slug}`;
  }

  return '/instructor/onboarding/verification';
};

export default function StripeConnectCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const fromParam = searchParams.get('from');

  useEffect(() => {
    let cancelled = false;

    const tryAuthMe = async () => {
      try {
        const response = await fetchWithAuth(API_ENDPOINTS.ME);
        if (response.ok) {
          return true;
        }
        logger.debug('Stripe Connect callback warm-up failed', {
          status: response.status,
        });
        return false;
      } catch (error) {
        logger.debug('Stripe Connect callback warm-up error', error);
        return false;
      }
    };

    const loadConnectStatus = async (): Promise<OnboardingStatusResponse | null> => {
      try {
        const response = await fetchWithAuth(API_ENDPOINTS.CONNECT_STATUS);
        if (!response.ok) {
          logger.warn('Stripe Connect status check failed', {
            status: response.status,
          });
          return null;
        }
        return (await response.json()) as OnboardingStatusResponse;
      } catch (error) {
        logger.error('Stripe Connect status check error', error);
        return null;
      }
    };

    const run = async () => {
      for (let attempt = 0; attempt < 3 && !cancelled; attempt += 1) {
        const authed = await tryAuthMe();
        if (authed || cancelled) {
          break;
        }
        await delay(400 + attempt * 200);
      }

      if (cancelled) {
        return;
      }

      const status = await loadConnectStatus();
      if (cancelled) {
        return;
      }

      const isConnected = Boolean(status?.onboarding_completed || status?.charges_enabled);
      toast(isConnected ? 'Stripe Connect linked' : 'Stripe Connect not linked', {
        description: isConnected ? "You're all set." : 'Please try again.',
      });

      router.replace(determineTargetPath(fromParam));
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, [fromParam, router]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-white to-gray-100 px-6">
      <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-8 text-center shadow-sm">
        <h1 className="text-2xl font-semibold text-gray-900">Finalizing Stripe Connect…</h1>
        <p className="mt-3 text-sm text-gray-600">
          We&apos;re updating your instructor account. You&apos;ll be redirected shortly.
        </p>
        <div className="mt-8 h-2 w-full overflow-hidden rounded-full bg-gray-200">
          <div className="h-full w-full animate-pulse bg-[#7E22CE]" />
        </div>
      </div>
    </div>
  );
}
