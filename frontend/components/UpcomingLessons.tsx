// frontend/components/UpcomingLessons.tsx
'use client';

import Link from 'next/link';
import { Calendar, MapPin, ChevronRight } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { queryFn } from '@/lib/react-query/api';
import { UpcomingBooking } from '@/types/booking';
import { logger } from '@/lib/logger';
import { useAuth, hasRole, getPrimaryRole } from '@/features/shared/hooks/useAuth';
import { RoleName } from '@/types/enums';

interface UpcomingBookingsResponse {
  items: UpcomingBooking[];
  total: number;
  page: number;
  per_page: number;
  has_next: boolean;
  has_prev: boolean;
}

export function UpcomingLessons() {
  const { isAuthenticated, user, isLoading: isAuthLoading } = useAuth();
  const [isClient, setIsClient] = useState(false);
  const hasToken = typeof window !== 'undefined' && !!localStorage.getItem('access_token');

  useEffect(() => {
    setIsClient(true);
  }, []);

  // Use React Query to fetch upcoming bookings
  const {
    data: response,
    isLoading,
    error,
  } = useQuery<UpcomingBookingsResponse>({
    queryKey: queryKeys.bookings.upcoming(2),
    queryFn: queryFn('/bookings/upcoming?limit=2', { requireAuth: true }),
    enabled: isClient && !isAuthLoading && isAuthenticated && hasToken,
    staleTime: CACHE_TIMES.FAST, // 1 minute - upcoming lessons can change frequently
    retry: 0,
  });

  // Extract bookings from response
  const bookings = response?.items ?? [];

  // Don't render if not authenticated or no bookings
  if (!isClient || isAuthLoading || !isAuthenticated || !hasToken || (!isLoading && bookings.length === 0)) {
    return null;
  }

  if (isLoading) {
    return (
      <section className="py-12 bg-white dark:bg-gray-900">
        <div className="max-w-7xl mx-auto px-4">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">
            📅 Your Upcoming Lessons
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="bg-gray-100 dark:bg-gray-800 rounded-lg p-4 animate-pulse">
                <div className="h-4 bg-gray-300 dark:bg-gray-700 rounded w-3/4 mb-2"></div>
                <div className="h-3 bg-gray-300 dark:bg-gray-700 rounded w-1/2 mb-2"></div>
                <div className="h-3 bg-gray-300 dark:bg-gray-700 rounded w-2/3"></div>
              </div>
            ))}
          </div>
        </div>
      </section>
    );
  }

  if (error) {
    return null; // Silently fail for now
  }

  const formatDate = (dateStr: string) => {
    // Parse the date string properly (assuming YYYY-MM-DD format from backend)
    const [year, month, day] = dateStr.split('-').map(Number);
    const bookingDate = new Date(year, month - 1, day); // month is 0-indexed

    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    // Compare using date strings to avoid timezone issues
    const bookingDateStr = bookingDate.toDateString();
    const todayStr = today.toDateString();
    const tomorrowStr = tomorrow.toDateString();

    if (bookingDateStr === todayStr) {
      return 'Today';
    } else if (bookingDateStr === tomorrowStr) {
      return 'Tomorrow';
    } else {
      return bookingDate.toLocaleDateString('en-US', {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
      });
    }
  };

  const formatTime = (timeStr: string) => {
    const [hours, minutes] = timeStr.split(':');
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'pm' : 'am';
    const displayHour = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
    return `${displayHour}:${minutes}${ampm}`;
  };

  const getLocationArea = (location?: string) => {
    if (!location) return null;
    // Extract area from location (e.g., "Upper West Side" from full address)
    const areas = ['Upper West', 'Midtown', 'Brooklyn', 'Queens', 'Harlem', 'Downtown'];
    for (const area of areas) {
      if (location.toLowerCase().includes(area.toLowerCase())) {
        return area;
      }
    }
    return null;
  };

  return (
    <section className="py-3 bg-white dark:bg-gray-900" style={{ borderTop: '0.5px solid #E0E0E0', borderBottom: '0.5px solid #E0E0E0' }}>
      <div className="max-w-4xl ml-8 px-1 pl-4">
        <div className="flex items-center mb-3">
          <Calendar className="h-6 w-6 text-purple-700 dark:text-purple-400 mr-2" />
          <h2 className="text-2xl font-bold text-gray-600">
            Your Upcoming Lessons
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 md:overflow-visible overflow-x-auto">
          <div className="flex gap-4 md:contents">
            {bookings.slice(0, 2).map((booking) => (
              <div
                key={booking.id}
                className="bg-white dark:bg-gray-800 rounded-lg p-2 hover:shadow-lg transition-shadow min-w-[250px] md:min-w-0"
                style={{ borderRadius: '8px', border: '0.5px solid #E0E0E0' }}
              >
                <div className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1">
                  {formatDate(booking.booking_date)} {formatTime(booking.start_time)}
                </div>
                <div className="text-base font-bold text-gray-600 mb-1">
                  {booking.service_name}
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                  with{' '}
                  {hasRole(user, RoleName.STUDENT)
                    ? booking.instructor_first_name
                      ? `${booking.instructor_first_name} ${booking.instructor_last_name}${booking.instructor_last_name.length === 1 ? '.' : ''}`
                      : 'Instructor'
                    : booking.student_first_name
                      ? `${booking.student_first_name} ${booking.student_last_name}${booking.student_last_name.length === 1 ? '.' : ''}`
                      : 'Student'}
                </div>
                {getLocationArea(booking.meeting_location) && (
                  <div className="flex items-center text-sm text-gray-600 dark:text-gray-400 mb-3">
                    <MapPin className="h-3 w-3 mr-1" />
                    {getLocationArea(booking.meeting_location)}
                  </div>
                )}
                <Link
                  href={
                    hasRole(user, RoleName.STUDENT)
                      ? `/student/lessons/${booking.id}`
                      : `/instructor/bookings/${booking.id}`
                  }
                  className="text-sm text-purple-700 hover:text-purple-800 flex items-center gap-1 font-medium"
                >
                  See lesson details
                  <ChevronRight className="h-4 w-4" />
                </Link>
              </div>
            ))}
          </div>
        </div>

        {bookings.length > 2 && (
          <div className="mt-4 text-center">
            <Link
              href={`/dashboard/${getPrimaryRole(user) || RoleName.STUDENT}/bookings`}
              className="text-blue-600 dark:text-blue-400 hover:underline"
            >
              View all {bookings.length} upcoming lessons →
            </Link>
          </div>
        )}
      </div>
    </section>
  );
}
