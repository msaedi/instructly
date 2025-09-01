'use client';

import { getErrorMessage } from '@/lib/api';
import { withApiBase } from '@/lib/apiBase';

export interface BetaSettings {
  beta_disabled: boolean;
  beta_phase: string;
  allow_signup_without_invite: boolean;
}

export async function getBetaSettings(): Promise<BetaSettings> {
  // Use toggleable base; rely on cookies for auth
  const res = await fetch(withApiBase('/beta/settings'), {
    credentials: 'include',
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(await getErrorMessage(res));
  return res.json();
}

export async function updateBetaSettings(payload: BetaSettings): Promise<BetaSettings> {
  const res = await fetch(withApiBase('/beta/settings'), {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
    credentials: 'include',
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(await getErrorMessage(res));
  return res.json();
}

export interface MetricsPerformanceResponse {
  availability_service?: Record<string, unknown>;
  booking_service?: Record<string, unknown>;
  conflict_checker?: Record<string, unknown>;
  cache?: Record<string, unknown>;
  system?: Record<string, unknown>;
  database?: Record<string, unknown>;
  // Optionally beta-related if backend adds it later
  beta_service?: Record<string, unknown>;
}

export async function getPerformanceMetrics(): Promise<MetricsPerformanceResponse> {
  const res = await fetch(withApiBase('/metrics/performance'), {
    credentials: 'include',
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(await getErrorMessage(res));
  return res.json();
}

export interface MetricsSummaryResponse {
  bookings_last_7d?: number;
  students_total?: number;
  earnings_last_7d?: number;
  // Allow other backend-provided fields without strict typing
  [key: string]: any;
}

export async function getMetricsSummary(): Promise<MetricsSummaryResponse> {
  const res = await fetch(withApiBase('/beta/metrics/summary'), {
    credentials: 'include',
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(await getErrorMessage(res));
  return res.json();
}
