'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { loadStripe } from '@stripe/stripe-js';
import { toast } from 'sonner';
import { createStripeIdentitySession, fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { logger } from '@/lib/logger';
import { BGCStep } from '@/components/instructor/BGCStep';
import { ShieldCheck } from 'lucide-react';
import { BackgroundCheckDisclosureModal } from '@/components/consent/BackgroundCheckDisclosureModal';
import { bgcConsent, type BGCConsentPayload, type BGCStatus } from '@/lib/api/bgc';
import { DISCLOSURE_VERSION } from '@/config/constants';
import {
  OnboardingProgressHeader,
  type OnboardingStepStatus,
} from '@/features/instructor-onboarding/OnboardingProgressHeader';
import { useOnboardingStepStatus } from '@/features/instructor-onboarding/useOnboardingStepStatus';
import type { components } from '@/features/shared/api/types';

type IdentityRefreshResponse = components['schemas']['IdentityRefreshResponse'];
type IdentityStatus =
  | 'not_started'
  | 'processing'
  | 'verified'
  | 'requires_input'
  | 'canceled';

const IDENTITY_ERROR_FALLBACK = "Verification couldn't be completed. Please try again.";

const IDENTITY_ERROR_MESSAGES: Record<string, string> = {
  document_expired:
    'Your document appears to be expired. Please try again with a valid, non-expired ID.',
  document_type_not_supported:
    "That document type isn't supported. Please use a passport, driver's license, or national ID.",
  document_unverified_other:
    "We couldn't verify your document. Please try again with a clearer photo.",
  selfie_document_missing_photo:
    "Your ID doesn't include a photo. Please use a photo ID.",
  selfie_face_mismatch:
    "The selfie didn't match the photo on your ID. Please try again.",
  selfie_manipulated:
    'There was an issue with your selfie. Please try again in good lighting without filters.',
  selfie_unverified_other:
    "We couldn't verify your selfie. Please try again with a clear, well-lit photo.",
};

const deriveInitialIdentityStatus = (
  profile:
    | {
        identity_verified_at?: string | null;
        identity_verification_session_id?: string | null;
      }
    | null
    | undefined
): IdentityStatus => {
  if (profile?.identity_verified_at) {
    return 'verified';
  }
  if (profile?.identity_verification_session_id) {
    return 'processing';
  }
  return 'not_started';
};

const normalizeIdentityStatus = (
  status: string | null | undefined,
  verified: boolean | null | undefined
): IdentityStatus | null => {
  if (verified || status === 'verified') {
    return 'verified';
  }

  switch ((status || '').toLowerCase()) {
    case 'not_started':
      return 'not_started';
    case 'processing':
      return 'processing';
    case 'requires_input':
      return 'requires_input';
    case 'canceled':
      return 'canceled';
    case 'verified':
      return 'verified';
    default:
      return null;
  }
};

export default function Step4Verification() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const fromStatus = (searchParams?.get('from') || '').toLowerCase() === 'status';
  const identityReturn = (searchParams?.get('identity_return') || '').toLowerCase() === 'true';

  const [identityLoading, setIdentityLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bgcStatusOverride, setBgcStatusOverride] = useState<BGCStatus | null>(null);
  const [consentModalOpen, setConsentModalOpen] = useState(false);
  const [consentSubmitting, setConsentSubmitting] = useState(false);
  const [hasRecentConsent, setHasRecentConsent] = useState(false);
  const consentResolverRef = useRef<((value: boolean) => void) | null>(null);
  const hasPolledIdentityReturnRef = useRef(false);
  const hydratedSessionIdRef = useRef<string | null>(null);

  const {
    stepStatus: evaluatedStepStatus,
    refresh: refreshStepStatus,
    rawData,
  } = useOnboardingStepStatus();

  const [identityStatus, setIdentityStatus] = useState<IdentityStatus>(() =>
    deriveInitialIdentityStatus(rawData.profile)
  );
  const [identitySessionId, setIdentitySessionId] = useState<string | null>(
    () => rawData.profile?.identity_verification_session_id ?? null
  );
  const [identityErrorCode, setIdentityErrorCode] = useState<string | null>(null);
  const [identityErrorReason, setIdentityErrorReason] = useState<string | null>(null);
  const prevProfileSessionIdRef = useRef<string | null>(
    rawData.profile?.identity_verification_session_id ?? null
  );

  const instructorProfileId = rawData.profile?.id ?? null;

  const bgcStatusRaw = bgcStatusOverride || rawData.bgcStatus || '';
  const bgcStatus = typeof bgcStatusRaw === 'string' ? bgcStatusRaw.toLowerCase() : '';
  const bgcPassed = bgcStatus === 'passed' || bgcStatus === 'clear' || bgcStatus === 'eligible';
  const verificationComplete = identityStatus === 'verified';
  const verifyIdentityComplete = verificationComplete && bgcPassed;

  const stepStatus = useMemo(
    () => ({
      ...evaluatedStepStatus,
      'verify-identity': verifyIdentityComplete
        ? ('done' as OnboardingStepStatus)
        : evaluatedStepStatus['verify-identity'],
    }),
    [evaluatedStepStatus, verifyIdentityComplete]
  );

  const updateIdentityState = useCallback(
    (
      nextStatus: IdentityStatus,
      options: {
        sessionId?: string | null;
        errorCode?: string | null;
        errorReason?: string | null;
      } = {}
    ) => {
      if (Object.prototype.hasOwnProperty.call(options, 'sessionId')) {
        setIdentitySessionId(options.sessionId ?? null);
      }

      setIdentityStatus(nextStatus);

      if (nextStatus === 'requires_input') {
        setIdentityErrorCode(options.errorCode ?? null);
        setIdentityErrorReason(options.errorReason ?? null);
        return;
      }

      setIdentityErrorCode(null);
      setIdentityErrorReason(null);
    },
    []
  );

  useEffect(() => {
    const nextSessionId = rawData.profile?.identity_verification_session_id ?? null;
    const profileVerified = Boolean(rawData.profile?.identity_verified_at);
    const prevProfileSessionId = prevProfileSessionIdRef.current;
    prevProfileSessionIdRef.current = nextSessionId;

    if (profileVerified) {
      updateIdentityState('verified', { sessionId: nextSessionId });
      return;
    }

    if (!nextSessionId) {
      if (identityStatus === 'processing' || identityStatus === 'not_started') {
        updateIdentityState('not_started', { sessionId: null });
      } else {
        setIdentitySessionId(null);
      }
      return;
    }

    if (prevProfileSessionId !== nextSessionId || identityStatus === 'not_started') {
      updateIdentityState('processing', { sessionId: nextSessionId });
      return;
    }

    setIdentitySessionId(nextSessionId);
  }, [
    rawData.profile?.identity_verified_at,
    rawData.profile?.identity_verification_session_id,
    identityStatus,
    updateIdentityState,
  ]);

  const ensureConsent = useCallback(async () => {
    if (hasRecentConsent) {
      return true;
    }
    return new Promise<boolean>((resolve) => {
      consentResolverRef.current = resolve;
      setConsentModalOpen(true);
    });
  }, [hasRecentConsent]);

  const handleDeclineDisclosure = useCallback(() => {
    if (consentSubmitting) {
      return;
    }
    setConsentModalOpen(false);
    if (consentResolverRef.current) {
      consentResolverRef.current(false);
      consentResolverRef.current = null;
    }
  }, [consentSubmitting]);

  const handleAcceptDisclosure = useCallback(async () => {
    if (!instructorProfileId) {
      consentResolverRef.current?.(false);
      consentResolverRef.current = null;
      setConsentModalOpen(false);
      return;
    }

    try {
      setConsentSubmitting(true);
      const payload: BGCConsentPayload = {
        consent_version: DISCLOSURE_VERSION,
        disclosure_version: DISCLOSURE_VERSION,
      };
      if (typeof window !== 'undefined' && window.navigator?.userAgent) {
        payload.user_agent = window.navigator.userAgent;
      }
      await bgcConsent(instructorProfileId, payload);
      setHasRecentConsent(true);
      consentResolverRef.current?.(true);
      consentResolverRef.current = null;
      setConsentModalOpen(false);
      toast.success('Disclosure accepted', {
        description: 'We will now continue to Checkr to start your background check.',
      });
    } catch (consentError) {
      const description =
        consentError instanceof Error ? consentError.message : 'Unable to record consent';
      toast.error('Consent required', { description });
    } finally {
      setConsentSubmitting(false);
    }
  }, [instructorProfileId]);

  const refreshIdentityStatus = useCallback(async (): Promise<IdentityStatus | null> => {
    try {
      const res = await fetchWithAuth(API_ENDPOINTS.STRIPE_IDENTITY_REFRESH, { method: 'POST' });
      if (!res.ok) {
        return null;
      }

      const data = (await res.json()) as IdentityRefreshResponse;
      await refreshStepStatus();

      const nextStatus = normalizeIdentityStatus(data.status, data.verified);
      if (!nextStatus) {
        return null;
      }

      updateIdentityState(nextStatus, {
        sessionId: nextStatus === 'not_started' ? null : identitySessionId,
        errorCode: data.last_error_code ?? null,
        errorReason: data.last_error_reason ?? null,
      });

      return nextStatus;
    } catch {
      return null;
    }
  }, [identitySessionId, refreshStepStatus, updateIdentityState]);

  useEffect(() => {
    if (!identityReturn) {
      hasPolledIdentityReturnRef.current = false;
    }
  }, [identityReturn]);

  useEffect(() => {
    if (identityReturn || !identitySessionId || identityStatus === 'verified') {
      return;
    }
    if (hydratedSessionIdRef.current === identitySessionId) {
      return;
    }

    hydratedSessionIdRef.current = identitySessionId;
    void refreshIdentityStatus();
  }, [identityReturn, identitySessionId, identityStatus, refreshIdentityStatus]);

  useEffect(() => {
    if (!identityReturn || hasPolledIdentityReturnRef.current) {
      return;
    }

    hasPolledIdentityReturnRef.current = true;
    let active = true;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;

    const POLL_INTERVAL_MS = 5000;
    const MAX_ATTEMPTS = 12;

    const cleanupIdentityParam = () => {
      const params = new URLSearchParams(searchParams?.toString() || '');
      params.delete('identity_return');
      const query = params.toString();
      router.replace(`/instructor/onboarding/verification${query ? `?${query}` : ''}`);
    };

    const pollIdentity = async (attempt: number = 1) => {
      if (!active) {
        return;
      }

      const nextStatus = await refreshIdentityStatus();
      if (!active) {
        return;
      }

      if (nextStatus === 'verified') {
        toast.success('Identity check complete', {
          description: 'Next, start your background check.',
        });
        cleanupIdentityParam();
        return;
      }

      if (
        nextStatus === 'requires_input' ||
        nextStatus === 'canceled' ||
        nextStatus === 'not_started'
      ) {
        cleanupIdentityParam();
        return;
      }

      if (attempt < MAX_ATTEMPTS) {
        pollTimer = setTimeout(() => {
          if (active) {
            void pollIdentity(attempt + 1);
          }
        }, POLL_INTERVAL_MS);
        return;
      }

      if (nextStatus === 'processing') {
        toast.info('Verification still processing', {
          description:
            'Stripe is finishing your verification. This page will update automatically when complete.',
        });
      }

      cleanupIdentityParam();
    };

    void pollIdentity();
    return () => {
      active = false;
      if (pollTimer) {
        clearTimeout(pollTimer);
      }
    };
  }, [identityReturn, router, searchParams, refreshIdentityStatus]);

  const startIdentity = async () => {
    const previousIdentityState = {
      status: identityStatus,
      sessionId: identitySessionId,
      errorCode: identityErrorCode,
      errorReason: identityErrorReason,
    };

    try {
      setIdentityLoading(true);
      setError(null);
      const session = await createStripeIdentitySession();
      const markProcessing = () => {
        updateIdentityState('processing', {
          sessionId: session.verification_session_id,
        });
      };

      try {
        const publishableKey = process.env['NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY'];
        if (publishableKey) {
          const stripe = await loadStripe(publishableKey);
          if (!stripe) {
            throw new Error('Failed to load Stripe.js');
          }

          markProcessing();
          const result = await stripe.verifyIdentity(session.client_secret);
          if (result?.error) {
            updateIdentityState(previousIdentityState.status, {
              sessionId: previousIdentityState.sessionId,
              errorCode: previousIdentityState.errorCode,
              errorReason: previousIdentityState.errorReason,
            });
            setError(result.error.message || 'Verification could not be started');
            return;
          }

          router.replace('/instructor/onboarding/verification?identity_return=true');
          return;
        }
      } catch (sdkError) {
        logger.warn(
          'Falling back to hosted Stripe Identity flow',
          sdkError instanceof Error ? sdkError : undefined
        );
      }

      markProcessing();
      window.location.href = `https://verify.stripe.com/start/${session.client_secret}`;
    } catch (startError) {
      logger.error('Identity start failed', startError);
      setError('Failed to start ID verification');
    } finally {
      setIdentityLoading(false);
    }
  };

  const handleStatusUpdate = useCallback(
    (snapshot: { consentRecent: boolean; status: BGCStatus | null }) => {
      setHasRecentConsent(snapshot.consentRecent);
      setBgcStatusOverride(snapshot.status ?? null);
    },
    []
  );

  const handleContinue = () => {
    const target = fromStatus
      ? '/instructor/onboarding/status'
      : '/instructor/onboarding/payment-setup';
    router.push(target);
  };

  const identityBanner = useMemo(() => {
    const hasRetryableIdentityError =
      identityStatus === 'requires_input' && Boolean(identityErrorCode);

    switch (identityStatus) {
      case 'processing':
        return {
          className:
            'mt-4 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700',
          message: "We're reviewing your documents. This usually takes less than a minute.",
        };
      case 'verified':
        return {
          className:
            'mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700',
          message: 'Identity verification complete.',
        };
      case 'requires_input':
        if (!hasRetryableIdentityError) {
          return null;
        }
        return {
          className:
            'mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700',
          message:
            (identityErrorCode && IDENTITY_ERROR_MESSAGES[identityErrorCode]) ||
            IDENTITY_ERROR_FALLBACK,
        };
      case 'canceled':
        return {
          className:
            'mt-4 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-700',
          message: 'Your verification session was canceled.',
        };
      default:
        return null;
    }
  }, [identityStatus, identityErrorCode]);

  const identityButtonDisabled =
    identityLoading || identityStatus === 'processing' || identityStatus === 'verified';

  const hasRetryableIdentityError =
    identityStatus === 'requires_input' && Boolean(identityErrorCode);

  const identityButtonLabel = identityLoading
    ? 'Starting...'
    : identityStatus === 'verified'
      ? 'Verified'
      : identityStatus === 'processing'
        ? 'Verification in progress'
        : hasRetryableIdentityError
          ? 'Retry verification'
          : 'Start verification';

  return (
    <div className="min-h-screen insta-onboarding-page">
      <OnboardingProgressHeader activeStep="verify-identity" stepStatus={stepStatus} />

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        <div className="insta-surface-card insta-onboarding-header">
          <div>
            <h1 className="insta-onboarding-title">Build trust with students</h1>
            <p className="insta-onboarding-subtitle">
              Complete identity verification and your background check to finish onboarding.
            </p>
          </div>
        </div>
        <div className="insta-onboarding-divider" />

        {error && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-red-700">
            {error}
          </div>
        )}

        <div className="grid gap-0 sm:gap-6">
          <section className="insta-surface-card relative p-4 sm:p-6">
            <div className="grid grid-cols-[3rem_1fr] gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-purple-100">
                <svg
                  className="h-6 w-6 text-[#7E22CE]"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M10 6H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V8a2 2 0 00-2-2h-5m-4 0V5a2 2 0 114 0v1m-4 0a2 2 0 104 0m-5 8a2 2 0 100-4 2 2 0 000 4zm0 0c1.306 0 2.417.835 2.83 2M9 14a3.001 3.001 0 00-2.83 2M15 11h3m-3 4h2"
                  />
                </svg>
              </div>
              <h2 className="self-center text-xl font-bold text-gray-900 dark:text-gray-100">
                Identity verification
              </h2>
              <p className="col-span-2 mt-2 text-gray-600 dark:text-gray-400">
                Verify your identity with a government-issued ID and a selfie.
              </p>

              {identityBanner && (
                <div className={`col-span-2 ${identityBanner.className}`}>{identityBanner.message}</div>
              )}

              <div className="col-span-2 mt-4 grid grid-cols-1 gap-4 sm:grid-cols-[1fr_auto] sm:items-end">
                <div className="space-y-2 text-sm text-gray-500 dark:text-gray-400">
                  <div className="flex items-center gap-2">
                    <svg
                      className="h-4 w-4 text-purple-600"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    <span>~5 minutes</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <svg
                      className="h-4 w-4 text-purple-600"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                      />
                    </svg>
                    <span>Secure & encrypted</span>
                  </div>
                </div>

                <Button
                  onClick={startIdentity}
                  disabled={identityButtonDisabled}
                  aria-label={identityButtonLabel}
                  className="insta-primary-btn mt-4 h-auto w-full rounded-lg px-4 py-2 text-base text-white shadow-sm sm:mt-0 sm:h-10 sm:w-auto sm:rounded-md sm:text-sm"
                >
                  {identityLoading ? (
                    <>
                      <svg
                        className="mr-2 h-4 w-4 animate-spin text-white"
                        fill="none"
                        viewBox="0 0 24 24"
                      >
                        <circle
                          className="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          strokeWidth="3"
                        ></circle>
                        <path
                          className="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                        ></path>
                      </svg>
                      Starting...
                    </>
                  ) : (
                    <>{identityButtonLabel}</>
                  )}
                </Button>
              </div>
            </div>
          </section>
          <div className="-mx-4 h-px bg-gray-200/80 sm:hidden" />

          <section id="bgc-step-card" className="insta-surface-card p-4 sm:p-6">
            <div className="mb-4 flex items-start gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-purple-100">
                <ShieldCheck className="h-6 w-6 text-[#7E22CE]" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
                  Background check
                </h2>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                  Start your Checkr background screening to unlock bookings.
                </p>
              </div>
            </div>
            {instructorProfileId ? (
              <BGCStep
                instructorId={instructorProfileId}
                ensureConsent={ensureConsent}
                onStatusUpdate={({ consentRecent, status }) =>
                  handleStatusUpdate({ consentRecent, status })
                }
              />
            ) : (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Loading background check status...
              </p>
            )}
          </section>
        </div>

        <div className="mt-4 flex items-center justify-end gap-3 sm:mt-8">
          <button
            type="button"
            onClick={() => {
              router.push(
                fromStatus
                  ? '/instructor/onboarding/status'
                  : '/instructor/onboarding/payment-setup'
              );
            }}
            className="insta-secondary-btn w-40 justify-center rounded-lg px-5 py-2.5 transition-colors focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20"
          >
            Skip for now
          </button>
          <button
            onClick={handleContinue}
            className="insta-primary-btn w-56 justify-center whitespace-nowrap rounded-lg px-5 py-2.5 text-white shadow-sm disabled:opacity-50"
          >
            Save & Continue
          </button>
        </div>
      </div>

      <BackgroundCheckDisclosureModal
        isOpen={consentModalOpen}
        onDecline={handleDeclineDisclosure}
        onAccept={handleAcceptDisclosure}
        submitting={consentSubmitting}
      />
    </div>
  );
}
