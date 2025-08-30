'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { getConnectStatus, fetchWithAuth, API_ENDPOINTS, createStripeIdentitySession } from '@/lib/api';
import { paymentService } from '@/services/api/payments';
import { loadStripe } from '@stripe/stripe-js';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { logger } from '@/lib/logger';
import UserProfileDropdown from '@/components/UserProfileDropdown';

export default function OnboardingStatusPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const [connectStatus, setConnectStatus] = useState<any>(null);
  const [profile, setProfile] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [connectLoading, setConnectLoading] = useState(false);
  const [skillsSkipped, setSkillsSkipped] = useState(false);
  const [verificationSkipped, setVerificationSkipped] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [s, me] = await Promise.all([
          getConnectStatus().catch(() => null),
          (async () => {
            try {
              const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);
              if (!res.ok) return null;
              return res.json();
            } catch {
              return null;
            }
          })(),
        ]);
        if (s) setConnectStatus(s);
        if (me) {
          setProfile(me);
        }

        // Check if skills were skipped
        if (typeof window !== 'undefined' && sessionStorage.getItem('skillsSkipped') === 'true') {
          setSkillsSkipped(true);
        } else if (me && (!me.services || me.services.length === 0)) {
          setSkillsSkipped(true);
        }

        // Check if verification was skipped
        if (typeof window !== 'undefined' && sessionStorage.getItem('verificationSkipped') === 'true') {
          setVerificationSkipped(true);
        } else if (me && (!me.background_check_status || me.background_check_status === 'pending')) {
          setVerificationSkipped(true);
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [isAuthenticated]);

  // If already live, redirect to dashboard
  useEffect(() => {
    if (profile?.is_live) {
      router.replace('/instructor/dashboard');
    }
  }, [profile?.is_live, router]);

  const canGoLive = Boolean(
    profile &&
      (profile.skills_configured || (Array.isArray(profile.services) && profile.services.length > 0)) &&
      connectStatus && connectStatus.onboarding_completed &&
      (profile.identity_verified_at || profile.identity_verification_session_id)
  );

  const pendingRequired: string[] = [];
  if (!(connectStatus && connectStatus.onboarding_completed)) pendingRequired.push('Stripe Connect');
  if (!(profile && (profile.identity_verified_at || profile.identity_verification_session_id))) pendingRequired.push('ID verification');
  if (!(profile && ((profile.skills_configured) || (Array.isArray(profile.services) && profile.services.length > 0)))) pendingRequired.push('Skills & pricing');

  const formatList = (items: string[]) => {
    if (items.length <= 1) return items.join('');
    if (items.length === 2) return `${items[0]} and ${items[1]}`;
    return `${items.slice(0, -1).join(', ')}, and ${items[items.length - 1]}`;
  };

  const goLive = async () => {
    try {
      setSaving(true);
      const res = await fetchWithAuth('/instructors/me/go-live', { method: 'POST' });
      if (res.ok) {
        window.location.href = '/instructor/dashboard';
        return;
      }
    } finally {
      setSaving(false);
    }
  };

  const startIdentity = async () => {
    try {
      const session = await createStripeIdentitySession();
      const pubkey = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;
      if (pubkey) {
        const stripe = await loadStripe(pubkey);
        if (stripe && session.client_secret) {
          // @ts-ignore - verifyIdentity typings
          const result = await stripe.verifyIdentity(session.client_secret);
          // After return, force backend refresh of identity status and then refresh profile/connect status
          try {
            await fetchWithAuth(API_ENDPOINTS.STRIPE_IDENTITY_REFRESH, { method: 'POST' });
          } catch {}
          const [s, me] = await Promise.all([
            getConnectStatus().catch(() => null),
            fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE).then((r) => (r.ok ? r.json() : null)).catch(() => null),
          ]);
          if (s) setConnectStatus(s);
          if (me) setProfile(me);
        }
      } else {
        // Fallback: hosted link by opening in same tab
        window.location.href = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/payments/identity/session`;
      }
    } catch {
      // no-op
    }
  };

  const startBackgroundUpload = () => {
    // Navigate to verification section where upload widget lives
    window.location.href = '/instructor/onboarding/verification?from=status';
  };

  const enrollStripeConnect = async () => {
    try {
      setConnectLoading(true);
      const resp = await paymentService.startOnboardingWithReturn('/instructor/onboarding/status?stripe_onboarding_return=true');
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
      // silent fail; could add toast
    } finally {
      setConnectLoading(false);
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
            {/* Walking Stick Figure Animation - positioned on the line between step 3 and 4 */}
            <div className="absolute inst-anim-walk" style={{ top: '-12px', left: '544px' }}>
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

            {/* Step 3 - Completed or Skipped */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => window.location.href = '/instructor/onboarding/verification'}
                  className={`w-6 h-6 rounded-full flex items-center justify-center transition-colors cursor-pointer ${
                    verificationSkipped
                      ? 'bg-purple-300 hover:bg-purple-400'
                      : 'bg-purple-600 hover:bg-purple-700'
                  }`}
                  title={verificationSkipped ? "Step 3: Verification (Skipped)" : "Step 3: Verification"}
                >
                  {verificationSkipped ? (
                    <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  ) : (
                    <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </button>
                <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">Verify Identity</span>
              </div>
              <div
                className={`w-60 h-0.5 ${verificationSkipped ? 'border-t-2 border-dashed border-gray-400' : 'bg-purple-600'}`}
                style={verificationSkipped ? { borderTopStyle: 'dashed', backgroundColor: 'transparent' } : {}}
              ></div>
            </div>

            {/* Step 4 - Current (Status) */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => {/* Already on this page */}}
                  className="w-6 h-6 rounded-full border-2 border-purple-300 bg-purple-100 hover:border-purple-400 transition-colors cursor-pointer"
                  title="Step 4: Status (Current)"
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
        {/* Page Header */}
        <div className="bg-white rounded-lg p-6 mb-6 border border-gray-200">
          <h1 className="text-3xl font-bold text-gray-600 mb-2">Onboarding Status</h1>
          <p className="text-gray-600">Finish these steps to go live.</p>
        </div>

        <div className="mt-6 space-y-4">
          <Row label="Stripe Connect" ok={!!connectStatus?.onboarding_completed} action={<button onClick={enrollStripeConnect} className="text-purple-700 hover:underline disabled:text-gray-400" disabled={!!connectStatus?.onboarding_completed || connectLoading}>{connectStatus?.onboarding_completed ? 'Completed' : (connectLoading ? 'Opening…' : 'Enroll')}</button>} />
        <Row label="ID verification" ok={Boolean(profile?.identity_verified_at)} action={profile?.identity_verified_at ? <span className="text-gray-400">Completed</span> : <button onClick={startIdentity} className="text-purple-700 hover:underline">Start</button>} />
        <Row label="Background check (optional)" ok={Boolean(profile?.background_check_uploaded_at)} action={<button onClick={startBackgroundUpload} className="text-purple-700 hover:underline">{profile?.background_check_uploaded_at ? 'Replace' : 'Upload'}</button>} />
        <Row label="Skills & pricing" ok={Boolean(profile && ((profile.skills_configured) || (Array.isArray(profile.services) && profile.services.length > 0)))} action={<Link href="/instructor/onboarding/skill-selection?redirect=%2Finstructor%2Fonboarding%2Fstatus" className="text-purple-700 hover:underline">Edit</Link>} />
        </div>

        <div className="mt-8">
        <button
          disabled={!canGoLive || saving}
          onClick={goLive}
          className={`px-5 py-2.5 rounded-lg text-white ${canGoLive ? 'bg-[#6A0DAD] hover:bg-[#5c0a9a]' : 'bg-gray-300 cursor-not-allowed'} shadow-sm`}
        >
          {canGoLive ? 'Go live' : 'Complete required steps to go live'}
        </button>
        {pendingRequired.length === 0 ? (
          <p className="text-sm text-gray-500 mt-2">All required steps complete.</p>
        ) : (
          <p className="text-sm text-gray-500 mt-2">Pending: {formatList(pendingRequired)}. Background check is optional.</p>
        )}
      </div>
      </div>

      {/* Animation CSS moved to global (app/globals.css) */}
    </div>
  );
}

function Row({ label, ok, action }: { label: string; ok: boolean; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border border-gray-100 rounded-md px-4 py-3 bg-white shadow-sm">
      <div className="text-gray-800">{label}</div>
      <div className={ok ? 'text-green-600' : 'text-gray-400'}>{ok ? '✓' : '•'}</div>
      <div>{action}</div>
    </div>
  );
}
