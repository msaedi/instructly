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
import { bgcConsent, type BGCConsentPayload } from '@/lib/api/bgc';
import { DISCLOSURE_VERSION } from '@/config/constants';
import { OnboardingProgressHeader, type OnboardingStepKey, type OnboardingStepStatus } from '@/features/instructor-onboarding/OnboardingProgressHeader';

export default function Step4Verification() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const fromStatus = (searchParams?.get('from') || '').toLowerCase() === 'status';
  const identityReturn = (searchParams?.get('identity_return') || '').toLowerCase() === 'true';

  const [identityLoading, setIdentityLoading] = useState(false);
  const [refreshingIdentity, setRefreshingIdentity] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verificationComplete, setVerificationComplete] = useState(false);
  const [instructorProfileId, setInstructorProfileId] = useState<string | null>(null);
  const hasRefreshedRef = useRef(false);
  const [consentModalOpen, setConsentModalOpen] = useState(false);
  const [consentSubmitting, setConsentSubmitting] = useState(false);
  const [hasRecentConsent, setHasRecentConsent] = useState(false);
  const consentResolverRef = useRef<((value: boolean) => void) | null>(null);
  const [stepStatus, setStepStatus] = useState<Partial<Record<OnboardingStepKey, OnboardingStepStatus>>>(() => ({
    'account-setup': 'done',
    'skill-selection': 'done',
    'verify-identity': 'pending',
  }));
  const completedSteps = useMemo(
    () => ({
      'account-setup': stepStatus['account-setup'] === 'done',
      'skill-selection': stepStatus['skill-selection'] === 'done',
      'verify-identity': stepStatus['verify-identity'] === 'done',
    }),
    [stepStatus]
  );

  useEffect(() => {
    const loadProfile = async () => {
      try {
        const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);
        if (!res.ok) return;
        const profile = await res.json();
        if (profile?.id) setInstructorProfileId(String(profile.id));
        if (profile?.identity_verified_at || profile?.identity_verification_session_id) {
          setVerificationComplete(true);
        }
      } catch (err) {
        logger.warn('Failed to load verification status', err instanceof Error ? err : undefined);
      }
    };

    void loadProfile();
  }, []);

  useEffect(() => {
    setStepStatus((prev) => ({
      ...prev,
      'verify-identity': verificationComplete ? 'done' : 'pending',
    }));
  }, [verificationComplete]);

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
    } catch (error) {
      const description = error instanceof Error ? error.message : 'Unable to record consent';
      toast.error('Consent required', { description });
    } finally {
      setConsentSubmitting(false);
    }
  }, [instructorProfileId]);

  useEffect(() => {
    if (!identityReturn || hasRefreshedRef.current) return;
    hasRefreshedRef.current = true;
    let active = true;

    const refreshIdentity = async () => {
      setRefreshingIdentity(true);
      try {
        const res = await fetchWithAuth(API_ENDPOINTS.STRIPE_IDENTITY_REFRESH, { method: 'POST' });
        if (!active) return;
        if (res.ok) {
          const data = await res.json();
          if (data?.verified) {
            setVerificationComplete(true);
            toast.success('Identity check complete', {
              description: 'Next, start your background check.',
            });
          } else {
            toast.info('Identity check updated', {
              description: 'Stripe is still finishing your verification.',
            });
          }
        } else {
          toast.error('Unable to refresh identity status');
        }
      } catch {
        if (active) toast.error('Unable to refresh identity status');
      } finally {
        if (active) {
          setRefreshingIdentity(false);
          const params = new URLSearchParams(searchParams?.toString() || '');
          params.delete('identity_return');
          const query = params.toString();
          router.replace(`/instructor/onboarding/verification${query ? `?${query}` : ''}`);
        }
      }
    };

    void refreshIdentity();
    return () => {
      active = false;
    };
  }, [identityReturn, router, searchParams]);

  const startIdentity = async () => {
    try {
      setIdentityLoading(true);
      setError(null);
      const session = await createStripeIdentitySession();
      try {
        const publishableKey = process.env['NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY'];
        if (publishableKey) {
          const stripe = await loadStripe(publishableKey);
          if (!stripe) throw new Error('Failed to load Stripe.js');
          const result = await stripe.verifyIdentity(session.client_secret);
          if (result?.error) {
            setError(result.error.message || 'Verification could not be started');
            return;
          }
          router.replace('/instructor/onboarding/verification?identity_return=true');
          return;
        }
      } catch (sdkError) {
        logger.warn('Falling back to hosted Stripe Identity flow', sdkError instanceof Error ? sdkError : undefined);
      }
      window.location.href = `https://verify.stripe.com/start/${session.client_secret}`;
    } catch (e) {
      logger.error('Identity start failed', e);
      setError('Failed to start ID verification');
    } finally {
      setIdentityLoading(false);
    }
  };

  const handleStatusUpdate = useCallback((snapshot: { consentRecent: boolean }) => {
    setHasRecentConsent(snapshot.consentRecent);
  }, []);

  const handleContinue = () => {
    const target = fromStatus ? '/instructor/onboarding/status' : '/instructor/onboarding/payment-setup';
    router.push(target);
  };

  return (
    <div className="min-h-screen">
      <OnboardingProgressHeader activeStep="verify-identity" stepStatus={stepStatus} completedSteps={completedSteps} />

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        <div className="mb-4 sm:mb-8 bg-transparent border-0 rounded-none p-4 sm:bg-white sm:rounded-lg sm:p-6 sm:border sm:border-gray-200">
          <div>
            <h1 className="text-3xl font-bold text-gray-800 mb-2">Build trust with students</h1>
            <p className="text-gray-600">Complete identity verification and your background check to finish onboarding.</p>
          </div>
        </div>
        {/* Divider */}
        <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />

        {refreshingIdentity && (
          <div className="mb-4 rounded-lg bg-purple-50 border border-purple-200 px-4 py-2 text-sm text-purple-700">
            Updating your verification status…
          </div>
        )}

        {error && (
          <div className="mt-4 rounded-lg bg-red-50 text-red-700 px-4 py-3 border border-red-200">{error}</div>
        )}

        <div className="grid gap-0 sm:gap-6">
          <section className="relative bg-white rounded-none border-0 p-4 sm:bg-white sm:rounded-lg sm:border sm:border-gray-200 sm:p-6">
            <div className="grid grid-cols-[3rem_1fr] gap-4">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <svg className="w-6 h-6 text-[#7E22CE]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V8a2 2 0 00-2-2h-5m-4 0V5a2 2 0 114 0v1m-4 0a2 2 0 104 0m-5 8a2 2 0 100-4 2 2 0 000 4zm0 0c1.306 0 2.417.835 2.83 2M9 14a3.001 3.001 0 00-2.83 2M15 11h3m-3 4h2" />
                </svg>
              </div>
              <h2 className="text-xl font-bold text-gray-900 self-center">Identity verification</h2>
              <p className="text-gray-600 mt-2 col-span-2">Verify your identity with a government-issued ID and a selfie.</p>

              <div className="mt-4 col-span-2 grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-4 sm:items-end">
                <div className="space-y-2 text-sm text-gray-500">
                  <div className="flex items-center gap-2">
                    <svg className="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span>~5 minutes</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <svg className="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                    </svg>
                    <span>Secure & encrypted</span>
                  </div>
                  {verificationComplete && (
                    <p className="text-xs text-emerald-600">Identity verification completed.</p>
                  )}
                </div>

                <Button
                  onClick={startIdentity}
                  disabled={identityLoading}
                  aria-label="Start verification"
                  className="w-full sm:w-auto mt-4 sm:mt-0 rounded-lg sm:rounded-md text-base sm:text-sm h-auto sm:h-10 px-4 py-2 bg-[#7E22CE] hover:bg-[#7E22CE] text-white shadow-sm"
                >
                  {identityLoading ? (
                    <>
                      <svg className="animate-spin h-4 w-4 mr-2 text-white" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      Starting…
                    </>
                  ) : (
                    <>Start verification</>
                  )}
                </Button>
              </div>
            </div>
          </section>
          {/* Divider */}
          <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />

          <section id="bgc-step-card" className="bg-white rounded-none border-0 p-4 sm:bg-white sm:rounded-lg sm:border sm:border-gray-200 sm:p-6">
            <div className="flex items-start gap-3 mb-4">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <ShieldCheck className="w-6 h-6 text-[#7E22CE]" />
              </div>
              <div>
                <h3 className="text-xl font-bold text-gray-900">Background check</h3>
                <p className="text-sm text-muted-foreground mt-1">Start your Checkr background screening to unlock bookings.</p>
              </div>
            </div>
            {instructorProfileId ? (
              <BGCStep
                instructorId={instructorProfileId}
                ensureConsent={ensureConsent}
                onStatusUpdate={({ consentRecent }) =>
                  handleStatusUpdate({ consentRecent })
                }
              />
            ) : (
              <p className="text-sm text-gray-500">Loading background check status…</p>
            )}
          </section>
        </div>

        <div className="mt-4 sm:mt-8 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={() => { router.push(fromStatus ? '/instructor/onboarding/status' : '/instructor/onboarding/payment-setup'); }}
            className="w-40 px-5 py-2.5 rounded-lg text-[#7E22CE] bg-white border border-purple-200 hover:bg-gray-50 hover:border-purple-300 transition-colors focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 justify-center"
          >
            Skip for now
          </button>
          <button
            onClick={handleContinue}
            className="w-56 whitespace-nowrap px-5 py-2.5 rounded-lg text-white bg-[#7E22CE] hover:!bg-[#7E22CE] hover:!text-white disabled:opacity-50 shadow-sm justify-center"
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
