'use client';

import { Suspense, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { BRAND } from '@/app/config/brand';
import { validateInviteCode } from '@/app/(public)/instructor/join/validateInvite';

function JoinInner() {
  const params = useSearchParams();
  const router = useRouter();
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const inFlightRef = useRef(false);
  const prefilledRef = useRef(false);

  useEffect(() => {
    if (prefilledRef.current) return;
    prefilledRef.current = true;
    // Prefill from query param if present; fall back to sessionStorage
    const qp = (params.get('invite_code') || '').trim();
    if (qp) {
      const up = qp.toUpperCase();
      setCode(up);
      try { sessionStorage.setItem('invite_code', up); } catch {}
    } else {
      const stored = typeof window !== 'undefined' ? sessionStorage.getItem('invite_code') : null;
      if (stored) {
        setCode((prev) => (prev ? prev : stored));
      }
    }
  }, [params]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = code.trim().toUpperCase();
    if (!/^[A-Z0-9]{6,12}$/.test(trimmed)) {
      setError('Invalid or expired code');
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
        const rawReason = (data?.reason ?? '').toString().toLowerCase();
        const friendly = rawReason.includes('used')
          ? 'Opps! This code was already redeemd.'
          : (data?.reason || 'Invalid or expired code');
        setError(friendly);
        return;
      }
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
    <div className="min-h-screen flex flex-col justify-center py-12 sm:px-6 lg:px-8 relative">
      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white/95 dark:bg-gray-800/95 py-8 px-4 shadow-[0_20px_40px_rgba(126,34,206,0.12)] rounded-[28px] border border-white/60 dark:border-gray-700/60 backdrop-blur-sm sm:px-10">
          <div className="text-center mb-6">
            <h1 className="text-4xl font-bold text-[#7E22CE] transition-colors">
              {BRAND.name}
            </h1>
            <h2 className="text-2xl font-bold mb-2 text-gray-900 dark:text-gray-100 mt-3">
              Founding Instructor Program
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-300 mt-3">
              You&apos;ve been selected to join the premium instruction platform.
            </p>
          </div>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="invite" className="block text-sm font-medium">Enter your founding instructor code</label>
              <input
                id="invite"
                className="mt-1 block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-[var(--primary)] focus:border-[var(--primary)] bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                placeholder="Enter code (e.g. ZBB5MWQP)"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                autoComplete="off"
              />
              {error && <p className="mt-1 text-sm text-red-600" role="alert">{error}</p>}
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-[#7E22CE] hover:bg-[#7E22CE] focus:bg-[#7E22CE] active:bg-[#7E22CE] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#7E22CE] disabled:opacity-50 transform-gpu will-change-transform transition-transform antialiased"
            >
              {submitting ? 'Validating…' : 'Join!'}
            </button>
          </form>
          <div className="mt-8">
            <div className="mx-auto h-px w-24 bg-gradient-to-r from-transparent via-[#7E22CE]/40 to-transparent" />
            <div className="mt-4 rounded-lg border border-gray-100 bg-gray-50 px-4 py-5 text-center text-xs text-gray-600 space-y-3">
              <p>
                By clicking Join, you agree to iNSTAiNSTRU&apos;s{' '}
                <a href="/legal#terms" className="text-[#7E22CE] hover:underline">Terms of Service</a> and{' '}
                <a href="/legal#privacy" className="text-[#7E22CE] hover:underline">Privacy Policy</a>.
              </p>
              <p>
                Don’t have a code? We’re handpicking our founding instructors. Request to{' '}
                <a className="text-[#7E22CE] hover:underline" href="mailto:teach@instainstru.com">join</a>{' '}
                our Profile Clinic.
              </p>
            </div>
          </div>
          <p className="mt-6 text-xs text-gray-500 text-center">
            Already have an account?{' '}
            <a href="/login" className="text-[#7E22CE] hover:underline">Sign in</a>
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
