"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import type { InstructorProfile } from '@/types/instructor';
import type { OnboardingStatusResponse } from '@/services/api/payments';

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

const safeJson = async (res: Response | null) => {
  if (!res || !res.ok) return null;
  try {
    return await res.json();
  } catch {
    return null;
  }
};

export function useOnboardingProgress() {
  const { user } = useAuth();
  const instructorId = user?.id ? String(user.id) : null;
  const [data, setData] = useState<OnboardingData>({});
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [visited, setVisited] = useState<VisitedMap>({});
  const [visitedLoaded, setVisitedLoaded] = useState(false);
  const pendingVisitedRef = useRef<VisitedMap>({});

  const readiness = useMemo<DataReadiness>(
    () => ({
      profileLoaded: typeof data.profile !== 'undefined',
      userLoaded: typeof data.user !== 'undefined',
      serviceAreasLoaded: typeof data.serviceAreas !== 'undefined',
      addressesLoaded: typeof data.addresses !== 'undefined',
      stripeLoaded: typeof data.stripe !== 'undefined',
    }),
    [data]
  );

  const allDataReady =
    readiness.profileLoaded &&
    readiness.userLoaded &&
    readiness.serviceAreasLoaded &&
    readiness.addressesLoaded &&
    readiness.stripeLoaded;
  const progressReady = Boolean(instructorId) && allDataReady;

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

  useEffect(() => {
    let active = true;
    const fetchData = async () => {
      if (!instructorId) {
        setData({});
        return;
      }
      setError(null);
      try {
        const [meRes, profileRes, serviceAreasRes, addressesRes] = await Promise.all([
          fetchWithAuth(API_ENDPOINTS.ME).catch(() => null),
          fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE).catch(() => null),
          fetchWithAuth('/api/addresses/service-areas/me').catch(() => null),
          fetchWithAuth('/api/addresses/me').catch(() => null),
        ]);

        const [me, profile, serviceAreas, addresses] = await Promise.all([
          safeJson(meRes),
          safeJson(profileRes),
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
        setData({
          user: me,
          profile,
          serviceAreas,
          addresses,
          stripe,
        });
      } catch {
        if (!active) return;
        setError('Failed to load onboarding progress');
        setData({
          user: null,
          profile: null,
          serviceAreas: null,
          addresses: null,
          stripe: null,
        });
      }
    };

    void fetchData();
    return () => {
      active = false;
    };
  }, [refreshToken, instructorId]);

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

  return {
    statusMap,
    loading,
    error,
    refresh,
    markStepVisited,
    data,
    readiness,
  };
}
