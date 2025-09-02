'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { BRAND } from '@/app/config/brand';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

function JoinInner() {
  const params = useSearchParams();
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Prefill from query param if present; fall back to sessionStorage
    const qp = (params.get('invite_code') || '').trim();
    if (qp) {
      const up = qp.toUpperCase();
      setCode(up);
      try { sessionStorage.setItem('invite_code', up); } catch {}
    } else {
      const stored = typeof window !== 'undefined' ? sessionStorage.getItem('invite_code') : null;
      if (stored && !code) setCode(stored);
    }
  }, []);

  const [validating, setValidating] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = code.trim().toUpperCase();
    if (!/^[A-Z0-9]{6,12}$/.test(trimmed)) {
      setError('Invalid or expired code');
      return;
    }
    // Call backend to validate
    setValidating(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/beta/invites/validate?code=${encodeURIComponent(trimmed)}`);
      const data = await res.json();
      if (!data.valid) {
        setError(data.reason || 'Invalid or expired code');
        setValidating(false);
        return;
      }
      try { sessionStorage.setItem('invite_code', trimmed); } catch {}
      const next = new URL(window.location.origin + '/instructor/welcome');
      next.searchParams.set('invite_code', trimmed);
      const prefill = params.get('email') || data.email;
      if (prefill) next.searchParams.set('email', prefill);
      window.location.href = next.toString();
    } catch {
      setError('Unable to validate code. Please try again.');
      setValidating(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col justify-center py-12 sm:px-6 lg:px-8 relative">
      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white dark:bg-gray-800 py-8 px-4 shadow sm:rounded-lg sm:px-10">
          <div className="text-center mb-6">
            <h1 className="text-4xl font-bold text-purple-700 hover:text-purple-800 transition-colors">
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
                className="mt-1 block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-purple-500 focus:border-purple-500 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                placeholder="Enter code (e.g. ZBB5MWQP)"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                autoComplete="off"
              />
              {error && <p className="mt-1 text-sm text-red-600" role="alert">{error}</p>}
            </div>
            <button
              type="submit"
              disabled={validating}
              className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-purple-700 hover:bg-purple-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:opacity-50"
            >
              {validating ? 'Validating…' : 'Continue'}
            </button>
          </form>
          <p className="mt-6 text-xs text-gray-500">
            Don&apos;t have a code? We&apos;re currently selecting founding instructors. Join our Profile Clinic or apply at
            {' '}<a className="underline" href="https://instainstru.com/teach" target="_blank" rel="noopener noreferrer">instainstru.com/teach</a>{' '}
            (or email{' '}
            <a
              className="underline"
              href="mailto:teach@instainstru.com?subject=Founding%20Instructor%20%E2%80%94%20Park%20Slope&body=Name:%0ACategory:%0AYears%20teaching:%0AAvailability:%0ARate%20range:%0ALinks:%0A"
            >
              teach@instainstru.com
            </a>
            ) if you teach in NYC.
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
