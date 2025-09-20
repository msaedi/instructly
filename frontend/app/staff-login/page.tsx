"use client";

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { BRAND } from '@/app/config/brand';

function StaffLoginInner() {
  const searchParams = useSearchParams();
  const [token, setToken] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const redirectPath = searchParams.get('redirect') || '/';
  const errorParam = searchParams.get('error');

  useEffect(() => {
    const input = document.getElementById('staff-token-input') as HTMLInputElement | null;
    input?.focus();
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const trimmed = token.trim();
    if (!trimmed) {
      setError('Please enter your staff access token.');
      return;
    }
    setIsSubmitting(true);
    try {
      // Redirect to a protected path (not /staff-login) so middleware can set the cookie
      const safeRedirect = redirectPath && redirectPath.startsWith('/') ? redirectPath : '/';
      const target = new URL(window.location.origin + safeRedirect);
      target.searchParams.set('token', trimmed);
      // Preserve original desired redirect if provided
      if (redirectPath && redirectPath !== safeRedirect) {
        target.searchParams.set('redirect', redirectPath);
      }
      window.location.href = target.toString();
    } catch {
      setError('Something went wrong. Please try again.');
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col justify-center py-12 sm:px-6 lg:px-8 relative">
      <div className="relative z-10">
        <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
          <div className="bg-white dark:bg-gray-800 py-8 px-4 shadow sm:rounded-lg sm:px-10">
            <div className="text-center mb-6">
              <Link href="/">
                <h1 className="text-4xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors">
                  {BRAND.name}
                </h1>
              </Link>
              <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">Staff Access Only</p>
            </div>

            {errorParam === 'invalid' && (
              <div className="mb-4 text-sm text-red-600" role="alert">
                Invalid token. Please try again.
              </div>
            )}

            <form data-testid="staff-gate-form" onSubmit={handleSubmit} className="space-y-6" noValidate>
              <div>
                <label htmlFor="staff-token-input" className="block text-sm font-medium text-gray-700 dark:text-gray-200">
                  Access Token
                </label>
                <div className="mt-1">
                  <input
                    id="staff-token-input"
                    type="password"
                    autoComplete="off"
                  data-testid="staff-gate-input"
                  className="appearance-none block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-transparent focus:border-gray-300 disabled:bg-gray-100 disabled:cursor-not-allowed bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 autofill-fix"
                    placeholder="Enter token"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                  />
                </div>
                {error && (
                  <p className="mt-1 text-sm text-red-600" role="alert">{error}</p>
                )}
              </div>

              <div>
                <button
                  type="submit"
                  data-testid="staff-gate-submit"
                  disabled={isSubmitting}
                  className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-[#7E22CE] hover:bg-[#7E22CE] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#7E22CE] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isSubmitting ? 'Verifying…' : 'Access Platform'}
                </button>
              </div>
            </form>

            <div className="mt-6 text-center text-xs text-gray-500 dark:text-gray-400">
              By proceeding you agree to keep this preview confidential.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function StaffLoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center p-6">Loading…</div>}>
      <StaffLoginInner />
    </Suspense>
  );
}

// Ensure this page is rendered dynamically to avoid prerender/export issues
export const dynamic = 'force-dynamic';
