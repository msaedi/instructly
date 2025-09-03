// frontend/app/(legacy)/dashboard/instructor/bookings/[id]/page.tsx
'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { ArrowLeft, Calendar, Clock, MapPin, User, DollarSign } from 'lucide-react';
import Link from 'next/link';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { Booking, getLocationTypeIcon } from '@/types/booking';
import { logger } from '@/lib/logger';
import { requireString } from '@/lib/ts/safe';

/**
 * BookingDetailsPage Component
 *
 * Displays full booking details for instructors.
 * Features:
 * - Complete booking information display
 * - Action buttons for booking management
 * - Responsive design
 * - Loading and error states
 *
 * Note: Action buttons are placeholders pending A-Team design decisions
 */
export default function BookingDetailsPage() {
  const params = useParams();
  const bookingId = params['id'] as string;

  const [booking, setBooking] = useState<Booking | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /**
   * Fetch booking details from API
   */
  const fetchBookingDetails = useCallback(async () => {
    try {
      logger.debug('Fetching booking details', { bookingId });

      const response = await fetchWithAuth(`${API_ENDPOINTS.BOOKINGS}/${requireString(bookingId)}`);

      if (!response.ok) {
        throw new Error('Failed to fetch booking details');
      }

      const data = await response.json();
      logger.debug('Booking details loaded', {
        bookingId,
        status: data.status,
        studentId: data.student_id,
      });

      setBooking(data);
    } catch (err) {
      const errorMessage = 'Failed to load booking details';
      logger.error('Error fetching booking', err, { bookingId });
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, [bookingId]);

  useEffect(() => {
    if (bookingId) {
      fetchBookingDetails();
    }
  }, [bookingId, fetchBookingDetails]);

  /**
   * Format time string to 12-hour format
   */
  const formatTime = (timeStr: string) => {
    const timeParts = timeStr.split(':');
    const hours = timeParts[0] || '0';
    const minutes = timeParts[1] || '00';
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour % 12 || 12;
    return `${displayHour}:${minutes} ${ampm}`;
  };

  /**
   * Get status badge styling
   */
  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'CONFIRMED':
        return 'bg-green-100 text-green-800';
      case 'COMPLETED':
        return 'bg-gray-100 text-gray-800';
      case 'CANCELLED':
        return 'bg-red-100 text-red-800';
      case 'NO_SHOW':
        return 'bg-yellow-100 text-yellow-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  // Error state
  if (error || !booking) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="text-center">
          <p className="text-red-600 mb-4">{error || 'Booking not found'}</p>
          <Link
            href="/instructor/availability"
            className="inline-flex items-center text-blue-600 hover:text-blue-800"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back to Schedule
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Back Navigation */}
      <Link
        href="/instructor/availability"
        className="inline-flex items-center text-gray-600 hover:text-gray-900 mb-6"
      >
        <ArrowLeft className="w-4 h-4 mr-2" />
        Back to Schedule
      </Link>

      <div className="bg-white rounded-lg shadow">
        {/* Header */}
        <div className="border-b px-6 py-4">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-2xl font-bold">Booking #{booking.id}</h1>
              <p className="text-gray-600 text-sm mt-1">
                Created on {new Date(booking.created_at).toLocaleDateString()}
              </p>
            </div>
            <span
              className={`px-3 py-1 rounded-full text-sm font-medium ${getStatusBadgeClass(
                booking.status
              )}`}
            >
              {booking.status}
            </span>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Service Info */}
          <div className="bg-blue-50 rounded-lg p-4">
            <h2 className="font-semibold text-lg text-blue-900 mb-3">{booking.service_name}</h2>
            <div className="grid md:grid-cols-3 gap-4 text-sm">
              <div className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-blue-600" />
                <span className="text-blue-700">Duration: {booking.duration_minutes} minutes</span>
              </div>
              <div className="flex items-center gap-2">
                <DollarSign className="w-4 h-4 text-blue-600" />
                <span className="text-blue-700">Rate: ${booking.hourly_rate}/hour</span>
              </div>
              <div className="flex items-center gap-2">
                <DollarSign className="w-4 h-4 text-blue-600" />
                <span className="text-blue-700 font-semibold">Total: ${booking.total_price}</span>
              </div>
            </div>
          </div>

          {/* Date and Time */}
          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Calendar className="w-4 h-4 text-gray-400" />
                <h3 className="font-medium text-gray-900">Date</h3>
              </div>
              <p className="text-gray-600">
                {new Date(booking.booking_date).toLocaleDateString('en-US', {
                  weekday: 'long',
                  month: 'long',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </p>
            </div>
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Clock className="w-4 h-4 text-gray-400" />
                <h3 className="font-medium text-gray-900">Time</h3>
              </div>
              <p className="text-gray-600">
                {formatTime(booking.start_time)} - {formatTime(booking.end_time)}
              </p>
            </div>
          </div>

          {/* Location */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <MapPin className="w-4 h-4 text-gray-400" />
              <h3 className="font-medium text-gray-900">Location</h3>
            </div>
            <div className="text-gray-600">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg">
                  {booking.location_type ? getLocationTypeIcon(booking.location_type) : '📍'}
                </span>
                <span className="font-medium">
                  {booking.location_type === 'student_home'
                    ? "Student's Home"
                    : booking.location_type === 'instructor_location'
                      ? "Instructor's Location"
                      : 'Neutral Location'}
                </span>
              </div>
              {booking.meeting_location && (
                <p className="ml-7 text-sm">{booking.meeting_location}</p>
              )}
              {booking.service_area && (
                <p className="ml-7 text-sm text-gray-500">Service area: {booking.service_area}</p>
              )}
            </div>
          </div>

          {/* Student Info */}
          <div className="border-t pt-6">
            <div className="flex items-center gap-2 mb-3">
              <User className="w-4 h-4 text-gray-400" />
              <h3 className="font-medium text-gray-900">Student Information</h3>
            </div>
            <div className="ml-6">
              <p className="text-lg text-gray-800 font-medium">
                {booking.student
                  ? `${booking.student.first_name} ${booking.student.last_name}`
                  : `Student #${booking.student_id}`}
              </p>
              {booking.student?.email && (
                <a
                  href={`mailto:${booking.student.email}`}
                  className="text-blue-600 hover:text-blue-800 text-sm"
                >
                  {booking.student.email}
                </a>
              )}
            </div>
          </div>

          {/* Notes Section */}
          {(booking.student_note || booking.instructor_note) && (
            <div className="border-t pt-6 space-y-4">
              {booking.student_note && (
                <div>
                  <h3 className="font-medium text-gray-900 mb-2">Note from student</h3>
                  <div className="bg-gray-50 rounded-lg p-4">
                    <p className="text-gray-700 italic">&ldquo;{booking.student_note}&rdquo;</p>
                  </div>
                </div>
              )}

              {booking.instructor_note && (
                <div>
                  <h3 className="font-medium text-gray-900 mb-2">Instructor notes</h3>
                  <div className="bg-yellow-50 rounded-lg p-4">
                    <p className="text-gray-700">{booking.instructor_note}</p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Cancellation Info */}
          {booking.status === 'CANCELLED' && booking.cancellation_reason && (
            <div className="border-t pt-6">
              <h3 className="font-medium text-gray-900 mb-2">Cancellation Details</h3>
              <div className="bg-red-50 rounded-lg p-4">
                <p className="text-red-800">
                  <span className="font-medium">Reason:</span> {booking.cancellation_reason}
                </p>
                {booking.cancelled_at && (
                  <p className="text-red-600 text-sm mt-1">
                    Cancelled on {new Date(booking.cancelled_at).toLocaleDateString()}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Action Buttons - Only show for confirmed bookings */}
          {booking.status === 'CONFIRMED' && (
            <div className="border-t pt-6 space-y-3">
              <button
                className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                onClick={() => {
                  logger.info('Mark as complete clicked', { bookingId: booking.id });
                  // TODO: Implement mark as complete functionality
                }}
              >
                Mark as Complete
              </button>
              <div className="grid grid-cols-2 gap-3">
                <button
                  className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
                  onClick={() => {
                    logger.info('Reschedule clicked', { bookingId: booking.id });
                    // TODO: Implement reschedule functionality
                  }}
                >
                  Reschedule
                </button>
                <button
                  className="px-4 py-2 border border-red-300 text-red-700 rounded-lg hover:bg-red-50 transition-colors"
                  onClick={() => {
                    logger.info('Cancel booking clicked', { bookingId: booking.id });
                    // TODO: Implement cancel functionality
                  }}
                >
                  Cancel Booking
                </button>
              </div>
              <p className="text-xs text-gray-500 text-center">
                Note: These actions are not yet implemented
              </p>
            </div>
          )}

          {/* Status-specific messages */}
          {booking.status === 'COMPLETED' && (
            <div className="border-t pt-6">
              <div className="bg-green-50 rounded-lg p-4 text-center">
                <p className="text-green-800">
                  ✓ This booking was completed on{' '}
                  {booking.completed_at
                    ? new Date(booking.completed_at).toLocaleDateString()
                    : 'N/A'}
                </p>
              </div>
            </div>
          )}

          {booking.status === 'NO_SHOW' && (
            <div className="border-t pt-6">
              <div className="bg-yellow-50 rounded-lg p-4 text-center">
                <p className="text-yellow-800">⚠️ Student did not show up for this booking</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
