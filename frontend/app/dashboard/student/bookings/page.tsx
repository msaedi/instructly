// frontend/app/dashboard/student/bookings/page.tsx
'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { protectedApi } from '@/features/shared/api/client';
import { logger } from '@/lib/logger';
import type { Booking } from '@/types/booking';

export default function MyBookingsPage() {
  const router = useRouter();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'upcoming' | 'past' | 'cancelled'>('upcoming');
  const [cancellingBookingId, setCancellingBookingId] = useState<number | null>(null);

  useEffect(() => {
    // Debug token state on page load
    const token = localStorage.getItem('access_token');
    logger.debug('Page load token check', {
      hasToken: !!token,
      tokenLength: token?.length,
      tokenPreview: token ? `${token.substring(0, 20)}...` : 'null',
      pageUrl: window.location.href,
    });

    fetchBookings();
  }, []);

  const fetchBookings = async () => {
    try {
      setLoading(true);
      setError(null);

      // Check if token exists
      const token = localStorage.getItem('access_token');
      logger.info('Fetching bookings for student', {
        hasToken: !!token,
        tokenPreview: token ? `${token.substring(0, 10)}...` : 'null',
      });

      if (!token) {
        throw new Error('No authentication token found. Please log in again.');
      }

      const response = await protectedApi.getBookings({
        limit: 50, // Request up to 50 bookings
      });

      logger.info('Raw API response', {
        hasData: !!response.data,
        hasError: !!response.error,
        status: response.status,
        responseKeys: Object.keys(response),
      });

      if (response.error) {
        logger.error('API returned error', undefined, {
          error: response.error,
          status: response.status,
        });

        // If it's an authentication error, redirect to login
        if (
          response.error.includes('credentials') ||
          response.error.includes('Unauthorized') ||
          response.status === 401
        ) {
          localStorage.removeItem('access_token');
          router.push('/login?message=Session expired. Please log in again.');
          return;
        }

        throw new Error(response.error);
      }

      const bookingsData = Array.isArray(response.data)
        ? response.data
        : response.data?.bookings || [];
      logger.info('Bookings fetched successfully', { count: bookingsData.length });

      if (bookingsData.length > 0) {
        logger.debug('Sample booking structure', { booking: bookingsData[0] });
      }

      setBookings(bookingsData as any);
    } catch (err) {
      logger.error('Failed to fetch bookings', err as Error);

      // Handle specific authentication errors
      if (
        err instanceof Error &&
        (err.message.includes('credentials') || err.message.includes('Unauthorized'))
      ) {
        localStorage.removeItem('access_token');
        setError('Your session has expired. Please log in again.');
        setTimeout(() => {
          router.push('/login?message=Session expired. Please log in again.');
        }, 2000);
      } else {
        setError(
          `Failed to load bookings: ${err instanceof Error ? err.message : 'Unknown error'}`
        );
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCancelBooking = async (bookingId: number) => {
    if (cancellingBookingId) return;

    const shouldCancel = window.confirm('Are you sure you want to cancel this booking?');
    if (!shouldCancel) return;

    setCancellingBookingId(bookingId);

    try {
      const response = await protectedApi.cancelBooking(
        bookingId.toString(),
        'Cancelled by student'
      );
      if (response.error) {
        throw new Error(response.error);
      }
      await fetchBookings();
    } catch (err) {
      alert('Failed to cancel booking. Please try again.');
    } finally {
      setCancellingBookingId(null);
    }
  };

  const filteredBookings = bookings
    .filter((booking) => {
      const bookingDateTime = new Date(`${booking.booking_date}T${booking.end_time}`);
      const now = new Date();

      switch (activeTab) {
        case 'upcoming':
          return bookingDateTime >= now && booking.status.toLowerCase() === 'confirmed';
        case 'past':
          return (
            (bookingDateTime < now && booking.status.toLowerCase() === 'confirmed') ||
            booking.status.toLowerCase() === 'completed'
          );
        case 'cancelled':
          return booking.status.toLowerCase() === 'cancelled';
        default:
          return false;
      }
    })
    .sort((a, b) => {
      const dateTimeA = new Date(`${a.booking_date}T${a.start_time}`);
      const dateTimeB = new Date(`${b.booking_date}T${b.start_time}`);

      if (activeTab === 'upcoming') {
        return dateTimeA.getTime() - dateTimeB.getTime();
      } else {
        return dateTimeB.getTime() - dateTimeA.getTime();
      }
    });

  const getTabCount = (tab: 'upcoming' | 'past' | 'cancelled'): number => {
    return bookings.filter((b) => {
      const bookingDateTime = new Date(`${b.booking_date}T${b.end_time}`);
      const now = new Date();

      switch (tab) {
        case 'upcoming':
          return bookingDateTime >= now && b.status.toLowerCase() === 'confirmed';
        case 'past':
          return (
            (bookingDateTime < now && b.status.toLowerCase() === 'confirmed') ||
            b.status.toLowerCase() === 'completed'
          );
        case 'cancelled':
          return b.status.toLowerCase() === 'cancelled';
        default:
          return false;
      }
    }).length;
  };

  const formatTime = (time: string) => {
    const [hours, minutes] = time.split(':');
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
    return `${displayHour}:${minutes} ${ampm}`;
  };

  const formatDate = (date: string) => {
    return new Date(date + 'T00:00:00').toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  };

  const getLocationDisplay = (booking: Booking) => {
    switch (booking.location_type) {
      case 'student_home':
        return "Student's Home";
      case 'instructor_location':
        return "Instructor's Location";
      case 'neutral':
        return booking.meeting_location || 'Neutral Location';
      default:
        return 'To be determined';
    }
  };

  const handleBookingClick = (booking: Booking) => {
    router.push(`/booking/confirmation?bookingId=${booking.id}`);
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <div className="bg-white dark:bg-gray-800 shadow-sm border-b dark:border-gray-700">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-center">
            <Link
              href="/dashboard/student"
              className="mr-4 p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full transition"
            >
              <svg
                className="h-5 w-5 text-gray-600 dark:text-gray-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15 19l-7-7 7-7"
                />
              </svg>
            </Link>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">My Bookings</h1>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* Tabs */}
        <div className="border-b border-gray-200 dark:border-gray-700 mb-6">
          <nav className="-mb-px flex space-x-8">
            <button
              onClick={() => setActiveTab('upcoming')}
              className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'upcoming'
                  ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
            >
              Upcoming
              <span className="ml-2 text-xs">({getTabCount('upcoming')})</span>
            </button>
            <button
              onClick={() => setActiveTab('past')}
              className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'past'
                  ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
            >
              Past
              <span className="ml-2 text-xs">({getTabCount('past')})</span>
            </button>
            <button
              onClick={() => setActiveTab('cancelled')}
              className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'cancelled'
                  ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
            >
              Cancelled
              <span className="ml-2 text-xs">({getTabCount('cancelled')})</span>
            </button>
          </nav>
        </div>

        {/* Content Area */}
        <div>
          {loading ? (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-indigo-500 mx-auto"></div>
              <p className="mt-2 text-gray-500 dark:text-gray-400">Loading bookings...</p>
            </div>
          ) : error ? (
            <div className="text-center py-8">
              <p className="text-red-600 dark:text-red-400 mb-4">{error}</p>
              <button
                onClick={fetchBookings}
                className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 transition-colors"
              >
                Try Again
              </button>
            </div>
          ) : filteredBookings.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-500 dark:text-gray-400 text-lg">
                {activeTab === 'upcoming' && 'No upcoming bookings'}
                {activeTab === 'past' && 'No past bookings yet'}
                {activeTab === 'cancelled' && 'No cancelled bookings'}
              </p>
              {activeTab === 'upcoming' && (
                <Link
                  href="/search"
                  className="mt-4 inline-block px-6 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 transition-colors"
                >
                  Find an Instructor
                </Link>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              {filteredBookings.map((booking) => (
                <div
                  key={booking.id}
                  className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 cursor-pointer hover:shadow-lg transition-shadow"
                  onClick={() => handleBookingClick(booking)}
                >
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="flex items-start">
                        <div className="w-16 h-16 bg-gray-200 dark:bg-gray-700 rounded-lg mr-4 flex items-center justify-center">
                          <span className="text-2xl">👤</span>
                        </div>
                        <div className="flex-1">
                          <h3 className="font-semibold text-gray-900 dark:text-white">
                            {(booking.instructor as any)?.user?.full_name ||
                              (booking.instructor as any)?.full_name ||
                              `Instructor #${booking.instructor_id}`}
                          </h3>
                          <p className="text-gray-600 dark:text-gray-400">
                            {(booking.service as any)?.skill || `Service #${booking.service_id}`}
                          </p>
                          <div className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                            <p>
                              {formatDate(booking.booking_date)} • {formatTime(booking.start_time)}{' '}
                              - {formatTime(booking.end_time)}
                            </p>
                            <p>{getLocationDisplay(booking)}</p>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="ml-4 flex flex-col items-end">
                      <span
                        className={`px-2 py-1 text-xs font-medium rounded-full ${
                          booking.status.toLowerCase() === 'confirmed'
                            ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                            : booking.status.toLowerCase() === 'completed'
                              ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
                              : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
                        }`}
                      >
                        {booking.status.toLowerCase() === 'confirmed'
                          ? 'Confirmed'
                          : booking.status.toLowerCase() === 'completed'
                            ? 'Completed'
                            : 'Cancelled'}
                      </span>
                      <p className="mt-2 font-semibold text-gray-900 dark:text-white">
                        ${booking.total_price || 'TBD'}
                      </p>
                      {activeTab === 'upcoming' && booking.status.toLowerCase() === 'confirmed' && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleCancelBooking(booking.id);
                          }}
                          disabled={cancellingBookingId === booking.id}
                          className="mt-3 text-sm text-red-600 hover:text-red-500 dark:text-red-400 dark:hover:text-red-300 disabled:opacity-50"
                        >
                          {cancellingBookingId === booking.id ? 'Cancelling...' : 'Cancel Booking'}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
