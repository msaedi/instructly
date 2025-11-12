"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { usePathname as useNextPathname } from 'next/navigation';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { paymentService } from '@/services/api/payments';
import { useAuth } from '@/features/shared/hooks/useAuth';
import {
  createEmptyStatusMap,
  deriveStatusMap,
  persistVisitedSteps,
  readVisitedSteps,
  type OnboardingStatusMap,
  type StepKey,
  type VisitedMap,
} from './stepStatus';
import type { OnboardingStatusResponse } from '@/services/api/payments';
import {
  buildProgressSnapshot,
  logProgressSnapshot,
  type ProgressDomainData,
} from './progressLogging';
import { getProfileCache, setProfileCacheNormalized } from '@/features/shared/onboarding/profileCache';
import { logger } from '@/frontend/lib/logger';
import type { InstructorProfile } from '@/types/instructor';

const usePathnameSafe = typeof useNextPathname === 'function' ? useNextPathname : () => '';

type OnboardingData = {
  profile?: Partial<InstructorProfile> | null;
  user?: Record<string, unknown> | null;
  serviceAreas?: { items?: unknown[] } | null;
  addresses?: { items?: Array<Record<string, unknown>> } | null;
  stripe?: OnboardingStatusResponse | null;
};

type DataReadiness = {
  profileLoaded: boolean;
  userLoaded: boolean;
  serviceAreasLoaded: boolean;
  addressesLoaded: boolean;
  stripeLoaded: boolean;
};

const BASE_PROFILE_RETRY_DELAY_MS = 1000;
const MAX_PROFILE_RETRY_DELAY_MS = 10_000;

const parseRetryAfterHeader = (value?: string | null): number | null => {
  if (!value) return null;
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    const milliseconds = numeric * 1000;
    return milliseconds > 0 ? milliseconds : null;
  }
  const parsedDate = Date.parse(value);
  if (!Number.isNaN(parsedDate)) {
    const delta = parsedDate - Date.now();
    return delta > 0 ? delta : null;
  }
  return null;
};

const safeJson = async (res: Response | null) => {
  if (!res || !res.ok) return null;
  try {
    return await res.json();
  } catch {
    return null;
  }
};

type UseOnboardingProgressOptions = {
  activeStep?: StepKey | 'status';
};

export function useOnboardingProgress(options?: UseOnboardingProgressOptions) {
  const { user } = useAuth();
  const instructorId = user?.id ? String(user.id) : null;
  const activeStep: StepKey | 'status' = options?.activeStep ?? 'account-setup';
  const [data, setData] = useState<OnboardingData>(() => {
    const cachedProfile = getProfileCache();
    return cachedProfile ? { profile: cachedProfile } : {};
  });
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [visited, setVisited] = useState<VisitedMap>({});
  const [visitedLoaded, setVisitedLoaded] = useState(false);
  const pendingVisitedRef = useRef<VisitedMap>({});
  const [profileHasGoodSnapshot, setProfileHasGoodSnapshot] = useState<boolean>(() =>
    Boolean(getProfileCache())
  );
  const [profileLoadState, setProfileLoadState] = useState<'idle' | 'loading' | 'success' | 'error'>(
    () => (getProfileCache() ? 'success' : 'idle')
  );
  const profileFetchSeqRef = useRef(0);
  const profileAbortControllerRef = useRef<AbortController | null>(null);
  const profileRetryTimeoutRef = useRef<number | null>(null);
  const profileRetryDelayRef = useRef<number>(BASE_PROFILE_RETRY_DELAY_MS);

  const readiness = useMemo<DataReadiness>(
    () => ({
      profileLoaded: profileHasGoodSnapshot,
      userLoaded: typeof data.user !== 'undefined',
      serviceAreasLoaded: typeof data.serviceAreas !== 'undefined',
      addressesLoaded: typeof data.addresses !== 'undefined',
      stripeLoaded: typeof data.stripe !== 'undefined',
    }),
    [data.user, data.serviceAreas, data.addresses, data.stripe, profileHasGoodSnapshot]
  );

  const allDataReady =
    readiness.profileLoaded &&
    readiness.userLoaded &&
    readiness.serviceAreasLoaded &&
    readiness.addressesLoaded &&
    readiness.stripeLoaded;
  const progressReady = Boolean(instructorId) && allDataReady;
  const pathname = usePathnameSafe();
  const route = pathname ?? '';
  const snapshotHashRef = useRef<string>('');
  const debounceRef = useRef<number | null>(null);

  useEffect(() => {
    pendingVisitedRef.current = {};
    setVisited({});
    setVisitedLoaded(false);
  }, [instructorId]);

  useEffect(() => {
    if (!progressReady || !instructorId || visitedLoaded) return;
    if (typeof window === 'undefined') return;
    const stored = readVisitedSteps(instructorId);
    setVisited((prev) => {
      const merged = { ...stored, ...prev, ...pendingVisitedRef.current };
      pendingVisitedRef.current = {};
      return merged;
    });
    setVisitedLoaded(true);
  }, [progressReady, instructorId, visitedLoaded]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!visitedLoaded || !instructorId) return;
    persistVisitedSteps(instructorId, visited);
  }, [instructorId, visited, visitedLoaded]);

  const scheduleProfileRetry = useCallback(
    (retryAfter?: string | null) => {
      if (typeof window === 'undefined') return;
      const headerDelay = parseRetryAfterHeader(retryAfter);
      let delayMs = headerDelay ?? profileRetryDelayRef.current;
      const jitter = 0.75 + Math.random() * 0.5;
      delayMs = Math.min(
        MAX_PROFILE_RETRY_DELAY_MS,
        Math.max(BASE_PROFILE_RETRY_DELAY_MS, delayMs * jitter)
      );
      if (profileRetryTimeoutRef.current) {
        window.clearTimeout(profileRetryTimeoutRef.current);
      }
      profileRetryTimeoutRef.current = window.setTimeout(() => {
        profileRetryTimeoutRef.current = null;
        setRefreshToken((token) => token + 1);
      }, delayMs);
      profileRetryDelayRef.current = Math.min(delayMs * 1.5, MAX_PROFILE_RETRY_DELAY_MS);
    },
    [setRefreshToken]
  );

  useEffect(() => {
    let active = true;
    const fetchData = async () => {
      if (!instructorId) {
        setData({});
        return;
      }
      setError(null);
      setProfileLoadState((prev) => (prev === 'success' ? prev : 'loading'));

      const profileRequestId = profileFetchSeqRef.current + 1;
      profileFetchSeqRef.current = profileRequestId;
      if (profileAbortControllerRef.current) {
        profileAbortControllerRef.current.abort();
      }
      const profileController = new AbortController();
      profileAbortControllerRef.current = profileController;
      logger.info('onboarding_profile_fetch_start', {
        requestId: profileRequestId,
        source: 'useOnboardingProgress:GET',
      });

      let me: Record<string, unknown> | null = null;
      let serviceAreas: { items?: unknown[] } | null = null;
      let addresses: { items?: Array<Record<string, unknown>> } | null = null;

      try {
        const profileResPromise = fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
          signal: profileController.signal,
        }).catch((error) => {
          if (error instanceof DOMException && error.name === 'AbortError') {
            return null;
          }
          throw error;
        });

        const [meRes, serviceAreasRes, addressesRes, profileRes] = await Promise.all([
          fetchWithAuth(API_ENDPOINTS.ME).catch(() => null),
          fetchWithAuth('/api/addresses/service-areas/me').catch(() => null),
          fetchWithAuth('/api/addresses/me').catch(() => null),
          profileResPromise,
        ]);

        [me, serviceAreas, addresses] = await Promise.all([
          safeJson(meRes),
          safeJson(serviceAreasRes),
          safeJson(addressesRes),
        ]);

        let stripe: OnboardingStatusResponse | null = null;
        try {
          stripe = await paymentService.getOnboardingStatus();
        } catch {
          stripe = null;
        }

        if (!active) return;
        const isLatestRequest = profileRequestId === profileFetchSeqRef.current;
        if (!isLatestRequest) {
          logger.info('onboarding_profile_fetch_ignore_stale', {
            staleRequestId: profileRequestId,
            latestRequestId: profileFetchSeqRef.current,
            source: 'useOnboardingProgress:GET',
          });
          return;
        }

        const retryAfterHeader = profileRes?.headers?.get?.('Retry-After') ?? null;
        const profileOk = Boolean(profileRes?.ok);

        if (!profileOk) {
          logger.info('onboarding_profile_fetch_reject', {
            requestId: profileRequestId,
            status: profileRes?.status ?? null,
            source: 'useOnboardingProgress:GET',
          });
          setProfileLoadState((prev) => (profileHasGoodSnapshot ? prev : 'error'));
          setData((prev) => ({
            user: me ?? prev.user ?? null,
            profile: getProfileCache() ?? prev.profile ?? null,
            serviceAreas: serviceAreas ?? prev.serviceAreas ?? null,
            addresses: addresses ?? prev.addresses ?? null,
            stripe: stripe ?? prev.stripe ?? null,
          }));
          setError('Temporarily rate-limited. Retrying…');
          if (active) {
            scheduleProfileRetry(retryAfterHeader);
          }
          return;
        }

        const profileRaw = await safeJson(profileRes);
        logger.info('onboarding_profile_fetch_accept', {
          requestId: profileRequestId,
          source: 'useOnboardingProgress:GET',
        });
        const normalizedProfile =
          setProfileCacheNormalized('useOnboardingProgress:GET', profileRaw, {
            intent: 'GET',
            requestId: profileRequestId,
          }) ?? getProfileCache();

        setData((prev) => ({
          user: me ?? prev.user ?? null,
          profile: normalizedProfile ?? prev.profile ?? null,
          serviceAreas: serviceAreas ?? prev.serviceAreas ?? null,
          addresses: addresses ?? prev.addresses ?? null,
          stripe,
        }));
        setProfileHasGoodSnapshot(Boolean(normalizedProfile));
        setProfileLoadState('success');
        setError(null);
        profileRetryDelayRef.current = BASE_PROFILE_RETRY_DELAY_MS;
        if (profileRetryTimeoutRef.current) {
          window.clearTimeout(profileRetryTimeoutRef.current);
          profileRetryTimeoutRef.current = null;
        }
      } catch (error) {
        if (!active) return;
        if (profileRequestId !== profileFetchSeqRef.current) return;
        if (error instanceof DOMException && error.name === 'AbortError') {
          logger.info('onboarding_profile_fetch_aborted', {
            requestId: profileRequestId,
            source: 'useOnboardingProgress:GET',
          });
          return;
        }
        logger.warn('onboarding_profile_fetch_exception', {
          requestId: profileRequestId,
          source: 'useOnboardingProgress:GET',
        });
        setProfileLoadState((prev) => (profileHasGoodSnapshot ? prev : 'error'));
        setError('Temporarily unable to refresh profile');
        if (active) {
          scheduleProfileRetry();
        }
      } finally {
        if (profileAbortControllerRef.current === profileController) {
          profileAbortControllerRef.current = null;
        }
      }
    };

    void fetchData();
    return () => {
      active = false;
      if (profileAbortControllerRef.current) {
        profileAbortControllerRef.current.abort();
        profileAbortControllerRef.current = null;
      }
    };
  }, [refreshToken, instructorId, profileHasGoodSnapshot, scheduleProfileRetry]);

  const statusMap: OnboardingStatusMap = useMemo(() => {
    if (!progressReady) {
      return createEmptyStatusMap();
    }
    return deriveStatusMap({ data, visited });
  }, [data, visited, progressReady]);

  const loading = !progressReady;
  const refresh = useCallback(() => setRefreshToken((token) => token + 1), []);

  const markStepVisited = useCallback(
    (step: StepKey) => {
      const visit = () => {
        setVisited((prev) => {
          if (prev?.[step]) return prev;
          if (!visitedLoaded) {
            pendingVisitedRef.current = { ...pendingVisitedRef.current, [step]: true };
          }
          return { ...prev, [step]: true };
        });
      };

      if (typeof window !== 'undefined' && 'requestAnimationFrame' in window) {
        window.requestAnimationFrame(visit);
      } else {
        visit();
      }
    },
    [visitedLoaded]
  );

  useEffect(() => {
    if (!progressReady) return;
    if (!instructorId) return;

    const hasBio =
      typeof data.profile?.bio === 'string' && data.profile.bio.trim().length > 0;
    const hasYears =
      typeof data.profile?.years_experience === 'number' && data.profile.years_experience > 0;

    logger.info('onboarding_profile_provenance', {
      instructorId,
      route,
      hasBio,
      hasYears,
      source: 'useOnboardingProgress',
    });
  }, [progressReady, data.profile, instructorId, route]);

  useEffect(() => {
    if (!progressReady) return;
    if (typeof window === 'undefined') return;

    const hash = JSON.stringify({ statusMap, activeStep, route });
    if (hash === snapshotHashRef.current) return;
    snapshotHashRef.current = hash;

    const snapshotData: ProgressDomainData = {
      profile: data.profile ?? null,
      user: data.user ?? null,
      serviceAreas: data.serviceAreas ?? null,
      addresses: data.addresses ?? null,
      stripe: data.stripe ?? null,
    };

    const snapshot = buildProgressSnapshot({
      instructorId,
      route,
      activeStep,
      progressReady,
      statusMap,
      data: snapshotData,
    });

    if (debounceRef.current) {
      window.clearTimeout(debounceRef.current);
    }

    debounceRef.current = window.setTimeout(() => {
      logProgressSnapshot(snapshot);
      debounceRef.current = null;
    }, 300);

    return () => {
      if (debounceRef.current) {
        window.clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
    };
  }, [progressReady, statusMap, activeStep, instructorId, route, data]);

  return {
    statusMap,
    loading,
    progressReady,
    error,
    refresh,
    markStepVisited,
    data,
    readiness,
    activeStep,
    instructorId,
    profileLoadState,
  };
}
