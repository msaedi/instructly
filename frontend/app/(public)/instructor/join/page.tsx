'use client';

import { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { BRAND } from '@/app/config/brand';
import { validateInviteCode } from '@/app/(public)/instructor/join/validateInvite';
import { logger } from '@/lib/logger';

const sanitizeCode = (input: string): string =>
  input.replace(/[^a-zA-Z0-9]/g, '').toUpperCase().slice(0, 8);

const formatDisplayCode = (value: string): string =>
  value.length > 4 ? `${value.slice(0, 4)}-${value.slice(4)}` : value;

const trackInviteEvent = (name: string, detail: Record<string, unknown> = {}) => {
  logger.info('invite_event', { name, ...detail });
  if (typeof window !== 'undefined') {
    try {
      window.dispatchEvent(new CustomEvent('invite-event', { detail: { name, ...detail } }));
      // Optional analytics adapters if present
      const analyticsAny = (window as typeof window & { analytics?: { track?: (event: string, data?: Record<string, unknown>) => void } }).analytics;
      analyticsAny?.track?.(name, detail);
    } catch {
      // noop
    }
  }
};

function JoinInner() {
  const params = useSearchParams();
  const router = useRouter();
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const inFlightRef = useRef(false);
  const prefilledRef = useRef(false);

  useEffect(() => {
    if (prefilledRef.current) return;
    prefilledRef.current = true;
    // Prefill from query param if present; fall back to sessionStorage
    const qp = sanitizeCode(params.get('invite_code') || '');
    if (qp) {
      setCode(qp);
      try { sessionStorage.setItem('invite_code', qp); } catch {}
    } else {
      const stored = typeof window !== 'undefined' ? sessionStorage.getItem('invite_code') : null;
      if (stored) {
        setCode((prev) => (prev ? prev : sanitizeCode(stored)));
      }
    }
  }, [params]);

  const formattedCode = useMemo(() => formatDisplayCode(code), [code]);

  const handleInputChange = (value: string) => {
    if (!touched) setTouched(true);
    const sanitized = sanitizeCode(value);
    setCode(sanitized);
    if (error) setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = sanitizeCode(code);
    trackInviteEvent('code_submit', { value_length: trimmed.length });
    if (!/^[A-Z0-9]{6,12}$/.test(trimmed)) {
      setError('Code already used or expired.');
      trackInviteEvent('code_invalid', { reason: 'client_validation', value_length: trimmed.length });
      return;
    }
    if (inFlightRef.current) return;
    // Call backend to validate
    inFlightRef.current = true;
    setSubmitting(true);
    try {
      setError(null);
      const { data, trimmed: resolvedCode } = await validateInviteCode(code, params.get('email'));
      if (!data.valid) {
        setError('Code already used or expired.');
        trackInviteEvent('code_invalid', { reason: data?.reason ?? 'server_validation' });
        return;
      }
      trackInviteEvent('code_verified', { invite_code_length: resolvedCode.length });
      try { sessionStorage.setItem('invite_code', resolvedCode); } catch {}
      const next = new URL('/instructor/welcome', window.location.origin);
      next.searchParams.set('invite_code', resolvedCode);
      const prefill = params.get('email') || data.email;
      if (prefill) next.searchParams.set('email', prefill);
      router.replace(next.toString());
    } catch (err: unknown) {
      const message = err instanceof Error && err.message ? err.message : 'Unable to validate code. Please try again.';
      setError(message);
    } finally {
      setSubmitting(false);
      inFlightRef.current = false;
    }
  };

  return (
    <div className="min-h-screen flex flex-col justify-center py-12 sm:px-6 lg:px-8 relative transition-colors duration-200">
      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white/95 dark:bg-gray-900/80 py-8 px-4 shadow-[0_20px_40px_rgba(126,34,206,0.12)] rounded-[28px] border border-white/60 dark:border-gray-800/60 backdrop-blur-sm sm:px-10 transition-colors duration-200">
          <div className="text-center mb-6">
            <h1 className="text-4xl font-bold text-[#7E22CE] transition-colors">
              {BRAND.name}
            </h1>
            <h2 className="text-2xl font-bold mb-2 text-gray-900 dark:text-gray-100 mt-3">
              Founding Instructor Program
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-300 mt-3">
              You&apos;ve been selected for early access to iNSTAiNSTRU <span className="text-xs">NYC&apos;s most selective instant-booking marketplace for instructors & students</span>
            </p>
          </div>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="flex justify-center items-center">
              <div className="h-px w-48 bg-gradient-to-r from-transparent via-[#7E22CE]/40 to-transparent" />
            </div>
            <div>
              <label htmlFor="invite" className="block text-sm font-medium">Enter your founding instructor code</label>
              <input
                id="invite"
                data-testid="invite-code-input"
                className="mt-1 block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-[var(--primary)] focus:border-[var(--primary)] bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                placeholder="Enter code (e.g. ZBB5-MWQP)"
                value={formattedCode}
                onChange={(e) => handleInputChange(e.target.value)}
                onBlur={() => setTouched(true)}
                autoComplete="off"
                aria-invalid={error ? 'true' : 'false'}
                aria-describedby={
                  [
                    !error && touched && code.length === 8 ? 'invite-helper-success' : null,
                    error ? 'invite-helper-error' : null,
                  ]
                    .filter(Boolean)
                    .join(' ') || undefined
                }
              />
              {!error && touched && code.length === 8 && (
                <p
                  id="invite-helper-success"
                  className="mt-1 text-sm text-emerald-600 flex items-center gap-2 animate-invite-pop"
                >
                  <span aria-hidden="true">✔</span> Invite confirmed.
                </p>
              )}
              {error && (
                <p id="invite-helper-error" className="mt-1 text-sm text-red-600" role="alert">
                  {error}
                </p>
              )}
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="w-full flex justify-center items-center h-12 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-[#7E22CE] hover:bg-[#7E22CE] focus:bg-[#7E22CE] active:bg-[#7E22CE] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#7E22CE] disabled:opacity-60 disabled:cursor-not-allowed transform-gpu will-change-transform transition-all antialiased"
            >
              {submitting ? 'Verifying…' : 'Join!'}
            </button>
          </form>
          <div className="mt-8">
            <div className="mt-4 rounded-lg border border-gray-100 bg-gray-50 px-4 py-5 text-center text-xs text-gray-600 space-y-3">
              <p>
                By clicking Join, you agree to iNSTAiNSTRU&apos;s{' '}
                <a href="/legal#terms" className="focus-link text-[#7E22CE] hover:text-[#7E22CE]">
                  Terms of Service
                </a>{' '}
                and{' '}
                <a href="/legal#privacy" className="focus-link text-[#7E22CE] hover:text-[#7E22CE]">
                  Privacy Policy
                </a>.
              </p>
              <p>
                Don’t have a code? We’re hand-selecting our founding instructors.{' '}
                <a
                  className="focus-link text-[#7E22CE] hover:underline"
                  href="/instructor/apply"
                  onClick={() => trackInviteEvent('apply_access_click')}
                >
                  Apply
                </a>{' '}
                for access.
              </p>
            </div>
          </div>
          <p className="mt-6 text-xs text-gray-500 text-center">
            Already have an account?{' '}
            <a href="/login" className="focus-link text-[#7E22CE] hover:underline">Sign in</a>
          </p>
        </div>
      </div>
    </div>
  );
}

export default function InstructorJoinPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center p-6">Loading…</div>}>
      <JoinInner />
    </Suspense>
  );
}
