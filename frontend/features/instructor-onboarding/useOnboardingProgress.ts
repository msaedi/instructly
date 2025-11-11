"use client";

import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { paymentService } from '@/services/api/payments';
import { useAuth } from '@/features/shared/hooks/useAuth';
import {
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
  const [visited, setVisited] = useState<VisitedMap>(() => readVisitedSteps(instructorId));
  const [data, setData] = useState<OnboardingData>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    setVisited((prev) => {
      if (!instructorId) return prev;
      const stored = readVisitedSteps(instructorId);
      return { ...stored, ...prev };
    });
  }, [instructorId]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!instructorId) return;
    persistVisitedSteps(instructorId, visited);
  }, [instructorId, visited]);

  useEffect(() => {
    let active = true;
    const fetchData = async () => {
      setLoading(true);
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

        let stripe = null;
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
      } finally {
        if (!active) return;
        setLoading(false);
      }
    };

    void fetchData();
    return () => {
      active = false;
    };
  }, [refreshToken, instructorId]);

  const statusMap: OnboardingStatusMap = useMemo(
    () => deriveStatusMap({ data, visited }),
    [data, visited]
  );

  const refresh = useCallback(() => setRefreshToken((token) => token + 1), []);

  const markStepVisited = useCallback(
    (step: StepKey) => {
      setVisited((prev) => {
        if (prev?.[step]) return prev;
        const next = { ...prev, [step]: true };
        if (instructorId) {
          persistVisitedSteps(instructorId, next);
        }
        return next;
      });
    },
    [instructorId]
  );

  return {
    statusMap,
    loading,
    error,
    refresh,
    markStepVisited,
    data,
  };
}
