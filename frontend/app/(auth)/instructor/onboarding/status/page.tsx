'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { getConnectStatus, fetchWithAuth, API_ENDPOINTS, createStripeIdentitySession } from '@/lib/api';
import { paymentService } from '@/services/api/payments';
import { loadStripe } from '@stripe/stripe-js';
import { useAuth } from '@/features/shared/hooks/useAuth';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { BGCStep } from '@/components/instructor/BGCStep';
import type { BGCStatus } from '@/lib/api/bgc';
import { ShieldCheck } from 'lucide-react';

export default function OnboardingStatusPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const [connectStatus, setConnectStatus] = useState<{
    has_account: boolean;
    onboarding_completed: boolean;
    charges_enabled: boolean;
    payouts_enabled: boolean;
    details_submitted: boolean;
  } | null>(null);
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [connectLoading, setConnectLoading] = useState(false);
  const [skillsSkipped, setSkillsSkipped] = useState(false);
  const [verificationSkipped, setVerificationSkipped] = useState(false);
  const [instructorProfileId, setInstructorProfileId] = useState<string | null>(null);
  const [bgcSnapshot, setBgcSnapshot] = useState<{
    status: BGCStatus | null;
    completedAt: string | null;
    consentRecent: boolean;
    consentRecentAt: string | null;
  }>({ status: null, completedAt: null, consentRecent: false, consentRecentAt: null });
  const redirectingRef = useRef(false);

  const handleBgcSnapshot = useCallback(
    (
      next: {
        status: BGCStatus | null;
        reportId: string | null;
        completedAt: string | null;
        consentRecent: boolean;
        consentRecentAt: string | null;
      },
    ) => {
      setBgcSnapshot({
        status: next.status,
        completedAt: next.completedAt,
        consentRecent: next.consentRecent,
        consentRecentAt: next.consentRecentAt,
      });
    },
    []
  );

  useEffect(() => {
    if (bgcSnapshot.status === null) return;
    setVerificationSkipped(bgcSnapshot.status !== 'passed');
  }, [bgcSnapshot.status]);

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
          try {
            const profileIdValue = (me as Record<string, unknown>)?.['id'];
            if (typeof profileIdValue === 'string') {
              setInstructorProfileId(profileIdValue);
            } else if (typeof profileIdValue === 'number') {
              setInstructorProfileId(String(profileIdValue));
            } else {
              setInstructorProfileId(null);
            }
          } catch {
            setInstructorProfileId(null);
          }
        }

        // Check if skills were skipped
        if (typeof window !== 'undefined' && sessionStorage.getItem('skillsSkipped') === 'true') {
          setSkillsSkipped(true);
        } else if (me && (!me['services'] || me['services'].length === 0)) {
          setSkillsSkipped(true);
        }

        // Check if verification was skipped
        if (typeof window !== 'undefined' && sessionStorage.getItem('verificationSkipped') === 'true') {
          setVerificationSkipped(true);
        } else if (me) {
          const rawBgc = typeof me['bgc_status'] === 'string'
            ? me['bgc_status']
            : (typeof me['background_check_status'] === 'string' ? me['background_check_status'] : '');
          setVerificationSkipped(rawBgc?.toLowerCase() !== 'passed');
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [isAuthenticated]);

  // If already live, redirect to dashboard
  useEffect(() => {
    if (profile?.['is_live']) {
      router.replace('/instructor/dashboard');
    }
  }, [profile, router]);

  const canGoLive = Boolean(
    profile &&
      (profile['skills_configured'] || (Array.isArray(profile['services']) && profile['services'].length > 0)) &&
      connectStatus && connectStatus.onboarding_completed &&
      (profile['identity_verified_at'] || profile['identity_verification_session_id']) &&
      bgcSnapshot.status === 'passed'
  );

  const needsStripe = !(connectStatus && connectStatus.onboarding_completed);
  const needsIdentity = !(profile && (profile['identity_verified_at'] || profile['identity_verification_session_id']));
  const needsSkills = !(profile && ((profile['skills_configured']) || (Array.isArray(profile['services']) && profile['services'].length > 0)));
  const needsBGC = bgcSnapshot.status !== 'passed';

  // Compute pending in canonical step order for display
  const pendingRequired: string[] = [];
  if (needsSkills) pendingRequired.push('Skills & pricing');
  if (needsIdentity) pendingRequired.push('ID verification');
  if (needsBGC) pendingRequired.push('Background check');
  if (needsStripe) pendingRequired.push('Stripe Connect');

  // User-facing labels for the fun/actionable card in the desired order
  const pendingLabels: string[] = [];
  if (needsSkills) pendingLabels.push('Add skills');
  if (needsIdentity) pendingLabels.push('Verify Identity');
  if (needsBGC) pendingLabels.push('Start background check');
  if (needsStripe) pendingLabels.push('Payment setup');

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
      const pubkey = process.env['NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY'];
      if (pubkey) {
        const stripe = await loadStripe(pubkey);
        if (stripe && session.client_secret) {
          await stripe.verifyIdentity(session.client_secret);
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
        window.location.href = `${process.env['NEXT_PUBLIC_API_BASE'] || 'http://localhost:8000'}/api/payments/identity/session`;
      }
    } catch {
      // no-op
    }
  };

  const enrollStripeConnect = async () => {
    try {
      setConnectLoading(true);
      redirectingRef.current = false;
      const resp = await paymentService.startOnboardingWithReturn('/instructor/onboarding/status');
      if (resp.already_onboarded) {
        const s = await getConnectStatus().catch(() => null);
        if (s) setConnectStatus(s);
        return;
      }
      if (resp.onboarding_url) {
        // Keep the button in "Opening…" state until navigation happens
        redirectingRef.current = true;
        window.location.href = resp.onboarding_url;
        return;
      }
    } catch {
      // silent fail; could add toast
    } finally {
      if (!redirectingRef.current) setConnectLoading(false);
    }
  };

  return (
    <div className="min-h-screen">
      {/* Header - matching other pages */}
      <header className="bg-white backdrop-blur-sm border-b border-gray-200 px-4 sm:px-6 py-4">
        <div className="flex items-center justify-between max-w-full relative">
          <Link href="/instructor/dashboard" className="inline-block">
            <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-0 sm:pl-4">iNSTAiNSTRU</h1>
          </Link>

          {/* Progress Bar - 4 Steps - Absolutely centered (hide on smaller screens to avoid overlap) */}
          <div className="absolute left-1/2 transform -translate-x-1/2 items-center gap-0 hidden min-[1400px]:flex">

            {/* Step 1 - Completed */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => window.location.href = '/instructor/profile'}
                  className="w-6 h-6 rounded-full bg-[#7E22CE] flex items-center justify-center hover:bg-[#7E22CE] transition-colors cursor-pointer"
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
                      : 'bg-[#7E22CE] hover:bg-[#7E22CE]'
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
                className={`w-60 h-0.5 ${skillsSkipped ? 'border-t-2 border-dashed border-gray-400' : 'bg-[#7E22CE]'}`}
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
                      : 'bg-[#7E22CE] hover:bg-[#7E22CE]'
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
                className={`w-60 h-0.5 ${verificationSkipped ? 'border-t-2 border-dashed border-gray-400' : 'bg-[#7E22CE]'}`}
                style={verificationSkipped ? { borderTopStyle: 'dashed', backgroundColor: 'transparent' } : {}}
              ></div>
            </div>

            {/* Step 4 - Current (Status) */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => {/* Already on this page */}}
                  className={`w-6 h-6 rounded-full flex items-center justify-center transition-colors cursor-pointer ${
                    canGoLive ? 'bg-[#7E22CE] hover:bg-[#7E22CE]' : (pendingRequired.length === 0 ? 'bg-[#7E22CE]' : 'bg-purple-300 hover:bg-purple-400')
                  }`}
                  title="Step 4: Payment Setup / Status"
                >
                  {pendingRequired.length === 0 ? (
                    <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  )}
                </button>
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

        {pendingRequired.length > 0 && (
          <div className="bg-white rounded-lg p-4 mb-6 border border-gray-200 blink-card text-center">
            <p className="text-sm text-gray-800 font-medium">
              You&apos;re close! Finish {formatList(pendingLabels)} to go live.
            </p>
            <div className="mt-3 flex flex-wrap gap-2 justify-center">
              {needsSkills && (
                <Link
                  href="/instructor/onboarding/skill-selection?redirect=%2Finstructor%2Fonboarding%2Fstatus"
                  className="px-3 py-1.5 rounded-md bg-primary hover:bg-primary text-white shadow-sm text-xs"
                >
                  Add skills
                </Link>
              )}
              {needsIdentity && (
                <button
                  onClick={startIdentity}
                  className="px-3 py-1.5 rounded-md bg-primary hover:bg-primary text-white shadow-sm text-xs"
                >
                  Start ID check
                </button>
              )}
              {needsStripe && (
                <button
                  onClick={enrollStripeConnect}
                  className="px-3 py-1.5 rounded-md bg-primary hover:bg-primary text-white shadow-sm text-xs"
                >
                  Connect Stripe
                </button>
              )}
            </div>
          </div>
        )}

        {instructorProfileId ? (
          <div id="bgc-step-card" className="bg-white rounded-lg border border-gray-200 p-6">
            <div className="flex items-start gap-3 mb-4">
              <div className="w-12 h-12 rounded-full bg-emerald-50 flex items-center justify-center">
                <ShieldCheck className="w-6 h-6 text-emerald-600" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Background check</h2>
                <p className="text-sm text-muted-foreground">Invite yourself via Checkr to complete your screening.</p>
              </div>
            </div>
            <BGCStep instructorId={instructorProfileId} onStatusUpdate={handleBgcSnapshot} />
          </div>
        ) : null}

        <div className="mt-6 space-y-4">
          {/* 1) Skills & pricing */}
          <Row label="Skills & pricing" ok={Boolean(profile && ((profile['skills_configured']) || (Array.isArray(profile['services']) && profile['services'].length > 0)))} action={<Link href="/instructor/onboarding/skill-selection?redirect=%2Finstructor%2Fonboarding%2Fstatus" className="text-[#7E22CE] hover:underline">Edit</Link>} />
          {/* 2) ID verification */}
          <Row label="ID verification" ok={Boolean(profile?.['identity_verified_at'])} action={profile?.['identity_verified_at'] ? <span className="text-gray-400">Completed</span> : <button onClick={startIdentity} className="text-[#7E22CE] hover:underline">Start</button>} />
          {/* 3) Background check */}
          <Row
            label="Background check"
            ok={bgcSnapshot.status === 'passed'}
            action={
              bgcSnapshot.status === 'passed'
                ? <span className="text-gray-400 text-sm">Completed</span>
                : (
                  <button
                    onClick={() => router.push('/instructor/onboarding/verification?from=status#bgc-step-card')}
                    className="text-[#7E22CE] hover:underline text-sm"
                  >
                    Start
                  </button>
                )
            }
          />
          {/* 4) Stripe Connect */}
          <Row label="Stripe Connect" ok={!!connectStatus?.onboarding_completed} action={<button onClick={enrollStripeConnect} className="text-[#7E22CE] hover:underline disabled:text-gray-400" disabled={!!connectStatus?.onboarding_completed || connectLoading}>{connectStatus?.onboarding_completed ? 'Completed' : (connectLoading ? 'Opening…' : 'Enroll')}</button>} />
        </div>

        <div className="mt-8 flex justify-end">
        <button
          disabled={!canGoLive || saving}
          onClick={goLive}
          className={`px-5 py-2.5 rounded-lg text-white bg-[#7E22CE] hover:!bg-[#7E22CE] hover:!text-white disabled:opacity-50 disabled:cursor-not-allowed shadow-sm`}
        >
          {canGoLive ? 'Go live' : 'Complete required steps to go live'}
        </button>
        {pendingRequired.length === 0 && (
          <p className="text-sm text-gray-500 mt-2 text-right w-full">All required steps complete.</p>
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
      {ok ? <div className="text-green-600">✓</div> : null}
      <div>{action}</div>
    </div>
  );
}
