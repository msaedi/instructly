'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { API_ENDPOINTS } from '@/lib/api';
import { logger } from '@/lib/logger';
import { ApiError, http, httpPost } from '@/lib/http';
import { getGuestSessionId } from '@/lib/searchTracking';
import { buildAuthHref, claimReferralCode } from '@/features/referrals/referralAuth';
import { BRAND } from '@/app/config/brand';
import { useAuth } from '@/features/shared/hooks/useAuth';
import {
  buildRegistrationPayload,
  clearPendingSignup,
  readPendingSignup,
  updatePendingSignupVerificationToken,
  type PendingSignupData,
} from '@/features/shared/auth/pendingSignup';
import { RoleName } from '@/types/enums';

type ApiProblemPayload = {
  code?: unknown;
  errors?: Record<string, unknown>;
};

function maskEmailAddress(email: string): string {
  const [localPart, domain] = email.split('@');
  if (!localPart || !domain) {
    return email;
  }

  if (localPart.length <= 2) {
    return `${localPart[0] ?? '*'}*@${domain}`;
  }

  return `${localPart.slice(0, 2)}${'*'.repeat(Math.max(localPart.length - 2, 2))}@${domain}`;
}

function getProblemPayload(error: ApiError): ApiProblemPayload {
  const data = error.data;
  if (!data || typeof data !== 'object') {
    return {};
  }

  const record = data as Record<string, unknown>;
  const payload: ApiProblemPayload = {};

  if ('code' in record) {
    payload.code = record['code'];
  }

  if (record['errors'] && typeof record['errors'] === 'object') {
    payload.errors = record['errors'] as Record<string, unknown>;
  }

  return payload;
}

function buildSignupBackHref(pendingSignup: PendingSignupData): string {
  const params = new URLSearchParams();
  params.set('redirect', pendingSignup.redirect);
  params.set('email', pendingSignup.email);
  if (pendingSignup.role === RoleName.INSTRUCTOR) {
    params.set('role', 'instructor');
  }
  if (pendingSignup.referralCode) {
    params.set('ref', pendingSignup.referralCode);
  }
  if (pendingSignup.founding) {
    params.set('founding', 'true');
  }
  if (pendingSignup.inviteCode) {
    params.set('invite_code', pendingSignup.inviteCode);
  }
  return `/signup?${params.toString()}`;
}

function getPostSignupDestination(pendingSignup: PendingSignupData): string {
  if (pendingSignup.redirect && pendingSignup.redirect !== '/') {
    return pendingSignup.redirect;
  }

  return pendingSignup.role === RoleName.INSTRUCTOR
    ? '/instructor/onboarding/welcome'
    : '/';
}

export function VerifyEmailPageContent() {
  const router = useRouter();
  const { checkAuth } = useAuth();
  const [pendingSignup, setPendingSignup] = useState<PendingSignupData | null>(null);
  const [code, setCode] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(30);

  useEffect(() => {
    setPendingSignup(readPendingSignup());
  }, []);

  useEffect(() => {
    if (resendCooldown <= 0) {
      return;
    }

    const timer = window.setTimeout(() => {
      setResendCooldown((value) => Math.max(0, value - 1));
    }, 1000);

    return () => window.clearTimeout(timer);
  }, [resendCooldown]);

  const maskedEmail = useMemo(
    () => (pendingSignup ? maskEmailAddress(pendingSignup.email) : ''),
    [pendingSignup]
  );

  const handleResendCode = async () => {
    if (!pendingSignup || resendCooldown > 0 || resending) {
      return;
    }

    setResending(true);
    setErrorMessage(null);
    setStatusMessage(null);

    try {
      await httpPost<{ message: string }>(API_ENDPOINTS.SEND_EMAIL_VERIFICATION, {
        email: pendingSignup.email,
      });
      setResendCooldown(30);
      setStatusMessage('A fresh verification code is on its way.');
    } catch (error) {
      const message =
        error instanceof ApiError || error instanceof Error
          ? error.message
          : 'Unable to resend the verification code.';
      setErrorMessage(message);
    } finally {
      setResending(false);
    }
  };

  const handleWrongEmail = () => {
    if (!pendingSignup) {
      router.push('/signup');
      return;
    }

    router.push(buildSignupBackHref(pendingSignup));
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!pendingSignup) {
      setErrorMessage('Your signup details have expired. Please start again.');
      return;
    }

    if (code.trim().length !== 6) {
      setErrorMessage('Enter the 6-digit verification code.');
      return;
    }

    setSubmitting(true);
    setErrorMessage(null);
    setStatusMessage(null);

    try {
      const verificationResponse = await httpPost<{
        verification_token: string;
        expires_in_seconds: number;
      }>(API_ENDPOINTS.VERIFY_EMAIL_CODE, {
        email: pendingSignup.email,
        code: code.trim(),
      });

      const verifiedPendingSignup = updatePendingSignupVerificationToken(
        verificationResponse.verification_token
      );

      if (!verifiedPendingSignup) {
        throw new Error('Your signup details have expired. Please start again.');
      }

      const guestSessionId = getGuestSessionId();
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
      const registrationPayload = buildRegistrationPayload(
        verifiedPendingSignup,
        guestSessionId,
        timezone
      );

      await httpPost<{ message: string }>(API_ENDPOINTS.REGISTER, registrationPayload);

      clearPendingSignup();
      if (typeof window !== 'undefined') {
        try {
          window.sessionStorage.removeItem('invite_code');
        } catch {
          // Ignore sessionStorage failures after successful registration.
        }
      }

      const loginPath = guestSessionId
        ? '/api/v1/auth/login-with-session'
        : API_ENDPOINTS.LOGIN;
      const loginHeaders = guestSessionId
        ? { 'Content-Type': 'application/json' }
        : { 'Content-Type': 'application/x-www-form-urlencoded' };
      const loginPayload = guestSessionId
        ? {
            email: verifiedPendingSignup.email,
            password: verifiedPendingSignup.password,
            guest_session_id: guestSessionId,
          }
        : new URLSearchParams({
            username: verifiedPendingSignup.email,
            password: verifiedPendingSignup.password,
          }).toString();

      try {
        await http('POST', loginPath, {
          headers: loginHeaders,
          body: loginPayload,
        });
      } catch (error) {
        if (error instanceof ApiError) {
          logger.error('Auto-login failed after verified signup', error, {
            status: error.status,
          });
          router.push(
            buildAuthHref('/login', {
              redirect: verifiedPendingSignup.redirect || '/',
              ref: verifiedPendingSignup.referralCode,
              registered: true,
            })
          );
          return;
        }
        throw error;
      }

      if (verifiedPendingSignup.referralCode) {
        await claimReferralCode(verifiedPendingSignup.referralCode);
      }

      await checkAuth();
      router.push(getPostSignupDestination(verifiedPendingSignup));
    } catch (error) {
      if (error instanceof ApiError) {
        const payload = getProblemPayload(error);
        const remainingAttempts = payload.errors?.['remaining_attempts'];
        const expired = payload.errors?.['expired'];

        if (typeof remainingAttempts === 'number') {
          setErrorMessage(`${error.message} ${remainingAttempts} attempt${remainingAttempts === 1 ? '' : 's'} remaining.`);
        } else if (expired === true) {
          setErrorMessage('Code expired. Resend for a new one.');
        } else if (payload.code === 'EMAIL_VERIFICATION_LOCKED') {
          setErrorMessage('Too many attempts. Please wait 10 minutes before trying again.');
        } else {
          setErrorMessage(error.message);
        }
      } else if (error instanceof Error) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage('An unexpected error occurred.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (!pendingSignup) {
    return (
      <div className="min-h-screen px-4 sm:px-6 lg:px-8 flex items-center justify-center">
        <div className="w-full sm:max-w-md sm:mx-auto">
          <div className="insta-surface-card py-8 px-6 sm:px-10 sm:shadow">
            <div className="text-center">
              <h1 className="text-4xl font-bold text-(--color-brand)">{BRAND.name}</h1>
              <h2 className="mt-6 text-2xl font-bold text-gray-900 dark:text-gray-100">
                Start again
              </h2>
              <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                We couldn&apos;t find your pending signup details.
              </p>
              <Link
                href="/signup"
                className="mt-6 inline-flex items-center justify-center rounded-md bg-(--color-brand) px-4 py-2 text-sm font-semibold text-white transition hover:bg-purple-800 focus:outline-none "
              >
                Back to signup
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen px-4 sm:px-6 lg:px-8 flex items-center justify-center">
      <div className="w-full sm:max-w-md sm:mx-auto">
        <div className="insta-surface-card py-8 px-6 sm:px-10 sm:shadow">
          <div className="text-center">
            <Link href="/">
              <h1 className="text-4xl font-bold text-(--color-brand) hover:text-purple-900 dark:hover:text-purple-300 transition-colors">
                {BRAND.name}
              </h1>
            </Link>
            <h2 className="mt-6 text-2xl font-bold text-gray-900 dark:text-gray-100">
              Verify your email
            </h2>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
              We sent a 6-digit code to <span className="font-semibold text-gray-900 dark:text-gray-100">{maskedEmail}</span>.
            </p>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              This code expires in 5 minutes.
            </p>
          </div>

          <form className="mt-8 space-y-5" onSubmit={handleSubmit} noValidate>
            <div className="sr-only" role="status" aria-live="polite">
              {[errorMessage, statusMessage].filter(Boolean).join('. ')}
            </div>

            {errorMessage ? (
              <div role="alert" className="rounded-md bg-red-50 p-4 dark:bg-red-900/20">
                <p className="text-sm text-red-800 dark:text-red-300">{errorMessage}</p>
              </div>
            ) : null}

            {statusMessage ? (
              <div className="rounded-md bg-emerald-50 p-4 dark:bg-emerald-900/20">
                <p className="text-sm text-emerald-800 dark:text-emerald-300">{statusMessage}</p>
              </div>
            ) : null}

            <div>
              <label
                htmlFor="verification-code"
                className="block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Verification code
              </label>
              <input
                id="verification-code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                maxLength={6}
                value={code}
                onChange={(event) => {
                  setCode(event.target.value.replace(/\D/g, ''));
                  setErrorMessage(null);
                }}
                className="mx-auto mt-2 block w-full max-w-[220px] rounded-md border border-gray-300 px-3 py-2 text-center tracking-[0.35em] text-2xl font-semibold text-gray-900 shadow-sm focus:border-(--color-focus-brand) focus:outline-none   dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                aria-invalid={Boolean(errorMessage)}
              />
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="insta-primary-btn flex w-full items-center justify-center rounded-md px-4 py-2 text-sm font-semibold text-white focus:outline-none  disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? 'Verifying…' : 'Verify and continue'}
            </button>

            <div className="flex items-center justify-between gap-3 text-sm">
              <button
                type="button"
                onClick={() => void handleResendCode()}
                disabled={resending || resendCooldown > 0}
                className={`font-medium ${
                  resending || resendCooldown > 0
                    ? 'text-gray-400 dark:text-gray-500'
                    : 'text-(--color-brand) hover:text-purple-900 dark:text-purple-400 dark:hover:text-purple-300'
                }`}
              >
                {resending
                  ? 'Sending…'
                  : resendCooldown > 0
                    ? `Resend in ${resendCooldown}s`
                    : 'Resend code'}
              </button>
              <button
                type="button"
                onClick={handleWrongEmail}
                className="font-medium text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white"
              >
                Wrong email? Go back
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return <VerifyEmailPageContent />;
}
