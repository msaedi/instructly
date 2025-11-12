import { logger } from '@/frontend/lib/logger';
import type { InstructorProfile } from '@/types/instructor';

export type ProfileWriteSource =
  | 'useOnboardingProgress:GET'
  | 'InstructorProfileForm:GET'
  | 'InstructorProfileForm:PATCH'
  | 'SkillSelection:GET'
  | 'Verification:GET'
  | 'PaymentSetup:GET'
  | 'ProgressHeader:GET'
  | 'Other';

let cachedProfile: Partial<InstructorProfile> | null = null;

const toRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' ? (value as Record<string, unknown>) : null;

const firstNonEmptyString = (...values: Array<unknown>): string | null => {
  for (const value of values) {
    if (typeof value === 'string') {
      const trimmed = value.trim();
      if (trimmed.length > 0) return trimmed;
    }
  }
  return null;
};

const firstFiniteNumber = (...values: Array<unknown>): number | null => {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.trim().length > 0) {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) return parsed;
    }
  }
  return null;
};

export const normalizeInstructorProfile = (raw: unknown): Partial<InstructorProfile> | null => {
  const record = toRecord(raw);
  if (!record) return null;

  const normalized: Partial<InstructorProfile> = { ...(record as Partial<InstructorProfile>) };

  const bio = firstNonEmptyString(
    record['bio'],
    record['about'],
    record['profile_bio'],
    record['profileBio']
  );
  if (bio) {
    normalized.bio = bio.trim();
  } else {
    delete normalized.bio;
  }

  const years = firstFiniteNumber(
    record['years_experience'],
    record['yearsExperience'],
    record['experience_years']
  );
  if (years !== null) {
    normalized.years_experience = years;
  } else {
    delete normalized.years_experience;
  }

  const topLevelFirst = firstNonEmptyString(record['first_name']);
  const topLevelLast = firstNonEmptyString(record['last_name'], record['last_initial']);
  const userRecord = toRecord(record['user']) ?? {};
  const normalizedUser: Record<string, unknown> = { ...userRecord };

  const resolvedFirst =
    firstNonEmptyString(userRecord['first_name'], topLevelFirst) ?? '';
  normalizedUser['first_name'] = resolvedFirst.trim();

  const resolvedLast = firstNonEmptyString(
    userRecord['last_name'],
    topLevelLast,
    userRecord['last_initial']
  );
  if (resolvedLast) {
    normalizedUser['last_name'] = resolvedLast.trim();
    if (!firstNonEmptyString(normalizedUser['last_initial'])) {
      normalizedUser['last_initial'] = resolvedLast.charAt(0).toUpperCase();
    }
  }

  if (Object.keys(normalizedUser).length > 0) {
    normalized.user = normalizedUser as InstructorProfile['user'];
  }

  return normalized;
};

const mergeProfiles = (
  existing: Partial<InstructorProfile> | null,
  incoming: Partial<InstructorProfile>
): Partial<InstructorProfile> => {
  if (!existing) {
    return { ...incoming };
  }

  const merged: Partial<InstructorProfile> = {
    ...existing,
    ...incoming,
  };

  if (existing.user || incoming.user) {
    merged.user = {
      ...(existing.user ?? {}),
      ...(incoming.user ?? {}),
    } as InstructorProfile['user'];
  }

  if (!incoming.bio && existing.bio) {
    merged.bio = existing.bio;
  }

  if (
    !(typeof incoming.years_experience === 'number' && Number.isFinite(incoming.years_experience)) &&
    typeof existing.years_experience === 'number'
  ) {
    merged.years_experience = existing.years_experience;
  }

  return merged;
};

type ProfileCacheWriteOptions = {
  intent?: 'GET' | 'MUTATION';
  requestId?: number;
};

let lastWriteRequestId = 0;

export function logProfileCacheWrite(
  source: ProfileWriteSource,
  payload: unknown,
  meta?: { intent?: 'GET' | 'MUTATION'; requestId?: number }
) {
  const record = toRecord(payload) ?? {};
  const bioSource = firstNonEmptyString(record['bio'], record['about']);
  const yearsValue = record['years_experience'] ?? record['yearsExperience'];
  const hasYears =
    typeof yearsValue === 'number'
      ? Number.isFinite(yearsValue) && yearsValue > 0
      : typeof yearsValue === 'string' && Number(yearsValue) > 0;

  logger.info('onboarding_profile_cache_write', {
    source,
    fields: {
      hasBio: Boolean(bioSource && bioSource.trim().length > 0),
      yearsType: typeof yearsValue,
      hasYears,
    },
    intent: meta?.intent ?? 'MUTATION',
    requestId: meta?.requestId ?? null,
  });
}

export const getProfileCache = (): Partial<InstructorProfile> | null => cachedProfile;

export function setProfileCacheNormalized(
  source: ProfileWriteSource,
  incoming: unknown,
  options?: ProfileCacheWriteOptions
): Partial<InstructorProfile> | null {
  const normalized = normalizeInstructorProfile(incoming);
  if (!normalized) return cachedProfile;
  const intent = options?.intent ?? 'MUTATION';
  const requestId = options?.requestId;

  if (intent === 'GET' && typeof requestId === 'number') {
    if (requestId < lastWriteRequestId) {
      logger.info('onboarding_profile_fetch_ignore_stale_write', {
        source,
        requestId,
        lastWriteRequestId,
      });
      return cachedProfile;
    }
    lastWriteRequestId = requestId;
  }

  cachedProfile = mergeProfiles(cachedProfile, normalized);
  const meta: { intent?: 'GET' | 'MUTATION'; requestId?: number } = { intent };
  if (typeof requestId === 'number') {
    meta.requestId = requestId;
  }
  logProfileCacheWrite(source, cachedProfile, meta);
  return cachedProfile;
}

export const resetProfileCache = () => {
  cachedProfile = null;
};
