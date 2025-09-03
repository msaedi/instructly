// frontend/app/(shared)/forgot-password/page.tsx
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { CheckCircle } from 'lucide-react';
import { fetchAPI } from '@/lib/api';
import { logger } from '@/lib/logger';
import type { PasswordResetRequest } from '@/types/user';
import { RequestStatus } from '@/types/api';
import { getErrorMessage } from '@/types/common';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [requestStatus, setRequestStatus] = useState<RequestStatus>(RequestStatus.IDLE);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [error, setError] = useState('');

  logger.debug('ForgotPasswordPage rendered', { hasEmail: !!email, isSubmitted });

  const validateEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    logger.info('Password reset requested', { email });
    setError('');

    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail) {
      setError('Please enter your email address');
      return;
    }
    if (!validateEmail(trimmedEmail)) {
      setError('Please enter a valid email address');
      return;
    }

    setRequestStatus(RequestStatus.LOADING);
    try {
      logger.time('passwordResetRequest');
      const requestData: PasswordResetRequest = { email: trimmedEmail };
      const response = await fetchAPI('/api/auth/password-reset/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestData),
      });
      logger.timeEnd('passwordResetRequest');

      if (!response.ok) {
        const data = await response.json();
        if (response.status === 404) throw new Error('No account found with this email address');
        if (response.status === 429) throw new Error('Too many reset attempts. Please try again later');
        throw new Error(data.detail || 'Failed to send reset email');
      }

      logger.info('Password reset email sent successfully', { email: trimmedEmail });
      setRequestStatus(RequestStatus.SUCCESS);
      setIsSubmitted(true);
    } catch (err) {
      const errorMessage = getErrorMessage(err);
      logger.error('Password reset request error', err as Error, { email: trimmedEmail, errorMessage });
      setError(errorMessage);
      setRequestStatus(RequestStatus.ERROR);
    }
  };

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setEmail(e.target.value);
    if (error) setError('');
  };

  const isLoading = requestStatus === RequestStatus.LOADING;

  if (isSubmitted && requestStatus === RequestStatus.SUCCESS) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          <Link href="/" className="flex justify-center mb-6">
            <h1 className="text-4xl font-bold text-[#6A0DAD] dark:text-purple-400">iNSTAiNSTRU</h1>
          </Link>
          <div className="bg-white dark:bg-gray-800 p-8 shadow sm:rounded-lg">
            <div className="text-center">
              <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-100 dark:bg-green-900/20 mb-4">
                <CheckCircle className="h-6 w-6 text-green-600 dark:text-green-400" aria-hidden="true" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Check your email</h2>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
                We&apos;ve sent a password reset link to <strong className="text-gray-900 dark:text-white">{email}</strong>
              </p>
              <p className="text-sm text-gray-500 dark:text-gray-500 mb-6">The link will expire in 1 hour.</p>
              <Link href="/login" className="text-[#6A0DAD] hover:text-purple-600 dark:text-purple-400 dark:hover:text-purple-300 font-medium">
                Back to login
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <Link href="/" className="flex justify-center mb-6">
          <h1 className="text-4xl font-bold text-[#6A0DAD] dark:text-purple-400">iNSTAiNSTRU</h1>
        </Link>
        <h2 className="text-center text-3xl font-extrabold text-gray-900 dark:text-white">Forgot your password?</h2>
        <p className="mt-2 text-center text-sm text-gray-600 dark:text-gray-400">Enter your email and we&apos;ll send you a reset link</p>
      </div>
      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white dark:bg-gray-800 p-8 shadow sm:rounded-lg">
          <form className="space-y-6" onSubmit={handleSubmit} noValidate>
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Email</label>
              <div className="mt-1">
                <input id="email" name="email" type="email" autoComplete="email" required value={email} onChange={handleEmailChange} disabled={isLoading}
                  className="appearance-none block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-[#6A0DAD] focus:border-purple-500 dark:bg-gray-700 dark:text-white sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  placeholder="Enter your email" aria-invalid={!!error} aria-describedby={error ? 'email-error' : undefined} />
              </div>
            </div>
            {error && (
              <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4" role="alert">
                <p id="email-error" className="text-sm text-red-800 dark:text-red-400">{error}</p>
              </div>
            )}
            <div>
              <button type="submit" disabled={isLoading}
                className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-[#6A0DAD] hover:bg-[#6A0DAD] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#6A0DAD] disabled:opacity-50 disabled:cursor-not-allowed dark:ring-offset-gray-800">
                {isLoading ? (
                  <>
                    <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
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
