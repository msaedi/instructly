// frontend/components/BookingCard.tsx
import React from 'react';
import { Booking, BookingStatus } from '@/types/booking';
import { logger } from '@/lib/logger';

/**
 * BookingCard Component
 * 
 * Displays a booking card with key information and action buttons.
 * Used in student/instructor booking lists and dashboards.
 * 
 * Features:
 * - Status badge with color coding
 * - Formatted date and time display
 * - Action buttons based on booking status
 * - Notes and cancellation reason display
 * - Responsive design
 * - Hover effects
 * 
 * @component
 * @example
 * ```tsx
 * <BookingCard
 *   booking={booking}
 *   variant="upcoming"
 *   onCancel={() => handleCancel(booking.id)}
 *   onViewDetails={() => handleViewDetails(booking.id)}
 * />
 * ```
 */
interface BookingCardProps {
  /** The booking data to display */
  booking: Booking;
  /** Visual variant of the card */
  variant?: 'upcoming' | 'past' | 'detailed';
  /** Callback when cancel button is clicked */
  onCancel?: () => void;
  /** Callback when complete button is clicked */
  onComplete?: () => void;
  /** Callback when view details button is clicked */
  onViewDetails?: () => void;
  /** Additional CSS classes */
  className?: string;
}

export const BookingCard: React.FC<BookingCardProps> = ({
  booking,
  variant = 'upcoming',
  onCancel,
  onComplete,
  onViewDetails,
  className = ''
}) => {
  /**
   * Format date string for display
   * @param dateStr - ISO date string
   * @returns Formatted date (e.g., "Mon, January 15")
   */
  const formatDate = (dateStr: string): string => {
    try {
      return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-US', {
        weekday: 'short',
        month: 'long',
        day: 'numeric'
      });
    } catch (error) {
      logger.error('Failed to format date', error, { dateStr });
      return dateStr;
    }
  };

  /**
   * Format time string for display
   * @param timeStr - Time string (HH:MM:SS)
   * @returns Formatted time (e.g., "9:00 AM")
   */
  const formatTime = (timeStr: string): string => {
    try {
      const [hours, minutes] = timeStr.split(':').map(Number);
      const period = hours >= 12 ? 'PM' : 'AM';
      const displayHours = hours === 0 ? 12 : hours > 12 ? hours - 12 : hours;
      return `${displayHours}:${minutes.toString().padStart(2, '0')} ${period}`;
    } catch (error) {
      logger.error('Failed to format time', error, { timeStr });
      return timeStr;
    }
  };

  /**
   * Get status badge configuration
   * @param status - Booking status
   * @returns Badge styling and label
   */
  const getStatusBadge = (status: BookingStatus) => {
    const statusConfig = {
      CONFIRMED: { bg: 'bg-green-100', text: 'text-green-800', label: 'Confirmed' },
      COMPLETED: { bg: 'bg-blue-100', text: 'text-blue-800', label: 'Completed' },
      CANCELLED: { bg: 'bg-red-100', text: 'text-red-800', label: 'Cancelled' },
      NO_SHOW: { bg: 'bg-gray-100', text: 'text-gray-800', label: 'No Show' }
    };

    const config = statusConfig[status] || { bg: 'bg-gray-100', text: 'text-gray-800', label: status };
    
    return (
      <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${config.bg} ${config.text}`}>
        {config.label}
      </span>
    );
  };

  // Determine booking state for action buttons
  const isPastBooking = new Date(`${booking.booking_date}T${booking.end_time}`) < new Date();
  const canCancel = booking.status === 'CONFIRMED' && !isPastBooking;
  const canComplete = booking.status === 'CONFIRMED' && isPastBooking;

  logger.debug('Rendering booking card', { 
    bookingId: booking.id, 
    status: booking.status,
    variant,
    canCancel,
    canComplete 
  });

  return (
    <div className={`
      border rounded-lg p-4 bg-white hover:shadow-md transition-shadow duration-200
      ${className}
    `}>
      {/* Header with service name and status */}
      <div className="flex justify-between items-start mb-3">
        <div>
          <h3 className="font-semibold text-lg text-gray-900">
            {booking.service_name}
          </h3>
          <p className="text-sm text-gray-600">
            with {booking.instructor?.full_name || 'Instructor'}
          </p>
        </div>
        {getStatusBadge(booking.status)}
      </div>

      {/* Booking details */}
      <div className="space-y-2 text-sm">
        {/* Date */}
        <div className="flex items-center text-gray-600">
          <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
              d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          {formatDate(booking.booking_date)}
        </div>
        
        {/* Time */}
        <div className="flex items-center text-gray-600">
          <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {formatTime(booking.start_time)} - {formatTime(booking.end_time)}
        </div>
        
        {/* Price */}
        <div className="flex items-center text-gray-600">
          <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
              d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          ${booking.total_price}
        </div>
      </div>

      {/* Student notes */}
      {booking.student_note && (
        <div className="mt-3 p-2 bg-gray-50 rounded text-sm text-gray-600">
          <p className="font-medium">Notes:</p>
          <p>{booking.student_note}</p>
        </div>
      )}

      {/* Cancellation reason */}
      {booking.cancellation_reason && (
        <div className="mt-3 p-2 bg-red-50 rounded text-sm text-red-600">
          <p className="font-medium">Cancellation reason:</p>
          <p>{booking.cancellation_reason}</p>
        </div>
      )}

      {/* Action buttons */}
      <div className="mt-4 flex gap-2">
        {onViewDetails && (
          <button
            onClick={() => {
              logger.info('View details clicked', { bookingId: booking.id });
              onViewDetails();
            }}
            className="flex-1 px-3 py-2 text-sm font-medium text-blue-600 bg-white border border-blue-600 rounded-md hover:bg-blue-50 transition-colors"
          >
            View Details
          </button>
        )}
        {canCancel && onCancel && (
          <button
            onClick={() => {
              logger.info('Cancel booking clicked', { bookingId: booking.id });
              onCancel();
            }}
            className="flex-1 px-3 py-2 text-sm font-medium text-red-600 bg-white border border-red-600 rounded-md hover:bg-red-50 transition-colors"
          >
            Cancel Booking
          </button>
        )}
        {canComplete && onComplete && (
          <button
            onClick={() => {
              logger.info('Mark complete clicked', { bookingId: booking.id });
              onComplete();
            }}
            className="flex-1 px-3 py-2 text-sm font-medium text-green-600 bg-white border border-green-600 rounded-md hover:bg-green-50 transition-colors"
          >
            Mark Complete
          </button>
        )}
      </div>
    </div>
  );
};