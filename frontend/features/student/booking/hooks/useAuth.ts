// frontend/features/student/booking/hooks/useAuth.ts
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { API_ENDPOINTS, fetchWithAuth } from '@/lib/api';
import { logger } from '@/lib/logger';

interface User {
  id: number;
  email: string;
  full_name: string;
  role: 'student' | 'instructor';
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface UseAuthReturn {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  redirectToLogin: (returnUrl?: string) => void;
  checkAuth: () => Promise<void>;
}

/**
 * Custom hook for authentication in the booking flow
 *
 * Features:
 * - Checks current authentication status
 * - Provides user data if authenticated
 * - Handles login redirects with return URL
 * - Manages loading and error states
 *
 * @returns {UseAuthReturn} Authentication state and utilities
 */
export function useAuth(): UseAuthReturn {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /**
   * Check if user is authenticated and fetch user data
   */
  const checkAuth = async () => {
    setIsLoading(true);
    setError(null);

    const token = localStorage.getItem('access_token');

    if (!token) {
      logger.debug('No auth token found');
      setUser(null);
      setIsLoading(false);
      return;
    }

    try {
      logger.info('Checking authentication status');
      const response = await fetchWithAuth(API_ENDPOINTS.ME);

      if (response.ok) {
        const userData = await response.json();
        logger.info('User authenticated', {
          userId: userData.id,
          role: userData.role,
          email: userData.email,
        });
        setUser(userData);
      } else if (response.status === 401) {
        logger.warn('Invalid or expired auth token');
        localStorage.removeItem('access_token');
        setUser(null);
      } else {
        logger.error('Failed to fetch user data', undefined, {
          status: response.status,
          statusText: response.statusText,
        });
        setError('Failed to verify authentication');
      }
    } catch (err) {
      logger.error('Authentication check error', err);
      setError('Network error while checking authentication');
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Redirect to login page with optional return URL
   * Preserves the current page as the return destination
   */
  const redirectToLogin = (returnUrl?: string) => {
    const url = returnUrl || window.location.pathname + window.location.search;
    const encodedUrl = encodeURIComponent(url);

    logger.info('Redirecting to login', {
      returnUrl: url,
      encodedUrl,
    });

    router.push(`/login?redirect=${encodedUrl}`);
  };

  // Check authentication on mount
  useEffect(() => {
    checkAuth();
  }, []);

  return {
    user,
    isAuthenticated: !!user,
    isLoading,
    error,
    redirectToLogin,
    checkAuth,
  };
}

/**
 * Store booking intent in sessionStorage for persistence across login
 *
 * @param bookingIntent - The booking details to preserve
 */
export function storeBookingIntent(bookingIntent: {
  instructorId: number;
  serviceId?: number;
  date: string;
  time: string;
  duration: number;
}) {
  try {
    sessionStorage.setItem('bookingIntent', JSON.stringify(bookingIntent));
    logger.info('Stored booking intent', bookingIntent);
  } catch (err) {
    logger.error('Failed to store booking intent', err);
  }
}

/**
 * Retrieve stored booking intent from sessionStorage
 *
 * @returns The stored booking intent or null
 */
export function getBookingIntent(): {
  instructorId: number;
  serviceId?: number;
  date: string;
  time: string;
  duration: number;
} | null {
  try {
    const stored = sessionStorage.getItem('bookingIntent');
    if (stored) {
      const intent = JSON.parse(stored);
      logger.info('Retrieved booking intent', intent);
      return intent;
    }
  } catch (err) {
    logger.error('Failed to retrieve booking intent', err);
  }
  return null;
}

/**
 * Clear stored booking intent from sessionStorage
 */
export function clearBookingIntent() {
  try {
    sessionStorage.removeItem('bookingIntent');
    logger.info('Cleared booking intent');
  } catch (err) {
    logger.error('Failed to clear booking intent', err);
  }
}
