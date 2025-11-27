import { useCallback, useEffect, useState } from 'react';
import { fetchWithAuth, API_ENDPOINTS, getConnectStatus } from '@/lib/api';
import type { OnboardingStepKey, OnboardingStepStatus } from './OnboardingProgressHeader';

export type OnboardingStepStatuses = Record<OnboardingStepKey, OnboardingStepStatus>;

type ProfileData = {
  id?: string;
  bio?: string;
  services?: unknown[];
  identity_verified_at?: string;
  identity_verification_session_id?: string;
  bgc_status?: string;
  background_check_status?: string;
  is_live?: boolean;
};

type UserData = {
  first_name?: string;
  last_name?: string;
  zip_code?: string;
  postal_code?: string;
  has_profile_picture?: boolean;
  profile_picture_version?: number;
};

type ConnectStatus = {
  has_account: boolean;
  onboarding_completed: boolean;
  charges_enabled: boolean;
  payouts_enabled: boolean;
  details_submitted: boolean;
};

/**
 * Unified hook to evaluate onboarding step completion status.
 * Used across all onboarding pages for consistent status display.
 * @param options.skip - If true, skip all API calls (useful when status is passed as prop)
 */
export function useOnboardingStepStatus(options?: { skip?: boolean }) {
  const skip = options?.skip ?? false;
  const [loading, setLoading] = useState(!skip);
  const [stepStatus, setStepStatus] = useState<OnboardingStepStatuses>({
    'account-setup': 'pending',
    'skill-selection': 'pending',
    'verify-identity': 'pending',
    'payment-setup': 'pending',
  });
  const [rawData, setRawData] = useState<{
    profile: ProfileData | null;
    user: UserData | null;
    serviceAreas: unknown[] | null;
    connectStatus: ConnectStatus | null;
    bgcStatus: string | null;
  }>({
    profile: null,
    user: null,
    serviceAreas: null,
    connectStatus: null,
    bgcStatus: null,
  });

  const evaluate = useCallback(async () => {
    try {
      setLoading(true);

      // Fetch all data in parallel
      const [meRes, profRes, areasRes, addrsRes, connectStatusRes] = await Promise.all([
        fetchWithAuth(API_ENDPOINTS.ME).catch(() => null),
        fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE).catch(() => null),
        fetchWithAuth('/api/v1/addresses/service-areas/me').catch(() => null),
        fetchWithAuth('/api/v1/addresses/me').catch(() => null),
        getConnectStatus().catch(() => null),
      ]);

      const user: UserData | null = meRes?.ok ? await meRes.json() : null;
      const profile: ProfileData | null = profRes?.ok ? await profRes.json() : null;
      const areasData = areasRes?.ok ? await areasRes.json() : { items: [] };
      const serviceAreas = Array.isArray(areasData?.items) ? areasData.items : [];

      // Get postal code from default address or user
      let postalCode = '';
      try {
        if (addrsRes?.ok) {
          const list = await addrsRes.json();
          const def = (list.items || []).find((a: unknown) => (a as Record<string, unknown>)['is_default']) || (list.items || [])[0];
          postalCode = String((def as Record<string, unknown>)?.['postal_code'] || '').trim();
        }
      } catch { /* ignore */ }
      if (!postalCode && user) {
        postalCode = String(user.zip_code || user.postal_code || '').trim();
      }

      // Store raw data for consumers that need it
      const bgcRaw = profile?.bgc_status || profile?.background_check_status || '';
      setRawData({
        profile,
        user,
        serviceAreas,
        connectStatus: connectStatusRes,
        bgcStatus: typeof bgcRaw === 'string' ? bgcRaw.toLowerCase() : null,
      });

      // Evaluate Account Setup (Step 1)
      const hasPic = Boolean(user?.has_profile_picture) || Number.isFinite(user?.profile_picture_version);
      const personalInfoFilled = Boolean(user?.first_name?.trim()) && Boolean(user?.last_name?.trim()) && Boolean(postalCode);
      const bioOk = (String(profile?.bio || '').trim().length) >= 400;
      const hasServiceArea = serviceAreas.length > 0;
      const accountSetupComplete = hasPic && personalInfoFilled && bioOk && hasServiceArea;

      // Evaluate Skill Selection (Step 2)
      const hasSkills = Array.isArray(profile?.services) && profile.services.length > 0;

      // Evaluate Verify Identity (Step 3)
      // identity_verified_at means Stripe verification is complete
      // Note: BGC is tracked separately on the status page, so this step only checks identity
      const identityVerified = Boolean(profile?.identity_verified_at);

      // Evaluate Payment Setup (Step 4)
      const paymentSetupComplete = Boolean(connectStatusRes?.onboarding_completed);

      // Step status: 'done' = completed, 'failed' = incomplete/needs attention, 'pending' = in progress
      setStepStatus({
        'account-setup': accountSetupComplete ? 'done' : 'failed',
        'skill-selection': hasSkills ? 'done' : 'failed',
        // Verify identity step tracks Stripe identity verification
        // BGC is tracked separately on the status page
        'verify-identity': identityVerified ? 'done' : 'failed',
        'payment-setup': paymentSetupComplete ? 'done' : 'failed',
      });
    } catch {
      // Keep pending status on error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!skip) {
      void evaluate();
    }
  }, [evaluate, skip]);

  return {
    loading,
    stepStatus,
    rawData,
    refresh: evaluate,
  };
}

/**
 * Check if instructor can go live based on all requirements.
 */
export function canInstructorGoLive(rawData: {
  profile: ProfileData | null;
  user: UserData | null;
  serviceAreas: unknown[] | null;
  connectStatus: ConnectStatus | null;
  bgcStatus: string | null;
}): { canGoLive: boolean; missing: string[] } {
  const missing: string[] = [];
  const { profile, user, serviceAreas, connectStatus, bgcStatus } = rawData;

  // Check profile picture
  const hasPic = Boolean(user?.has_profile_picture) || Number.isFinite(user?.profile_picture_version);
  if (!hasPic) missing.push('Profile picture');

  // Check personal info
  if (!user?.first_name?.trim()) missing.push('First name');
  if (!user?.last_name?.trim()) missing.push('Last name');

  // Check bio
  const bioLength = String(profile?.bio || '').trim().length;
  if (bioLength < 400) missing.push('Bio (400+ characters)');

  // Check service areas
  if (!serviceAreas || serviceAreas.length === 0) missing.push('Service areas');

  // Check skills
  if (!profile?.services || !Array.isArray(profile.services) || profile.services.length === 0) {
    missing.push('Skills & pricing');
  }

  // Check identity verification
  if (!profile?.identity_verified_at && !profile?.identity_verification_session_id) {
    missing.push('ID verification');
  }

  // Check background check
  if (bgcStatus !== 'passed') missing.push('Background check');

  // Check Stripe Connect
  if (!connectStatus?.onboarding_completed) missing.push('Stripe Connect');

  return {
    canGoLive: missing.length === 0,
    missing,
  };
}
