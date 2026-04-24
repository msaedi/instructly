'use client';

/**
 * Reset Password Page
 *
 * This page handles the password reset process after a user clicks
 * the reset link in their email. It validates the reset token,
 * displays password requirements, and allows users to set a new password.
 * Includes real-time password strength validation and confirmation matching.
 */

import { useState, useEffect, useCallback, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Lock, Eye, EyeOff, CheckCircle, XCircle } from 'lucide-react';
import { fetchAPI } from '@/lib/api';
import type { PasswordResetConfirm } from '@/types/user';
import type { ApiErrorResponse, PasswordResetVerifyResponse } from '@/features/shared/api/types';
import { extractApiErrorMessage } from '@/lib/apiErrors';
import { RequestStatus } from '@/types/api';
import { getErrorMessage } from '@/types/common';
import { AuthShell } from '@/app/(shared)/_components/AuthShell';

interface PasswordValidations {
  minLength: boolean;
  hasUppercase: boolean;
  hasNumber: boolean;
}

function AuthSpinner({ label }: { label: string }) {
  return (
    <AuthShell>
      <div className="flex justify-center">
        <div
          className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-(--color-brand)"
          role="status"
          aria-label={label}
        />
      </div>
    </AuthShell>
  );
}

function StatusIcon({ type }: { type: 'success' | 'error' }) {
  const Icon = type === 'success' ? CheckCircle : XCircle;
  return (
    <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-(--color-brand-light)">
      <Icon className="h-6 w-6 text-(--color-brand)" aria-hidden="true" />
    </div>
  );
}

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get('token');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [requestStatus, setRequestStatus] = useState<RequestStatus>(RequestStatus.IDLE);
  const [isVerifying, setIsVerifying] = useState(true);
  const [tokenValid, setTokenValid] = useState(false);
  const [error, setError] = useState('');
  const [isSuccess, setIsSuccess] = useState(false);
  const [passwordValidations, setPasswordValidations] = useState<PasswordValidations>({
    minLength: false,
    hasUppercase: false,
    hasNumber: false,
  });

  const verifyToken = useCallback(async () => {
    if (!token) {
      setIsVerifying(false);
      return;
    }

    try {
      const response = await fetchAPI(`/api/v1/password-reset/verify/${token}`);
      const data: PasswordResetVerifyResponse = await response.json();
      if (data.valid) {
        setTokenValid(true);
      } else {
        setError('This reset link is invalid or has expired.');
      }
    } catch {
      setError('Failed to verify reset link.');
    } finally {
      setIsVerifying(false);
    }
  }, [token]);

  useEffect(() => {
    void verifyToken();
  }, [token, verifyToken]);

  useEffect(() => {
    setPasswordValidations({
      minLength: password.length >= 8,
      hasUppercase: /[A-Z]/.test(password),
      hasNumber: /[0-9]/.test(password),
    });
  }, [password]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    if (!Object.values(passwordValidations).every(Boolean)) {
      setError('Password does not meet all requirements');
      return;
    }

    setRequestStatus(RequestStatus.LOADING);
    try {
      const resetData: PasswordResetConfirm = {
        token: token!,
        new_password: password,
        password_confirm: confirmPassword,
      };
      const response = await fetchAPI('/api/v1/password-reset/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token: resetData.token,
          new_password: resetData.new_password,
        }),
      });

      if (!response.ok) {
        const data = (await response.json()) as ApiErrorResponse;
        if (response.status === 400 && typeof data.detail === 'string' && data.detail.includes('expired')) {
          throw new Error('This reset link has expired. Please request a new one.');
        }
        throw new Error(extractApiErrorMessage(data, 'Failed to reset password'));
      }

      setRequestStatus(RequestStatus.SUCCESS);
      setIsSuccess(true);
    } catch (err) {
      setError(getErrorMessage(err));
      setRequestStatus(RequestStatus.ERROR);
    }
  };

  const handleGoToLogin = () => {
    router.push('/login');
  };

  const isLoading = requestStatus === RequestStatus.LOADING;
  const isPasswordValid = Object.values(passwordValidations).every((value: boolean) => value);

  if (isVerifying) {
    return <AuthSpinner label="Verifying reset link" />;
  }

  if (!token || !tokenValid) {
    return (
      <AuthShell>
        <div className="text-center">
          <StatusIcon type="error" />
          <h2 className="mb-2 text-2xl font-bold text-gray-900 dark:text-gray-100">
            Invalid Reset Link
          </h2>
          <p className="mb-6 text-sm text-gray-600 dark:text-gray-400">
            {error || 'This password reset link is invalid or has expired.'}
          </p>
          <Link
            href="/forgot-password"
            className="font-medium text-(--color-brand) hover:text-purple-900 dark:hover:text-purple-300"
          >
            Request a new reset link
          </Link>
        </div>
      </AuthShell>
    );
  }

  if (isSuccess) {
    return (
      <AuthShell>
        <div className="text-center">
          <StatusIcon type="success" />
          <h2 className="mb-2 text-2xl font-bold text-gray-900 dark:text-gray-100">
            Password Reset Successful
          </h2>
          <p className="mb-6 text-sm text-gray-600 dark:text-gray-400">
            Your password has been successfully reset. You can now log in with your new password.
          </p>
          <button
            onClick={handleGoToLogin}
            className="insta-primary-btn w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white focus:outline-none dark:ring-offset-gray-800"
          >
            Go to Login
          </button>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Reset your password" subtitle="Choose a new password for your account.">
      <form method="POST" className="space-y-5 md:space-y-6" onSubmit={handleSubmit} noValidate>
        <div>
          <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-gray-300">New Password</label>
          <div className="mt-1 relative rounded-md border border-gray-300 dark:border-gray-600 shadow-sm bg-white dark:bg-gray-700 insta-focus-composite">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none"><Lock className="h-5 w-5 text-gray-400 dark:text-gray-300" aria-hidden="true" /></div>
            <input id="password" name="password" type={showPassword ? 'text' : 'password'} required value={password} onChange={(e) => setPassword(e.target.value)} disabled={isLoading} className="insta-focus-composite-input appearance-none block w-full pl-10 pr-10 py-2 border-0 rounded-md shadow-none placeholder-gray-400 dark:placeholder-gray-500 bg-transparent dark:text-white sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed" placeholder="Enter new password" aria-describedby="password-requirements" />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="insta-focus-icon-btn absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 focus-visible:outline-none"
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? (<EyeOff className="h-5 w-5 text-current" />) : (<Eye className="h-5 w-5 text-current" />)}
            </button>
          </div>
        </div>
        <div>
          <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Confirm New Password</label>
          <div className="mt-1 relative rounded-md border border-gray-300 dark:border-gray-600 shadow-sm bg-white dark:bg-gray-700 insta-focus-composite">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none"><Lock className="h-5 w-5 text-gray-400 dark:text-gray-300" aria-hidden="true" /></div>
            <input id="confirmPassword" name="confirmPassword" type={showConfirmPassword ? 'text' : 'password'} required value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} disabled={isLoading} className="insta-focus-composite-input appearance-none block w-full pl-10 pr-10 py-2 border-0 rounded-md shadow-none placeholder-gray-400 dark:placeholder-gray-500 bg-transparent dark:text-white sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed" placeholder="Confirm new password" />
            <button
              type="button"
              onClick={() => setShowConfirmPassword(!showConfirmPassword)}
              className="insta-focus-icon-btn absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 focus-visible:outline-none"
              aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
            >
              {showConfirmPassword ? (<EyeOff className="h-5 w-5 text-current" />) : (<Eye className="h-5 w-5 text-current" />)}
            </button>
          </div>
        </div>
        <div id="password-requirements" className="rounded-md bg-gray-50 dark:bg-gray-700 p-3">
          <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">Password must contain:</p>
          <ul className="text-xs space-y-1" role="list">
            <li className={`flex items-center ${passwordValidations.minLength ? 'text-green-600 dark:text-green-400' : 'text-gray-400 dark:text-gray-300'}`}>{passwordValidations.minLength ? '✓' : '○'} At least 8 characters</li>
            <li className={`flex items-center ${passwordValidations.hasUppercase ? 'text-green-600 dark:text-green-400' : 'text-gray-400 dark:text-gray-300'}`}>{passwordValidations.hasUppercase ? '✓' : '○'} One uppercase letter</li>
            <li className={`flex items-center ${passwordValidations.hasNumber ? 'text-green-600 dark:text-green-400' : 'text-gray-400 dark:text-gray-300'}`}>{passwordValidations.hasNumber ? '✓' : '○'} One number</li>
          </ul>
        </div>
        {error && (<div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4" role="alert"><p className="text-sm text-red-800 dark:text-red-400">{error}</p></div>)}
        <div>
          <button type="submit" disabled={isLoading || !isPasswordValid} className="insta-primary-btn w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed dark:ring-offset-gray-800">{isLoading ? 'Resetting...' : 'Reset Password'}</button>
        </div>
      </form>
    </AuthShell>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<AuthSpinner label="Loading" />}>
      <ResetPasswordForm />
    </Suspense>
  );
}
