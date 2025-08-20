// frontend/app/forgot-password/page.tsx
'use client';

/**
 * Forgot Password Page
 *
 * This page allows users to request a password reset link via email.
 * Users enter their email address and receive instructions to reset
 * their password. The page shows a success message after submission
 * to inform users to check their email.
 *
 * @module forgot-password/page
 */

import { useState } from 'react';
import Link from 'next/link';
import { CheckCircle } from 'lucide-react';
import { fetchAPI } from '@/lib/api';
import { logger } from '@/lib/logger';

// Import centralized types
import type { PasswordResetRequest } from '@/types/user';
import { RequestStatus } from '@/types/api';
import { getErrorMessage } from '@/types/common';

/**
 * Forgot Password Page Component
 *
 * Handles password reset requests by sending reset links to user emails
 *
 * @component
 * @returns {JSX.Element} The forgot password page
 */
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [requestStatus, setRequestStatus] = useState<RequestStatus>(RequestStatus.IDLE);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [error, setError] = useState('');

  logger.debug('ForgotPasswordPage rendered', {
    hasEmail: !!email,
    isSubmitted,
  });

  /**
   * Validate email format
   *
   * @param {string} email - Email to validate
   * @returns {boolean} True if email is valid
   */
  const validateEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  };

  /**
   * Handle form submission for password reset request
   *
   * @param {React.FormEvent} e - Form event
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    logger.info('Password reset requested', { email });

    // Reset previous errors
    setError('');

    // Validate email
    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail) {
      setError('Please enter your email address');
      logger.warn('Password reset validation failed: empty email');
      return;
    }

    if (!validateEmail(trimmedEmail)) {
      setError('Please enter a valid email address');
      logger.warn('Password reset validation failed: invalid email format', {
        email: trimmedEmail,
      });
      return;
    }

    setRequestStatus(RequestStatus.LOADING);

    try {
      logger.time('passwordResetRequest');

      const requestData: PasswordResetRequest = {
        email: trimmedEmail,
      };

      const response = await fetchAPI('/api/auth/password-reset/request', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestData),
      });

      logger.timeEnd('passwordResetRequest');

      if (!response.ok) {
        const data = await response.json();
        logger.warn('Password reset request failed', {
          status: response.status,
          email: trimmedEmail,
          error: data.detail,
        });

        // Handle specific error cases
        if (response.status === 404) {
          throw new Error('No account found with this email address');
        } else if (response.status === 429) {
          throw new Error('Too many reset attempts. Please try again later');
        }

        throw new Error(data.detail || 'Failed to send reset email');
      }

      logger.info('Password reset email sent successfully', {
        email: trimmedEmail,
      });

      setRequestStatus(RequestStatus.SUCCESS);
      setIsSubmitted(true);
    } catch (err) {
      const errorMessage = getErrorMessage(err);
      logger.error('Password reset request error', err, {
        email: trimmedEmail,
        errorMessage,
      });

      setError(errorMessage);
      setRequestStatus(RequestStatus.ERROR);
    }
  };

  /**
   * Handle email input change
   *
   * @param {React.ChangeEvent<HTMLInputElement>} e - Change event
   */
  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newEmail = e.target.value;
    setEmail(newEmail);

    // Clear error when user starts typing
    if (error) {
      setError('');
    }
  };


  const isLoading = requestStatus === RequestStatus.LOADING;

  // Success state - show confirmation message
  if (isSubmitted && requestStatus === RequestStatus.SUCCESS) {
    logger.debug('Rendering password reset success state');

    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          <Link
            href="/"
            className="flex justify-center mb-6"
            onClick={() => logger.info('Navigating to home from password reset success')}
          >
            <h1 className="text-4xl font-bold text-purple-700 dark:text-purple-400">
              iNSTAiNSTRU
            </h1>
          </Link>

          <div className="bg-white dark:bg-gray-800 p-8 shadow sm:rounded-lg">
            <div className="text-center">
              <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-100 dark:bg-green-900/20 mb-4">
                <CheckCircle
                  className="h-6 w-6 text-green-600 dark:text-green-400"
                  aria-hidden="true"
                />
              </div>

              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                Check your email
              </h2>

              <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
                We've sent a password reset link to{' '}
                <strong className="text-gray-900 dark:text-white">{email}</strong>
              </p>

              <p className="text-sm text-gray-500 dark:text-gray-500 mb-6">
                The link will expire in 1 hour. If you don't see the email, check your spam folder.
              </p>

              <Link
                href="/login"
                className="text-purple-700 hover:text-purple-600 dark:text-purple-400 dark:hover:text-purple-300 font-medium"
                onClick={() => logger.info('Navigating to login from password reset success')}
              >
                Back to login
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Main form state
  logger.debug('Rendering password reset form');

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <Link
          href="/"
          className="flex justify-center mb-6"
          onClick={() => logger.info('Navigating to home from forgot password')}
        >
          <h1 className="text-4xl font-bold text-purple-700 dark:text-purple-400">iNSTAiNSTRU</h1>
        </Link>

        <h2 className="text-center text-3xl font-extrabold text-gray-900 dark:text-white">
          Forgot your password?
        </h2>
        <p className="mt-2 text-center text-sm text-gray-600 dark:text-gray-400">
          Enter your email and we'll send you a reset link
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white dark:bg-gray-800 p-8 shadow sm:rounded-lg">
          {/* Bio Section */}
          <div className="mb-8 pb-8 border-b border-gray-200 dark:border-gray-700">
            <div className="text-center">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                Secure Password Recovery
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                We take your security seriously. Enter the email address associated with your account,
                and we'll send you a secure link to reset your password. The link will expire in 1 hour
                for your protection.
              </p>
            </div>
          </div>

          <form className="space-y-6" onSubmit={handleSubmit} noValidate>
            {/* Email Field */}
            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Email
              </label>
              <div className="mt-1">
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={handleEmailChange}
                  disabled={isLoading}
                  className="appearance-none block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-purple-500 focus:border-purple-500 dark:bg-gray-700 dark:text-white sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  placeholder="Enter your email"
                  aria-invalid={!!error}
                  aria-describedby={error ? 'email-error' : undefined}
                />
              </div>
            </div>

            {/* Error Message */}
            {error && (
              <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4" role="alert">
                <p id="email-error" className="text-sm text-red-800 dark:text-red-400">
                  {error}
                </p>
              </div>
            )}

            {/* Submit Button */}
            <div>
              <button
                type="submit"
                disabled={isLoading}
                className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-purple-700 hover:bg-purple-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-purple-500 disabled:opacity-50 disabled:cursor-not-allowed dark:ring-offset-gray-800"
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
                    Sending...
                  </>
                ) : (
                  'Send reset link'
                )}
              </button>
            </div>

          </form>
        </div>
      </div>
    </div>
  );
}
