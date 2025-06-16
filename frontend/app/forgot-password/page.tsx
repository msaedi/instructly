// frontend/app/forgot-password/page.tsx
"use client";

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

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Mail, ArrowLeft, CheckCircle } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { BRAND } from '@/app/config/brand';
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
  const [email, setEmail] = useState("");
  const [requestStatus, setRequestStatus] = useState<RequestStatus>(RequestStatus.IDLE);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  logger.debug('ForgotPasswordPage rendered', { 
    hasEmail: !!email,
    isSubmitted 
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
    setError("");
    
    // Validate email
    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail) {
      setError("Please enter your email address");
      logger.warn('Password reset validation failed: empty email');
      return;
    }
    
    if (!validateEmail(trimmedEmail)) {
      setError("Please enter a valid email address");
      logger.warn('Password reset validation failed: invalid email format', { email: trimmedEmail });
      return;
    }
    
    setRequestStatus(RequestStatus.LOADING);

    try {
      logger.time('passwordResetRequest');
      
      const requestData: PasswordResetRequest = {
        email: trimmedEmail
      };
      
      const response = await fetchAPI("/auth/password-reset/request", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(requestData),
      });

      logger.timeEnd('passwordResetRequest');

      if (!response.ok) {
        const data = await response.json();
        logger.warn('Password reset request failed', {
          status: response.status,
          email: trimmedEmail,
          error: data.detail
        });
        
        // Handle specific error cases
        if (response.status === 404) {
          throw new Error("No account found with this email address");
        } else if (response.status === 429) {
          throw new Error("Too many reset attempts. Please try again later");
        }
        
        throw new Error(data.detail || "Failed to send reset email");
      }

      logger.info('Password reset email sent successfully', { 
        email: trimmedEmail 
      });
      
      setRequestStatus(RequestStatus.SUCCESS);
      setIsSubmitted(true);
    } catch (err) {
      const errorMessage = getErrorMessage(err);
      logger.error('Password reset request error', err, {
        email: trimmedEmail,
        errorMessage
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
      setError("");
    }
  };

  /**
   * Navigate back to login page
   */
  const handleBackToLogin = () => {
    logger.info('Navigating back to login from forgot password');
    router.push("/login");
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
            <h1 className="text-3xl font-bold text-indigo-600 dark:text-indigo-400">
              {BRAND.name}
            </h1>
          </Link>
          
          <div className="bg-white dark:bg-gray-800 py-8 px-4 shadow sm:rounded-lg sm:px-10">
            <div className="text-center">
              <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-100 dark:bg-green-900/20 mb-4">
                <CheckCircle className="h-6 w-6 text-green-600 dark:text-green-400" aria-hidden="true" />
              </div>
              
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                Check your email
              </h2>
              
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
                We've sent a password reset link to{" "}
                <strong className="text-gray-900 dark:text-white">{email}</strong>
              </p>
              
              <p className="text-sm text-gray-500 dark:text-gray-500 mb-6">
                The link will expire in 1 hour. If you don't see the email, 
                check your spam folder.
              </p>
              
              <Link
                href="/login"
                className="text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300 font-medium"
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
          <h1 className="text-3xl font-bold text-indigo-600 dark:text-indigo-400">
            {BRAND.name}
          </h1>
        </Link>
        
        <h2 className="text-center text-3xl font-extrabold text-gray-900 dark:text-white">
          Forgot your password?
        </h2>
        <p className="mt-2 text-center text-sm text-gray-600 dark:text-gray-400">
          Enter your email and we'll send you a reset link
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white dark:bg-gray-800 py-8 px-4 shadow sm:rounded-lg sm:px-10">
          <form className="space-y-6" onSubmit={handleSubmit} noValidate>
            {/* Email Field */}
            <div>
              <label 
                htmlFor="email" 
                className="block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Email address
              </label>
              <div className="mt-1 relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Mail className="h-5 w-5 text-gray-400" aria-hidden="true" />
                </div>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={handleEmailChange}
                  disabled={isLoading}
                  className="appearance-none block w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white sm:text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  placeholder="Enter your email"
                  aria-invalid={!!error}
                  aria-describedby={error ? "email-error" : undefined}
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

            {/* Divider */}
            <div className="mt-6">
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-300 dark:border-gray-600" />
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="px-2 bg-white dark:bg-gray-800 text-gray-500">
                    Remember your password?
                  </span>
                </div>
              </div>

              {/* Back to Login Button */}
              <div className="mt-6">
                <button
                  type="button"
                  onClick={handleBackToLogin}
                  className="w-full flex items-center justify-center px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 dark:ring-offset-gray-800"
                >
                  <ArrowLeft className="w-4 h-4 mr-2" aria-hidden="true" />
                  Back to login
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}