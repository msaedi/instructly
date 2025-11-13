'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchWithAuth, API_ENDPOINTS, createStripeIdentitySession } from '@/lib/api';
import { paymentService } from '@/services/api/payments';
import { loadStripe } from '@stripe/stripe-js';
import type { BGCStatus } from '@/lib/api/bgc';
import { bgcStatus } from '@/lib/api/bgc';
import { OnboardingProgressHeader } from '@/features/instructor-onboarding/OnboardingProgressHeader';
import { useOnboardingProgress } from '@/features/instructor-onboarding/useOnboardingProgress';
import { STEP_KEYS, type StepKey, type StepState } from '@/features/instructor-onboarding/stepStatus';
import { Button } from '@/components/ui/button';
import { useOnboardingInlineProfileMenu } from '@/features/instructor-onboarding/useInlineProfileMenu';

type PillState = 'not-started' | 'in-progress' | 'completed';

export default function OnboardingStatusPage() {
  const router = useRouter();
  const preferInlineProfileMenu = useOnboardingInlineProfileMenu();
  const { statusMap, data, refresh, loading } = useOnboardingProgress({ activeStep: 'status' });
  const profile = data.profile;
  const accountState = statusMap['account-setup'];
  const skillsState = statusMap['skill-selection'];
  const verifyState = statusMap['verify-identity'];
  const paymentState = statusMap['payment-setup'];
  const [saving, setSaving] = useState(false);
  const [connectLoading, setConnectLoading] = useState(false);
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

  const activeStep: StepKey = useMemo(() => {
    if (loading) return 'account-setup';
    const next = STEP_KEYS.find((step) => !statusMap[step]?.completed);
    return next ?? 'payment-setup';
  }, [loading, statusMap]);

  const instructorProfileId = useMemo(() => {
    const idValue = profile?.['id'];
    if (typeof idValue === 'string') return idValue;
    if (typeof idValue === 'number') return String(idValue);
    return null;
  }, [profile]);

  // If already live, redirect to dashboard
  useEffect(() => {
    if (profile?.['is_live']) {
      router.replace('/instructor/dashboard');
    }
  }, [profile, router]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('stripe_onboarding_return') === 'true') {
      refresh();
    }
  }, [refresh]);

  useEffect(() => {
    if (!instructorProfileId) return;
    let alive = true;
    const loadBgcStatus = async () => {
      try {
        const res = await bgcStatus(instructorProfileId);
        if (!alive) return;
        handleBgcSnapshot({
          status: res.status ?? null,
          reportId: res.report_id ?? null,
          completedAt: res.completed_at ?? null,
          consentRecent: Boolean(res.consent_recent),
          consentRecentAt: res.consent_recent_at ?? null,
        });
      } catch {
        if (!alive) return;
        handleBgcSnapshot({
          status: null,
          reportId: null,
          completedAt: null,
          consentRecent: false,
          consentRecentAt: null,
        });
      }
    };
    void loadBgcStatus();
    return () => {
      alive = false;
    };
  }, [instructorProfileId, handleBgcSnapshot]);

  if (loading) {
    return (
      <div className="min-h-screen">
        <OnboardingProgressHeader activeStep={activeStep} statusMap={statusMap} loading preferInlineProfileMenu={preferInlineProfileMenu} />
        <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
          <div className="bg-white rounded-lg p-6 mb-6 border border-gray-200 animate-pulse h-36" />
          <div className="bg-white rounded-lg border border-gray-200 p-6 animate-pulse h-48" />
        </div>
      </div>
    );
  }

  const needsSkills = !skillsState?.completed;
  const needsIdentity = !verifyState?.completed;
  const needsStripe = !paymentState?.completed;
  const needsBGC = bgcSnapshot.status !== 'passed';

  const canGoLive = Boolean(!needsSkills && !needsIdentity && !needsBGC && !needsStripe);

  // Compute pending in canonical step order for display
  const pendingRequired: string[] = [];
  if (needsSkills) pendingRequired.push('Skills & pricing');
  if (needsIdentity) pendingRequired.push('ID verification');
  if (needsBGC) pendingRequired.push('Background check');
  if (needsStripe) pendingRequired.push('Stripe Connect');

  // User-facing labels for the fun/actionable card in the desired order
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
          refresh();
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
        refresh();
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

  const handleAccountSetupNav = () => {
    router.push('/instructor/onboarding/account-setup');
  };
  const handleSkillsNav = () => {
    router.push('/instructor/onboarding/skill-selection?redirect=%2Finstructor%2Fonboarding%2Fstatus');
  };
  const handleBackgroundNav = () => {
    router.push('/instructor/onboarding/verification?from=status#bgc-step-card');
  };

  return (
    <div className="min-h-screen">
      {/* Header - matching other pages */}
      <OnboardingProgressHeader
        activeStep={activeStep}
        statusMap={statusMap}
        loading={loading}
        preferInlineProfileMenu={preferInlineProfileMenu}
      />

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        {/* Page Header */}
        <div className="bg-white rounded-lg p-6 mb-6 border border-gray-200">
          <h1 className="text-3xl font-bold text-gray-600 mb-2">Onboarding Status</h1>
          <p className="text-gray-600">Finish these steps to go live.</p>
        </div>

        {pendingRequired.length > 0 && (
          <div className="rounded-lg px-5 sm:px-7 py-4 mb-6 border border-purple-200 bg-purple-50 text-purple-800 blink-card text-center">
            <p className="text-base sm:text-lg font-bold leading-relaxed">
              You&apos;re close! Finish the steps below to go live.
            </p>
          </div>
        )}

        <div className="mt-6 space-y-4">
          <StatusCardRow
            data-testid="status-card-account-setup"
            title="Account setup"
            description="Complete your profile details so students can learn about you."
            pillState={derivePillState(accountState)}
            action={
              <StatusActionButton
                label={accountState?.visited ? 'Edit' : 'Start'}
                ariaLabel={`${accountState?.visited ? 'Edit' : 'Start'} account setup`}
                onClick={handleAccountSetupNav}
                variant={accountState?.visited ? 'outline' : 'default'}
              />
            }
          />

          <StatusCardRow
            title="Skills & pricing"
            description="Add at least one skill with a rate to unlock bookings."
            pillState={derivePillState(skillsState)}
            action={
              <StatusActionButton
                label={skillsState?.visited ? 'Edit' : 'Start'}
                ariaLabel={`${skillsState?.visited ? 'Edit' : 'Start'} skills & pricing`}
                onClick={handleSkillsNav}
                variant={skillsState?.visited ? 'outline' : 'default'}
              />
            }
          />

          <StatusCardRow
            title="ID verification"
            description="Verify your identity through Stripe to build trust with students."
            pillState={derivePillState(verifyState)}
            action={
              <StatusActionButton
                label="Start"
                ariaLabel="Start ID verification"
                onClick={startIdentity}
                disabled={!needsIdentity}
                variant={needsIdentity ? 'default' : 'outline'}
              />
            }
          />

          <StatusCardRow
            title="Background check"
            description="Complete your background check to unlock your verified badge."
            pillState={deriveBackgroundPillState(bgcSnapshot.status)}
            action={
              <StatusActionButton
                label="Start"
                ariaLabel="Start background check"
                onClick={handleBackgroundNav}
                disabled={bgcSnapshot.status === 'passed'}
                variant={bgcSnapshot.status === 'passed' ? 'outline' : 'default'}
              />
            }
          />

          <StatusCardRow
            title="Stripe Connect"
            description="Connect Stripe to receive payouts for your lessons."
            pillState={derivePillState(paymentState)}
            action={
              <StatusActionButton
                label="Enroll"
                ariaLabel="Enroll in Stripe Connect"
                onClick={enrollStripeConnect}
                disabled={!needsStripe || connectLoading}
                variant={!needsStripe ? 'outline' : 'default'}
              />
            }
          />
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

function derivePillState(state?: StepState): PillState {
  if (state?.completed) return 'completed';
  if (state?.visited) return 'in-progress';
  return 'not-started';
}

function deriveBackgroundPillState(status: BGCStatus | null): PillState {
  if (status === 'passed') return 'completed';
  if (status) return 'in-progress';
  return 'not-started';
}

type StatusCardRowProps = {
  title: string;
  description?: string;
  pillState: PillState;
  action: React.ReactNode;
  'data-testid'?: string;
};

function StatusCardRow({ title, description, pillState, action, ...rest }: StatusCardRowProps) {
  return (
    <div
      className="flex flex-col gap-3 rounded-lg border border-gray-100 bg-white px-4 py-3 shadow-sm sm:flex-row sm:items-center sm:justify-between"
      {...rest}
    >
      <div>
        <p className="text-base font-semibold text-gray-900">{title}</p>
        {description && <p className="text-sm text-gray-500">{description}</p>}
      </div>
      <div className="flex items-center gap-3 sm:min-w-[240px] sm:justify-end">
        <StatusPill state={pillState} />
        {action}
      </div>
    </div>
  );
}

function StatusPill({ state }: { state: PillState }) {
  const map: Record<PillState, { label: string; className: string }> = {
    completed: { label: 'Completed', className: 'bg-emerald-50 text-emerald-700 border border-emerald-200' },
    'in-progress': { label: 'In progress', className: 'bg-purple-50 text-purple-700 border border-purple-200' },
    'not-started': { label: 'Not started', className: 'bg-gray-100 text-gray-600 border border-gray-200' },
  };
  return (
    <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${map[state].className}`}>
      {map[state].label}
    </span>
  );
}

type StatusActionButtonProps = {
  label: string;
  ariaLabel: string;
  onClick?: () => void;
  disabled?: boolean;
  variant?: 'default' | 'outline';
};

function StatusActionButton({ label, ariaLabel, onClick, disabled, variant = 'default' }: StatusActionButtonProps) {
  return (
    <Button
      size="sm"
      variant={variant}
      onClick={onClick}
      aria-label={ariaLabel}
      disabled={disabled}
      className="min-w-[104px] justify-center"
    >
      {label}
    </Button>
  );
}
