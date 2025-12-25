// frontend/components/BookingDetailsModal.tsx
import React from 'react';
import { X, Calendar, Clock, MapPin, User, DollarSign, Hash } from 'lucide-react';
import { Booking } from '@/types/booking';
import { logger } from '@/lib/logger';
import { formatInstructorFromUser, formatFullName } from '@/utils/nameDisplay';
import { formatBookingDate, formatBookingTimeRange } from '@/lib/timezone/formatBookingTime';

/**
 * BookingDetailsModal Component
 *
 * Displays comprehensive booking information in a modal dialog.
 * Used by students to view their booking details.
 *
 * Features:
 * - Full booking information display
 * - Status badge with color coding
 * - Service and pricing details
 * - Date and time formatting
 * - Location information
 * - Student/instructor details
 * - Notes and cancellation info
 * - Responsive design with scroll handling
 *
 * @component
 * @example
 * ```tsx
 * <BookingDetailsModal
 *   booking={selectedBooking}
 *   isOpen={showModal}
 *   onClose={() => setShowModal(false)}
 * />
 * ```
 */
interface BookingDetailsModalProps {
  /** The booking to display (null if no booking selected) */
  booking: Booking | null;
  /** Whether the modal is open */
  isOpen: boolean;
  /** Callback when modal should close */
  onClose: () => void;
}

export default function BookingDetailsModal({
  booking,
  isOpen,
  onClose,
}: BookingDetailsModalProps) {
  // Don't render if not open or no booking
  if (!isOpen || !booking) return null;

  logger.debug('Rendering booking details modal', {
    bookingId: booking?.id,
    status: booking?.status,
  });
  const viewerTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const lessonTimezone =
    (booking as { lesson_timezone?: string | null }).lesson_timezone || null;
  const showLessonTimezone = Boolean(
    lessonTimezone && lessonTimezone !== viewerTimezone
  );

  /**
   * Format price for display
   * @param price - Price value (string or number)
   * @returns Formatted price string
   */
  const formatPrice = (price: string | number): string => {
    try {
      if (typeof price === 'number') {
        return price.toFixed(2);
      }
      if (typeof price === 'string' && !isNaN(parseFloat(price))) {
        return parseFloat(price).toFixed(2);
      }
      return '0.00';
    } catch (error) {
      logger.error('Failed to format price', error, { price });
      return '0.00';
    }
  };

  const formatMetaDate = (value?: string | null): string => {
    if (!value) {
      return '';
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }
    return parsed.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  /**
   * Get status badge color classes
   * @param status - Booking status
   * @returns CSS classes for status badge
   */
  const getStatusColor = (status: string): string => {
    const statusColors: Record<string, string> = {
      CONFIRMED: 'bg-green-100 text-green-800',
      COMPLETED: 'bg-gray-100 text-gray-800',
      CANCELLED: 'bg-red-100 text-red-800',
      NO_SHOW: 'bg-yellow-100 text-yellow-800',
    };
    return statusColors[status.toUpperCase()] || 'bg-gray-100 text-gray-800';
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b px-6 py-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-gray-900">Booking Details</h2>
          <button
            onClick={() => {
              logger.debug('Booking details modal closed');
              onClose();
            }}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            aria-label="Close modal"
          >
            <X className="w-5 h-5 text-gray-500" aria-hidden="true" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Status and Confirmation */}
          <div className="flex items-center justify-between">
            <span
              className={`px-3 py-1 rounded-full text-sm font-medium ${getStatusColor(
                booking.status
              )}`}
            >
              {booking.status}
            </span>
            <div className="flex items-center text-gray-600">
              <Hash className="w-4 h-4 mr-1" />
              <span className="text-sm">Booking #{booking.id}</span>
            </div>
          </div>

          {/* Service Info */}
          <div className="bg-blue-50 rounded-lg p-4">
            <h3 className="font-semibold text-lg text-blue-900 mb-2">{booking.service_name}</h3>
            <div className="space-y-1">
              <div className="flex items-center text-blue-700">
                <DollarSign className="w-4 h-4 mr-1" />
                <span>Total: ${formatPrice(booking.total_price)}</span>
              </div>
              {booking.service?.hourly_rate !== undefined && booking.service?.hourly_rate !== null && (
                <div className="flex items-center text-blue-600 text-sm">
                  <span className="ml-5">(${formatPrice(booking.service.hourly_rate as unknown as number | string)}/hour)</span>
                </div>
              )}
            </div>
          </div>

          {/* Date and Time */}
          <div className="grid md:grid-cols-2 gap-4">
            <div className="flex items-start gap-3">
              <Calendar className="w-5 h-5 text-gray-400 mt-0.5" />
              <div>
                <p className="font-medium text-gray-900">Date</p>
                <p className="text-gray-600">{formatBookingDate(booking, viewerTimezone)}</p>
                {showLessonTimezone ? (
                  <p className="text-xs text-gray-500">
                    {formatBookingDate(booking, lessonTimezone ?? undefined)} ({lessonTimezone})
                  </p>
                ) : null}
              </div>
            </div>
            <div className="flex items-start gap-3">
              <Clock className="w-5 h-5 text-gray-400 mt-0.5" />
              <div>
                <p className="font-medium text-gray-900">Time</p>
                <p className="text-gray-600">
                  {formatBookingTimeRange(booking, viewerTimezone)}
                </p>
                {showLessonTimezone ? (
                  <p className="text-xs text-gray-500">
                    {formatBookingTimeRange(booking, lessonTimezone ?? undefined)} ({lessonTimezone})
                  </p>
                ) : null}
              </div>
            </div>
          </div>

          {/* Instructor Info */}
          <div className="border-t pt-6">
            <div className="flex items-start gap-3">
              <User className="w-5 h-5 text-gray-400 mt-0.5" />
              <div className="flex-1">
                <p className="font-medium text-gray-900">Instructor</p>
                <p className="text-lg text-gray-800">
                  {formatInstructorFromUser(booking.instructor) || `Instructor #${booking.instructor_id}`}
                </p>
              </div>
            </div>
          </div>

          {/* Location */}
          <div className="border-t pt-6">
            <div className="flex items-start gap-3">
              <MapPin className="w-5 h-5 text-gray-400 mt-0.5" />
              <div>
                <p className="font-medium text-gray-900">Location</p>
                <p className="text-gray-600">
                  {booking.meeting_location || 'Location details will be provided by instructor'}
                </p>
                {booking.service_area && (
                  <p className="text-sm text-gray-500 mt-1">Service area: {booking.service_area}</p>
                )}
              </div>
            </div>
          </div>

          {/* Student Info (only if viewing as instructor) */}
          {booking.student && (
            <div className="border-t pt-6">
              <div className="flex items-start gap-3">
                <User className="w-5 h-5 text-gray-400 mt-0.5" />
                <div>
                  <p className="font-medium text-gray-900">Student</p>
                  <p className="text-gray-800">{formatFullName(booking.student)}</p>
                  <p className="text-gray-600 text-sm">{booking.student.email}</p>
                </div>
              </div>
            </div>
          )}

          {/* Notes */}
          {booking.student_note && (
            <div className="border-t pt-6">
              <p className="font-medium text-gray-900 mb-2">Booking Notes</p>
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-gray-700">{booking.student_note}</p>
              </div>
            </div>
          )}

          {/* Cancellation Info */}
          {booking.status === 'CANCELLED' && booking.cancellation_reason && (
            <div className="border-t pt-6">
              <p className="font-medium text-gray-900 mb-2">Cancellation Details</p>
              <div className="bg-red-50 rounded-lg p-4">
                <p className="text-red-800">{booking.cancellation_reason}</p>
                {booking.cancelled_at && (
                  <p className="text-red-600 text-sm mt-2">
                    Cancelled on {formatMetaDate(booking.cancelled_at)}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Booking Metadata */}
          <div className="border-t pt-6 text-sm text-gray-500">
            <p>Booked on {formatMetaDate(booking.created_at)}</p>
            {booking.updated_at !== booking.created_at && (
              <p>Last updated {formatMetaDate(booking.updated_at)}</p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 bg-gray-50 px-6 py-4 border-t">
          <button
            onClick={() => {
              logger.debug('Booking details modal closed via button');
              onClose();
            }}
            className="w-full px-4 py-2 bg-gray-200 text-gray-800 rounded-lg hover:bg-gray-300 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
