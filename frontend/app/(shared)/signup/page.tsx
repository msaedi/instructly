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

import { useEffect, useState, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Eye, EyeOff } from 'lucide-react';
import { API_ENDPOINTS, checkIsNYCZip } from '@/lib/api';
import { BRAND } from '@/app/config/brand';
import { logger } from '@/lib/logger';
import { ApiError, http, httpGet, httpPost } from '@/lib/http';
import { getGuestSessionId } from '@/lib/searchTracking';
import { useBetaConfig } from '@/lib/beta-config';
// Background handled globally via GlobalBackground

// Import centralized types
import { RequestStatus } from '@/types/api';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { hasRole } from '@/features/shared/hooks/useAuth.helpers';
import { RoleName } from '@/types/enums';
import type { AuthUserResponse, components } from '@/features/shared/api/types';

/**
 * Form validation errors interface
 */
interface FormErrors {
  firstName?: string;
  lastName?: string;
  email?: string;
  phone?: string;
  zipCode?: string;
  password?: string;
  confirmPassword?: string;
  general?: string;
}

/**
 * Format phone number for display
 */
function formatPhoneNumber(value: string): string {
  let cleaned = value.replace(/\D/g, '');

  // Remove leading 1 if it's 11 digits (US country code)
  if (cleaned.length === 11 && cleaned[0] === '1') {
    cleaned = cleaned.slice(1);
  }

  if (cleaned.length <= 3) return cleaned;
  if (cleaned.length <= 6) return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3)}`;
  return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6, 10)}`;
}

/**
 * Format phone number for API (E.164 format)
 */
function formatPhoneForAPI(phone: string): string {
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length === 10) {
    return `+1${cleaned}`;
  }
  if (cleaned.length === 11 && cleaned[0] === '1') {
    return `+${cleaned}`;
  }
  return phone; // Return as-is if not a valid US phone
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
  const { checkAuth, user } = useAuth();
  const betaConfig = useBetaConfig();

  // Get the redirect parameter, but if it's the login page, use home instead
  let redirect = searchParams.get('redirect') || '/';
  if (redirect === '/login' || redirect.startsWith('/login?')) {
    redirect = '/';
  }

  const [formData, setFormData] = useState({
    firstName: '',
    lastName: '',
    email: (searchParams.get('email') || '').toLowerCase(),
    phone: '',
    zipCode: '',
    password: '',
    confirmPassword: '',
  });
  const [errors, setErrors] = useState<FormErrors>({});
  const [requestStatus, setRequestStatus] = useState<RequestStatus>(RequestStatus.IDLE);
  const [showPassword, setShowPassword] = useState(false);
  const [postSignupRedirect, setPostSignupRedirect] = useState<{ target: string; expectedUserId: string } | null>(null);
  const [mounted, setMounted] = useState(false);

  // Avoid hydration mismatch by only applying beta config after mount
  useEffect(() => {
    setMounted(true);
  }, []);

  const clearFieldError = (field: keyof FormErrors) => {
    setErrors((prev) => {
      if (!prev[field]) return prev;
      const nextErrors = { ...prev };
      delete nextErrors[field];
      return nextErrors;
    });
  };

  useEffect(() => {
    if (!postSignupRedirect) return;
    if (typeof window === 'undefined') return;
    const fallback = window.setTimeout(() => {
      router.push(postSignupRedirect.target);
      setPostSignupRedirect(null);
    }, 2000);
    if (user?.id === postSignupRedirect.expectedUserId) {
      router.push(postSignupRedirect.target);
      setPostSignupRedirect(null);
      window.clearTimeout(fallback);
    }
    return () => {
      window.clearTimeout(fallback);
    };
  }, [postSignupRedirect, user, router]);

  logger.debug('SignUpForm initialized', {
    redirectTo: redirect,
    hasRedirect: redirect !== '/',
  });

  const isInstructorFlow = (searchParams.get('role') || '').toLowerCase() === 'instructor';

  /**
   * Handle form input changes
   *
   * @param {React.ChangeEvent<HTMLInputElement>} e - Change event
   */
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    let nextValue = value;

    // Special handling for different fields
    if (name === 'email') {
      nextValue = value.toLowerCase();
    } else if (name === 'phone') {
      nextValue = formatPhoneNumber(value);
    } else if (name === 'zipCode') {
      // Only allow digits and limit to 5 characters
      nextValue = value.replace(/\D/g, '').slice(0, 5);
    }

    setFormData((prev) => ({
      ...prev,
      [name]: nextValue,
    }));

    clearFieldError(name as keyof FormErrors);
  };

  // Validate email on blur (not on first keystroke)
  const handleEmailBlur = (e: React.FocusEvent<HTMLInputElement>) => {
    const value = (e.target.value || '').trim();
    if (!value) {
      // Do not show "required" on blur; defer to submit
      clearFieldError('email');
      return;
    }
    const invalid = !/\S+@\S+\.\S+/.test(value);
    setErrors((prev) => {
      if (invalid) {
        return { ...prev, email: 'Please enter a valid email' };
      }
      const nextErrors = { ...prev };
      delete nextErrors.email;
      return nextErrors;
    });
  };

  const handlePhoneBlur = (e: React.FocusEvent<HTMLInputElement>) => {
    const value = e.target.value || '';
    const cleaned = value.replace(/\D/g, '');
    if (!cleaned) {
      clearFieldError('phone');
      return;
    }
    if (cleaned.length !== 10) {
      setErrors((prev) => ({ ...prev, phone: 'Please enter a valid phone number' }));
      return;
    }
    clearFieldError('phone');
  };

  // Validate ZIP against backend NYC checker for instructor flow
  const handleZipBlur = async (e: React.FocusEvent<HTMLInputElement>) => {
    const value = (e.target.value || '').trim();
    if (!value) {
      clearFieldError('zipCode');
      return;
    }

    if (value.length !== 5) {
      setErrors((prev) => ({ ...prev, zipCode: 'Please enter a valid ZIP code' }));
      return;
    }

    if (!isInstructorFlow) {
      clearFieldError('zipCode');
      return;
    }

    try {
      const res = await checkIsNYCZip(value);
      if (!res.is_nyc) {
        setErrors((prev) => ({ ...prev, zipCode: 'Please enter a New York City ZIP code' }));
      } else {
        clearFieldError('zipCode');
      }
    } catch {
      // Network or parsing error: do not block; keep existing validation
    }
  };

  /**
   * Validate form data before submission
   *
   * @returns {boolean} True if form is valid
   */
  const validateForm = (): { isValid: boolean; errors: FormErrors } => {
    logger.debug('Validating signup form');
    const newErrors: FormErrors = {};

    // Validate first name
    if (!formData.firstName.trim()) {
      newErrors.firstName = 'First name is required';
    } else if (formData.firstName.trim().length < 2) {
      newErrors.firstName = 'First name must be at least 2 characters';
    }

    // Validate last name
    if (!formData.lastName.trim()) {
      newErrors.lastName = 'Last name is required';
    } else if (formData.lastName.trim().length < 2) {
      newErrors.lastName = 'Last name must be at least 2 characters';
    }

    // Validate email
    if (!formData.email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!/\S+@\S+\.\S+/.test(formData.email)) {
      newErrors.email = 'Please enter a valid email';
    }

    // Validate phone
    const cleanedPhone = formData.phone.replace(/\D/g, '');
    if (!formData.phone.trim()) {
      newErrors.phone = 'Phone number is required';
    } else if (cleanedPhone.length !== 10) {
      newErrors.phone = 'Please enter a valid phone number';
    }

    // Validate zip code
    if (!formData.zipCode.trim()) {
      newErrors.zipCode = 'Zip code is required';
    } else if (formData.zipCode.length !== 5) {
      newErrors.zipCode = 'Please enter a valid ZIP code';
    }

    // Validate password
    if (!formData.password) {
      newErrors.password = 'Password is required';
    } else if (formData.password.length < 8) {
      newErrors.password = 'Password must be at least 8 characters';
    }

    // Validate password confirmation
    if (formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    const isValid = Object.keys(newErrors).length === 0;

    logger.debug('Form validation result', {
      isValid,
      errorCount: Object.keys(newErrors).length,
      errors: Object.keys(newErrors),
    });

    return { isValid, errors: newErrors };
  };

  /**
   * Handle form submission
   *
   * @param {React.FormEvent} e - Form event
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    logger.info('Signup form submitted');

    const { isValid, errors: vfErrors } = validateForm();
    if (!isValid) {
      logger.warn('Signup form validation failed');
      setErrors(vfErrors);
      // Focus first invalid field for faster correction
      const order: Array<keyof FormErrors> = [
        'firstName',
        'lastName',
        'email',
        'phone',
        'zipCode',
        'password',
        'confirmPassword',
      ];
      for (const key of order) {
        if (vfErrors[key]) {
          const el = document.getElementById(key as string) as HTMLInputElement | null;
          if (el) {
            el.focus();
          }
          break;
        }
      }
      return;
    }

    setRequestStatus(RequestStatus.LOADING);
    setErrors({});

    try {
      // Get guest session ID if available
      const guestSessionId = getGuestSessionId();

      // Prepare registration data with new fields
      const registrationData: components['schemas']['UserCreate'] = {
        first_name: formData.firstName.trim(),
        last_name: formData.lastName.trim(),
        email: formData.email.trim().toLowerCase(),
        phone: formatPhoneForAPI(formData.phone),
        zip_code: formData.zipCode.trim(),
        password: formData.password,
        role: searchParams.get('role') === 'instructor' ? RoleName.INSTRUCTOR : RoleName.STUDENT,
        is_active: true,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
        ...(guestSessionId && { guest_session_id: guestSessionId }),
        metadata: {
          invite_code: searchParams.get('invite_code') ?? null,
        },
      };

      logger.info('Attempting user registration', {
        email: registrationData.email,
        role: registrationData.role,
      });
      logger.time('registration');
      try {
        await httpPost<{ message: string }>(API_ENDPOINTS.REGISTER, registrationData);
      } catch (err) {
        if (err instanceof ApiError) {
          const status = err.status;
          const errorData = (err.data ?? {}) as { detail?: unknown };
          logger.warn('Registration failed', { status, error: errorData });

          let errorMessage = 'Registration failed';

          if (status === 429 && errorData.detail) {
            const detail = errorData.detail as { retry_after?: number; message?: string };
            if (detail?.retry_after) {
              const minutes = Math.ceil(detail.retry_after / 60);
              errorMessage = `${
                detail.message || 'Too many registration attempts. Please try again later.'
              } Please wait ${minutes} minute${minutes > 1 ? 's' : ''} before trying again.`;
            } else if (detail?.message) {
              errorMessage = detail.message;
            } else {
              errorMessage = 'Too many attempts. Please try again later.';
            }
          } else if (Array.isArray(errorData.detail)) {
            errorMessage = (errorData.detail as Array<{ msg?: string }>)
              .map((e) => e.msg)
              .filter(Boolean)
              .join(', ');
          } else if (typeof errorData.detail === 'string') {
            errorMessage = errorData.detail;
          } else {
            errorMessage = `Registration failed (${status})`;
          }

          setErrors({ general: errorMessage });
          setRequestStatus(RequestStatus.ERROR);
          return;
        }

        throw err;
      } finally {
        logger.timeEnd('registration');
      }

      logger.info('Registration successful, attempting auto-login');

      // Auto-login after successful registration
      // Use new endpoint if we have a guest session (already converted during registration)
      logger.time('auto-login');
      const loginPath = guestSessionId ? '/api/v1/auth/login-with-session' : API_ENDPOINTS.LOGIN;
      const loginHeaders = guestSessionId
        ? { 'Content-Type': 'application/json' }
        : { 'Content-Type': 'application/x-www-form-urlencoded' };
      const loginPayload = guestSessionId
        ? {
            email: formData.email,
            password: formData.password,
            guest_session_id: guestSessionId,
          }
        : new URLSearchParams({
            username: formData.email,
            password: formData.password,
          }).toString();

      try {
        await http<components['schemas']['LoginResponse']>('POST', loginPath, {
          headers: loginHeaders,
          body: loginPayload,
        });
      } catch (err) {
        if (err instanceof ApiError) {
          logger.error('Auto-login failed after registration', err, { status: err.status });
          const originalRedirect = searchParams.get('redirect') || '/';
          router.push(`/login?redirect=${encodeURIComponent(originalRedirect)}&registered=true`);
          return;
        }
        throw err;
      } finally {
        logger.timeEnd('auto-login');
      }

      logger.info('Auto-login successful, fetching user data and updating auth context');

      // Session is cookie-based; fetch user data without storing tokens client-side
      let userData: AuthUserResponse | null = null;
      try {
        userData = await httpGet<AuthUserResponse>(API_ENDPOINTS.ME);
      } catch (fetchError) {
        logger.warn('Failed to fetch user data after login, using default redirect', fetchError instanceof Error ? fetchError : undefined);
        await checkAuth();
        router.push(redirect);
        setRequestStatus(RequestStatus.SUCCESS);
        return;
      }

      if (userData) {
        try {
          const inviteCode = searchParams.get('invite_code') || (typeof window !== 'undefined' ? sessionStorage.getItem('invite_code') || '' : '');
          if (inviteCode) {
            logger.info('Consuming beta invite for new user', { inviteCode, userId: userData.id });
            await http('POST', '/api/v1/beta/invites/consume', {
              headers: {
                'Content-Type': 'application/json',
              },
              body: {
                code: inviteCode,
                user_id: userData.id,
                role: 'instructor_beta',
                phase: 'instructor_only',
              },
            });
          }
        } catch (e) {
          logger.warn('Failed to consume beta invite after signup', e instanceof Error ? e : new Error(String(e)));
        }
        const {
          phone,
          zip_code,
          timezone,
          profile_picture_version,
          has_profile_picture,
          permissions,
          ...restUser
        } = userData;
        const normalizedUser = {
          ...restUser,
          permissions: permissions ?? [],
          ...(phone != null ? { phone } : {}),
          ...(zip_code != null ? { zip_code } : {}),
          ...(timezone != null ? { timezone } : {}),
          ...(profile_picture_version != null ? { profile_picture_version } : {}),
          ...(has_profile_picture != null ? { has_profile_picture } : {}),
        };
        logger.info('User data fetched, redirecting based on role', {
          userId: userData.id,
          roles: userData.roles,
          redirectTo: hasRole(normalizedUser, RoleName.INSTRUCTOR) ? '/instructor/dashboard' : redirect,
        });
        // Ensure AuthProvider state is up-to-date before hitting gated routes
        await checkAuth();
        const nextDestination = redirect || (hasRole(normalizedUser, RoleName.INSTRUCTOR) ? '/instructor/onboarding/welcome' : '/');
        setPostSignupRedirect({ target: nextDestination, expectedUserId: userData.id });
      }

      setRequestStatus(RequestStatus.SUCCESS);
    } catch (error) {
      let errorMessage = 'An unexpected error occurred';

      if (error instanceof Error) {
        errorMessage = error.message;
      }

      logger.error('Signup process failed', error, {
        email: formData.email,
        errorMessage,
      });

      setErrors({ general: errorMessage });
      setRequestStatus(RequestStatus.ERROR);
    }
  };

  const isLoading = requestStatus === RequestStatus.LOADING;

  // Hide student signup CTA on beta instructor-only phase
  // Only apply after mount to avoid hydration mismatch
  const showStudentSignupCta = !mounted || !(betaConfig.site === 'beta' && betaConfig.phase === 'instructor_only');

  return (
    <div className="mt-0 sm:mt-4 sm:mx-auto sm:w-full sm:max-w-md">
      {/* Mobile: no card chrome; Desktop: keep card with shadow */}
      <div className="bg-transparent sm:bg-white dark:bg-transparent sm:dark:bg-gray-800 py-4 md:py-8 px-0 sm:px-10 sm:shadow sm:rounded-lg">
        <div className="text-center mb-1 md:mb-2">
          <Link href="/" onClick={() => logger.info('Navigating to home from signup inside box')}>
            <h1 className="text-4xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors">{BRAND.name}</h1>
          </Link>
        </div>
        {isInstructorFlow && (
          <div className="text-center mb-2 md:mb-3">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Join as an Instructor</h2>
            <p className="text-gray-600 dark:text-gray-300 mt-0.5">Share your skills and earn on your schedule</p>
          </div>
        )}
        {!isInstructorFlow && (
          <div className="text-center mb-2 md:mb-3">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Start Learning Today</h2>
            <p className="text-gray-600 dark:text-gray-300 mt-0.5">Discover instructors and book lessons instantly.</p>
          </div>
        )}
        <form method="POST" className="space-y-5 md:space-y-6" onSubmit={handleSubmit} noValidate>
          {/* Screen reader live region for aggregated errors */}
          <div className="sr-only" role="status" aria-live="polite">
            {(Object.values(errors).filter(Boolean) as string[]).join('. ')}
          </div>
          {/* General error message */}
          {errors.general && (
            <div role="alert" className="rounded-md p-4 bg-red-50 dark:bg-red-900/20">
              <p className="text-sm text-red-800 dark:text-red-400">{errors.general}</p>
            </div>
          )}

          {/* Name Fields Row */}
          <div className="grid grid-cols-2 gap-3 md:gap-4">
            {/* First Name Field */}
            <div>
              <label htmlFor="firstName" className="block text-sm font-medium text-gray-700 dark:text-gray-300">First Name</label>
              <div className="mt-1">
                <input id="firstName" name="firstName" type="text" autoComplete="given-name" required value={formData.firstName} onChange={handleChange} disabled={isLoading} className="appearance-none block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-[#7E22CE] focus:border-purple-500 dark:bg-gray-700 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed autofill-fix" aria-invalid={!!errors.firstName} aria-describedby={errors.firstName ? 'firstName-error' : undefined} />
                {errors.firstName && (<p id="firstName-error" className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.firstName}</p>)}
              </div>
            </div>

            {/* Last Name Field */}
            <div>
              <label htmlFor="lastName" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Last Name</label>
              <div className="mt-1">
                <input id="lastName" name="lastName" type="text" autoComplete="family-name" required value={formData.lastName} onChange={handleChange} disabled={isLoading} className="appearance-none block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-[#7E22CE] focus:border-purple-500 dark:bg-gray-700 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed autofill-fix" aria-invalid={!!errors.lastName} aria-describedby={errors.lastName ? 'lastName-error' : undefined} />
                {errors.lastName && (<p id="lastName-error" className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.lastName}</p>)}
              </div>
            </div>
          </div>

          {/* Email Field */}
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Email</label>
            <div className="mt-1">
              <input id="email" name="email" type="email" autoComplete="email" autoCapitalize="none" autoCorrect="off" inputMode="email" required value={formData.email} onChange={handleChange} onBlur={handleEmailBlur} disabled={isLoading} className="appearance-none block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-[#7E22CE] focus:border-purple-500 dark:bg-gray-700 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed autofill-fix" aria-invalid={!!errors.email} aria-describedby={errors.email ? 'email-error' : undefined} />
              {errors.email && (<p id="email-error" role="alert" aria-live="polite" className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.email}</p>)}
            </div>
          </div>

          {/* Phone and Zip Code Row */}
          <div className="grid grid-cols-2 gap-3 md:gap-4">
            {/* Phone Field */}
            <div>
              <label htmlFor="phone" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Phone Number</label>
              <div className="mt-1">
                <input id="phone" name="phone" type="tel" inputMode="tel" autoComplete="tel" required placeholder="(555) 555-5555" value={formData.phone} onChange={handleChange} onBlur={handlePhoneBlur} disabled={isLoading} className="appearance-none block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-[#7E22CE] focus:border-purple-500 dark:bg-gray-700 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed autofill-fix" aria-invalid={!!errors.phone} aria-describedby={errors.phone ? 'phone-error' : undefined} />
                {errors.phone && (<p id="phone-error" role="alert" aria-live="polite" className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.phone}</p>)}
              </div>
            </div>

            {/* Zip Code Field */}
            <div>
              <label htmlFor="zipCode" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Zip Code</label>
              <div className="mt-1">
                <input id="zipCode" name="zipCode" type="text" inputMode="numeric" pattern="\\d{5}" autoComplete="postal-code" required placeholder="10001" maxLength={5} value={formData.zipCode} onChange={handleChange} onBlur={handleZipBlur} disabled={isLoading} className="appearance-none block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-[#7E22CE] focus:border-purple-500 dark:bg-gray-700 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed autofill-fix" aria-invalid={!!errors.zipCode} aria-describedby={errors.zipCode ? 'zipCode-error' : undefined} />
                {errors.zipCode && (
                  <p id="zipCode-error" role="alert" aria-live="polite" className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.zipCode}</p>
                )}
              </div>
            </div>
          </div>

          {/* Password Field */}
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Password</label>
            <div className="mt-1 relative">
              <input id="password" name="password" type={showPassword ? 'text' : 'password'} autoComplete="new-password" minLength={8} required value={formData.password} onChange={handleChange} disabled={isLoading} className="appearance-none block w-full px-3 py-2 h-10 pr-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-[#7E22CE] focus:border-purple-500 dark:bg-gray-700 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed autofill-fix" aria-invalid={!!errors.password} aria-describedby={errors.password ? 'password-error' : 'password-hint'} />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-0 top-1/2 -translate-y-1/2 -mt-2.5 pr-3 flex items-center text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 focus:outline-none focus-visible:outline-none focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:text-[#7E22CE]"
                style={{ outline: 'none', boxShadow: 'none' }}
                disabled={isLoading}
              >
                {showPassword ? (<EyeOff className="h-5 w-5" aria-hidden="true" />) : (<Eye className="h-5 w-5" aria-hidden="true" />)}
              </button>
              {errors.password && (<p id="password-error" className="mt-1 text-sm text-red-600 dark:text-red-400">At least 8 characters</p>)}
              {/* Strength hint */}
              {!errors.password && (
                <p id="password-hint" className="mt-1 text-sm text-gray-500 dark:text-gray-400">At least 8 characters</p>
              )}
            </div>
          </div>

          {/* Confirm Password Field */}
          <div>
            <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Confirm Password</label>
            <div className="mt-1">
              <input id="confirmPassword" name="confirmPassword" type={showPassword ? 'text' : 'password'} autoComplete="new-password" minLength={8} required value={formData.confirmPassword} onChange={handleChange} disabled={isLoading} className="appearance-none block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-[#7E22CE] focus:border-purple-500 dark:bg-gray-700 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed autofill-fix" aria-invalid={!!errors.confirmPassword} aria-describedby={errors.confirmPassword ? 'confirmPassword-error' : undefined} />
              {errors.confirmPassword && (<p id="confirmPassword-error" className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.confirmPassword}</p>)}
            </div>
          </div>

          {/* Submit Button */}
          <div>
            {/* Terms and Privacy Policy - smaller and tight above button */}
            <p className="text-center text-[11px] leading-4 text-gray-600 dark:text-gray-400 mb-3">
              By clicking below and creating an account,
              <br />
              I agree to iNSTAiNSTRU&apos;s{' '}
              <Link
                href="/terms"
                className="focus-link text-[#7E22CE] hover:text-[#7E22CE]"
              >
                Terms of Service
              </Link>{' '}
              and{' '}
              <Link
                href="/privacy"
                className="focus-link text-[#7E22CE] hover:text-[#7E22CE]"
              >
                Privacy Policy
              </Link>
            </p>
            <button type="submit" disabled={isLoading} className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-[#7E22CE] hover:bg-[#7E22CE] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#7E22CE] disabled:opacity-50 disabled:cursor-not-allowed dark:bg-purple-600 dark:hover:bg-[#7E22CE]">{isLoading ? 'Creating account...' : (isInstructorFlow ? 'Sign up as Instructor' : 'Sign up as Student')}</button>

            {/* Instructor CTAs placed tight under the button */}
            {isInstructorFlow && (
              <div className="text-center mt-1">
                {showStudentSignupCta && (
                  <span className="text-sm text-gray-600 dark:text-gray-400">
                    Looking to learn instead?{' '}
                    <Link
                      href={`/signup${redirect !== '/' ? `?redirect=${encodeURIComponent(redirect)}` : ''}`}
                      className="focus-link font-medium text-[#7E22CE] hover:text-[#7E22CE] dark:text-purple-400 dark:hover:text-purple-300"
                    >
                      Sign up as a student
                    </Link>
                  </span>
                )}
                <div className={showStudentSignupCta ? "mt-0.5" : ""}>
                  <span className="text-sm text-gray-600 dark:text-gray-400">
                    Already have an account?{' '}
                    <Link
                      href={`/login${redirect !== '/' ? `?redirect=${encodeURIComponent(redirect)}` : ''}`}
                      className="focus-link font-medium text-[#7E22CE] hover:text-[#7E22CE] dark:text-purple-400 dark:hover:text-purple-300"
                      onClick={() => logger.info('Navigating to login from signup')}
                    >
                      Sign in
                    </Link>
                  </span>
                </div>
              </div>
            )}
            {!isInstructorFlow && (
              <div className="text-center mt-1">
                <span className="text-sm text-gray-600 dark:text-gray-400">
                  Looking to teach instead?{' '}
                  <Link
                    href={`/signup?role=instructor${redirect !== '/' ? `&redirect=${encodeURIComponent(redirect)}` : ''}`}
                    className="focus-link font-medium text-[#7E22CE] hover:text-[#7E22CE] dark:text-purple-400 dark:hover:text-purple-300"
                  >
                    Sign up as Instructor
                  </Link>
                </span>
                <div className="mt-0.5">
                  <span className="text-sm text-gray-600 dark:text-gray-400">
                    Already have an account?{' '}
                    <Link
                      href={`/login${redirect !== '/' ? `?redirect=${encodeURIComponent(redirect)}` : ''}`}
                      className="focus-link font-medium text-[#7E22CE] hover:text-[#7E22CE] dark:text-purple-400 dark:hover:text-purple-300"
                      onClick={() => logger.info('Navigating to login from signup')}
                    >
                      Sign in
                    </Link>
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* CTAs are now rendered just above inside the button block */}

          {/* Login link for student flow moved under submit button above */}
        </form>
      </div>
    </div>
  );
}

/**
 * Signup page component
 *
 * @page
 * @returns {JSX.Element} The signup page
 */
export default function SignUpPage() {
  return (
    <div className="min-h-screen px-4 sm:px-6 lg:px-8 flex items-center justify-center">
      {/* Mobile: full-width, no modal look; Desktop: centered card */}
      <div className="w-full sm:max-w-md sm:mx-auto">
        <Suspense fallback={<div className="flex justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7E22CE] dark:border-purple-400" /></div>}>
          <SignUpForm />
        </Suspense>
      </div>
    </div>
  );
}
