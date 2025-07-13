// frontend/app/dashboard/student/page.tsx
'use client';

import { BRAND } from '@/app/config/brand';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Calendar, Search, LogOut } from 'lucide-react';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { bookingsApi } from '@/lib/api/bookings';
import { Booking } from '@/types/booking';
import { logger } from '@/lib/logger';
import { UserData } from '@/types/user';

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
  const [userData, setUserData] = useState<UserData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [upcomingBookings, setUpcomingBookings] = useState<Booking[]>([]);
  const [bookingsLoading, setBookingsLoading] = useState(true);

  useEffect(() => {
    logger.info('Student dashboard loaded');
    fetchUserData();
  }, [router]);

  /**
   * Fetch user data and verify student role
   * Redirects to appropriate dashboard if not a student
   */
  const fetchUserData = async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      logger.warn('No access token found, redirecting to login');
      router.push('/login');
      return;
    }

    try {
      logger.debug('Fetching user data');
      const response = await fetchWithAuth(API_ENDPOINTS.ME);

      if (!response.ok) {
        throw new Error('Failed to fetch user data');
      }

      const data: UserData = await response.json();

      // Verify user role
      if (data.role !== 'student') {
        logger.info('User is instructor, redirecting to instructor dashboard', {
          userId: data.id,
          role: data.role,
        });
        router.push('/dashboard/instructor');
        return;
      }

      logger.info('Student data loaded successfully', {
        userId: data.id,
        email: data.email,
      });

      setUserData(data);
      // Once we have user data, fetch bookings
      fetchBookings();
    } catch (err) {
      logger.error('Error fetching user data', err);
      router.push('/login');
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Fetch upcoming bookings for the student
   */
  const fetchBookings = async () => {
    try {
      logger.debug('Fetching upcoming bookings for student dashboard');

      const myBookings = await bookingsApi.getMyBookings({
        upcoming: true,
        per_page: 10,
      });

      // If we have bookings, sort them by date (nearest first) and store them
      if (myBookings.bookings && Array.isArray(myBookings.bookings)) {
        const sortedBookings = myBookings.bookings.sort((a, b) => {
          const dateTimeA = new Date(`${a.booking_date}T${a.start_time}`);
          const dateTimeB = new Date(`${b.booking_date}T${b.start_time}`);
          return dateTimeA.getTime() - dateTimeB.getTime();
        });

        logger.info('Upcoming bookings loaded and sorted', {
          count: sortedBookings.length,
        });
        setUpcomingBookings(sortedBookings);
      }
    } catch (error) {
      logger.error('Error fetching bookings', error);
    } finally {
      setBookingsLoading(false);
    }
  };

  /**
   * Handle user logout
   */
  const handleLogout = () => {
    logger.info('Student logging out');
    localStorage.removeItem('access_token');
    router.push('/');
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
            Welcome back, {userData.full_name}!
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
            href="/dashboard/student/bookings"
            className="block"
            onClick={() => logger.debug('Navigating to my bookings')}
          >
            <div className="bg-white rounded-lg shadow-sm p-6 hover:shadow-md transition-shadow">
              <div className="flex items-center">
                <Calendar className="h-8 w-8 text-indigo-600 mr-4" />
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">My Bookings</h3>
                  <p className="text-gray-600">View and manage your sessions</p>
                </div>
              </div>
            </div>
          </Link>
        </div>

        {/* Upcoming Sessions */}
        <div className="bg-white rounded-lg shadow-sm p-6">
          <h2 className="text-xl font-bold text-gray-900 mb-4">Upcoming Sessions</h2>

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
                  className="border rounded-lg p-4 hover:bg-gray-50 transition-colors cursor-pointer"
                  onClick={() => {
                    logger.debug('Booking card clicked', { bookingId: booking.id });
                    router.push(`/booking/confirmation?bookingId=${booking.id}`);
                  }}
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <h4 className="font-semibold text-gray-900">{booking.service_name}</h4>
                      <p className="text-sm text-gray-600">
                        with {booking.instructor?.full_name || 'Instructor'}
                      </p>
                      <p className="text-sm text-gray-500 mt-1">
                        {new Date(booking.booking_date).toLocaleDateString('en-US', {
                          weekday: 'long',
                          year: 'numeric',
                          month: 'long',
                          day: 'numeric',
                        })}{' '}
                        at {formatTime(booking.start_time)}
                      </p>
                      {booking.meeting_location && (
                        <p className="text-sm text-gray-500">📍 {booking.meeting_location}</p>
                      )}
                    </div>
                    <div className="text-right">
                      <p className="font-semibold text-gray-900">${booking.total_price}</p>
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
                  href="/dashboard/student/bookings"
                  className="block text-center text-indigo-600 hover:text-indigo-700 font-medium transition-colors"
                  onClick={() =>
                    logger.debug('View all bookings clicked', {
                      totalBookings: upcomingBookings.length,
                    })
                  }
                >
                  View all {upcomingBookings.length} bookings →
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
