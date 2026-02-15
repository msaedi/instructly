'use client';

import { getErrorMessage } from '@/lib/api';
import { withApiBase } from '@/lib/apiBase';
import { fetchWithSessionRefresh } from '@/lib/auth/sessionRefresh';
import type {
  BetaSettingsResponse,
  BetaSettingsUpdateRequest,
  PerformanceMetricsResponse,
  BetaMetricsSummaryResponse,
} from '@/features/shared/api/types';

export type BetaSettings = BetaSettingsResponse;
export type MetricsPerformanceResponse = PerformanceMetricsResponse;

export async function getBetaSettings(): Promise<BetaSettingsResponse> {
  // Use toggleable base; rely on cookies for auth
  const res = await fetchWithSessionRefresh(withApiBase('/api/v1/beta/settings'), {
    credentials: 'include',
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(await getErrorMessage(res));
  return res.json() as Promise<BetaSettingsResponse>;
}

export async function updateBetaSettings(payload: BetaSettingsUpdateRequest): Promise<BetaSettingsResponse> {
  const res = await fetchWithSessionRefresh(withApiBase('/api/v1/beta/settings'), {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
    credentials: 'include',
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(await getErrorMessage(res));
  return res.json() as Promise<BetaSettingsResponse>;
}

export async function getPerformanceMetrics(): Promise<PerformanceMetricsResponse> {
  const res = await fetchWithSessionRefresh(withApiBase('/ops/performance'), {
    credentials: 'include',
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(await getErrorMessage(res));
  return res.json() as Promise<PerformanceMetricsResponse>;
}

export async function getMetricsSummary(): Promise<BetaMetricsSummaryResponse> {
  const res = await fetchWithSessionRefresh(withApiBase('/api/v1/beta/metrics/summary'), {
    credentials: 'include',
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(await getErrorMessage(res));
  return res.json() as Promise<BetaMetricsSummaryResponse>;
}
