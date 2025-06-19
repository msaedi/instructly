// frontend/app/signup/page.tsx
'use client';

/**
 * User Registration Page
 *
 * This page handles new user registration for the platform.
 * Users can create a student account and are automatically logged in
 * upon successful registration. The page supports redirect parameters
 * to return users to their intended destination after signup.
 *
 * @module signup/page
 */

import { useState, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { API_URL, API_ENDPOINTS, fetchWithAuth } from '@/lib/api';
import { BRAND } from '@/app/config/brand';
import { logger } from '@/lib/logger';

// Import centralized types
import type { RegisterRequest, AuthResponse, UserData } from '@/types/user';
import { UserRole, isInstructorUser } from '@/types/user';
import { RequestStatus } from '@/types/api';
import { getErrorMessage } from '@/types/common';

/**
 * Form validation errors interface
 */
interface FormErrors {
  fullName?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
  general?: string;
}

/**
 * Signup form component with validation and auto-login
 *
 * @component
 * @returns {JSX.Element} The signup form
 */
function SignUpForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = searchParams.get('redirect') || '/';

  const [formData, setFormData] = useState({
    fullName: '',
    email: '',
    password: '',
    confirmPassword: '',
  });
  const [errors, setErrors] = useState<FormErrors>({});
  const [requestStatus, setRequestStatus] = useState<RequestStatus>(RequestStatus.IDLE);

  logger.debug('SignUpForm initialized', {
    redirectTo: redirect,
    hasRedirect: redirect !== '/',
  });

  /**
   * Handle form input changes
   *
   * @param {React.ChangeEvent<HTMLInputElement>} e - Change event
   */
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));

    // Clear error for this field when user types
    if (errors[name as keyof FormErrors]) {
      setErrors((prev) => ({
        ...prev,
        [name]: undefined,
      }));
    }
  };

  /**
   * Validate form data before submission
   *
   * @returns {boolean} True if form is valid
   */
  const validateForm = (): boolean => {
    logger.debug('Validating signup form');
    const newErrors: FormErrors = {};

    if (!formData.fullName.trim()) {
      newErrors.fullName = 'Full name is required';
    } else if (formData.fullName.trim().length < 2) {
      newErrors.fullName = 'Full name must be at least 2 characters';
    }

    if (!formData.email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!/\S+@\S+\.\S+/.test(formData.email)) {
      newErrors.email = 'Please enter a valid email';
    }

    if (!formData.password) {
      newErrors.password = 'Password is required';
    } else if (formData.password.length < 8) {
      newErrors.password = 'Password must be at least 8 characters';
    }

    if (formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    setErrors(newErrors);
    const isValid = Object.keys(newErrors).length === 0;

    logger.debug('Form validation result', {
      isValid,
      errorCount: Object.keys(newErrors).length,
      errors: Object.keys(newErrors),
    });

    return isValid;
  };

  /**
   * Handle form submission
   *
   * @param {React.FormEvent} e - Form event
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    logger.info('Signup form submitted');

    if (!validateForm()) {
      logger.warn('Signup form validation failed');
      return;
    }

    setRequestStatus(RequestStatus.LOADING);
    setErrors({});

    try {
      // Prepare registration data
      const registrationData: RegisterRequest = {
        full_name: formData.fullName.trim(),
        email: formData.email.trim().toLowerCase(),
        password: formData.password,
        role: UserRole.STUDENT,
      };

      logger.info('Attempting user registration', {
        email: registrationData.email,
        role: registrationData.role,
      });
      logger.time('registration');

      // Register the user
      const response = await fetch(`${API_URL}${API_ENDPOINTS.REGISTER}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(registrationData),
      });

      logger.timeEnd('registration');

      if (!response.ok) {
        const errorData = await response.json();
        logger.warn('Registration failed', {
          status: response.status,
          error: errorData.detail,
        });

        // Handle specific error cases
        if (response.status === 400 && errorData.detail?.includes('already registered')) {
          throw new Error('An account with this email already exists');
        }

        throw new Error(errorData.detail || 'Registration failed');
      }

      logger.info('Registration successful, attempting auto-login');

      // Auto-login after successful registration
      logger.time('auto-login');
      const loginResponse = await fetch(`${API_URL}${API_ENDPOINTS.LOGIN}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          username: formData.email,
          password: formData.password,
        }),
      });
      logger.timeEnd('auto-login');

      if (!loginResponse.ok) {
        logger.error('Auto-login failed after registration', null, {
          status: loginResponse.status,
        });
        // Registration succeeded but login failed - redirect to login
        router.push(`/login?redirect=${encodeURIComponent(redirect)}`);
        return;
      }

      const authData: AuthResponse = await loginResponse.json();
      localStorage.setItem('access_token', authData.access_token);
      logger.info('Auto-login successful, fetching user data');

      // Fetch user data to determine redirect
      const userResponse = await fetch(`${API_URL}${API_ENDPOINTS.ME}`, {
        headers: {
          Authorization: `Bearer ${authData.access_token}`,
        },
      });

      if (userResponse.ok) {
        const userData: UserData = await userResponse.json();
        logger.info('User data fetched, redirecting based on role', {
          userId: userData.id,
          role: userData.role,
          redirectTo: isInstructorUser(userData) ? '/dashboard/instructor' : redirect,
        });

        // Redirect based on role
        if (isInstructorUser(userData)) {
          router.push('/dashboard/instructor');
        } else {
          router.push(redirect);
        }
      } else {
        logger.warn('Failed to fetch user data after login, using default redirect');
        router.push(redirect);
      }

      setRequestStatus(RequestStatus.SUCCESS);
    } catch (error) {
      const errorMessage = getErrorMessage(error);
      logger.error('Signup process failed', error, {
        email: formData.email,
        errorMessage,
      });

      setErrors({ general: errorMessage });
      setRequestStatus(RequestStatus.ERROR);
    }
  };

  const isLoading = requestStatus === RequestStatus.LOADING;

  return (
    <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
      <div className="bg-white dark:bg-gray-800 py-8 px-4 shadow sm:rounded-lg sm:px-10">
        <form className="space-y-6" onSubmit={handleSubmit} noValidate>
          {/* General error message */}
          {errors.general && (
            <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
              <p className="text-sm text-red-800 dark:text-red-400">{errors.general}</p>
            </div>
          )}

          {/* Full Name Field */}
          <div>
            <label
              htmlFor="fullName"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Full Name
            </label>
            <div className="mt-1">
              <input
                id="fullName"
                name="fullName"
                type="text"
                autoComplete="name"
                required
                value={formData.fullName}
                onChange={handleChange}
                disabled={isLoading}
                className="appearance-none block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed"
                aria-invalid={!!errors.fullName}
                aria-describedby={errors.fullName ? 'fullName-error' : undefined}
              />
              {errors.fullName && (
                <p id="fullName-error" className="mt-1 text-sm text-red-600 dark:text-red-400">
                  {errors.fullName}
                </p>
              )}
            </div>
          </div>

          {/* Email Field */}
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Email address
            </label>
            <div className="mt-1">
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={formData.email}
                onChange={handleChange}
                disabled={isLoading}
                className="appearance-none block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed"
                aria-invalid={!!errors.email}
                aria-describedby={errors.email ? 'email-error' : undefined}
              />
              {errors.email && (
                <p id="email-error" className="mt-1 text-sm text-red-600 dark:text-red-400">
                  {errors.email}
                </p>
              )}
            </div>
          </div>

          {/* Password Field */}
          <div>
            <label
              htmlFor="password"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Password
            </label>
            <div className="mt-1">
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="new-password"
                required
                value={formData.password}
                onChange={handleChange}
                disabled={isLoading}
                className="appearance-none block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed"
                aria-invalid={!!errors.password}
                aria-describedby={errors.password ? 'password-error' : 'password-hint'}
              />
              {errors.password && (
                <p id="password-error" className="mt-1 text-sm text-red-600 dark:text-red-400">
                  {errors.password}
                </p>
              )}
              <p id="password-hint" className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Password must be at least 8 characters long
              </p>
            </div>
          </div>

          {/* Confirm Password Field */}
          <div>
            <label
              htmlFor="confirmPassword"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Confirm Password
            </label>
            <div className="mt-1">
              <input
                id="confirmPassword"
                name="confirmPassword"
                type="password"
                autoComplete="new-password"
                required
                value={formData.confirmPassword}
                onChange={handleChange}
                disabled={isLoading}
                className="appearance-none block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed"
                aria-invalid={!!errors.confirmPassword}
                aria-describedby={errors.confirmPassword ? 'confirmPassword-error' : undefined}
              />
              {errors.confirmPassword && (
                <p
                  id="confirmPassword-error"
                  className="mt-1 text-sm text-red-600 dark:text-red-400"
                >
                  {errors.confirmPassword}
                </p>
              )}
            </div>
          </div>

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
                  Creating account...
                </>
              ) : (
                'Sign up'
              )}
            </button>
          </div>
        </form>

        {/* Login Link */}
        <div className="mt-6 text-center">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Already have an account?{' '}
            <Link
              href={`/login${redirect !== '/' ? `?redirect=${encodeURIComponent(redirect)}` : ''}`}
              className="font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300"
              onClick={() => logger.info('Navigating to login from signup', { redirect })}
            >
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

/**
 * Main signup page component
 *
 * @component
 * @returns {JSX.Element} The signup page
 */
export default function SignUp() {
  logger.debug('SignUp page rendered');

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <Link
          href="/"
          className="flex justify-center"
          onClick={() => logger.info('Navigating to home from signup')}
        >
          <h1 className="text-3xl font-bold text-indigo-600 dark:text-indigo-400">{BRAND.name}</h1>
        </Link>
        <h2 className="mt-6 text-center text-2xl font-bold text-gray-900 dark:text-white">
          Create your account
        </h2>
      </div>

      <Suspense
        fallback={
          <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
            <div className="bg-white dark:bg-gray-800 py-8 px-4 shadow sm:rounded-lg sm:px-10">
              <div className="animate-pulse">
                <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded mb-4"></div>
                <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded mb-4"></div>
                <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded mb-4"></div>
                <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded"></div>
              </div>
            </div>
          </div>
        }
      >
        <SignUpForm />
      </Suspense>
    </div>
  );
}
