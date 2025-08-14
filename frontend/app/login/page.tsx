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
  const { login: authLogin, checkAuth } = useAuth();
  const [formData, setFormData] = useState({
    email: '',
    password: '',
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

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
    // Clear error for this field when user starts typing
    if (errors[name]) {
      setErrors((prev) => ({
        ...prev,
        [name]: '',
      }));
    }
  };

  /**
   * Validate form inputs
   * @returns boolean indicating if form is valid
   */
  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!/\S+@\S+\.\S+/.test(formData.email)) {
      newErrors.email = 'Please enter a valid email';
    }

    if (!formData.password) {
      newErrors.password = 'Password is required';
    }

    setErrors(newErrors);

    if (Object.keys(newErrors).length > 0) {
      logger.debug('Login form validation failed', { errors: newErrors });
    }

    return Object.keys(newErrors).length === 0;
  };

  /**
   * Handle form submission
   * Authenticates user and redirects based on role
   */
  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setIsSubmitting(true);
    logger.info('Login attempt started', {
      email: formData.email,
      hasRedirect: redirect !== '/',
      redirectTo: redirect,
      API_URL,
      LOGIN_ENDPOINT: API_ENDPOINTS.LOGIN,
    });

    try {
      // Use the auth context login method
      const success = await authLogin(formData.email, formData.password);

      if (success) {
        logger.info('Login successful via auth context');

        // Force auth check to ensure state is updated
        await checkAuth();

        // Now navigate with updated auth state
        router.push(redirect);
      } else {
        logger.warn('Login failed - invalid credentials', {
          email: formData.email,
        });
        setErrors({ password: 'Invalid email or password' });
      }
    } catch (error) {
      logger.error('Login network error', error);
      setErrors({ password: 'Network error. Please check your connection and try again.' });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
      <div className="bg-white dark:bg-gray-800 py-8 px-4 shadow sm:rounded-lg sm:px-10">
        <div className="text-center mb-6">
          <Link href="/" onClick={() => logger.debug('Navigating to home from login inside box')}>
            <h1 className="text-3xl font-bold text-indigo-400">
              {BRAND.name}
            </h1>
          </Link>
        </div>
        <form className="space-y-6" onSubmit={handleSubmit} noValidate>
          {/* Email Field */}
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-gray-700 dark:text-gray-200"
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
                disabled={isSubmitting}
                className="appearance-none block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-gray-100 disabled:cursor-not-allowed bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 autofill-fix"
                placeholder="you@example.com"
              />
              {errors.email && (
                <p className="mt-1 text-sm text-red-600" role="alert">
                  {errors.email}
                </p>
              )}
            </div>
          </div>

          {/* Password Field */}
          <div>
            <label
              htmlFor="password"
              className="block text-sm font-medium text-gray-700 dark:text-gray-200"
            >
              Password
            </label>
            <div className="mt-1">
              <div className="relative">
                <input
                  id="password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  value={formData.password}
                  onChange={handleChange}
                  disabled={isSubmitting}
                  className="appearance-none block w-full px-3 py-2 h-10 pr-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-gray-100 disabled:cursor-not-allowed bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 autofill-fix"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
                  disabled={isSubmitting}
                >
                  {showPassword ? (
                    <EyeOff className="h-5 w-5" aria-hidden="true" />
                  ) : (
                    <Eye className="h-5 w-5" aria-hidden="true" />
                  )}
                </button>
              </div>
              {errors.password && (
                <p className="mt-1 text-sm text-red-600" role="alert">
                  {errors.password}
                </p>
              )}
            </div>
          </div>

          {/* Forgot Password Link */}
          <div className="flex items-center justify-between">
            <div className="text-sm">
              <Link
                href="/forgot-password"
                className="font-medium text-indigo-600 hover:text-indigo-500 transition-colors"
                onClick={() => logger.debug('Navigating to forgot password')}
              >
                Forgot your password?
              </Link>
            </div>
          </div>

          {/* Submit Button */}
          <div>
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isSubmitting ? (
                <>
                  <svg
                    className="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
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
                  Signing in...
                </>
              ) : (
                'Sign in'
              )}
            </button>
          </div>
        </form>

        {/* Sign Up Link */}
        <div className="mt-6 text-center">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Don't have an account?{' '}
            <Link
              href={`/signup${redirect !== '/' ? `?redirect=${encodeURIComponent(redirect)}` : ''}`}
              className="font-medium text-indigo-600 hover:text-indigo-500 transition-colors"
              onClick={() => logger.debug('Navigating to sign up', { preservedRedirect: redirect })}
            >
              Sign up
            </Link>
          </p>
        </div>
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
 * // Or with redirect: /login?redirect=/dashboard/instructor
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
