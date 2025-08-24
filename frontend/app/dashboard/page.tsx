// frontend/app/dashboard/page.tsx
'use client';
// LEGACY-ONLY: Legacy dashboard entry. New Phoenix pages should not import from here.

/**
 * Dashboard Router Page
 *
 * This page acts as a router that checks the user's role and redirects them
 * to the appropriate dashboard (student or instructor). It handles authentication
 * verification and provides a loading state during the redirect process.
 *
 * @module dashboard/page
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { BRAND } from '@/app/config/brand';
import { logger } from '@/lib/logger';

// Import centralized types
import { RequestStatus } from '@/types/api';
import { getErrorMessage } from '@/types/common';
import { hasRole, type User } from '@/features/shared/hooks/useAuth';
import { RoleName } from '@/types/enums';

/**
 * Dashboard router component
 *
 * Automatically redirects users to their role-specific dashboard
 *
 * @component
 * @returns {JSX.Element} Loading state while determining redirect
 */
export default function Dashboard() {
  const router = useRouter();
  const [status, setStatus] = useState<RequestStatus>(RequestStatus.LOADING);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    /**
     * Check user authentication and role, then redirect accordingly
     */
    const checkUserRoleAndRedirect = async () => {
      logger.info('Dashboard: Checking user role for redirect');

      // Check for authentication token
      const token = localStorage.getItem('access_token');

      if (!token) {
        logger.warn('Dashboard: No access token found, redirecting to login');
        router.push('/login');
        return;
      }

      try {
        logger.time('fetchUserData');
        const response = await fetchWithAuth(API_ENDPOINTS.ME);
        logger.timeEnd('fetchUserData');

        if (!response.ok) {
          logger.warn('Dashboard: Failed to fetch user data', {
            status: response.status,
            statusText: response.statusText,
          });

          // Clear invalid token
          localStorage.removeItem('access_token');
          router.push('/login');
          return;
        }

        const userData = await response.json();
        logger.info('Dashboard: User data fetched successfully', {
          userId: userData.id,
          roles: userData.roles,
          permissions: userData.permissions,
        });

        // Redirect based on role
        if (hasRole(userData, RoleName.INSTRUCTOR)) {
          logger.info('Dashboard: Redirecting instructor to instructor dashboard', {
            userId: userData.id,
            roles: userData.roles,
          });
          router.push('/dashboard/instructor');
        } else if (hasRole(userData, RoleName.STUDENT)) {
          logger.info('Dashboard: Redirecting student to student dashboard', {
            userId: userData.id,
            roles: userData.roles,
          });
          router.push('/dashboard/student');
        } else {
          // Handle unexpected role
          logger.error('Dashboard: Unknown user roles', null, {
            userId: userData.id,
            roles: userData.roles,
          });
          setError(`Unknown user roles: ${userData.roles?.join(', ') || 'none'}`);
          setStatus(RequestStatus.ERROR);
        }
      } catch (error) {
        const errorMessage = getErrorMessage(error);
        logger.error('Dashboard: Error checking user role', error, {
          errorMessage,
        });

        setError(errorMessage);
        setStatus(RequestStatus.ERROR);

        // On error, redirect to login after a delay
        setTimeout(() => {
          logger.info('Dashboard: Redirecting to login after error');
          router.push('/login');
        }, 2000);
      }
    };

    checkUserRoleAndRedirect();
  }, [router]);

  // Error state
  if (status === RequestStatus.ERROR && error) {
    logger.debug('Dashboard: Rendering error state', { error });
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="text-center">
          <div className="bg-red-100 dark:bg-red-900/20 rounded-full p-4 mx-auto w-16 h-16 flex items-center justify-center mb-4">
            <svg
              className="w-8 h-8 text-red-600 dark:text-red-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
            Something went wrong
          </h2>
          <p className="text-gray-600 dark:text-gray-400 mb-4">{error}</p>
          <p className="text-sm text-gray-500 dark:text-gray-500">Redirecting to login...</p>
        </div>
      </div>
    );
  }

  // Loading state
  logger.debug('Dashboard: Rendering loading state');
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="text-center">
        <div
          className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 dark:border-indigo-400 mx-auto"
          role="status"
          aria-label="Loading"
        ></div>
        <h1 className="mt-4 text-lg font-medium text-gray-900 dark:text-white">{BRAND.name}</h1>
        <p className="mt-2 text-gray-600 dark:text-gray-400">Loading your dashboard...</p>
      </div>
    </div>
  );
}
