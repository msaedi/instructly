// frontend/app/login/page.tsx
'use client';

import { BRAND } from '@/app/config/brand';
import { useState, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { API_URL, API_ENDPOINTS, fetchWithAuth } from '@/lib/api';
import { logger } from '@/lib/logger';

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
  const redirect = searchParams.get('redirect') || '/';
  const [formData, setFormData] = useState({
    email: '',
    password: '',
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  /**
   * Handle form input changes
   */
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
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
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setIsSubmitting(true);
    logger.info('Login attempt', {
      email: formData.email,
      hasRedirect: redirect !== '/',
      redirectTo: redirect,
    });

    try {
      // FastAPI expects form data for OAuth2
      const params = new URLSearchParams();
      params.append('username', formData.email); // OAuth2 expects 'username'
      params.append('password', formData.password);

      const response = await fetch(`${API_URL}${API_ENDPOINTS.LOGIN}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: params,
      });

      if (response.ok) {
        const data = await response.json();

        // Store token in localStorage
        localStorage.setItem('access_token', data.access_token);
        logger.info('Login successful, token stored');

        // Fetch user data to get their role
        try {
          const userResponse = await fetchWithAuth(API_ENDPOINTS.ME);
          if (userResponse.ok) {
            const userData = await userResponse.json();

            logger.info('User data fetched', {
              role: userData.role,
              userId: userData.id,
            });

            // Redirect based on role
            if (userData.role === 'instructor') {
              logger.debug('Redirecting to instructor dashboard');
              router.push('/dashboard/instructor');
            } else {
              logger.debug('Redirecting to specified location', { redirect });
              router.push(redirect); // Use the redirect parameter for students
            }
          } else {
            logger.warn('Failed to fetch user data after login, using fallback redirect');
            // Fallback to redirect parameter if user fetch fails
            router.push(redirect);
          }
        } catch (userError) {
          logger.error('Error fetching user data after login', userError);
          // Fallback redirect
          router.push(redirect);
        }
      } else {
        // Handle login failure
        if (response.status === 401) {
          logger.warn('Login failed - invalid credentials', {
            email: formData.email,
          });
          setErrors({ password: 'Invalid email or password' });
        } else {
          logger.error('Login failed - server error', {
            status: response.status,
            statusText: response.statusText,
          });
          setErrors({ password: 'Server error. Please try again later.' });
        }
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
      <div className="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10">
        <form className="space-y-6" onSubmit={handleSubmit} noValidate>
          {/* Email Field */}
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700">
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
                className="appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
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
            <label htmlFor="password" className="block text-sm font-medium text-gray-700">
              Password
            </label>
            <div className="mt-1">
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={formData.password}
                onChange={handleChange}
                disabled={isSubmitting}
                className="appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
                placeholder="••••••••"
              />
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
          <p className="text-sm text-gray-600">
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

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <Link
          href="/"
          className="flex justify-center"
          onClick={() => logger.debug('Navigating to home from login')}
        >
          <h1 className="text-3xl font-bold text-indigo-600 hover:text-indigo-700 transition-colors">
            {BRAND.name}
          </h1>
        </Link>
        <h2 className="mt-6 text-center text-2xl font-bold text-gray-900">
          Sign in to your account
        </h2>
      </div>

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
  );
}
