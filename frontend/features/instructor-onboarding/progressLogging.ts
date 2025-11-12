import { logger } from '@/frontend/lib/logger';
import type { InstructorProfile } from '@/types/instructor';
import type { OnboardingStatusResponse } from '@/services/api/payments';
import {
  type OnboardingStatusMap,
  type StepKey,
  getInstructorPostal,
  hasCompletedIdentity,
  hasCompletedPayments,
  hasProfilePicture,
  hasProfileServiceAreas,
  hasServiceAreasConfigured,
  hasSkillsConfigured,
} from './stepStatus';

export type OnboardingPendingKey =
  | 'first_name'
  | 'last_name'
  | 'zip'
  | 'bio'
  | 'years_experience'
  | 'avatar'
  | 'service_area'
  | 'skill'
  | 'id_verification'
  | 'background_check'
  | 'stripe_connect';

export type ProgressDomainData = {
  profile?: Partial<InstructorProfile> | null;
  user?: Record<string, unknown> | null;
  serviceAreas?: { items?: unknown[] } | null;
  addresses?: { items?: Array<Record<string, unknown>> } | null;
  stripe?: OnboardingStatusResponse | null;
  skills?: unknown;
  identity?: unknown;
};

export type OnboardingProgressSnapshot = {
  event: 'onboarding_progress_snapshot';
  instructorId: string | number | null;
  route: string;
  activeStep: StepKey | 'status';
  progressReady: boolean;
  status: Record<
    StepKey,
    {
      visited: boolean;
      completed: boolean;
      pending: OnboardingPendingKey[];
    }
  >;
  ts: number;
};

const coerceRecord = (value: unknown): Record<string, unknown> | null => {
  if (value && typeof value === 'object') return value as Record<string, unknown>;
  return null;
};

const hasBackgroundCheck = (profile?: Partial<InstructorProfile> | null) => {
  const record = coerceRecord(profile);
  if (!record) return false;
  if (typeof record['background_check_completed'] === 'boolean') {
    return record['background_check_completed'] as boolean;
  }
  if (record['background_check_uploaded_at']) return true;
  return false;
};

const pendingAccountFields = (data: ProgressDomainData): OnboardingPendingKey[] => {
  const pending: OnboardingPendingKey[] = [];
  const profile = data.profile ?? null;
  const user = data.user ?? profile?.user ?? null;
  const userRecord = coerceRecord(user);
  const profileRecord = coerceRecord(profile);
  const profileUserRecord = coerceRecord(profile?.user);

  const firstName = String(
    userRecord?.['first_name'] ?? profileUserRecord?.['first_name'] ?? ''
  ).trim();
  if (!firstName) pending.push('first_name');

  const lastName = String(
    userRecord?.['last_name'] ?? profileUserRecord?.['last_name'] ?? ''
  ).trim();
  if (!lastName) pending.push('last_name');

  const postal = getInstructorPostal(userRecord, profile, data.addresses);
  if (!/^\d{5}$/.test(postal)) pending.push('zip');

  const bioSource = String(
    profile?.bio ?? profileRecord?.['about'] ?? ''
  ).trim();
  if (!bioSource) pending.push('bio');

  const yearsExperience =
    typeof profile?.years_experience === 'number'
      ? profile.years_experience
      : Number(profileRecord?.['yearsExperience']);
  if (!Number.isFinite(yearsExperience) || Number(yearsExperience) <= 0) {
    pending.push('years_experience');
  }

  if (!hasProfilePicture(userRecord, profile)) {
    pending.push('avatar');
  }

  const hasServiceArea = hasProfileServiceAreas(profile) || hasServiceAreasConfigured(data.serviceAreas);
  if (!hasServiceArea) {
    pending.push('service_area');
  }

  return pending;
};

export function getPendingForStep(step: StepKey, data: ProgressDomainData): OnboardingPendingKey[] {
  switch (step) {
    case 'account-setup':
      return pendingAccountFields(data);
    case 'skill-selection':
      return hasSkillsConfigured(data.profile) ? [] : ['skill'];
    case 'verify-identity': {
      const pending: OnboardingPendingKey[] = [];
      if (!hasCompletedIdentity(data.profile)) pending.push('id_verification');
      if (!hasBackgroundCheck(data.profile)) pending.push('background_check');
      return pending;
    }
    case 'payment-setup':
      return hasCompletedPayments(data.stripe) ? [] : ['stripe_connect'];
    default:
      return [];
  }
}

export function buildProgressSnapshot(args: {
  instructorId: string | number | null;
  route: string;
  activeStep: StepKey | 'status';
  progressReady: boolean;
  statusMap: OnboardingStatusMap;
  data: ProgressDomainData;
}): OnboardingProgressSnapshot {
  const { instructorId, route, activeStep, progressReady, statusMap, data } = args;
  const status = (Object.keys(statusMap) as StepKey[]).reduce((acc, key) => {
    const state = statusMap[key];
    acc[key] = {
      visited: state.visited,
      completed: state.completed,
      pending: state.completed ? [] : getPendingForStep(key, data),
    };
    return acc;
  }, {} as OnboardingProgressSnapshot['status']);

  return {
    event: 'onboarding_progress_snapshot',
    instructorId,
    route,
    activeStep,
    progressReady,
    status,
    ts: Date.now(),
  };
}

export function logProgressSnapshot(snapshot: OnboardingProgressSnapshot) {
  logger.info('onboarding_progress_snapshot', snapshot);
}
