'use client';

import { fetchWithAuth, getErrorMessage } from '@/lib/api';

export interface BetaSettings {
  beta_disabled: boolean;
  beta_phase: string;
  allow_signup_without_invite: boolean;
}

export async function getBetaSettings(): Promise<BetaSettings> {
  // Go through Next.js route handler to avoid CORS/hydration issues
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const res = await fetch('/api/proxy/beta/settings', {
    credentials: 'include',
    cache: 'no-store',
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new Error(await getErrorMessage(res));
  return res.json();
}

export async function updateBetaSettings(payload: BetaSettings): Promise<BetaSettings> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const res = await fetch('/api/proxy/beta/settings', {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
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
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const res = await fetch('/api/proxy/metrics/performance', {
    credentials: 'include',
    cache: 'no-store',
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new Error(await getErrorMessage(res));
  return res.json();
}
