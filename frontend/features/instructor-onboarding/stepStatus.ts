import type { InstructorProfile } from '@/types/instructor';
import type { OnboardingStatusResponse } from '@/services/api/payments';
import { STEP_KEYS, createEmptyStatusMap } from '@/lib/onboardingSteps';
import type { OnboardingStatusMap, StepKey } from '@/lib/onboardingSteps';

export { STEP_KEYS, createEmptyStatusMap } from '@/lib/onboardingSteps';
export type { StepKey, StepState, OnboardingStatusMap } from '@/lib/onboardingSteps';

export type VisitedMap = Partial<Record<StepKey, boolean>>;

type DeriveStatusArgs = {
  data?: {
    profile?: Partial<InstructorProfile> | null;
    user?: Record<string, unknown> | null;
    serviceAreas?: { items?: unknown[] } | null;
    addresses?: { items?: Array<Record<string, unknown>> } | null;
    stripe?: OnboardingStatusResponse | null;
  };
  visited?: VisitedMap;
};

const VISITED_STORAGE_PREFIX = 'onboarding.visited.v2';

const getLocalStorage = () => {
  if (typeof window === 'undefined') return null;
  const storageHost = window as unknown as Record<string, Storage | undefined>;
  return storageHost['localStorage'] ?? null;
};

export const getInstructorPostal = (
  user: Record<string, unknown> | null | undefined,
  profile: Partial<InstructorProfile> | null | undefined,
  addresses?: { items?: Array<Record<string, unknown>> } | null
) => {
  const profileRecord = profile as Record<string, unknown> | null | undefined;
  const profileUserRecord = profile?.user ? (profile.user as Record<string, unknown>) : null;
  const fromProfile = String(profileRecord?.['postal_code'] ?? '').trim();
  const fromProfileUser = String(profileUserRecord?.['postal_code'] ?? '').trim();
  const fromProfileZip = String(profileUserRecord?.['zip_code'] ?? '').trim();
  const fromUserPostal = String(user?.['postal_code'] ?? '').trim();
  const fromUserZip = String(user?.['zip_code'] ?? '').trim();

  const direct = [fromProfile, fromProfileUser, fromProfileZip, fromUserPostal, fromUserZip].find((value) => value.length > 0);
  if (direct) return direct;

  const addressList = Array.isArray(addresses?.items) ? (addresses?.items as Array<Record<string, unknown>>) : [];
  if (addressList.length === 0) return '';
  const defaultAddress =
    addressList.find((addr) => Boolean(addr['is_default'])) ||
    addressList[0];
  return String(defaultAddress?.['postal_code'] ?? '').trim();
};

export const hasProfilePicture = (
  user: Record<string, unknown> | null | undefined,
  profile: Partial<InstructorProfile> | null | undefined
) => {
  if (!user && !profile) return false;
  const candidates = [
    user?.['has_profile_picture'],
    user?.['profile_picture_version'],
    profile?.has_profile_picture,
    profile?.profile_picture_version,
    profile?.user?.has_profile_picture,
    profile?.user?.profile_picture_version,
    (profile as Record<string, unknown> | undefined)?.['profile_photo_url'],
    (profile as Record<string, unknown> | undefined)?.['profile_photo'],
    (profile as Record<string, unknown> | undefined)?.['profilePhotoUrl'],
    (profile as Record<string, unknown> | undefined)?.['profile_photo'],
    (profile as Record<string, unknown> | undefined)?.['avatar_url'],
    (profile as Record<string, unknown> | undefined)?.['photo_url'],
    typeof (profile as Record<string, unknown> | undefined)?.['photo'] === 'object'
      ? ((profile as Record<string, { url?: string }> | undefined)?.['photo']?.url ?? undefined)
      : undefined,
  ];
  return candidates.some((value) => {
    if (typeof value === 'boolean') return value;
    if (typeof value === 'number') return Number.isFinite(value);
    if (typeof value === 'string') return value.trim().length > 0;
    return false;
  });
};

export const hasServiceAreasConfigured = (serviceAreas?: { items?: unknown[] } | null) =>
  Array.isArray(serviceAreas?.items) && serviceAreas.items.length > 0;

export const hasProfileServiceAreas = (profile?: Partial<InstructorProfile> | null) =>
  Boolean(
    (Array.isArray(profile?.service_area_boroughs) && profile!.service_area_boroughs!.length > 0) ||
      (Array.isArray(profile?.service_area_neighborhoods) && profile!.service_area_neighborhoods!.length > 0) ||
      (Array.isArray((profile as Record<string, unknown> | undefined)?.['service_areas']) &&
        ((profile as Record<string, unknown> | undefined)?.['service_areas'] as unknown[])?.length > 0)
  );

export const hasSkillsConfigured = (profile?: Partial<InstructorProfile> | null) =>
  Boolean(
    profile &&
      (profile['skills_configured'] === true ||
        (Array.isArray(profile['services']) && profile['services'].length > 0))
  );

export const hasCompletedIdentity = (profile?: Partial<InstructorProfile> | null) =>
  Boolean(profile?.['identity_verified_at']);

export const hasCompletedPayments = (stripe?: OnboardingStatusResponse | null) =>
  Boolean(
    stripe &&
      stripe.onboarding_completed &&
      stripe.charges_enabled &&
      stripe.payouts_enabled
  );

type AccountSetupParams = {
  profile?: Partial<InstructorProfile> | null;
  user?: Record<string, unknown> | null;
  serviceAreas?: { items?: unknown[] } | null;
  addresses?: { items?: Array<Record<string, unknown>> } | null;
};

export function isAccountSetupComplete(params: AccountSetupParams = {}): boolean {
  const { profile, user, serviceAreas, addresses } = params;
  const firstName = String(user?.['first_name'] ?? profile?.user?.first_name ?? '').trim();
  const lastName = String(
    user?.['last_name'] ??
      (profile?.user && (profile.user as Record<string, unknown>)['last_name']) ??
      ''
  ).trim();
  const postal = getInstructorPostal(user, profile, addresses);
  const postalOk = /^\d{5}$/.test(postal);
  const bioSource = String(
    profile?.bio ?? (profile as Record<string, unknown> | undefined)?.['about'] ?? ''
  ).trim();
  const bioOk = bioSource.length > 0;
  const yearsExperience =
    typeof profile?.years_experience === 'number'
      ? profile.years_experience
      : Number((profile as Record<string, unknown> | undefined)?.['yearsExperience']);
  const yearsExperienceOk = Number.isFinite(yearsExperience) && yearsExperience! > 0;
  const hasPic = hasProfilePicture(user, profile);
  const serviceAreasOk = hasProfileServiceAreas(profile) || hasServiceAreasConfigured(serviceAreas);

  return Boolean(
    firstName &&
      lastName &&
      postalOk &&
      bioOk &&
      yearsExperienceOk &&
      hasPic &&
      serviceAreasOk
  );
}

export function deriveStatusMap(args: DeriveStatusArgs): OnboardingStatusMap {
  const data = args.data ?? {};
  const visitedMap = args.visited ?? {};

  const accountComplete = isAccountSetupComplete({
    profile: data.profile ?? null,
    user: data.user ?? null,
    serviceAreas: data.serviceAreas ?? null,
    addresses: data.addresses ?? null,
  });
  const skillsComplete = hasSkillsConfigured(data.profile);
  const identityComplete = hasCompletedIdentity(data.profile);
  const paymentComplete = hasCompletedPayments(data.stripe);

  const completionMap: Record<StepKey, boolean> = {
    'account-setup': accountComplete,
    'skill-selection': skillsComplete,
    'verify-identity': identityComplete,
    'payment-setup': paymentComplete,
  };

  return STEP_KEYS.reduce((acc, key) => {
    const completed = completionMap[key];
    const visited = completed || Boolean(visitedMap[key]);
    acc[key] = { completed, visited };
    return acc;
  }, createEmptyStatusMap());
}

export const getVisitedStorageKey = (instructorId?: string | null) =>
  instructorId ? `${VISITED_STORAGE_PREFIX}.${instructorId}` : '';

export const readVisitedSteps = (instructorId?: string | null): VisitedMap => {
  const storage = getLocalStorage();
  const key = getVisitedStorageKey(instructorId);
  if (!key || !storage) return {};
  try {
    const raw = storage.getItem(key);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as VisitedMap;
    if (typeof parsed !== 'object' || parsed === null) return {};
    return parsed;
  } catch {
    return {};
  }
};

export const persistVisitedSteps = (instructorId: string | null | undefined, state: VisitedMap) => {
  const storage = getLocalStorage();
  const key = getVisitedStorageKey(instructorId);
  if (!key || !storage) return;
  try {
    storage.setItem(key, JSON.stringify(state));
  } catch {
    // Ignore storage failures (private mode, etc.)
  }
};
