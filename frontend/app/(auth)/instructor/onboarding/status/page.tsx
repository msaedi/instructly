'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { getConnectStatus, fetchWithAuth, API_ENDPOINTS, createStripeIdentitySession } from '@/lib/api';
import { paymentService } from '@/services/api/payments';
import { loadStripe } from '@stripe/stripe-js';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { BGCStep } from '@/components/instructor/BGCStep';
import type { BGCStatus } from '@/lib/api/bgc';
import { ShieldCheck } from 'lucide-react';
import { useGoLiveInstructor } from '@/src/api/services/instructors';
import { logger } from '@/lib/logger';
import { OnboardingProgressHeader } from '@/features/instructor-onboarding/OnboardingProgressHeader';
import { useOnboardingStepStatus, canInstructorGoLive } from '@/features/instructor-onboarding/useOnboardingStepStatus';

export default function OnboardingStatusPage() {
  const router = useRouter();
  useAuth(); // Ensure auth context is available
  const goLiveMutation = useGoLiveInstructor();
  const { stepStatus, rawData } = useOnboardingStepStatus();
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
  // Derive instructorProfileId from hook's rawData to avoid duplicate fetch
  const instructorProfileId = rawData.profile?.id ?? null;
  const [bgcSnapshot, setBgcSnapshot] = useState<{
    status: BGCStatus | null;
    completedAt: string | null;
    consentRecent: boolean;
    consentRecentAt: string | null;
    eta: string | null;
  }>({ status: null, completedAt: null, consentRecent: false, consentRecentAt: null, eta: null });
  const redirectingRef = useRef(false);

  const handleBgcSnapshot = useCallback(
    (
      next: {
        status: BGCStatus | null;
        reportId: string | null;
        completedAt: string | null;
        consentRecent: boolean;
        consentRecentAt: string | null;
        eta: string | null;
      },
    ) => {
      setBgcSnapshot({
        status: next.status,
        completedAt: next.completedAt,
        consentRecent: next.consentRecent,
        consentRecentAt: next.consentRecentAt,
        eta: next.eta ?? null,
      });
    },
    []
  );

  // Sync from hook's rawData to avoid duplicate fetches
  useEffect(() => {
    if (rawData.connectStatus) {
      setConnectStatus(rawData.connectStatus);
    }
    if (rawData.profile) {
      setProfile(rawData.profile as Record<string, unknown>);
    }
    setLoading(false);
  }, [rawData.profile, rawData.connectStatus]);

  // If already live, redirect to dashboard
  useEffect(() => {
    if (profile?.['is_live']) {
      router.replace('/instructor/dashboard');
    }
  }, [profile, router]);

  // Use unified go-live check that includes service areas
  const goLiveCheck = canInstructorGoLive({
    ...rawData,
    connectStatus: connectStatus || rawData.connectStatus,
    bgcStatus: bgcSnapshot.status || rawData.bgcStatus,
  });
  const canGoLive = goLiveCheck.canGoLive;
  const pendingRequired = goLiveCheck.missing;

  const needsStripe = !(connectStatus && connectStatus.onboarding_completed);
  const needsIdentity = !(profile && (profile['identity_verified_at'] || profile['identity_verification_session_id']));
  const needsSkills = !(profile && ((profile['skills_configured']) || (Array.isArray(profile['services']) && profile['services'].length > 0)));
  const needsBGC = bgcSnapshot.status !== 'passed';
  const needsServiceAreas = !rawData.serviceAreas || rawData.serviceAreas.length === 0;

  // User-facing labels for the fun/actionable card in the desired order
  const pendingLabels: string[] = [];
  if (needsServiceAreas) pendingLabels.push('Add service areas');
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
      await goLiveMutation.mutateAsync();
      window.location.href = '/instructor/dashboard';
    } catch (error) {
      // Mutation will handle error state
      logger.error('Failed to go live', error as Error);
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
        window.location.href = `${process.env['NEXT_PUBLIC_API_BASE'] || 'http://localhost:8000'}/api/v1/payments/identity/session`;
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
      {/* Use shared OnboardingProgressHeader - status page is a summary, allow clicking all steps */}
      <OnboardingProgressHeader activeStep="verify-identity" stepStatus={stepStatus} allowClickAll />

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
              {needsServiceAreas && (
                <Link
                  href="/instructor/onboarding/account-setup"
                  className="px-3 py-1.5 rounded-md bg-primary hover:bg-primary text-white shadow-sm text-xs"
                >
                  Add service areas
                </Link>
              )}
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
          {/* 1) Service areas */}
          <Row label="Service areas" ok={!needsServiceAreas} action={<Link href="/instructor/onboarding/account-setup" className="text-[#7E22CE] hover:underline">{needsServiceAreas ? 'Add' : 'Edit'}</Link>} />
          {/* 2) Skills & pricing */}
          <Row label="Skills & pricing" ok={Boolean(profile && ((profile['skills_configured']) || (Array.isArray(profile['services']) && profile['services'].length > 0)))} action={<Link href="/instructor/onboarding/skill-selection?redirect=%2Finstructor%2Fonboarding%2Fstatus" className="text-[#7E22CE] hover:underline">Edit</Link>} />
          {/* 3) ID verification */}
          <Row label="ID verification" ok={Boolean(profile?.['identity_verified_at'])} action={profile?.['identity_verified_at'] ? <span className="text-gray-400">Completed</span> : <button onClick={startIdentity} className="text-[#7E22CE] hover:underline">Start</button>} />
          {/* 4) Background check */}
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
