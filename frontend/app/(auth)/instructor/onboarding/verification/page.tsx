'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { loadStripe } from '@stripe/stripe-js';
import { toast } from 'sonner';
import { createStripeIdentitySession, fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { logger } from '@/lib/logger';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import BGCStep from '@/components/instructor/BGCStep';
import { ShieldCheck } from 'lucide-react';
import Modal from '@/components/Modal';
import { Button } from '@/components/ui/button';
import { bgcConsent } from '@/lib/api/bgc';

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

  const ensureConsent = useCallback(async () => {
    if (hasRecentConsent) {
      return true;
    }
    return new Promise<boolean>((resolve) => {
      consentResolverRef.current = resolve;
      setConsentModalOpen(true);
    });
  }, [hasRecentConsent]);

  const handleCloseConsentModal = useCallback(() => {
    if (consentSubmitting) return;
    setConsentModalOpen(false);
    if (consentResolverRef.current) {
      consentResolverRef.current(false);
      consentResolverRef.current = null;
    }
  }, [consentSubmitting]);

  const handleConfirmConsent = useCallback(async () => {
    if (!instructorProfileId) {
      consentResolverRef.current?.(false);
      consentResolverRef.current = null;
      setConsentModalOpen(false);
      return;
    }
    try {
      setConsentSubmitting(true);
      await bgcConsent(instructorProfileId, { consent_version: 'v1' });
      setHasRecentConsent(true);
      consentResolverRef.current?.(true);
      consentResolverRef.current = null;
      setConsentModalOpen(false);
      toast.success('Consent recorded', {
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

  const handleContinue = () => {
    const target = fromStatus ? '/instructor/onboarding/status' : '/instructor/onboarding/payment-setup';
    router.push(target);
  };

  return (
    <div className="min-h-screen">
      <header className="bg-white backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full relative">
          <Link href="/" className="inline-block">
            <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
          </Link>

          <div className="absolute left-1/2 transform -translate-x-1/2 items-center gap-0 hidden min-[1400px]:flex">
            <div className="absolute inst-anim-walk" style={{ top: '-12px', left: '284px' }}>
              <svg width="16" height="20" viewBox="0 0 16 20" fill="none">
                <circle cx="8" cy="4" r="2.5" stroke="#7E22CE" strokeWidth="1.2" fill="none" />
                <line x1="8" y1="6.5" x2="8" y2="12" stroke="#7E22CE" strokeWidth="1.2" />
                <line x1="8" y1="8" x2="5" y2="10" stroke="#7E22CE" strokeWidth="1.2" className="inst-anim-leftArm" />
                <line x1="8" y1="8" x2="11" y2="10" stroke="#7E22CE" strokeWidth="1.2" className="inst-anim-rightArm" />
                <line x1="8" y1="12" x2="6" y2="17" stroke="#7E22CE" strokeWidth="1.2" className="inst-anim-leftLeg" />
                <line x1="8" y1="12" x2="10" y2="17" stroke="#7E22CE" strokeWidth="1.2" className="inst-anim-rightLeg" />
              </svg>
            </div>

            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => { window.location.href = '/instructor/profile'; }}
                  className="w-6 h-6 rounded-full border-2 border-purple-300 bg-purple-100 hover:border-purple-400 transition-colors cursor-pointer"
                  title="Step 1: Account Setup"
                ></button>
                <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">Account Setup</span>
              </div>
              <div className="w-60 h-0.5 bg-gray-300"></div>
            </div>

            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => { window.location.href = '/instructor/onboarding/skill-selection'; }}
                  className="w-6 h-6 rounded-full border-2 border-purple-300 bg-purple-100 hover:border-purple-400 transition-colors cursor-pointer"
                  title="Step 2: Skills & Pricing"
                ></button>
                <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">Add Skills</span>
              </div>
              <div className="w-60 h-0.5 bg-gray-300"></div>
            </div>

            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => {}}
                  className="w-6 h-6 rounded-full border-2 border-purple-300 bg-purple-100 hover:border-purple-400 transition-colors cursor-pointer"
                  title="Step 3: Verification (Current)"
                ></button>
                <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">Verify Identity</span>
              </div>
              <div className="w-60 h-0.5 bg-gray-300"></div>
            </div>

            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => { window.location.href = '/instructor/onboarding/payment-setup'; }}
                  className="w-6 h-6 rounded-full border-2 border-gray-300 hover:border-gray-400 transition-colors cursor-pointer"
                  title="Step 4: Payment Setup"
                ></button>
                <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">Payment Setup</span>
              </div>
            </div>
          </div>

          <div className="pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        <div className="bg-white rounded-lg p-6 mb-8 border border-gray-200">
          <div>
            <h1 className="text-3xl font-bold text-gray-800 mb-2">Build trust with students</h1>
            <p className="text-gray-600">Complete identity verification and your background check to finish onboarding.</p>
          </div>
        </div>

        {refreshingIdentity && (
          <div className="mb-4 rounded-lg bg-purple-50 border border-purple-200 px-4 py-2 text-sm text-purple-700">
            Updating your verification status…
          </div>
        )}

        {error && (
          <div className="mt-4 rounded-lg bg-red-50 text-red-700 px-4 py-3 border border-red-200">{error}</div>
        )}

        <div className="grid gap-6">
          <section className="relative bg-white rounded-lg border border-gray-200 p-6 hover:shadow-sm transition-shadow">
            <div className="grid grid-cols-[3rem_1fr] gap-4">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <svg className="w-6 h-6 text-[#7E22CE]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V8a2 2 0 00-2-2h-5m-4 0V5a2 2 0 114 0v1m-4 0a2 2 0 104 0m-5 8a2 2 0 100-4 2 2 0 000 4zm0 0c1.306 0 2.417.835 2.83 2M9 14a3.001 3.001 0 00-2.83 2M15 11h3m-3 4h2" />
                </svg>
              </div>
              <h2 className="text-xl font-bold text-gray-900 self-center">Identity verification</h2>
              <p className="text-gray-600 mt-2 col-span-2">Verify your identity with a government-issued ID and a selfie.</p>

              <div className="mt-4 col-span-2 grid grid-cols-[1fr_auto] gap-4 items-end">
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

                <button
                  onClick={startIdentity}
                  disabled={identityLoading}
                  aria-label="Start verification"
                  className="inline-flex items-center justify-center w-56 whitespace-nowrap px-4 py-2 rounded-lg text-white bg-[#7E22CE] hover:!bg-[#7E22CE] hover:!text-white disabled:opacity-50 shadow-sm"
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
                </button>
              </div>
            </div>
          </section>

          <section id="bgc-step-card" className="bg-white rounded-lg border border-gray-200 hover:shadow-sm transition-shadow p-6">
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
              <BGCStep instructorId={instructorProfileId} ensureConsent={ensureConsent} />
            ) : (
              <p className="text-sm text-gray-500">Loading background check status…</p>
            )}
          </section>
        </div>

        <div className="mt-8 flex items-center justify-end">
          <button
            onClick={handleContinue}
            className="w-40 px-5 py-2.5 rounded-lg text-white bg-[#7E22CE] hover:!bg-[#7E22CE] hover:!text-white disabled:opacity-50 shadow-sm justify-center"
          >
            Continue
          </button>
        </div>
      </div>

      <Modal
        isOpen={consentModalOpen}
        onClose={handleCloseConsentModal}
        title="FCRA Disclosure & Authorization"
        closeOnBackdrop={!consentSubmitting}
        closeOnEscape={!consentSubmitting}
        footer={
          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={handleCloseConsentModal} disabled={consentSubmitting}>
              Cancel
            </Button>
            <Button onClick={handleConfirmConsent} disabled={consentSubmitting}>
              {consentSubmitting ? 'Recording…' : 'I consent'}
            </Button>
          </div>
        }
      >
        <p className="text-sm text-gray-700 leading-relaxed">
          I authorize InstaInstru and its background screening provider to obtain my background report
          for onboarding and ongoing participation. This authorization remains in effect while I
          participate on the platform, and I can revoke it by contacting support.
        </p>
      </Modal>
    </div>
  );
}
