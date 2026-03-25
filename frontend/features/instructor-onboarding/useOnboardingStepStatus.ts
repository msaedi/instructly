import { useCallback, useEffect, useState } from 'react';
import { fetchWithAuth, API_ENDPOINTS, getConnectStatus } from '@/lib/api';
import type { AddressListResponse, ServiceAreasResponse, components } from '@/features/shared/api/types';
import type { OnboardingStepKey, OnboardingStepStatus } from './OnboardingProgressHeader';

export type OnboardingStepStatuses = Record<OnboardingStepKey, OnboardingStepStatus>;

type ProfileData = components['schemas']['InstructorProfileResponse'];
type UserData = components['schemas']['AuthUserWithPermissionsResponse'];
type ConnectStatus = components['schemas']['OnboardingStatusResponse'];
type ServiceAreaItem = components['schemas']['ServiceAreaItem'];
type BackgroundCheckStatusResponse = components['schemas']['BackgroundCheckStatusResponse'];

function profileUsesInstructorLocation(profile: ProfileData | null): boolean {
  if (!Array.isArray(profile?.services)) {
    return false;
  }

  return profile.services.some((service) => {
    const serviceRecord = service as Record<string, unknown>;
    const formatPrices = Array.isArray(serviceRecord['format_prices'])
      ? (serviceRecord['format_prices'] as Array<Record<string, unknown>>)
      : [];

    return formatPrices.some((formatPrice) => formatPrice['format'] === 'instructor_location');
  });
}

function hasPreferredTeachingLocations(profile: ProfileData | null): boolean {
  const teachingLocations = Array.isArray(profile?.preferred_teaching_locations)
    ? profile.preferred_teaching_locations
    : [];

  return teachingLocations.some((location) => {
    if (!location || typeof location !== 'object') {
      return false;
    }

    return typeof location['address'] === 'string' && location['address'].trim().length > 0;
  });
}

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
    serviceAreas: ServiceAreaItem[] | null;
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

      const user: UserData | null = meRes?.ok ? ((await meRes.json()) as UserData) : null;
      const profile: ProfileData | null = profRes?.ok ? ((await profRes.json()) as ProfileData) : null;
      let bgcStatus: string | null = null;
      if (profile?.id) {
        try {
          const bgcRes = await fetchWithAuth(`/api/v1/instructors/${profile.id}/bgc/status`);
          if (bgcRes.ok) {
            const bgcData = (await bgcRes.json()) as BackgroundCheckStatusResponse;
            const statusValue = bgcData?.status;
            if (typeof statusValue === 'string') {
              bgcStatus = statusValue.toLowerCase();
            }
          }
        } catch {
          // Swallow background check status errors; fall back to profile fields if present
        }
      }
      const areasData = areasRes?.ok ? ((await areasRes.json()) as ServiceAreasResponse) : null;
      const serviceAreas = Array.isArray(areasData?.items) ? areasData.items : [];

      // Get postal code from default address or user
      let postalCode = '';
      try {
        if (addrsRes?.ok) {
          const list = (await addrsRes.json()) as AddressListResponse;
          const def = list.items.find((a) => a.is_default) || list.items[0];
          postalCode = String(def?.postal_code || '').trim();
        }
      } catch { /* ignore */ }
      if (!postalCode && user) {
        postalCode = String(user.zip_code || '').trim();
      }

      // Store raw data for consumers that need it
      const profileFields = profile as Record<string, unknown>;
      const bgcRaw = profileFields['bgc_status'] || profileFields['background_check_status'] || '';
      if (!bgcStatus) {
        bgcStatus = typeof bgcRaw === 'string' ? bgcRaw.toLowerCase() : null;
      }
      setRawData({
        profile,
        user,
        serviceAreas,
        connectStatus: connectStatusRes,
        bgcStatus,
      });

      // Evaluate Account Setup (Step 1)
      const hasPic = Boolean(user?.has_profile_picture) || Number.isFinite(user?.profile_picture_version);
      const personalInfoFilled = Boolean(user?.first_name?.trim()) && Boolean(user?.last_name?.trim()) && Boolean(postalCode);
      const bioOk = (String(profile?.bio || '').trim().length) >= 400;
      const hasServiceArea = serviceAreas.length > 0;
      const requiresTeachingLocation = profileUsesInstructorLocation(profile);
      const hasTeachingLocation = hasPreferredTeachingLocations(profile);
      const accountSetupComplete =
        hasPic &&
        personalInfoFilled &&
        bioOk &&
        hasServiceArea &&
        (!requiresTeachingLocation || hasTeachingLocation);

      // Evaluate Skill Selection (Step 2)
      const hasSkills = Array.isArray(profile?.services) && profile.services.length > 0;

      // Evaluate Verify Identity (Step 3)
      // identity_verified_at means Stripe verification is complete
      // This step is complete only after background check clears.
      const identityVerified = Boolean(profile?.identity_verified_at);
      const bgcPassed = bgcStatus === 'passed' || bgcStatus === 'clear' || bgcStatus === 'eligible';
      const verificationStepComplete = identityVerified && bgcPassed;

      // Evaluate Payment Setup (Step 4)
      const paymentSetupComplete = Boolean(connectStatusRes?.onboarding_completed);

      // Step status: 'done' = completed, 'failed' = incomplete/needs attention, 'pending' = in progress
      setStepStatus({
        'account-setup': accountSetupComplete ? 'done' : 'failed',
        'skill-selection': hasSkills ? 'done' : 'failed',
        // Verify identity step requires BOTH identity verification and background check clearance
        'verify-identity': verificationStepComplete ? 'done' : 'failed',
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
  serviceAreas: ServiceAreaItem[] | null;
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
  if (!user?.phone_verified) missing.push('Phone verification');

  // Check bio
  const bioLength = String(profile?.bio || '').trim().length;
  if (bioLength < 400) missing.push('Bio (400+ characters)');

  // Check service areas
  if (!serviceAreas || serviceAreas.length === 0) missing.push('Service areas');
  if (profileUsesInstructorLocation(profile) && !hasPreferredTeachingLocations(profile)) {
    missing.push('Class locations');
  }

  // Check skills
  if (!profile?.services || !Array.isArray(profile.services) || profile.services.length === 0) {
    missing.push('Skills & pricing');
  }

  // Check identity verification — only verified_at counts; a pending session is not enough to go live
  if (!profile?.identity_verified_at) {
    missing.push('ID verification');
  }
  if (profile?.identity_name_mismatch) {
    missing.push('Account name must match government ID');
  }
  if (profile?.bgc_name_mismatch) {
    missing.push('Background check name must match verified identity');
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
