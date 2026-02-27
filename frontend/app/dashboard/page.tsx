// frontend/app/dashboard/page.tsx
'use client';
// REDIRECT-ONLY: Dashboard router. Redirects to role-specific dashboard pages.

/**
 * Dashboard Router Page
 *
 * This page acts as a router that checks the user's role and redirects them
 * to the appropriate dashboard (student or instructor). It handles authentication
 * verification and provides a loading state during the redirect process.
 *
 * @module dashboard/page
 */

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { BRAND } from '@/app/config/brand';
import { logger } from '@/lib/logger';

// Import centralized types
import { RoleName } from '@/types/enums';
import { useSession } from '@/src/api/hooks/useSession';

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
  // Use React Query hook for user session (prevents duplicate API calls)
  const { data: userData, isLoading, error: queryError } = useSession();

  // Redirect based on role when user data is available
  useEffect(() => {
    // Still loading
    if (isLoading) return;

    // Error fetching user - redirect to login
    if (queryError) {
      logger.warn('Dashboard: Failed to fetch user data, redirecting to login');
      router.push('/login');
      return;
    }

    // No user data - not authenticated
    if (!userData) {
      logger.warn('Dashboard: Not authenticated, redirecting to login');
      router.push('/login');
      return;
    }

    logger.info('Dashboard: User data fetched successfully', {
      userId: userData.id,
      roles: userData.roles,
      permissions: userData.permissions,
    });

    // Redirect based on role (inline check since userData type differs from User type)
    const userRoles = userData.roles ?? [];
    if (userRoles.includes(RoleName.INSTRUCTOR)) {
      logger.info('Dashboard: Redirecting instructor to instructor dashboard', {
        userId: userData.id,
        roles: userData.roles,
      });
      router.push('/dashboard/instructor');
    } else if (userRoles.includes(RoleName.STUDENT)) {
      logger.info('Dashboard: Redirecting student to student dashboard', {
        userId: userData.id,
        roles: userData.roles,
      });
      router.push('/dashboard/student');
    } else {
      // Handle unexpected role - redirect to login
      logger.error('Dashboard: Unknown user roles', null, {
        userId: userData.id,
        roles: userData.roles,
      });
      router.push('/login');
    }
  }, [userData, isLoading, queryError, router]);

  // Loading state (will redirect once data is fetched)
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
