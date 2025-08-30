'use client';

import { useEffect, useState } from 'react';
import { loadStripe } from '@stripe/stripe-js';
import { createStripeIdentitySession, createSignedUpload, fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { logger } from '@/lib/logger';
import UserProfileDropdown from '@/components/UserProfileDropdown';

export default function Step4Verification() {
  // Suppress hydration warning if needed (browser extensions can cause mismatches)
  // This is only for development - remove if the issue persists in production
  const [identityLoading, setIdentityLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [fileInfo, setFileInfo] = useState<{ name: string; size: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [skillsSkipped, setSkillsSkipped] = useState(false);
  const [verificationComplete, setVerificationComplete] = useState(false);
  const [verificationSkipped, setVerificationSkipped] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        // Check sessionStorage for skip flags
        if (typeof window !== 'undefined') {
          if (sessionStorage.getItem('skillsSkipped') === 'true') {
            setSkillsSkipped(true);
          }
          if (sessionStorage.getItem('verificationSkipped') === 'true') {
            setVerificationSkipped(true);
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
              setVerificationComplete(true);
            }
          }
        } catch {
          // Ignore errors - assume not skipped
        }
      } catch (e) {
        logger.warn('Failed to load connect status');
      }
    };
    void load();
  }, []);

  const startIdentity = async () => {
    try {
      setIdentityLoading(true);
      setError(null);
      const session = await createStripeIdentitySession();
      // Prefer Stripe.js modal to avoid brittle hosted-link flows
      try {
        const publishableKey = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;
        if (publishableKey) {
          const stripe = await loadStripe(publishableKey);
          if (!stripe) throw new Error('Failed to load Stripe.js');
          const result = await stripe.verifyIdentity(session.client_secret);
          if (result?.error) {
            setError(result.error.message || 'Verification could not be started');
            return;
          }
          // On completion or dismissal, take user to status
          window.location.href = '/instructor/onboarding/status?identity_return=true';
          return;
        }
      } catch (e) {
        // Fallback to hosted link
      }
      window.location.href = `https://verify.stripe.com/start/${session.client_secret}`;
    } catch (e) {
      logger.error('Identity start failed', e);
      setError('Failed to start ID verification');
    } finally {
      setIdentityLoading(false);
    }
  };

  const onFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setError(null);
    setUploading(true);
    try {
      const signed = await createSignedUpload({
        filename: f.name,
        content_type: f.type || 'application/octet-stream',
        size_bytes: f.size,
        purpose: 'background_check',
      });
      const putRes = await fetch(signed.upload_url, {
        method: 'PUT',
        headers: signed.headers,
        body: f,
      });
      if (!putRes.ok) throw new Error('Upload failed');
      setFileInfo({ name: f.name, size: f.size });
    } catch (err) {
      logger.error('Upload failed', err);
      setError('Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="min-h-screen">
      {/* Header - matching other pages */}
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full relative">
          <a href="/" className="inline-block">
            <h1 className="text-3xl font-bold text-purple-700 hover:text-purple-800 transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
          </a>

          {/* Progress Bar - 4 Steps - Absolutely centered */}
          <div className="absolute left-1/2 transform -translate-x-1/2 flex items-center gap-0">
            {/* Walking Stick Figure Animation - positioned on the line between step 2 and 3 */}
            <div className="absolute inst-anim-walk" style={{ top: '-12px', left: '284px' }}>
              <svg width="16" height="20" viewBox="0 0 16 20" fill="none">
                {/* Head */}
                <circle cx="8" cy="4" r="2.5" stroke="#6A0DAD" strokeWidth="1.2" fill="none" />
                {/* Body */}
                <line x1="8" y1="6.5" x2="8" y2="12" stroke="#6A0DAD" strokeWidth="1.2" />
                {/* Left arm */}
                <line x1="8" y1="8" x2="5" y2="10" stroke="#6A0DAD" strokeWidth="1.2" className="inst-anim-leftArm" />
                {/* Right arm */}
                <line x1="8" y1="8" x2="11" y2="10" stroke="#6A0DAD" strokeWidth="1.2" className="inst-anim-rightArm" />
                {/* Left leg */}
                <line x1="8" y1="12" x2="6" y2="17" stroke="#6A0DAD" strokeWidth="1.2" className="inst-anim-leftLeg" />
                {/* Right leg */}
                <line x1="8" y1="12" x2="10" y2="17" stroke="#6A0DAD" strokeWidth="1.2" className="inst-anim-rightLeg" />
              </svg>
            </div>

            {/* Step 1 - Completed */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => window.location.href = '/instructor/profile'}
                  className="w-6 h-6 rounded-full bg-purple-600 flex items-center justify-center hover:bg-purple-700 transition-colors cursor-pointer"
                  title="Step 1: Account Created - Click to edit profile"
                >
                  <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                  </svg>
                </button>
                <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">Account Setup</span>
              </div>
              <div className="w-60 h-0.5 bg-purple-600"></div>
            </div>

            {/* Step 2 - Completed or Skipped */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => window.location.href = '/instructor/onboarding/skill-selection'}
                  className={`w-6 h-6 rounded-full flex items-center justify-center transition-colors cursor-pointer ${
                    skillsSkipped
                      ? 'bg-purple-300 hover:bg-purple-400'
                      : 'bg-purple-600 hover:bg-purple-700'
                  }`}
                  title={skillsSkipped ? "Step 2: Skills & Pricing (Skipped)" : "Step 2: Skills & Pricing"}
                >
                  {skillsSkipped ? (
                    <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  ) : (
                    <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </button>
                <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">Add Skills</span>
              </div>
              <div
                className={`w-60 h-0.5 ${skillsSkipped ? 'border-t-2 border-dashed border-gray-400' : 'bg-purple-600'}`}
                style={skillsSkipped ? { borderTopStyle: 'dashed', backgroundColor: 'transparent' } : {}}
              ></div>
            </div>

            {/* Step 3 - Current (Verification) */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => {/* Already on this page */}}
                  className={`w-6 h-6 rounded-full ${
                    verificationComplete
                      ? 'bg-purple-600 hover:bg-purple-700'
                      : verificationSkipped
                      ? 'bg-purple-300 hover:bg-purple-400'
                      : 'border-2 border-purple-300 bg-purple-100 hover:border-purple-400'
                  } transition-colors cursor-pointer flex items-center justify-center`}
                  title={`Step 3: Verification ${
                    verificationComplete ? '(Completed)' : verificationSkipped ? '(Skipped)' : '(Current)'
                  }`}
                >
                  {verificationComplete ? (
                    <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                    </svg>
                  ) : verificationSkipped ? (
                    <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  ) : null}
                </button>
                <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">Verify Identity</span>
              </div>
              <div
                className={`w-60 h-0.5 ${
                  verificationComplete
                    ? 'bg-purple-600'
                    : verificationSkipped
                    ? 'border-t-2 border-dashed border-gray-400'
                    : 'bg-gray-300'
                }`}
                style={verificationSkipped ? { borderTopStyle: 'dashed', backgroundColor: 'transparent' } : {}}
              ></div>
            </div>

            {/* Step 4 - Upcoming */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => window.location.href = '/instructor/onboarding/payment-setup'}
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
        {/* Page Header with subtle purple accent */}
        <div className="bg-white rounded-lg p-6 mb-8 border border-gray-200">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
              <svg className="w-6 h-6 text-purple-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <h1 className="text-3xl font-bold text-gray-800">Build Trust With Students</h1>
              <p className="text-gray-600">Complete verification to start teaching on iNSTAiNSTRU</p>
            </div>
          </div>
        </div>

      {error && <div className="mt-4 rounded-lg bg-red-50 text-red-700 px-4 py-3 border border-red-200">{error}</div>}

      <div className="grid gap-6">
        {/* ID Verification Card - Enhanced with gradient */}
        <div className="relative">
          <div className="absolute inset-0 bg-gradient-to-r from-purple-600 to-purple-400 rounded-xl opacity-10"></div>
          <div className="relative bg-white rounded-xl border-2 border-purple-200 p-6">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center flex-shrink-0">
              <svg className="w-5 h-5 text-purple-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V8a2 2 0 00-2-2h-5m-4 0V5a2 2 0 114 0v1m-4 0a2 2 0 104 0m-5 8a2 2 0 100-4 2 2 0 000 4zm0 0c1.306 0 2.417.835 2.83 2M9 14a3.001 3.001 0 00-2.83 2M15 11h3m-3 4h2" />
              </svg>
            </div>
            <div className="flex-1">
              <h2 className="text-lg font-semibold text-gray-900">Identity Verification</h2>
              <p className="text-gray-600 mt-1">Verify your identity with a government ID and selfie</p>

              <div className="mt-4 flex items-center gap-6 text-sm text-gray-500">
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
              </div>

              <button
                onClick={startIdentity}
                disabled={identityLoading}
                className="mt-5 inline-flex items-center px-5 py-2.5 rounded-lg text-white bg-purple-700 hover:bg-purple-800 disabled:opacity-50 transition-colors font-medium"
              >
                {identityLoading ? (
                  <>
                    <svg className="animate-spin h-4 w-4 mr-2 text-white" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Starting...
                  </>
                ) : (
                  <>Start Verification</>
                )}
              </button>
            </div>
          </div>
          </div>
        </div>

        {/* Background Check Card - Enhanced */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-shadow p-6">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center flex-shrink-0">
              <svg className="w-5 h-5 text-purple-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div className="flex-1">
              <h2 className="text-lg font-semibold text-gray-900">Background Check</h2>
              <p className="text-gray-600 mt-1">Upload your background check document (optional)</p>

              <div className="mt-4 p-3 bg-purple-50 rounded-lg border border-purple-100">
                <p className="text-sm text-purple-900 font-medium mb-2">Accepted providers:</p>
                <div className="flex flex-wrap gap-2">
                  <span className="inline-flex items-center px-2.5 py-1 bg-white rounded-md text-xs text-purple-700 border border-purple-200">
                    Checkr
                  </span>
                  <span className="inline-flex items-center px-2.5 py-1 bg-white rounded-md text-xs text-purple-700 border border-purple-200">
                    Sterling
                  </span>
                  <span className="inline-flex items-center px-2.5 py-1 bg-white rounded-md text-xs text-purple-700 border border-purple-200">
                    NYC DOE
                  </span>
                </div>
              </div>

              <div className="mt-4 flex items-center gap-4 text-xs text-gray-500">
                <span>PDF, JPG, PNG</span>
                <span>•</span>
                <span>Max 10MB</span>
              </div>

              <div className="mt-5">
                <label className="inline-flex items-center px-4 py-2.5 rounded-lg bg-purple-50 border border-purple-200 text-purple-700 font-medium hover:bg-purple-100 transition-colors cursor-pointer">
                  <input type="file" accept=".pdf,.png,.jpg,.jpeg" className="hidden" onChange={onFileSelected} disabled={uploading} />
                  <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  <span>{uploading ? 'Uploading…' : 'Choose File'}</span>
                </label>
                {fileInfo && (
                  <div className="mt-3 flex items-center gap-2 text-sm text-green-700">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                    </svg>
                    <span>{fileInfo.name}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-8 flex justify-between items-center">
        <button
          className="px-4 py-2.5 text-gray-600 hover:text-gray-800 font-medium transition-colors"
          onClick={() => window.location.href = '/instructor/onboarding/skill-selection'}
        >
          ← Back
        </button>
        <button
          className="px-6 py-2.5 rounded-lg text-white bg-purple-700 hover:bg-purple-800 transition-colors font-medium shadow-sm"
          onClick={() => {
            // If verification wasn't completed, mark it as skipped
            if (!verificationComplete && typeof window !== 'undefined') {
              sessionStorage.setItem('verificationSkipped', 'true');
            }
            window.location.href = '/instructor/onboarding/status';
          }}
        >
          Continue →
        </button>
      </div>
      </div>

      {/* Animation CSS moved to global (app/globals.css) */}
    </div>
  );
}
