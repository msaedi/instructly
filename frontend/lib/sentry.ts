// frontend/lib/sentry.ts
import * as Sentry from '@sentry/nextjs';

import { SENTRY_DSN } from '@/lib/publicEnv';

export interface SentryUserContext {
  id: string;
  email?: string;
  first_name?: string;
  last_name?: string;
}

export interface FetchErrorContext {
  url: string;
  method: string;
  status?: number;
  error?: unknown;
}

export function isSentryEnabled(): boolean {
  return process.env.NODE_ENV === 'production' && Boolean(SENTRY_DSN);
}

export function setSentryUser(user: SentryUserContext | null): void {
  if (!user) {
    Sentry.setUser(null);
    return;
  }

  const nameParts = [user.first_name, user.last_name].filter(Boolean);
  const username = nameParts.join(' ').trim();

  const payload: { id: string; email?: string; username?: string } = { id: user.id };
  if (user.email) {
    payload.email = user.email;
  }
  if (username) {
    payload.username = username;
  }
  Sentry.setUser(payload);
}

export function clearSentryUser(): void {
  Sentry.setUser(null);
}

export function captureFetchError({ url, method, status, error }: FetchErrorContext): void {
  if (!isSentryEnabled()) {
    return;
  }

  Sentry.withScope((scope) => {
    scope.setTag('http.method', method);
    scope.setTag('http.url', url);
    if (status) {
      scope.setTag('http.status_code', String(status));
    }
    scope.setContext('fetch', { url, method, status });

    if (error instanceof Error) {
      Sentry.captureException(error);
      return;
    }

    const message = status
      ? `HTTP ${status} ${method} ${url}`
      : `Network error ${method} ${url}`;
    Sentry.captureMessage(message, 'error');
  });
}
