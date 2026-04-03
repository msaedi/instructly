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

import { useEffect, useState, Suspense, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Eye, EyeOff } from 'lucide-react';
import { API_ENDPOINTS, checkIsNYCZip } from '@/lib/api';
import { BRAND } from '@/app/config/brand';
import { logger } from '@/lib/logger';
import { ApiError, httpPost } from '@/lib/http';
import { useBetaConfig } from '@/lib/beta-config';
import { buildAuthHref } from '@/features/referrals/referralAuth';
// Background handled globally via GlobalBackground

// Import centralized types
import { RequestStatus } from '@/types/api';
import { RoleName } from '@/types/enums';
import {
  readPendingSignup,
  savePendingSignup,
} from '@/features/shared/auth/pendingSignup';

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
 * Signup form component with validation and auto-login
 *
 * @component
 * @returns {JSX.Element} The signup form
 */
function SignUpForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const betaConfig = useBetaConfig();
  const referralCode = searchParams.get('ref');
  const redirectParam = searchParams.get('redirect');
  const searchEmail = (searchParams.get('email') || '').toLowerCase();
  const isInstructorFlow = (searchParams.get('role') || '').toLowerCase() === 'instructor';
  const isFoundingFlow = searchParams.get('founding') === 'true';
  const inviteCodeFromSearch = searchParams.get('invite_code') || '';

  // Get the redirect parameter, but if it's the login page, use home instead
  let redirect = redirectParam || '/';
  if (redirect === '/login' || redirect.startsWith('/login?')) {
    redirect = '/';
  }

  const hasMounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false
  );
  const [formData, setFormData] = useState(() => {
    const pendingSignup = readPendingSignup();
    const expectedRole = isInstructorFlow ? RoleName.INSTRUCTOR : RoleName.STUDENT;
    if (pendingSignup && pendingSignup.role === expectedRole) {
      return {
        firstName: pendingSignup.firstName,
        lastName: pendingSignup.lastName,
        email: (searchEmail || pendingSignup.email || '').toLowerCase(),
        phone: pendingSignup.phone,
        zipCode: pendingSignup.zipCode,
        password: pendingSignup.password,
        confirmPassword: pendingSignup.confirmPassword,
      };
    }

    return {
      firstName: '',
      lastName: '',
      email: searchEmail,
      phone: '',
      zipCode: '',
      password: '',
      confirmPassword: '',
    };
  });
  const [errors, setErrors] = useState<FormErrors>({});
  const [requestStatus, setRequestStatus] = useState<RequestStatus>(RequestStatus.IDLE);
  const [showPassword, setShowPassword] = useState(false);

  const clearFieldError = (field: keyof FormErrors) => {
    setErrors((prev) => {
      if (!prev[field]) return prev;
      const nextErrors = { ...prev };
      delete nextErrors[field];
      return nextErrors;
    });
  };

  useEffect(() => {
    logger.debug('SignUpForm initialized', {
      redirectTo: redirect,
      hasRedirect: redirect !== '/',
    });
  }, [redirect]);

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
    const normalizedEmail = formData.email.trim().toLowerCase();
    const emailDomain = normalizedEmail.includes('@')
      ? (normalizedEmail.split('@')[1] ?? null)
      : null;

    try {
      const inviteCode =
        inviteCodeFromSearch ||
        (typeof window !== 'undefined' ? window.sessionStorage.getItem('invite_code') || '' : '');
      const role = isInstructorFlow ? RoleName.INSTRUCTOR : RoleName.STUDENT;

      savePendingSignup({
        firstName: formData.firstName.trim(),
        lastName: formData.lastName.trim(),
        email: normalizedEmail,
        phone: formData.phone,
        zipCode: formData.zipCode.trim(),
        password: formData.password,
        confirmPassword: formData.confirmPassword,
        role,
        redirect,
        referralCode,
        founding: isFoundingFlow,
        inviteCode: inviteCode || null,
        emailVerificationToken: null,
      });

      logger.info('Sending signup email verification code', {
        emailDomain,
        role,
      });
      await httpPost<{ message: string }>(API_ENDPOINTS.SEND_EMAIL_VERIFICATION, {
        email: normalizedEmail,
      });

      setRequestStatus(RequestStatus.SUCCESS);
      const verifyEmailParams = new URLSearchParams();
      verifyEmailParams.set('redirect', redirect);
      verifyEmailParams.set('email', normalizedEmail);
      if (isInstructorFlow) {
        verifyEmailParams.set('role', 'instructor');
      }
      if (referralCode) {
        verifyEmailParams.set('ref', referralCode);
      }
      if (isFoundingFlow) {
        verifyEmailParams.set('founding', 'true');
      }
      if (inviteCode) {
        verifyEmailParams.set('invite_code', inviteCode);
      }
      router.push(`/verify-email?${verifyEmailParams.toString()}`);
    } catch (error) {
      const errorMessage =
        error instanceof ApiError || error instanceof Error
          ? error.message
          : 'An unexpected error occurred';

      logger.error('Signup process failed', error, {
        emailDomain,
        errorMessage,
      });

      setErrors({ general: errorMessage });
      setRequestStatus(RequestStatus.ERROR);
    }
  };

  const isLoading = requestStatus === RequestStatus.LOADING;

  // Hide student signup CTA on beta instructor-only phase
  // Only apply after mount to avoid hydration mismatch
  const showStudentSignupCta =
    !hasMounted || !(betaConfig.site === 'beta' && betaConfig.phase === 'instructor_only');

  return (
    <div className="mt-0 sm:mt-4 sm:mx-auto sm:w-full sm:max-w-md">
      {/* Mobile: no card chrome; Desktop: keep card with shadow */}
      <div className="insta-surface-card py-4 md:py-8 px-0 sm:px-10 sm:shadow">
        <div className="text-center mb-1 md:mb-2">
          <Link href="/" onClick={() => logger.info('Navigating to home from signup inside box')}>
            <h1 className="text-4xl font-bold text-(--color-brand-dark) hover:text-purple-900 dark:hover:text-purple-300 transition-colors">{BRAND.name}</h1>
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
                <input id="firstName" name="firstName" type="text" autoComplete="given-name" required value={formData.firstName} onChange={handleChange} disabled={isLoading} className="appearance-none block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none  focus:border-(--color-focus-brand) dark:bg-gray-700 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed autofill-fix" aria-invalid={!!errors.firstName} aria-describedby={errors.firstName ? 'firstName-error' : undefined} />
                {errors.firstName && (<p id="firstName-error" className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.firstName}</p>)}
              </div>
            </div>

            {/* Last Name Field */}
            <div>
              <label htmlFor="lastName" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Last Name</label>
              <div className="mt-1">
                <input id="lastName" name="lastName" type="text" autoComplete="family-name" required value={formData.lastName} onChange={handleChange} disabled={isLoading} className="appearance-none block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none  focus:border-(--color-focus-brand) dark:bg-gray-700 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed autofill-fix" aria-invalid={!!errors.lastName} aria-describedby={errors.lastName ? 'lastName-error' : undefined} />
                {errors.lastName && (<p id="lastName-error" className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.lastName}</p>)}
              </div>
            </div>
          </div>

          {/* Email Field */}
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Email</label>
            <div className="mt-1">
              <input id="email" name="email" type="email" autoComplete="email" autoCapitalize="none" autoCorrect="off" inputMode="email" required value={formData.email} onChange={handleChange} onBlur={handleEmailBlur} disabled={isLoading} className="appearance-none block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none  focus:border-(--color-focus-brand) dark:bg-gray-700 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed autofill-fix" aria-invalid={!!errors.email} aria-describedby={errors.email ? 'email-error' : undefined} />
              {errors.email && (<p id="email-error" role="alert" className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.email}</p>)}
            </div>
          </div>

          {/* Phone and Zip Code Row */}
          <div className="grid grid-cols-2 gap-3 md:gap-4">
            {/* Phone Field */}
            <div>
              <label htmlFor="phone" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Phone Number</label>
              <div className="mt-1">
                <input id="phone" name="phone" type="tel" inputMode="tel" autoComplete="tel" required placeholder="(555) 555-5555" value={formData.phone} onChange={handleChange} onBlur={handlePhoneBlur} disabled={isLoading} className="appearance-none block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none  focus:border-(--color-focus-brand) dark:bg-gray-700 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed autofill-fix" aria-invalid={!!errors.phone} aria-describedby={errors.phone ? 'phone-error' : undefined} />
                {errors.phone && (<p id="phone-error" role="alert" className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.phone}</p>)}
              </div>
            </div>

            {/* Zip Code Field */}
            <div>
              <label htmlFor="zipCode" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Zip Code</label>
              <div className="mt-1">
                <input id="zipCode" name="zipCode" type="text" inputMode="numeric" pattern="\\d{5}" autoComplete="postal-code" required placeholder="10001" maxLength={5} value={formData.zipCode} onChange={handleChange} onBlur={handleZipBlur} disabled={isLoading} className="appearance-none block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none  focus:border-(--color-focus-brand) dark:bg-gray-700 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed autofill-fix" aria-invalid={!!errors.zipCode} aria-describedby={errors.zipCode ? 'zipCode-error' : undefined} />
                {errors.zipCode && (
                  <p id="zipCode-error" role="alert" className="mt-1 text-sm text-red-600 dark:text-red-400">{errors.zipCode}</p>
                )}
              </div>
            </div>
          </div>

          {/* Password Field */}
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Password</label>
            <div className="mt-1">
              <div className="relative rounded-md border border-gray-300 dark:border-gray-600 shadow-sm bg-white dark:bg-gray-700 focus-within:border-(--color-focus-brand) insta-focus-composite">
                <input id="password" name="password" type={showPassword ? 'text' : 'password'} autoComplete="new-password" minLength={8} required value={formData.password} onChange={handleChange} disabled={isLoading} className="insta-focus-composite-input appearance-none block w-full px-3 py-2 h-10 pr-10 border-0 rounded-md shadow-none placeholder-gray-400 dark:placeholder-gray-500 bg-transparent dark:text-white disabled:opacity-50 disabled:cursor-not-allowed autofill-fix" aria-invalid={!!errors.password} aria-describedby={errors.password ? 'password-error' : 'password-hint'} />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="insta-focus-icon-btn absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 focus-visible:outline-none"
                  disabled={isLoading}
                >
                  {showPassword ? (<EyeOff className="h-5 w-5" aria-hidden="true" />) : (<Eye className="h-5 w-5" aria-hidden="true" />)}
                </button>
              </div>
              {errors.password && (<p id="password-error" className="mt-1 text-sm text-red-600 dark:text-red-400">At least 8 characters</p>)}
              {!errors.password && (
                <p id="password-hint" className="mt-1 text-sm text-gray-500 dark:text-gray-400">At least 8 characters</p>
              )}
            </div>
          </div>

          {/* Confirm Password Field */}
          <div>
            <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Confirm Password</label>
            <div className="mt-1">
              <input id="confirmPassword" name="confirmPassword" type={showPassword ? 'text' : 'password'} autoComplete="new-password" minLength={8} required value={formData.confirmPassword} onChange={handleChange} disabled={isLoading} className="appearance-none block w-full px-3 py-2 h-10 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none  focus:border-(--color-focus-brand) dark:bg-gray-700 dark:text-white disabled:opacity-50 disabled:cursor-not-allowed autofill-fix" aria-invalid={!!errors.confirmPassword} aria-describedby={errors.confirmPassword ? 'confirmPassword-error' : undefined} />
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
                className="focus-link text-(--color-brand-dark) hover:text-purple-900 dark:hover:text-purple-300"
              >
                Terms of Service
              </Link>{' '}
              and{' '}
              <Link
                href="/privacy"
                className="focus-link text-(--color-brand-dark) hover:text-purple-900 dark:hover:text-purple-300"
              >
                Privacy Policy
              </Link>
            </p>
            <button type="submit" disabled={isLoading} className="insta-primary-btn w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed">{isLoading ? 'Sending code…' : (isInstructorFlow ? 'Sign up as Instructor' : 'Sign up as Student')}</button>

            {/* Instructor CTAs placed tight under the button */}
            {isInstructorFlow && (
              <div className="text-center mt-1">
                {showStudentSignupCta && (
                  <span className="text-sm text-gray-600 dark:text-gray-400">
                    Looking to learn instead?{' '}
                    <Link
                      href={buildAuthHref('/signup', {
                        redirect,
                        ref: referralCode,
                      })}
                      className="focus-link font-medium text-(--color-brand-dark) hover:text-purple-900 dark:hover:text-purple-300 dark:text-purple-400"
                    >
                      Sign up as a student
                    </Link>
                  </span>
                )}
                <div className={showStudentSignupCta ? "mt-0.5" : ""}>
                  <span className="text-sm text-gray-600 dark:text-gray-400">
                    Already have an account?{' '}
                    <Link
                      href={buildAuthHref('/login', {
                        redirect,
                        ref: referralCode,
                      })}
                      className="focus-link font-medium text-(--color-brand-dark) hover:text-purple-900 dark:hover:text-purple-300 dark:text-purple-400"
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
                    href={buildAuthHref('/signup', {
                      role: 'instructor',
                      redirect,
                      ref: referralCode,
                    })}
                    className="focus-link font-medium text-(--color-brand-dark) hover:text-purple-900 dark:hover:text-purple-300 dark:text-purple-400"
                  >
                    Sign up as Instructor
                  </Link>
                </span>
                <div className="mt-0.5">
                  <span className="text-sm text-gray-600 dark:text-gray-400">
                    Already have an account?{' '}
                    <Link
                      href={buildAuthHref('/login', {
                        redirect,
                        ref: referralCode,
                      })}
                      className="focus-link font-medium text-(--color-brand-dark) hover:text-purple-900 dark:hover:text-purple-300 dark:text-purple-400"
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
        <Suspense fallback={<div className="flex justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-(--color-brand-dark) dark:border-purple-400" /></div>}>
          <SignUpForm />
        </Suspense>
      </div>
    </div>
  );
}
