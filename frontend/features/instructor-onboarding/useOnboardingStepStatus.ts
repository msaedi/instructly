import { useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchWithAuth } from '@/lib/api';
import { useInstructorProfileMe } from '@/hooks/queries/useInstructorProfileMe';
import { useInstructorServiceAreas } from '@/hooks/queries/useInstructorServiceAreas';
import { useStripeConnectStatus } from '@/hooks/queries/useStripeConnectStatus';
import { useUserAddresses } from '@/hooks/queries/useUserAddresses';
import type { AddressListResponse, components } from '@/features/shared/api/types';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';
import { useSession } from '@/src/api/hooks/useSession';
import { isAccountSetupComplete } from '@/lib/accountSetupCompletion';
import {
  hasPreferredTeachingLocations,
  servicesUseInstructorLocation,
} from '@/lib/teachingLocations';
import type { OnboardingStepKey, OnboardingStepStatus } from './OnboardingProgressHeader';

export type OnboardingStepStatuses = Record<OnboardingStepKey, OnboardingStepStatus>;

type ProfileData = components['schemas']['InstructorProfileResponse'];
type UserData = components['schemas']['AuthUserWithPermissionsResponse'];
type ConnectStatus = components['schemas']['OnboardingStatusResponse'];
type ServiceAreaItem = components['schemas']['ServiceAreaDisplayItem'];
type BackgroundCheckStatusResponse = components['schemas']['BackgroundCheckStatusResponse'];

const DEFAULT_STEP_STATUS: OnboardingStepStatuses = {
  'account-setup': 'pending',
  'skill-selection': 'pending',
  'verify-identity': 'pending',
  'payment-setup': 'pending',
};

const DEFAULT_RAW_DATA = {
  profile: null,
  user: null,
  serviceAreas: null,
  connectStatus: null,
  bgcStatus: null,
} satisfies {
  profile: ProfileData | null;
  user: UserData | null;
  serviceAreas: ServiceAreaItem[] | null;
  connectStatus: ConnectStatus | null;
  bgcStatus: string | null;
};

function getProfileBgcFallback(profile: ProfileData | null): string | null {
  if (!profile || typeof profile !== 'object') {
    return null;
  }

  const profileRecord = profile as Record<string, unknown>;
  const bgcRaw =
    profileRecord['bgc_status'] || profileRecord['background_check_status'] || '';
  return typeof bgcRaw === 'string' ? bgcRaw.toLowerCase() : null;
}

/**
 * Unified hook to evaluate onboarding step completion status.
 * Used across all onboarding pages for consistent status display.
 * @param options.skip - If true, skip all API calls (useful when status is passed as prop)
 */
export function useOnboardingStepStatus(options?: { skip?: boolean }) {
  const skip = options?.skip ?? false;
  const enabled = !skip;

  const userQuery = useSession(enabled);
  const profileQuery = useInstructorProfileMe(enabled);
  const addressesQuery = useUserAddresses(enabled);
  const serviceAreasQuery = useInstructorServiceAreas(enabled);
  const connectStatusQuery = useStripeConnectStatus(enabled);

  const profile = (profileQuery.data as ProfileData | undefined) ?? null;
  const profileId = profile?.id ?? null;

  const bgcQuery = useQuery<string | null>({
    queryKey: ['instructors', 'bgc-status', profileId],
    queryFn: async () => {
      const bgcRes = await fetchWithAuth(`/api/v1/instructors/${profileId}/bgc/status`);
      if (!bgcRes.ok) {
        throw new Error('Failed to fetch background check status');
      }

      const bgcData = (await bgcRes.json()) as BackgroundCheckStatusResponse;
      return typeof bgcData?.status === 'string' ? bgcData.status.toLowerCase() : null;
    },
    enabled: enabled && Boolean(profileId),
    staleTime: CACHE_TIMES.FREQUENT,
    refetchOnWindowFocus: false,
    retry: false,
  });

  const loading = enabled && (
    userQuery.isLoading ||
    profileQuery.isLoading ||
    addressesQuery.isLoading ||
    serviceAreasQuery.isLoading ||
    connectStatusQuery.isLoading ||
    (Boolean(profileId) && bgcQuery.isLoading)
  );

  const user = (userQuery.data as UserData | undefined) ?? null;
  const serviceAreas = useMemo<ServiceAreaItem[] | null>(() => {
    if (Array.isArray(serviceAreasQuery.data?.items)) {
      return serviceAreasQuery.data.items;
    }

    if (serviceAreasQuery.isError) {
      return null;
    }

    if (serviceAreasQuery.isFetched) {
      return [];
    }

    return null;
  }, [serviceAreasQuery.data, serviceAreasQuery.isError, serviceAreasQuery.isFetched]);

  const connectStatus =
    (connectStatusQuery.data as unknown as ConnectStatus | undefined) ?? null;

  const bgcStatus = useMemo(() => {
    if (typeof bgcQuery.data === 'string') {
      return bgcQuery.data;
    }

    return getProfileBgcFallback(profile);
  }, [bgcQuery.data, profile]);

  const rawData = useMemo(() => {
    if (!enabled) {
      return DEFAULT_RAW_DATA;
    }

    return {
      profile,
      user,
      serviceAreas,
      connectStatus,
      bgcStatus,
    };
  }, [bgcStatus, connectStatus, enabled, profile, serviceAreas, user]);

  const stepStatus = useMemo<OnboardingStepStatuses>(() => {
    if (!enabled || loading) {
      return DEFAULT_STEP_STATUS;
    }

    const noCoreDataLoaded =
      !rawData.profile &&
      !rawData.user &&
      rawData.serviceAreas === null &&
      !rawData.connectStatus;

    if (noCoreDataLoaded) {
      return DEFAULT_STEP_STATUS;
    }

    const addresses = addressesQuery.data as AddressListResponse | undefined;
    const defaultAddress = addresses?.items.find((address) => address.is_default) ?? addresses?.items[0];
    const postalCode = String(defaultAddress?.postal_code || rawData.user?.zip_code || '').trim();

    const hasPic = Boolean(rawData.user?.has_profile_picture) || Number.isFinite(rawData.user?.profile_picture_version);
    const hasServiceArea = Boolean(rawData.serviceAreas && rawData.serviceAreas.length > 0);
    const requiresTeachingLocation = servicesUseInstructorLocation(rawData.profile?.services);
    const hasTeachingLocation = hasPreferredTeachingLocations(
      rawData.profile?.preferred_teaching_locations
    );
    const accountSetupComplete = isAccountSetupComplete({
      hasProfilePicture: hasPic,
      firstName: rawData.user?.first_name,
      lastName: rawData.user?.last_name,
      postalCode,
      phoneVerified: Boolean(rawData.user?.phone_verified),
      bio: rawData.profile?.bio,
      hasServiceArea,
      requiresTeachingLocation,
      hasTeachingLocation,
    });

    const hasSkills =
      Array.isArray(rawData.profile?.services) && rawData.profile.services.length > 0;

    const identityVerified = Boolean(rawData.profile?.identity_verified_at);
    const bgcPassed =
      rawData.bgcStatus === 'passed' ||
      rawData.bgcStatus === 'clear' ||
      rawData.bgcStatus === 'eligible';
    const verificationStepComplete = identityVerified && bgcPassed;

    const paymentSetupComplete = Boolean(rawData.connectStatus?.onboarding_completed);

    return {
      'account-setup': accountSetupComplete ? 'done' : 'failed',
      'skill-selection': hasSkills ? 'done' : 'failed',
      'verify-identity': verificationStepComplete ? 'done' : 'failed',
      'payment-setup': paymentSetupComplete ? 'done' : 'failed',
    };
  }, [addressesQuery.data, enabled, loading, rawData]);

  const refresh = useCallback(async () => {
    if (!enabled) {
      return;
    }

    await Promise.all([
      userQuery.refetch(),
      profileQuery.refetch(),
      addressesQuery.refetch(),
      serviceAreasQuery.refetch(),
      connectStatusQuery.refetch(),
      profileId ? bgcQuery.refetch() : Promise.resolve(null),
    ]);
  }, [
    addressesQuery,
    bgcQuery,
    connectStatusQuery,
    enabled,
    profileId,
    profileQuery,
    serviceAreasQuery,
    userQuery,
  ]);

  return {
    loading,
    stepStatus,
    rawData,
    refresh,
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

  const hasPic = Boolean(user?.has_profile_picture) || Number.isFinite(user?.profile_picture_version);
  if (!hasPic) missing.push('Profile picture');

  if (!user?.first_name?.trim()) missing.push('First name');
  if (!user?.last_name?.trim()) missing.push('Last name');
  if (!user?.phone_verified) missing.push('Phone verification');

  const bioLength = String(profile?.bio || '').trim().length;
  if (bioLength < 400) missing.push('Bio (400+ characters)');

  if (!serviceAreas || serviceAreas.length === 0) missing.push('Service areas');
  if (servicesUseInstructorLocation(profile?.services) && !hasPreferredTeachingLocations(profile?.preferred_teaching_locations)) {
    missing.push('Class locations');
  }

  if (!profile?.services || !Array.isArray(profile.services) || profile.services.length === 0) {
    missing.push('Skills & pricing');
  }

  if (!profile?.identity_verified_at) {
    missing.push('ID verification');
  }
  if (profile?.identity_name_mismatch) {
    missing.push('Account name must match government ID');
  }
  if (profile?.bgc_name_mismatch) {
    missing.push('Background check name must match verified identity');
  }

  if (bgcStatus !== 'passed') missing.push('Background check');

  if (!connectStatus?.onboarding_completed) missing.push('Stripe Connect');

  return {
    canGoLive: missing.length === 0,
    missing,
  };
}
