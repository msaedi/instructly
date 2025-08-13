// frontend/app/dashboard/student/page.tsx
'use client';

import { BRAND } from '@/app/config/brand';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Calendar, Search, LogOut } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { queryFn } from '@/lib/react-query/api';
import { BookingListResponse } from '@/types/booking';
import { logger } from '@/lib/logger';
import { useAuth, hasRole, type User } from '@/features/shared/hooks/useAuth';
import { RoleName } from '@/types/enums';

/**
 * StudentDashboard Component
 *
 * Main dashboard interface for students. Provides quick access to instructor search,
 * booking management, and displays upcoming sessions.
 *
 * Features:
 * - Authentication verification and role-based redirect
 * - Quick action cards for common tasks
 * - Upcoming sessions preview (shows up to 3)
 * - Loading and empty states
 * - Responsive design
 *
 * @component
 * @example
 * ```tsx
 * // This is a page component, typically accessed via routing
 * // Route: /dashboard/student
 * ```
 */
export default function StudentDashboard() {
  const router = useRouter();
  const { logout } = useAuth();

  // Fetch user data with React Query
  const {
    data: userData,
    isLoading: isLoadingUser,
    error: userError,
  } = useQuery<User>({
    queryKey: queryKeys.user,
    queryFn: queryFn('/auth/me', { requireAuth: true }),
    staleTime: CACHE_TIMES.SESSION, // Session-long cache
    retry: false,
  });

  // Fetch upcoming bookings with React Query
  const { data: bookingsData, isLoading: isLoadingBookings } = useQuery<BookingListResponse>({
    queryKey: queryKeys.bookings.upcoming(10), // Call the function with limit
    queryFn: queryFn('/bookings/', {
      params: {
        upcoming: true,
        per_page: 10,
      },
      requireAuth: true,
    }),
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes
    enabled: !!userData && hasRole(userData, RoleName.STUDENT), // Only fetch if user is a student
  });

  // Sort bookings by date (nearest first)
  const upcomingBookings = bookingsData
    ? bookingsData.items.sort((a, b) => {
        const dateTimeA = new Date(`${a.booking_date}T${a.start_time}`);
        const dateTimeB = new Date(`${b.booking_date}T${b.start_time}`);
        return dateTimeA.getTime() - dateTimeB.getTime();
      })
    : [];

  const isLoading = isLoadingUser;
  const bookingsLoading = isLoadingBookings;

  // Handle authentication and role-based redirects
  useEffect(() => {
    if (userError || (!isLoadingUser && !userData)) {
      logger.warn('No user data, redirecting to login');
      router.push('/login');
      return;
    }

    if (userData && !hasRole(userData, RoleName.STUDENT)) {
      logger.info('User is not a student, redirecting to instructor dashboard', {
        userId: userData.id,
        roles: userData.roles,
      });
      router.push('/dashboard/instructor');
    }
  }, [userData, userError, isLoadingUser, router]);

  /**
   * Handle user logout
   */
  const handleLogout = () => {
    logger.info('Student logging out');
    logout();
  };

  /**
   * Format time string to display format
   * @param timeStr - Time string in HH:MM:SS format
   * @returns Formatted time string HH:MM
   */
  const formatTime = (timeStr: string): string => {
    return timeStr.slice(0, 5);
  };

  /**
   * Get appropriate status badge color
   * @param status - Booking status
   * @returns Tailwind color classes for the badge
   */
  const getStatusBadgeColor = (status: string): string => {
    switch (status) {
      case 'CONFIRMED':
        return 'bg-green-100 text-green-800';
      case 'COMPLETED':
        return 'bg-gray-100 text-gray-800';
      case 'CANCELLED':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  if (!userData) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navbar */}
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link href="/" className="text-2xl font-bold text-indigo-600">
              {BRAND.name}
            </Link>
            <button
              onClick={handleLogout}
              className="flex items-center text-gray-600 hover:text-gray-900 transition-colors"
            >
              <LogOut className="h-5 w-5 mr-2" />
              Log out
            </button>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Welcome Section */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-8">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">
            Welcome back, {userData.first_name}!
          </h1>
          <p className="text-gray-600">Find and book sessions with expert instructors</p>
        </div>

        {/* Quick Actions */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <Link
            href="/search"
            className="block"
            onClick={() => logger.debug('Navigating to find instructors')}
          >
            <div className="bg-white rounded-lg shadow-sm p-6 hover:shadow-md transition-shadow">
              <div className="flex items-center">
                <Search className="h-8 w-8 text-indigo-600 mr-4" />
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">Find Instructors</h3>
                  <p className="text-gray-600">Browse and search for instructors</p>
                </div>
              </div>
            </div>
          </Link>

          <Link
            href="/student/lessons"
            className="block"
            onClick={() => logger.debug('Navigating to my lessons')}
          >
            <div className="bg-white rounded-lg shadow-sm p-6 hover:shadow-md transition-shadow">
              <div className="flex items-center">
                <Calendar className="h-8 w-8 text-indigo-600 mr-4" />
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">My Lessons</h3>
                  <p className="text-gray-600">View and manage your sessions</p>
                </div>
              </div>
            </div>
          </Link>
        </div>

        {/* Upcoming Sessions */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">
            Upcoming Sessions
          </h2>

          {bookingsLoading ? (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-indigo-500 mx-auto"></div>
              <p className="text-gray-500 mt-2">Loading bookings...</p>
            </div>
          ) : upcomingBookings.length > 0 ? (
            <div className="space-y-4">
              {upcomingBookings.slice(0, 3).map((booking) => (
                <div
                  key={booking.id}
                  className="border border-gray-200 dark:border-gray-600 rounded-lg p-4 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer"
                  onClick={() => {
                    logger.debug('Booking card clicked', { bookingId: booking.id });
                    router.push(`/booking/confirmation?bookingId=${booking.id}`);
                  }}
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <h4 className="font-semibold text-gray-900 dark:text-white">
                        {booking.service_name}
                      </h4>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        with {booking.instructor
                          ? `${booking.instructor.first_name} ${booking.instructor.last_initial}.`
                          : 'Instructor'}
                      </p>
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        {new Date(booking.booking_date).toLocaleDateString('en-US', {
                          weekday: 'long',
                          year: 'numeric',
                          month: 'long',
                          day: 'numeric',
                        })}{' '}
                        at {formatTime(booking.start_time)}
                      </p>
                      {booking.meeting_location && (
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          📍 {booking.meeting_location}
                        </p>
                      )}
                    </div>
                    <div className="text-right">
                      <p className="font-semibold text-gray-900 dark:text-white">
                        ${booking.total_price}
                      </p>
                      <span
                        className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${getStatusBadgeColor(
                          booking.status
                        )}`}
                      >
                        {booking.status}
                      </span>
                    </div>
                  </div>
                </div>
              ))}

              {upcomingBookings.length > 3 && (
                <Link
                  href="/student/lessons"
                  className="block text-center text-indigo-600 hover:text-indigo-700 font-medium transition-colors"
                  onClick={() =>
                    logger.debug('View all lessons clicked', {
                      totalLessons: upcomingBookings.length,
                    })
                  }
                >
                  View all {upcomingBookings.length} lessons →
                </Link>
              )}
            </div>
          ) : (
            <>
              <p className="text-gray-500 text-center py-8">No upcoming sessions booked yet</p>
              <div className="text-center">
                <Link
                  href="/search"
                  className="inline-block px-6 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 transition-colors"
                  onClick={() => logger.debug('Find instructor CTA clicked from empty state')}
                >
                  Find an Instructor
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
