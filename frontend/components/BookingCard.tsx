// frontend/components/BookingCard.tsx
import React from 'react';
import { Booking, BookingStatus } from '@/types/booking';

interface BookingCardProps {
  booking: Booking;
  variant?: 'upcoming' | 'past' | 'detailed';
  onCancel?: () => void;
  onComplete?: () => void;
  onViewDetails?: () => void;
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
  // Format date and time helpers
  const formatDate = (dateStr: string): string => {
    return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'long',
      day: 'numeric'
    });
  };

  const formatTime = (timeStr: string): string => {
    const [hours, minutes] = timeStr.split(':').map(Number);
    const period = hours >= 12 ? 'PM' : 'AM';
    const displayHours = hours === 0 ? 12 : hours > 12 ? hours - 12 : hours;
    return `${displayHours}:${minutes.toString().padStart(2, '0')} ${period}`;
  };

  // Status badge helper
  const getStatusBadge = (status: BookingStatus) => {
    const statusConfig = {
      CONFIRMED: { bg: 'bg-green-100', text: 'text-green-800', label: 'Confirmed' },
      COMPLETED: { bg: 'bg-blue-100', text: 'text-blue-800', label: 'Completed' },
      CANCELLED: { bg: 'bg-red-100', text: 'text-red-800', label: 'Cancelled' },
      NO_SHOW: { bg: 'bg-gray-100', text: 'text-gray-800', label: 'No Show' }
    };

    const config = statusConfig[status];
    return (
      <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${config.bg} ${config.text}`}>
        {config.label}
      </span>
    );
  };

  const isPastBooking = new Date(`${booking.booking_date}T${booking.end_time}`) < new Date();
  const canCancel = booking.status === 'CONFIRMED' && !isPastBooking;
  const canComplete = booking.status === 'CONFIRMED' && isPastBooking;

  return (
    <div className={`
      border rounded-lg p-4 bg-white hover:shadow-md transition-shadow duration-200
      ${className}
    `}>
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

      <div className="space-y-2 text-sm">
        <div className="flex items-center text-gray-600">
          <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          {formatDate(booking.booking_date)}
        </div>
        <div className="flex items-center text-gray-600">
          <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {formatTime(booking.start_time)} - {formatTime(booking.end_time)}
        </div>
        <div className="flex items-center text-gray-600">
          <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          ${booking.total_price}
        </div>
      </div>

      {booking.notes && (
        <div className="mt-3 p-2 bg-gray-50 rounded text-sm text-gray-600">
          <p className="font-medium">Notes:</p>
          <p>{booking.notes}</p>
        </div>
      )}

      {booking.cancellation_reason && (
        <div className="mt-3 p-2 bg-red-50 rounded text-sm text-red-600">
          <p className="font-medium">Cancellation reason:</p>
          <p>{booking.cancellation_reason}</p>
        </div>
      )}

      <div className="mt-4 flex gap-2">
        {onViewDetails && (
          <button
            onClick={onViewDetails}
            className="flex-1 px-3 py-2 text-sm font-medium text-blue-600 bg-white border border-blue-600 rounded-md hover:bg-blue-50 transition-colors"
          >
            View Details
          </button>
        )}
        {canCancel && onCancel && (
          <button
            onClick={onCancel}
            className="flex-1 px-3 py-2 text-sm font-medium text-red-600 bg-white border border-red-600 rounded-md hover:bg-red-50 transition-colors"
          >
            Cancel Booking
          </button>
        )}
        {canComplete && onComplete && (
          <button
            onClick={onComplete}
            className="flex-1 px-3 py-2 text-sm font-medium text-green-600 bg-white border border-green-600 rounded-md hover:bg-green-50 transition-colors"
          >
            Mark Complete
          </button>
        )}
      </div>
    </div>
  );
};