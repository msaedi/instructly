'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { fetchWithAuth, API_ENDPOINTS, getConnectStatus } from '@/lib/api';
import { paymentService } from '@/services/api/payments';
import { logger } from '@/lib/logger';
import UserProfileDropdown from '@/components/UserProfileDropdown';

export default function Step3PaymentSetup() {
  const [connectLoading, setConnectLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [skillsSkipped, setSkillsSkipped] = useState<boolean>(false);
  const [connectStatus, setConnectStatus] = useState<{
    has_account: boolean;
    onboarding_completed: boolean;
    charges_enabled: boolean;
    payouts_enabled: boolean;
    details_submitted: boolean;
  } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);

        // Check for Stripe Connect status
        const status = await getConnectStatus().catch(() => null);
        if (status) {
          setConnectStatus(status);
        }

        // Check sessionStorage for skip flags
        if (typeof window !== 'undefined') {
          if (sessionStorage.getItem('skillsSkipped') === 'true') {
            setSkillsSkipped(true);
          }
        }

        // Check if instructor has completed verification or has no skills in profile
        try {
          const profileRes = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);
          if (profileRes.ok) {
            const profile = await profileRes.json();
            if (!profile.services || profile.services.length === 0) {
              setSkillsSkipped(true);
            }
            // Check if verification is complete
            if (profile.identity_verified_at || profile.identity_verification_session_id) {
              // setVerificationComplete(true); // This line was removed as per the edit hint
            }
          }
        } catch {
          // Ignore errors
        }
      } catch {
        logger.warn('Failed to load status');
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const enrollStripeConnect = async () => {
    try {
      setConnectLoading(true);
      setError(null);
      const resp = await paymentService.startOnboardingWithReturn('/instructor/onboarding/payment-setup');
      if (resp.already_onboarded) {
        const s = await getConnectStatus().catch(() => null);
        if (s) setConnectStatus(s);
        setConnectLoading(false);
        return;
      }
      if (resp.onboarding_url) {
        window.location.href = resp.onboarding_url;
        return;
      }
    } catch (e) {
      logger.error('Stripe Connect enrollment failed', e);
      setError('Failed to start payment setup');
    } finally {
      setConnectLoading(false);
    }
  };

  // Check for return from Stripe
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const urlParams = new URLSearchParams(window.location.search);
      if (urlParams.get('stripe_onboarding_return') === 'true') {
        // Reload status after returning from Stripe
        getConnectStatus().then((status) => {
          if (status) setConnectStatus(status);
        }).catch(() => {});
      }
    }
  }, []);

  return (
    <div className="min-h-screen">
      {/* Header - matching other pages */}
      <header className="bg-white backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full relative">
          <Link className="inline-block" href="/">
            <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
          </Link>

          {/* Progress Bar - 4 Steps - Absolutely centered */}
          <div className="absolute left-1/2 transform -translate-x-1/2 items-center gap-0 hidden min-[1400px]:flex">
            {/* Walking Stick Figure Animation - positioned on the line between step 3 and 4 */}
            <div className="absolute inst-anim-walk" style={{ top: '-12px', left: '544px' }}>
              <svg width="16" height="20" viewBox="0 0 16 20" fill="none">
                {/* Head */}
                <circle cx="8" cy="4" r="2.5" stroke="#7E22CE" strokeWidth="1.2" fill="none" />
                {/* Body */}
                <line x1="8" y1="6.5" x2="8" y2="12" stroke="#7E22CE" strokeWidth="1.2" />
                {/* Left arm */}
                <line x1="8" y1="8" x2="5" y2="10" stroke="#7E22CE" strokeWidth="1.2" className="inst-anim-leftArm" />
                {/* Right arm */}
                <line x1="8" y1="8" x2="11" y2="10" stroke="#7E22CE" strokeWidth="1.2" className="inst-anim-rightArm" />
                {/* Left leg */}
                <line x1="8" y1="12" x2="6" y2="17" stroke="#7E22CE" strokeWidth="1.2" className="inst-anim-leftLeg" />
                {/* Right leg */}
                <line x1="8" y1="12" x2="10" y2="17" stroke="#7E22CE" strokeWidth="1.2" className="inst-anim-rightLeg" />
              </svg>
            </div>

            {/* Step 1 - Previous */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => window.location.href = '/instructor/profile'}
                  className="w-6 h-6 rounded-full border-2 border-purple-300 bg-purple-100 hover:border-purple-400 transition-colors cursor-pointer"
                  title="Step 1: Account Setup"
                ></button>
                <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">Account Setup</span>
              </div>
              <div className="w-60 h-0.5 bg-gray-300"></div>
            </div>

            {/* Step 2 - Previous */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => window.location.href = '/instructor/onboarding/skill-selection'}
                  className="w-6 h-6 rounded-full border-2 border-purple-300 bg-purple-100 hover:border-purple-400 transition-colors cursor-pointer"
                  title="Step 2: Skills & Pricing"
                ></button>
                <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">Add Skills</span>
              </div>
              <div className="w-60 h-0.5 bg-gray-300"></div>
            </div>

            {/* Step 3 - Previous (Verification) */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => window.location.href = '/instructor/onboarding/verification'}
                  className="w-6 h-6 rounded-full border-2 border-purple-300 bg-purple-100 hover:border-purple-400 transition-colors cursor-pointer"
                  title="Step 3: Verification"
                ></button>
                <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">Verify Identity</span>
              </div>
              <div className="w-60 h-0.5 bg-gray-300"></div>
            </div>

            {/* Step 4 - Current (Payment Setup) */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => {/* Already on this page */}}
                  className="w-6 h-6 rounded-full border-2 border-purple-300 bg-purple-100 hover:border-purple-400 transition-colors cursor-pointer"
                  title="Step 4: Payment Setup (Current)"
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
        {/* Page Header - match verification */}
        <div className="bg-white rounded-lg p-6 mb-8 border border-gray-200">
          <div>
            <h1 className="text-3xl font-bold text-gray-800 mb-2">Get Paid for Your Lessons</h1>
            <p className="text-gray-600">Connect your bank securely through Stripe{skillsSkipped ? ' • You can add skills later' : ''}</p>
          </div>
        </div>

      {error && <div className="mt-4 rounded-lg bg-red-50 text-red-700 px-4 py-3 border border-red-200">{error}</div>}

      {loading ? (
        <div className="flex flex-col items-center justify-center py-16">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600"></div>
          <p className="mt-4 text-gray-600 font-medium">Loading payment setup...</p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Main Card */}
          <div className="relative">
            <div className="relative bg-white rounded-lg border border-gray-200 overflow-hidden">
              {/* Card Header with Icon */}
              <div className="bg-white p-6">
                <div className="grid grid-cols-[3rem_1fr] gap-4">
                  <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                    <svg className="w-6 h-6 text-[#7E22CE]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                    </svg>
                  </div>
                  <h2 className="text-xl font-bold text-gray-900 self-center">Connect Your Bank Account</h2>
                  <p className="text-gray-600 mt-2 col-span-2">You&apos;ll be redirected to Stripe to link your bank account securely. Once connected, payments from students will be deposited directly to you.</p>
                </div>
              </div>

              {/* Benefits Section */}
              <div className="px-8 pt-4 pb-8">
                <p className="text-gray-600 mb-2">What to expect</p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="bg-purple-50 rounded-lg p-4 border border-purple-100">
                    <div className="flex items-start gap-3">
                      <div className="w-8 h-8 rounded-full bg-purple-100 flex items-center justify-center flex-shrink-0">
                        <svg className="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      </div>
                      <div>
                        <p className="font-medium text-gray-900 text-sm">Quick Setup</p>
                        <p className="text-xs text-gray-600 mt-1">Usually takes just a few minutes</p>
                      </div>
                    </div>
                  </div>

                  <div className="bg-purple-50 rounded-lg p-4 border border-purple-100">
                    <div className="flex items-start gap-3">
                      <div className="w-8 h-8 rounded-full bg-purple-100 flex items-center justify-center flex-shrink-0">
                        <svg className="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      </div>
                      <div>
                        <p className="font-medium text-gray-900 text-sm">Direct Deposits</p>
                        <p className="text-xs text-gray-600 mt-1">Payments go straight to you</p>
                      </div>
                    </div>
                  </div>

                  <div className="bg-purple-50 rounded-lg p-4 border border-purple-100">
                    <div className="flex items-start gap-3">
                      <div className="w-8 h-8 rounded-full bg-purple-100 flex items-center justify-center flex-shrink-0">
                        <svg className="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                        </svg>
                      </div>
                      <div>
                        <p className="font-medium text-gray-900 text-sm">Bank Security</p>
                        <p className="text-xs text-gray-600 mt-1">Protected by Stripe&apos;s encryption</p>
                      </div>
                    </div>
                  </div>
                </div>



                {/* Success State */}
                {connectStatus?.onboarding_completed ? (
                  <div className="mt-6 bg-gradient-to-r from-green-50 to-green-100 border border-green-200 rounded-lg p-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-green-500 flex items-center justify-center">
                        <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                        </svg>
                      </div>
                      <div>
                        <p className="font-semibold text-green-900">Payment setup complete!</p>
                        <p className="text-sm text-green-700">You&apos;re ready to receive payments from students</p>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="mt-8 flex items-end justify-end">
                    <div className="text-right">
                      <button
                        onClick={enrollStripeConnect}
                        disabled={connectLoading}
                        className="inline-flex items-center justify-center w-56 px-4 py-2 rounded-lg text-white bg-[#7E22CE] hover:!bg-[#7E22CE] disabled:opacity-50 shadow-sm whitespace-nowrap"
                      >
                        {connectLoading ? (
                          <>
                            <svg className="animate-spin h-4 w-4 mr-2 text-white" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3"></circle>
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                            Opening Stripe...
                          </>
                        ) : (
                          <>Connect with Stripe →</>
                        )}
                      </button>
                      <p className="text-xs text-gray-500 mt-3">You&apos;ll be redirected to Stripe&apos;s secure portal</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>


        </div>
      )}

      <div className="mt-8 flex items-center justify-end gap-3">
        <button
          type="button"
          onClick={() => { window.location.href = '/instructor/onboarding/status'; }}
          className="w-40 px-5 py-2.5 rounded-lg text-[#7E22CE] bg-white border border-purple-200 hover:bg-gray-50 hover:border-purple-300 transition-colors focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 justify-center"
        >
          Skip for now
        </button>
        <button
          onClick={() => { window.location.href = '/instructor/onboarding/status'; }}
          className="w-40 px-5 py-2.5 rounded-lg text-white bg-[#7E22CE] hover:!bg-[#7E22CE] hover:!text-white disabled:opacity-50 shadow-sm justify-center"
        >
          Continue
        </button>
      </div>
      </div>

      {/* Animation CSS moved to global (app/globals.css) */}
    </div>
  );
}
