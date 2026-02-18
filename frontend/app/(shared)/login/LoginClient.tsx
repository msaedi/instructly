'use client';

import { BRAND } from '@/app/config/brand';
import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Eye, EyeOff } from 'lucide-react';
import { Turnstile, type TurnstileInstance } from '@marsidev/react-turnstile';
import { API_ENDPOINTS } from '@/lib/api';
import { ApiError, http, httpGet } from '@/lib/http';
import type { AuthUserResponse, InstructorProfile } from '@/features/shared/api/types';
import { logger } from '@/lib/logger';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { getGuestSessionId, transferGuestSearchesToAccount } from '@/lib/searchTracking';
import { TURNSTILE_SITE_KEY } from '@/lib/publicEnv';

function LoginForm({ redirect }: { redirect: string }) {
  const router = useRouter();
  const { checkAuth } = useAuth();
  const [formData, setFormData] = useState({
    email: '',
    password: '',
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [captchaRequired, setCaptchaRequired] = useState(false);
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [captchaError, setCaptchaError] = useState<string | null>(null);
  const turnstileRef = useRef<TurnstileInstance | null>(null);
  const [rateLimitedUntil, setRateLimitedUntil] = useState<number | null>(null);
  const [rateLimitSecondsRemaining, setRateLimitSecondsRemaining] = useState(0);

  const [requires2FA, setRequires2FA] = useState(false);
  const [tempToken, setTempToken] = useState<string | null>(null);
  const [twoFactorCode, setTwoFactorCode] = useState('');
  const [backupCode, setBackupCode] = useState('');
  const [trustThisBrowser, setTrustThisBrowser] = useState(false);
  const [isVerifying2FA, setIsVerifying2FA] = useState(false);

  type LoginResponseData = {
    requires_2fa?: boolean;
    temp_token?: string | null;
  };

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
    if (!formData['email'].trim()) newErrors['email'] = 'Email is required';
    else if (!/\S+@\S+\.\S+/.test(formData['email'])) newErrors['email'] = 'Please enter a valid email';
    if (!formData['password']) newErrors['password'] = 'Password is required';
    setErrors(newErrors);
    if (Object.keys(newErrors).length > 0) logger.debug('Login form validation failed', { errors: newErrors });
    return Object.keys(newErrors).length === 0;
  };

  const getButtonWaitLabel = (seconds: number): string => {
    if (seconds >= 120) {
      const minutes = Math.ceil(seconds / 60);
      return `Locked for ${minutes}m`;
    }
    return `Try again in ${seconds}s`;
  };

  useEffect(() => {
    if (!rateLimitedUntil) {
      setRateLimitSecondsRemaining(0);
      return;
    }

    const updateRemaining = () => {
      const remaining = Math.max(0, Math.ceil((rateLimitedUntil - Date.now()) / 1000));
      setRateLimitSecondsRemaining(remaining);
      if (remaining <= 0) {
        setRateLimitedUntil(null);
      }
    };

    updateRemaining();
    const interval = window.setInterval(updateRemaining, 1000);
    return () => window.clearInterval(interval);
  }, [rateLimitedUntil]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!validateForm()) return;

    setIsSubmitting(true);
    logger.info('Login attempt started', {
      email: formData.email,
      hasRedirect: redirect !== '/',
      redirectTo: redirect,
      LOGIN_ENDPOINT: API_ENDPOINTS.LOGIN,
    });

    try {
      const guestSessionId = getGuestSessionId();
      logger.info('Login attempt with guest session:', { guestSessionId, hasGuestSession: !!guestSessionId });

      const loginPath = guestSessionId ? '/api/v1/auth/login-with-session' : '/api/v1/auth/login';
      const headers = guestSessionId
        ? { 'Content-Type': 'application/json' }
        : { 'Content-Type': 'application/x-www-form-urlencoded' };

      const tokenForAttempt = captchaToken;

      const loginPayload = guestSessionId
        ? {
            email: formData['email'],
            password: formData['password'],
            guest_session_id: guestSessionId,
            ...(tokenForAttempt ? { captcha_token: tokenForAttempt } : {}),
          }
        : (() => {
            const params = new URLSearchParams({
              username: formData['email'],
              password: formData['password'],
            });
            if (tokenForAttempt) params.set('captcha_token', tokenForAttempt);
            return params.toString();
          })();

      logger.info('Sending login request:', {
        path: loginPath,
        hasGuestSession: !!guestSessionId,
        bodyPreview: guestSessionId ? { email: formData.email, guest_session_id: guestSessionId } : 'form-data',
      });

      const data = await http<LoginResponseData>('POST', loginPath, {
        headers,
        body: loginPayload,
      });

      if (data?.requires_2fa) {
        setRateLimitedUntil(null);
        setCaptchaRequired(false);
        setCaptchaToken(null);
        setCaptchaError(null);
        setRequires2FA(true);
        setTempToken(data?.temp_token ?? null);
        setIsSubmitting(false);
        return;
      }

      setRateLimitedUntil(null);
      setCaptchaRequired(false);
      setCaptchaToken(null);
      setCaptchaError(null);

      const transferGuestSession = getGuestSessionId();
      if (transferGuestSession) {
        logger.info('Initiating guest search transfer for session:', { guestSessionId: transferGuestSession });
        await transferGuestSearchesToAccount();
        logger.info('Guest search transfer completed after login');
      }

      await checkAuth();

      try {
        if (redirect && redirect !== '/' && !redirect.startsWith('/login')) {
          router.push(redirect);
          return;
        }

        const storedRedirect = typeof window !== 'undefined' ? sessionStorage.getItem('post_login_redirect') : null;
        if (storedRedirect && !storedRedirect.startsWith('/login')) {
          try {
            sessionStorage.removeItem('post_login_redirect');
          } catch {}
          router.push(storedRedirect);
          return;
        }

        const meUser = await httpGet<AuthUserResponse>(API_ENDPOINTS.ME);
        const roles = Array.isArray(meUser?.roles) ? meUser.roles : [];
        const isAdmin = roles.includes('admin');
        const isInstructor = roles.includes('instructor');

        if (isAdmin) {
          router.push('/admin/engineering/codebase');
        } else if (isInstructor) {
          try {
            const prof = await httpGet<InstructorProfile>(API_ENDPOINTS.INSTRUCTOR_PROFILE);
            const next = prof?.is_live ? '/instructor/dashboard' : '/instructor/onboarding/status';
            router.push(next);
          } catch (profileError) {
            logger.debug('Instructor profile lookup failed after login', profileError instanceof Error ? profileError : undefined);
            router.push('/instructor/onboarding/status');
          }
        } else {
          router.push('/');
        }
      } catch (routingError) {
        logger.debug('Post-login routing fallback', routingError instanceof Error ? routingError : undefined);
        router.push('/');
      }
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 429) {
          const retryAfterRaw = error.headers?.get('Retry-After') || '60';
          const parsedRetryAfter = Number.parseInt(retryAfterRaw, 10);
          const retryAfterSeconds =
            Number.isFinite(parsedRetryAfter) && parsedRetryAfter > 0 ? parsedRetryAfter : 60;
          const until = Date.now() + retryAfterSeconds * 1000;
          setRateLimitedUntil((prev) => (prev && prev > until ? prev : until));
          setErrors({});
          setCaptchaError(null);
          return;
        }

        if (error.status === 428) {
          setCaptchaRequired(true);
          setCaptchaToken(null);
          setCaptchaError('Please verify you\'re human to continue.');
          setErrors({});
          return;
        }

        const detail = (error.data as { detail?: string } | undefined)?.detail;
        if (error.status === 400 && detail?.toLowerCase().includes('captcha')) {
          setCaptchaRequired(true);
          setCaptchaToken(null);
          setCaptchaError(detail || 'CAPTCHA verification failed. Please try again.');
          setErrors({});
          return;
        }

        if (captchaRequired && captchaToken) {
          // Tokens are single-use; prompt for a fresh challenge on failure.
          setCaptchaToken(null);
          setCaptchaError('CAPTCHA required for further attempts. Please retry.');
          turnstileRef.current?.reset();
        }

        setErrors({ password: detail || 'Invalid email or password' });
      } else {
        logger.error('Login network error', error);
        setErrors({ password: 'Network error. Please check your connection and try again.' });
      }
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
    const sanitizedTwoFactor = twoFactorCode.trim();
    const sanitizedBackup = backupCode.trim();
    if (!sanitizedTwoFactor && !sanitizedBackup) {
      setErrors({ twofa: 'Enter a 6-digit code or a backup code' });
      return;
    }

    setIsVerifying2FA(true);
    try {
      await http('POST', '/api/v1/2fa/verify-login', {
        headers: {
          'Content-Type': 'application/json',
          'X-Trust-Browser': trustThisBrowser ? 'true' : 'false',
        },
        body: {
          temp_token: tempToken,
          code: sanitizedTwoFactor || undefined,
          backup_code: sanitizedBackup || undefined,
        },
      });
      if (trustThisBrowser) {
        try { sessionStorage.setItem('tfa_trusted', 'true'); } catch {}
      }
      await transferGuestSearchesToAccount();
      await checkAuth();
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
        const meUser = await httpGet<AuthUserResponse>(API_ENDPOINTS.ME);
        const roles = Array.isArray(meUser?.roles) ? meUser.roles : [];
        const isAdmin = roles.includes('admin');
        const isInstructor = roles.includes('instructor');
        if (isAdmin) {
          router.push('/admin/engineering/codebase');
        } else if (isInstructor) {
          try {
            const prof = await httpGet<InstructorProfile>(API_ENDPOINTS.INSTRUCTOR_PROFILE);
            const next = prof?.is_live ? '/instructor/dashboard' : '/instructor/onboarding/status';
            router.push(next);
          } catch (profileErr) {
            logger.debug('Instructor profile lookup failed after 2FA', profileErr instanceof Error ? profileErr : undefined);
            router.push('/instructor/onboarding/status');
          }
        } else {
          router.push('/student/lessons');
        }
      } catch (routingError) {
        logger.debug('Post-2FA routing fallback', routingError instanceof Error ? routingError : undefined);
        router.push('/student/lessons');
      }
    } catch (error) {
      if (error instanceof ApiError) {
        const detail = (error.data as { detail?: string } | undefined)?.detail;
        setErrors({ twofa: detail || 'Error verifying code. Please try again.' });
      } else {
        logger.error('2FA verification error', error);
        setErrors({ twofa: 'Network error verifying code' });
      }
    } finally {
      setIsVerifying2FA(false);
    }
  };

  const resolvedRedirect = redirect || '/';

  return (
    <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
      <div className="bg-white dark:bg-gray-800 py-8 px-4 shadow sm:rounded-lg sm:px-10">
        <div className="text-center mb-6">
          <Link href="/" onClick={() => logger.debug('Navigating to home from login inside box')}>
            <h1 className="text-4xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors">
              {BRAND.name}
            </h1>
          </Link>
        </div>
        {!requires2FA ? (
          <form method="POST" className="space-y-6" onSubmit={handleSubmit} noValidate>
            {/* Email Field */}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-gray-200">Email</label>
              <div className="mt-1">
                <input id="email" name="email" type="email" autoComplete="email" required value={formData.email} onChange={handleChange} disabled={isSubmitting} className="appearance-none block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-transparent focus:border-gray-300 disabled:bg-gray-100 disabled:cursor-not-allowed bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 autofill-fix" placeholder="you@example.com" />
                {errors['email'] && (<p className="mt-1 text-sm text-red-600" role="alert">{errors['email']}</p>)}
              </div>
            </div>
            {/* Password Field */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-gray-200">Password</label>
              <div className="mt-1">
                <div className="relative">
                  <input id="password" name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" required value={formData.password} onChange={handleChange} disabled={isSubmitting} className="appearance-none block w-full px-3 py-2 h-10 pr-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-transparent focus:border-gray-300 disabled:bg-gray-100 disabled:cursor-not-allowed bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 autofill-fix" placeholder="••••••••" />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 focus:outline-none focus-visible:outline-none focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:text-[#7E22CE]"
                    style={{ outline: 'none', boxShadow: 'none' }}
                    disabled={isSubmitting}
                  >
                    {showPassword ? (<EyeOff className="h-5 w-5" aria-hidden="true" />) : (<Eye className="h-5 w-5" aria-hidden="true" />)}
                  </button>
                </div>
                {errors['password'] && (<p className="mt-1 text-sm text-red-600" role="alert">{errors['password']}</p>)}
              </div>
            </div>
            {captchaRequired && (
              <div className="space-y-2">
                <p className="text-sm text-gray-700 dark:text-gray-200">Please verify you&apos;re human to continue.</p>
                {captchaError && (<p className="text-sm text-red-600" role="alert">{captchaError}</p>)}
                {TURNSTILE_SITE_KEY ? (
                  <Turnstile
                    siteKey={TURNSTILE_SITE_KEY}
                    ref={turnstileRef}
                    onSuccess={(token) => {
                      setCaptchaToken(token);
                      setCaptchaError(null);
                    }}
                    onError={() => {
                      setCaptchaToken(null);
                      setCaptchaError('CAPTCHA error. Please try again.');
                    }}
                    onExpire={() => {
                      setCaptchaToken(null);
                      setCaptchaError('CAPTCHA expired. Please retry.');
                    }}
                  />
                ) : (
                  <p className="text-sm text-red-600" role="alert">CAPTCHA is required but not configured.</p>
                )}
              </div>
            )}
            {/* Forgot Password */}
            <div className="flex items-center justify-between">
              <div className="text-sm">
                <Link href="/forgot-password" className="font-medium text-[#7E22CE] hover:text-[#7E22CE] transition-colors" onClick={() => logger.debug('Navigating to forgot password')}>
                  Forgot password
                </Link>
              </div>
            </div>
            {/* Submit */}
            <div>
              <button
                type="submit"
                disabled={isSubmitting || (captchaRequired && !captchaToken) || !!rateLimitedUntil}
                className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-[#7E22CE] hover:bg-[#7E22CE] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#7E22CE] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {rateLimitedUntil
                  ? getButtonWaitLabel(rateLimitSecondsRemaining)
                  : isSubmitting ? (
                    <>
                      <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                      Signing in...
                    </>
                  ) : (
                    'Sign in'
                  )}
              </button>
              {/* Single timer is shown on the button; no extra message needed */}
            </div>
          </form>
        ) : (
          <form method="POST" className="space-y-6" onSubmit={handleVerify2FA}>
            <div>
              <p className="text-sm text-gray-700">Enter your 6-digit authentication code or a backup code to continue.</p>
            </div>
            <div>
              <label htmlFor="twofa" className="block text-sm font-medium text-gray-700">6-digit code</label>
              <input id="twofa" inputMode="numeric" pattern="[0-9]*" maxLength={6} className="mt-1 block w-full px-3 py-2 h-10 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-[#7E22CE] focus:border-purple-500" value={twoFactorCode} onChange={(e) => setTwoFactorCode(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !isVerifying2FA && twoFactorCode.trim().length >= 6) { e.preventDefault(); void handleVerify2FA(); } }} placeholder="123 456" />
            </div>
            <div>
              <label htmlFor="backup" className="block text-sm font-medium text-gray-700">Backup code (optional)</label>
              <input id="backup" className="mt-1 block w-full px-3 py-2 h-10 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-[#7E22CE] focus:border-purple-500" value={backupCode} onChange={(e) => setBackupCode(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !isVerifying2FA && backupCode.trim().length > 0) { e.preventDefault(); void handleVerify2FA(); } }} placeholder="ABCD-EFGH-1234" />
            </div>
            <div className="flex items-center gap-2">
              <input id="trust" type="checkbox" className="h-4 w-4" checked={trustThisBrowser} onChange={(e) => setTrustThisBrowser(e.target.checked)} />
              <label htmlFor="trust" className="text-sm text-gray-700">Trust this browser</label>
            </div>
            {errors['twofa'] && (<p className="text-sm text-red-600" role="alert">{errors['twofa']}</p>)}
            <div>
              <button type="submit" disabled={isVerifying2FA} className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-[#7E22CE] hover:bg-[#7E22CE] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#7E22CE] disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                {isVerifying2FA ? 'Verifying…' : 'Verify & Continue'}
              </button>
            </div>
          </form>
        )}

        {!requires2FA && (
          <div className="mt-6 text-center">
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Don&apos;t have an account?{' '}
              <Link href={`/signup${resolvedRedirect !== '/' ? `?redirect=${encodeURIComponent(resolvedRedirect)}` : ''}`} className="font-medium text-[#7E22CE] hover:text-[#7E22CE] transition-colors" onClick={() => logger.debug('Navigating to sign up', { preservedRedirect: resolvedRedirect })}>
                Sign up
              </Link>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export function LoginClient({ redirect }: { redirect: string }) {
  logger.info('Login page loaded');
  return <LoginForm redirect={redirect} />;
}

export default LoginClient;
