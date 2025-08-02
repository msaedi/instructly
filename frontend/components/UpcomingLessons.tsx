// frontend/components/UpcomingLessons.tsx
'use client';

import Link from 'next/link';
import { Calendar, MapPin } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
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
  const { isAuthenticated, user } = useAuth();

  // Use React Query to fetch upcoming bookings
  const {
    data: response,
    isLoading,
    error,
  } = useQuery<UpcomingBookingsResponse>({
    queryKey: queryKeys.bookings.upcoming(2),
    queryFn: queryFn('/bookings/upcoming?limit=2', { requireAuth: true }),
    enabled: isAuthenticated,
    staleTime: CACHE_TIMES.FAST, // 1 minute - upcoming lessons can change frequently
  });

  // Extract bookings from response
  const bookings = response?.items || [];

  // Don't render if not authenticated or no bookings
  if (!isAuthenticated || (!isLoading && bookings.length === 0)) {
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
    const date = new Date(dateStr);
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    if (date.toDateString() === today.toDateString()) {
      return 'Today';
    } else if (date.toDateString() === tomorrow.toDateString()) {
      return 'Tomorrow';
    } else {
      return date.toLocaleDateString('en-US', {
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
    <section className="py-12 bg-white dark:bg-gray-900">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex items-center mb-6">
          <Calendar className="h-6 w-6 text-blue-600 dark:text-blue-400 mr-2" />
          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Your Upcoming Lessons
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:overflow-visible overflow-x-auto">
          <div className="flex gap-4 md:contents">
            {bookings.slice(0, 2).map((booking) => (
              <div
                key={booking.id}
                className="bg-white dark:bg-gray-800 border border-[#E0E0E0] dark:border-gray-700 rounded-lg p-4 hover:shadow-lg transition-shadow min-w-[250px] md:min-w-0"
                style={{ borderRadius: '8px' }}
              >
                <div className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1">
                  {formatDate(booking.booking_date)} {formatTime(booking.start_time)}
                </div>
                <div className="text-base text-gray-800 dark:text-gray-200 mb-1">
                  {booking.service_name}
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                  with{' '}
                  {hasRole(user, RoleName.STUDENT)
                    ? booking.instructor_name
                      ? booking.instructor_name
                          .split(' ')
                          .map((n, i) => (i === 0 ? n : n[0] + '.'))
                          .join(' ')
                      : 'Instructor'
                    : booking.student_name || 'Student'}
                </div>
                {getLocationArea(booking.meeting_location) && (
                  <div className="flex items-center text-sm text-gray-600 dark:text-gray-400 mb-3">
                    <MapPin className="h-3 w-3 mr-1" />
                    {getLocationArea(booking.meeting_location)}
                  </div>
                )}
                <Link
                  href={`/dashboard/${getPrimaryRole(user) || RoleName.STUDENT}/bookings/${
                    booking.id
                  }`}
                  className="text-blue-600 dark:text-blue-400 hover:underline text-sm font-medium"
                >
                  View Details
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
