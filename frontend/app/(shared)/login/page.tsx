// frontend/app/login/page.tsx
'use client';

import { BRAND } from '@/app/config/brand';
import { useState, Suspense, type ChangeEvent, type FormEvent } from 'react';
import Link from 'next/link';
// Background handled globally via GlobalBackground
import { useRouter, useSearchParams } from 'next/navigation';
import { Eye, EyeOff } from 'lucide-react';
import { API_URL, API_ENDPOINTS, fetchWithAuth } from '@/lib/api';
import { logger } from '@/lib/logger';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { getGuestSessionId, transferGuestSearchesToAccount } from '@/lib/searchTracking';
import { withApiBase } from '@/lib/apiBase';

/**
 * LoginForm Component
 *
 * Handles user authentication with email/password credentials.
 * Supports role-based redirection and custom redirect URLs.
 *
 * Features:
 * - Email and password validation
 * - Role-based redirection (instructor vs student)
 * - Custom redirect URL support via query parameter
 * - Error handling for invalid credentials and network errors
 * - Forgot password link
 * - Sign up link with redirect preservation
 * - Two-step 2FA support (TOTP or backup code)
 *
 * Security considerations:
 * - Uses OAuth2 password flow with form data
 * - Stores JWT token in localStorage
 * - Validates email format client-side
 *
 * @component
 */
function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = searchParams.get('redirect') || searchParams.get('returnTo') || '/';
  const { checkAuth } = useAuth();
  const [formData, setFormData] = useState({
    email: '',
    password: '',
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // 2FA state
  const [requires2FA, setRequires2FA] = useState(false);
  const [tempToken, setTempToken] = useState<string | null>(null);
  const [twoFactorCode, setTwoFactorCode] = useState('');
  const [backupCode, setBackupCode] = useState('');
  const [trustThisBrowser, setTrustThisBrowser] = useState(false);
  const [isVerifying2FA, setIsVerifying2FA] = useState(false);

  /**
   * Handle form input changes
   */
  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    const nextValue = name === 'email' ? value.toLowerCase() : value;
    setFormData((prev) => ({
      ...prev,
      [name]: nextValue,
    }));
    if (errors[name]) setErrors((prev) => ({ ...prev, [name]: '' }));
  };

  const validateForm = () => {
    const newErrors: Record<string, string> = {};
    if (!formData.email.trim()) newErrors.email = 'Email is required';
    else if (!/\S+@\S+\.\S+/.test(formData.email)) newErrors.email = 'Please enter a valid email';
    if (!formData.password) newErrors.password = 'Password is required';
    setErrors(newErrors);
    if (Object.keys(newErrors).length > 0) logger.debug('Login form validation failed', { errors: newErrors });
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!validateForm()) return;

    setIsSubmitting(true);
    logger.info('Login attempt started', {
      email: formData.email,
      hasRedirect: redirect !== '/',
      redirectTo: redirect,
      API_URL,
      LOGIN_ENDPOINT: API_ENDPOINTS.LOGIN,
    });

    try {
      // Get guest session ID if available
      const guestSessionId = getGuestSessionId();
      logger.info('Login attempt with guest session:', { guestSessionId, hasGuestSession: !!guestSessionId });

      // Determine endpoint and body based on guest session
      const loginPath = guestSessionId ? '/auth/login-with-session' : '/auth/login';
      const apiPath = withApiBase(loginPath);
      const endpoint = typeof window !== 'undefined'
        ? new URL(apiPath, window.location.origin).toString()
        : `${API_URL}${loginPath}`;

      const body = guestSessionId
        ? JSON.stringify({
            email: formData.email,
            password: formData.password,
            guest_session_id: guestSessionId,
          })
        : new URLSearchParams({ username: formData.email, password: formData.password }).toString();

      const headers = guestSessionId
        ? { 'Content-Type': 'application/json' }
        : { 'Content-Type': 'application/x-www-form-urlencoded' };

      logger.info('Sending login request:', {
        endpoint,
        hasGuestSession: !!guestSessionId,
        bodyPreview: guestSessionId ? { email: formData.email, guest_session_id: guestSessionId } : 'form-data'
      });

      const res = await fetch(endpoint, {
        method: 'POST',
        headers,
        body,
        credentials: 'include',
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setErrors({ password: body.detail || 'Invalid email or password' });
        return;
      }

      const data = await res.json();
      // 2FA required?
      if (data.requires_2fa) {
        setRequires2FA(true);
        setTempToken(data.temp_token || null);
        setIsSubmitting(false);
        return;
      }

      // No 2FA: cookie-based session; do not write tokens to localStorage

      // Transfer guest searches if we had a guest session
      const transferGuestSession = getGuestSessionId();
      if (transferGuestSession) {
        logger.info('Initiating guest search transfer for session:', { guestSessionId: transferGuestSession });
        await transferGuestSearchesToAccount();
        logger.info('Guest search transfer completed after login');
      }

      await checkAuth();
      // Decide post-login route: respect explicit redirect; otherwise use session fallback; else role-based
      try {
        if (redirect && redirect !== '/' && !redirect.startsWith('/login')) {
          router.push(redirect);
          return;
        }
        // Session fallback set by guards/helpers
        const storedRedirect = typeof window !== 'undefined' ? sessionStorage.getItem('post_login_redirect') : null;
        if (storedRedirect && !storedRedirect.startsWith('/login')) {
          try { sessionStorage.removeItem('post_login_redirect'); } catch {}
          router.push(storedRedirect);
          return;
        }
        // Determine role first
        const meUserRes = await fetchWithAuth(API_ENDPOINTS.ME);
        const meUser = meUserRes.ok ? await meUserRes.json() : null;
        const roles = Array.isArray(meUser?.roles) ? meUser.roles : [];
        const isAdmin = roles.includes('admin');
        const isInstructor = roles.includes('instructor');

        if (isAdmin) {
          router.push('/admin/analytics/codebase');
        } else if (isInstructor) {
          // Probe instructor profile; if exists and is_live => dashboard, else status
          const me = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);
          if (me.ok) {
            const prof = await me.json();
            const next = prof?.is_live ? '/instructor/dashboard' : '/instructor/onboarding/status';
            router.push(next);
          } else {
            router.push('/instructor/onboarding/status');
          }
        } else {
          // Student (or non-instructor) default landing
          router.push('/');
        }
      } catch {
        router.push('/');
      }
    } catch (error) {
      logger.error('Login network error', error);
      setErrors({ password: 'Network error. Please check your connection and try again.' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleVerify2FA = async (e?: FormEvent) => {
    if (e) e.preventDefault();
    if (!tempToken) {
      setErrors({ password: 'Invalid 2FA session. Please try logging in again.' });
      return;
    }
    if (!twoFactorCode.trim() && !backupCode.trim()) {
      setErrors({ twofa: 'Enter a 6-digit code or a backup code' });
      return;
    }

    setIsVerifying2FA(true);
    try {
      const res = await fetch(
        `${API_URL}/api/auth/2fa/verify-login`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Trust-Browser': trustThisBrowser ? 'true' : 'false' },
          body: JSON.stringify({ temp_token: tempToken, code: twoFactorCode || undefined, backup_code: backupCode || undefined }),
          credentials: 'include',
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setErrors({ twofa: body.detail || "That code didn’t work. Please check the 6‑digit code or use a backup code." });
        setIsVerifying2FA(false);
        return;
      }
      // Cookie-based session; do not write tokens to localStorage
      if (trustThisBrowser) {
        try { sessionStorage.setItem('tfa_trusted', 'true'); } catch {}
      }
      await checkAuth();
      // Decide post-login route after 2FA
      try {
        if (redirect && redirect !== '/' && !redirect.startsWith('/login')) {
          router.push(redirect);
          return;
        }
        const storedRedirect = typeof window !== 'undefined' ? sessionStorage.getItem('post_login_redirect') : null;
        if (storedRedirect && !storedRedirect.startsWith('/login')) {
          try { sessionStorage.removeItem('post_login_redirect'); } catch {}
          router.push(storedRedirect);
          return;
        }
        const meUserRes = await fetchWithAuth(API_ENDPOINTS.ME);
        const meUser = meUserRes.ok ? await meUserRes.json() : null;
        const roles = Array.isArray(meUser?.roles) ? meUser.roles : [];
        const isAdmin = roles.includes('admin');
        const isInstructor = roles.includes('instructor');
        if (isAdmin) {
          router.push('/admin/analytics/codebase');
        } else if (isInstructor) {
          const me = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);
          if (me.ok) {
            const prof = await me.json();
            const next = prof?.is_live ? '/instructor/dashboard' : '/instructor/onboarding/status';
            router.push(next);
          } else {
            router.push('/instructor/onboarding/status');
          }
        } else {
          router.push('/student/lessons');
        }
      } catch {
        router.push('/student/lessons');
      }
    } catch (err) {
      logger.error('2FA verification error', err);
      setErrors({ twofa: 'Network error verifying code' });
    } finally {
      setIsVerifying2FA(false);
    }
  };

  return (
    <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
      <div className="bg-white dark:bg-gray-800 py-8 px-4 shadow sm:rounded-lg sm:px-10">
        <div className="text-center mb-6">
          <Link href="/" onClick={() => logger.debug('Navigating to home from login inside box')}>
            <h1 className="text-4xl font-bold text-[#6A0DAD] hover:text-[#6A0DAD] transition-colors">
              {BRAND.name}
            </h1>
          </Link>
        </div>
        {!requires2FA ? (
          <form className="space-y-6" onSubmit={handleSubmit} noValidate>
            {/* Email Field */}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-gray-200">Email</label>
              <div className="mt-1">
                <input id="email" name="email" type="email" autoComplete="email" required value={formData.email} onChange={handleChange} disabled={isSubmitting} className="appearance-none block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-[#6A0DAD] focus:border-purple-500 disabled:bg-gray-100 disabled:cursor-not-allowed bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 autofill-fix" placeholder="you@example.com" />
                {errors.email && (<p className="mt-1 text-sm text-red-600" role="alert">{errors.email}</p>)}
              </div>
            </div>
            {/* Password Field */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-gray-200">Password</label>
              <div className="mt-1">
                <div className="relative">
                  <input id="password" name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" required value={formData.password} onChange={handleChange} disabled={isSubmitting} className="appearance-none block w-full px-3 py-2 h-10 pr-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-[#6A0DAD] focus:border-purple-500 disabled:bg-gray-100 disabled:cursor-not-allowed bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 autofill-fix" placeholder="••••••••" />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300" disabled={isSubmitting}>
                    {showPassword ? (<EyeOff className="h-5 w-5" aria-hidden="true" />) : (<Eye className="h-5 w-5" aria-hidden="true" />)}
                  </button>
                </div>
                {errors.password && (<p className="mt-1 text-sm text-red-600" role="alert">{errors.password}</p>)}
              </div>
            </div>
            {/* Forgot Password */}
            <div className="flex items-center justify-between">
              <div className="text-sm">
                <Link href="/forgot-password" className="font-medium text-[#6A0DAD] hover:text-[#6A0DAD] transition-colors" onClick={() => logger.debug('Navigating to forgot password')}>
                  Forgot password
                </Link>
              </div>
            </div>
            {/* Submit */}
            <div>
              <button type="submit" disabled={isSubmitting} className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-[#6A0DAD] hover:bg-[#6A0DAD] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#6A0DAD] disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                {isSubmitting ? (<><svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>Signing in...</>) : ('Sign in')}
              </button>
            </div>
          </form>
        ) : (
          <form className="space-y-6" onSubmit={handleVerify2FA}>
            <div>
              <p className="text-sm text-gray-700">Enter your 6-digit authentication code or a backup code to continue.</p>
            </div>
            <div>
              <label htmlFor="twofa" className="block text-sm font-medium text-gray-700">6-digit code</label>
              <input id="twofa" inputMode="numeric" pattern="[0-9]*" maxLength={6} className="mt-1 block w-full px-3 py-2 h-10 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-[#6A0DAD] focus:border-purple-500" value={twoFactorCode} onChange={(e) => setTwoFactorCode(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !isVerifying2FA && twoFactorCode.trim().length >= 6) { e.preventDefault(); handleVerify2FA(); } }} placeholder="123 456" />
            </div>
            <div>
              <label htmlFor="backup" className="block text-sm font-medium text-gray-700">Backup code (optional)</label>
              <input id="backup" className="mt-1 block w-full px-3 py-2 h-10 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-[#6A0DAD] focus:border-purple-500" value={backupCode} onChange={(e) => setBackupCode(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !isVerifying2FA && backupCode.trim().length > 0) { e.preventDefault(); handleVerify2FA(); } }} placeholder="ABCD-EFGH-1234" />
            </div>
            <div className="flex items-center gap-2">
              <input id="trust" type="checkbox" className="h-4 w-4" checked={trustThisBrowser} onChange={(e) => setTrustThisBrowser(e.target.checked)} />
              <label htmlFor="trust" className="text-sm text-gray-700">Trust this browser</label>
            </div>
            {errors.twofa && (<p className="text-sm text-red-600" role="alert">{errors.twofa}</p>)}
            <div>
              <button type="submit" disabled={isVerifying2FA} className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-[#6A0DAD] hover:bg-[#6A0DAD] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#6A0DAD] disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                {isVerifying2FA ? 'Verifying…' : 'Verify & Continue'}
              </button>
            </div>
          </form>
        )}

        {/* Sign Up Link (hidden during 2FA step) */}
        {!requires2FA && (
          <div className="mt-6 text-center">
            <p className="text-sm text-gray-600 dark:text-gray-400">
            Don&apos;t have an account?{' '}
              <Link href={`/signup${redirect !== '/' ? `?redirect=${encodeURIComponent(redirect)}` : ''}`} className="font-medium text-[#6A0DAD] hover:text-[#6A0DAD] transition-colors" onClick={() => logger.debug('Navigating to sign up', { preservedRedirect: redirect })}>
                Sign up
              </Link>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Login Page Component
 *
 * Main login page with InstaInstru branding and login form.
 * Uses Suspense for better loading experience with dynamic imports.
 *
 * @component
 * @example
 * ```tsx
 * // Access directly via /login
 * // Or with redirect: /login?redirect=/instructor/dashboard
 * ```
 */
export default function Login() {
  logger.info('Login page loaded');
  // Background handled globally

  return (
    <div className="min-h-screen flex flex-col justify-center py-12 sm:px-6 lg:px-8 relative">
      <div className="relative z-10">
      <Suspense
        fallback={
          <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
            <div className="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10">
              <div className="animate-pulse">
                <div className="h-10 bg-gray-200 rounded mb-4"></div>
                <div className="h-10 bg-gray-200 rounded mb-4"></div>
                <div className="h-10 bg-gray-200 rounded"></div>
              </div>
            </div>
          </div>
        }
      >
        <LoginForm />
      </Suspense>
      </div>
    </div>
  );
}
