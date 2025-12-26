// frontend/components/UpcomingLessons.tsx
'use client';

import Link from 'next/link';
import { Calendar, MapPin, ChevronRight } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { hasRole } from '@/features/shared/hooks/useAuth.helpers';
import { RoleName } from '@/types/enums';
import { useUpcomingBookings } from '@/src/api/services/bookings';
import { formatBookingDate, formatBookingTime } from '@/lib/timezone/formatBookingTime';

export function UpcomingLessons() {
  const { isAuthenticated, user, isLoading: isAuthLoading } = useAuth();
  const [isClient, setIsClient] = useState(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

  // Use v1 bookings service to fetch upcoming bookings
  // Note: Always pass valid limit (minimum 1) to avoid 422 validation error.
  // The enabled option in the underlying hook controls whether the request is made.
  const shouldFetch = isClient && !isAuthLoading && isAuthenticated;
  const {
    data: response,
    isLoading,
    error,
  } = useUpcomingBookings(2, { enabled: shouldFetch });

  // Extract bookings from response
  const bookings = response?.items ?? [];

  // Don't render if not authenticated or no bookings
  if (!isClient || isAuthLoading || !isAuthenticated || (!isLoading && bookings.length === 0)) {
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

  const viewerTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const dayKey = (value: Date) =>
    new Intl.DateTimeFormat('en-CA', {
      timeZone: viewerTimezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(value);

  const formatDateLabel = (booking: { booking_start_utc?: string | null; booking_date: string }) => {
    const bookingDate = booking.booking_start_utc
      ? new Date(booking.booking_start_utc)
      : new Date(`${booking.booking_date}T00:00:00`);
    const todayKey = dayKey(new Date());
    const tomorrowKey = dayKey(new Date(Date.now() + 24 * 60 * 60 * 1000));
    const bookingKey = dayKey(bookingDate);

    if (bookingKey === todayKey) {
      return 'Today';
    }
    if (bookingKey === tomorrowKey) {
      return 'Tomorrow';
    }
    return formatBookingDate(booking, viewerTimezone);
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
          <Calendar className="h-6 w-6 text-[#7E22CE] dark:text-purple-400 mr-2" />
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
                  {formatDateLabel(booking)} {formatBookingTime(booking, viewerTimezone)}
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
                {getLocationArea(booking.meeting_location ?? undefined) && (
                  <div className="flex items-center text-sm text-gray-600 dark:text-gray-400 mb-3">
                    <MapPin className="h-3 w-3 mr-1" />
                    {getLocationArea(booking.meeting_location ?? undefined)}
                  </div>
                )}
                <Link
                  href={
                    hasRole(user, RoleName.STUDENT)
                      ? `/student/lessons/${booking.id}`
                      : `/instructor/bookings/${booking.id}`
                  }
                  className="text-sm text-[#7E22CE] hover:text-[#7E22CE] flex items-center gap-1 font-medium"
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
              href={hasRole(user, RoleName.STUDENT) ? '/student/lessons' : '/instructor/dashboard'}
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
