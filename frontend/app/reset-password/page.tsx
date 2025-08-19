// frontend/app/reset-password/page.tsx
'use client';

/**
 * Reset Password Page
 *
 * This page handles the password reset process after a user clicks
 * the reset link in their email. It validates the reset token,
 * displays password requirements, and allows users to set a new password.
 * Includes real-time password strength validation and confirmation matching.
 *
 * @module reset-password/page
 */

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Lock, Eye, EyeOff, CheckCircle, XCircle } from 'lucide-react';
import { fetchAPI } from '@/lib/api';
import { BRAND } from '@/app/config/brand';
import { logger } from '@/lib/logger';

// Import centralized types
import type { PasswordResetConfirm } from '@/types/user';
import { RequestStatus } from '@/types/api';
import { getErrorMessage } from '@/types/common';

/**
 * Password validation requirements interface
 */
interface PasswordValidations {
  minLength: boolean;
  hasUppercase: boolean;
  hasNumber: boolean;
}

/**
 * Token validation response interface
 */
interface TokenValidationResponse {
  valid: boolean;
  email?: string;
  error?: string;
}

/**
 * Reset Password Form Component
 *
 * Handles token validation and password reset submission
 *
 * @component
 * @returns {JSX.Element} The reset password form
 */
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
  const [maskedEmail, setMaskedEmail] = useState('');
  const [error, setError] = useState('');
  const [isSuccess, setIsSuccess] = useState(false);

  // Password validation states
  const [passwordValidations, setPasswordValidations] = useState<PasswordValidations>({
    minLength: false,
    hasUppercase: false,
    hasNumber: false,
  });

  logger.debug('ResetPasswordForm initialized', {
    hasToken: !!token,
    tokenLength: token?.length,
  });

  /**
   * Verify reset token validity
   */
  const verifyToken = async () => {
    if (!token) {
      logger.warn('No reset token provided in URL');
      setIsVerifying(false);
      return;
    }

    logger.info('Verifying password reset token', {
      tokenPrefix: token.substring(0, 8) + '...',
    });

    try {
      logger.time('tokenVerification');
      const response = await fetchAPI(`/api/auth/password-reset/verify/${token}`);
      const data: TokenValidationResponse = await response.json();
      logger.timeEnd('tokenVerification');

      if (data.valid) {
        logger.info('Reset token validated successfully', {
          maskedEmail: data.email,
        });
        setTokenValid(true);
        setMaskedEmail(data.email || '');
      } else {
        logger.warn('Reset token invalid or expired', {
          error: data.error,
        });
        setError('This reset link is invalid or has expired.');
      }
    } catch (err) {
      logger.error('Failed to verify reset token', err, {
        token: token.substring(0, 8) + '...',
      });
      setError('Failed to verify reset link.');
    } finally {
      setIsVerifying(false);
    }
  };

  useEffect(() => {
    verifyToken();
  }, [token]);

  useEffect(() => {
    // Validate password as user types
    const validations: PasswordValidations = {
      minLength: password.length >= 8,
      hasUppercase: /[A-Z]/.test(password),
      hasNumber: /[0-9]/.test(password),
    };

    setPasswordValidations(validations);

    logger.debug('Password validation updated', {
      passwordLength: password.length,
      validations,
    });
  }, [password]);

  /**
   * Handle form submission
   *
   * @param {React.FormEvent} e - Form event
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    logger.info('Password reset form submitted');

    setError('');

    // Validate passwords match
    if (password !== confirmPassword) {
      const errorMsg = 'Passwords do not match';
      logger.warn('Password reset validation failed', { error: errorMsg });
      setError(errorMsg);
      return;
    }

    // Validate password requirements
    const allValid = Object.values(passwordValidations).every((v) => v);
    if (!allValid) {
      const errorMsg = 'Password does not meet all requirements';
      logger.warn('Password reset validation failed', {
        error: errorMsg,
        validations: passwordValidations,
      });
      setError(errorMsg);
      return;
    }

    setRequestStatus(RequestStatus.LOADING);

    try {
      logger.info('Submitting password reset', {
        tokenPrefix: token?.substring(0, 8) + '...',
      });
      logger.time('passwordReset');

      const resetData: PasswordResetConfirm = {
        token: token!,
        new_password: password,
        password_confirm: confirmPassword,
      };

      const response = await fetchAPI('/api/auth/password-reset/confirm', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          token: resetData.token,
          new_password: resetData.new_password,
        }),
      });

      logger.timeEnd('passwordReset');

      if (!response.ok) {
        const data = await response.json();
        logger.warn('Password reset failed', {
          status: response.status,
          error: data.detail,
        });

        // Handle specific error cases
        if (response.status === 400 && data.detail?.includes('expired')) {
          throw new Error('This reset link has expired. Please request a new one.');
        }

        throw new Error(data.detail || 'Failed to reset password');
      }

      logger.info('Password reset successful');
      setRequestStatus(RequestStatus.SUCCESS);
      setIsSuccess(true);
    } catch (err) {
      const errorMessage = getErrorMessage(err);
      logger.error('Password reset error', err, { errorMessage });

      setError(errorMessage);
      setRequestStatus(RequestStatus.ERROR);
    }
  };

  /**
   * Navigate to login page
   */
  const handleGoToLogin = () => {
    logger.info('Navigating to login from password reset');
    router.push('/login');
  };

  const isLoading = requestStatus === RequestStatus.LOADING;

  // Loading state while verifying token
  if (isVerifying) {
    logger.debug('Rendering token verification loading state');
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div
          className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"
          role="status"
          aria-label="Verifying reset link"
        ></div>
      </div>
    );
  }

  // Invalid or missing token state
  if (!token || !tokenValid) {
    logger.debug('Rendering invalid token state');
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          <Link
            href="/"
            className="flex justify-center mb-6"
            onClick={() => logger.info('Navigating to home from invalid token page')}
          >
            <h1 className="text-3xl font-bold text-indigo-600 dark:text-indigo-400">
              {BRAND.name}
            </h1>
          </Link>

          <div className="bg-white dark:bg-gray-800 py-8 px-4 shadow sm:rounded-lg sm:px-10">
            <div className="text-center">
              <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-red-100 dark:bg-red-900/20 mb-4">
                <XCircle className="h-6 w-6 text-red-600 dark:text-red-400" aria-hidden="true" />
              </div>

              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                Invalid Reset Link
              </h2>

              <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
                {error || 'This password reset link is invalid or has expired.'}
              </p>

              <Link
                href="/forgot-password"
                className="text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300 font-medium"
                onClick={() => logger.info('Navigating to forgot password from invalid token')}
              >
                Request a new reset link
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Success state
  if (isSuccess) {
    logger.debug('Rendering password reset success state');
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          <Link
            href="/"
            className="flex justify-center mb-6"
            onClick={() => logger.info('Navigating to home from reset success')}
          >
            <h1 className="text-3xl font-bold text-indigo-600 dark:text-indigo-400">
              {BRAND.name}
            </h1>
          </Link>

          <div className="bg-white dark:bg-gray-800 py-8 px-4 shadow sm:rounded-lg sm:px-10">
            <div className="text-center">
              <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-100 dark:bg-green-900/20 mb-4">
                <CheckCircle
                  className="h-6 w-6 text-green-600 dark:text-green-400"
                  aria-hidden="true"
                />
              </div>

              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                Password Reset Successful
              </h2>

              <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
                Your password has been successfully reset. You can now log in with your new
                password.
              </p>

              <button
                onClick={handleGoToLogin}
                className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 dark:ring-offset-gray-800"
              >
                Go to Login
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Main reset form
  logger.debug('Rendering password reset form');
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <Link
          href="/"
          className="flex justify-center mb-6"
          onClick={() => logger.info('Navigating to home from reset form')}
        >
          <h1 className="text-3xl font-bold text-indigo-600 dark:text-indigo-400">{BRAND.name}</h1>
        </Link>

        <h2 className="text-center text-3xl font-extrabold text-gray-900 dark:text-white">
          Reset your password
        </h2>
        {maskedEmail && (
          <p className="mt-2 text-center text-sm text-gray-600 dark:text-gray-400">
            for {maskedEmail}
          </p>
        )}
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white dark:bg-gray-800 py-8 px-4 shadow sm:rounded-lg sm:px-10">
          <form className="space-y-6" onSubmit={handleSubmit} noValidate>
            {/* New Password Field */}
            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                New Password
              </label>
              <div className="mt-1 relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Lock className="h-5 w-5 text-gray-400" aria-hidden="true" />
                </div>
                <input
                  id="password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isLoading}
                  className="appearance-none block w-full pl-10 pr-10 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  placeholder="Enter new password"
                  aria-describedby="password-requirements"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? (
                    <EyeOff className="h-5 w-5 text-gray-400" />
                  ) : (
                    <Eye className="h-5 w-5 text-gray-400" />
                  )}
                </button>
              </div>
            </div>

            {/* Confirm Password Field */}
            <div>
              <label
                htmlFor="confirmPassword"
                className="block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Confirm New Password
              </label>
              <div className="mt-1 relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Lock className="h-5 w-5 text-gray-400" aria-hidden="true" />
                </div>
                <input
                  id="confirmPassword"
                  name="confirmPassword"
                  type={showConfirmPassword ? 'text' : 'password'}
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  disabled={isLoading}
                  className="appearance-none block w-full pl-10 pr-10 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  placeholder="Confirm new password"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center"
                  aria-label={
                    showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'
                  }
                >
                  {showConfirmPassword ? (
                    <EyeOff className="h-5 w-5 text-gray-400" />
                  ) : (
                    <Eye className="h-5 w-5 text-gray-400" />
                  )}
                </button>
              </div>
            </div>

            {/* Password requirements */}
            <div id="password-requirements" className="rounded-md bg-gray-50 dark:bg-gray-700 p-3">
              <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
                Password must contain:
              </p>
              <ul className="text-xs space-y-1" role="list">
                <li
                  className={`flex items-center ${
                    passwordValidations.minLength
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-gray-400'
                  }`}
                  aria-label={`At least 8 characters: ${
                    passwordValidations.minLength ? 'requirement met' : 'requirement not met'
                  }`}
                >
                  {passwordValidations.minLength ? '✓' : '○'} At least 8 characters
                </li>
                <li
                  className={`flex items-center ${
                    passwordValidations.hasUppercase
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-gray-400'
                  }`}
                  aria-label={`One uppercase letter: ${
                    passwordValidations.hasUppercase ? 'requirement met' : 'requirement not met'
                  }`}
                >
                  {passwordValidations.hasUppercase ? '✓' : '○'} One uppercase letter
                </li>
                <li
                  className={`flex items-center ${
                    passwordValidations.hasNumber
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-gray-400'
                  }`}
                  aria-label={`One number: ${
                    passwordValidations.hasNumber ? 'requirement met' : 'requirement not met'
                  }`}
                >
                  {passwordValidations.hasNumber ? '✓' : '○'} One number
                </li>
              </ul>
            </div>

            {/* Error Message */}
            {error && (
              <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4" role="alert">
                <p className="text-sm text-red-800 dark:text-red-400">{error}</p>
              </div>
            )}

            {/* Submit Button */}
            <div>
              <button
                type="submit"
                disabled={isLoading || !Object.values(passwordValidations).every((v) => v)}
                className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed dark:ring-offset-gray-800"
              >
                {isLoading ? (
                  <>
                    <svg
                      className="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                      aria-hidden="true"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      ></circle>
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      ></path>
                    </svg>
                    Resetting...
                  </>
                ) : (
                  'Reset Password'
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

/**
 * Main Reset Password Page Component
 *
 * @component
 * @returns {JSX.Element} The reset password page with suspense boundary
 */
export default function ResetPasswordPage() {
  logger.debug('ResetPasswordPage rendered');

  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
          <div
            className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"
            role="status"
            aria-label="Loading"
          ></div>
        </div>
      }
    >
      <ResetPasswordForm />
    </Suspense>
  );
}
