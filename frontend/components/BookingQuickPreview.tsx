import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { BookingPreview, getLocationTypeIcon } from '@/types/booking';
import { fetchBookingPreview } from '@/lib/api';

interface BookingQuickPreviewProps {
  bookingId: number;
  onClose: () => void;
  onViewFullDetails: () => void;
  position?: { top: number; left: number }; // For desktop popover
  isMobile?: boolean;
}

const BookingQuickPreview: React.FC<BookingQuickPreviewProps> = ({
  bookingId,
  onClose,
  onViewFullDetails,
  position,
  isMobile = false
}) => {
    console.log('BookingQuickPreview rendering with:', { bookingId, position, isMobile });

  const [booking, setBooking] = useState<BookingPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Fetch preview data
    fetchBookingPreview(bookingId)
      .then(data => {
        setBooking(data);
        setLoading(false);
      })
      .catch(err => {
        setError('Failed to load booking details');
        setLoading(false);
      });
  }, [bookingId]);

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { 
      weekday: 'long', 
      month: 'short', 
      day: 'numeric' 
    });
  };

  const formatTime = (timeStr: string) => {
    const [hours, minutes] = timeStr.split(':');
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour % 12 || 12;
    return `${displayHour}:${minutes} ${ampm}`;
  };

  const content = (
    <div className="p-4 bg-white rounded-lg shadow-lg max-w-sm w-full mx-auto">
      {/* Header with close button */}
      <div className="flex justify-between items-start mb-3">
        <h3 className="font-semibold text-lg">Booking Details</h3>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 transition-colors"
          aria-label="Close preview"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Content */}
      {loading ? (
        <div className="space-y-2">
          <div className="h-4 bg-gray-200 rounded animate-pulse"></div>
          <div className="h-4 bg-gray-200 rounded animate-pulse w-3/4"></div>
          <div className="h-4 bg-gray-200 rounded animate-pulse w-1/2"></div>
        </div>
      ) : error ? (
        <div className="text-red-500 text-sm">{error}</div>
      ) : booking && (
        <div className="space-y-3">
          {/* Student name */}
          <div>
            <span className="text-sm text-gray-500">Student</span>
            <p className="font-medium">{booking.student_name}</p>
          </div>

          {/* Service and duration */}
          <div>
            <span className="text-sm text-gray-500">Service</span>
            <p className="font-medium">
              {booking.service_name} - {booking.duration_minutes} min
            </p>
          </div>

          {/* Date and time */}
          <div>
            <span className="text-sm text-gray-500">When</span>
            <p className="font-medium">
              {formatDate(booking.booking_date)}
            </p>
            <p className="text-sm text-gray-600">
              {formatTime(booking.start_time)} - {formatTime(booking.end_time)}
            </p>
          </div>

          {/* Location */}
          <div>
            <span className="text-sm text-gray-500">Location</span>
            <p className="font-medium flex items-center gap-1">
              <span>{getLocationTypeIcon(booking.location_type)}</span>
              <span>{booking.location_type_display}</span>
            </p>
            {booking.meeting_location && (
              <p className="text-sm text-gray-600 mt-1">{booking.meeting_location}</p>
            )}
          </div>

          {/* Student note if present */}
          {booking.student_note && (
            <div>
              <span className="text-sm text-gray-500">Note from student</span>
              <p className="text-sm mt-1 italic text-gray-700">"{booking.student_note}"</p>
            </div>
          )}

          {/* Price */}
          <div className="pt-2 border-t">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-500">Total</span>
              <span className="font-semibold text-lg">${booking.total_price.toFixed(2)}</span>
            </div>
          </div>

          {/* Action button */}
          <button
            onClick={onViewFullDetails}
            className="w-full mt-4 bg-blue-600 text-white py-2 rounded-lg
                     hover:bg-blue-700 transition-colors font-medium"
          >
            View Full Details →
          </button>
        </div>
      )}
    </div>
  );

// For mobile, use the same centered approach
if (isMobile) {
    return (
      <>
        {/* Light backdrop to close on outside click */}
        <div 
          className="fixed inset-0 bg-black/10 z-40" 
          onClick={onClose}
        />
        
        {/* Centered modal with safe padding */}
        <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none">
          <div className="pointer-events-auto w-full max-w-sm px-4">
            {content}
          </div>
        </div>
      </>
    );
  }

// Desktop popover - centered on screen
if (!isMobile) {
    return (
      <>
        {/* Very light backdrop to close on outside click */}
        <div 
          className="fixed inset-0 bg-black/10 z-40" 
          onClick={onClose}
        />
        
        {/* Centered modal */}
        <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none">
          <div className="pointer-events-auto">
            {content}
          </div>
        </div>
      </>
    );
  }

  // Fallback centered modal
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
      {content}
    </div>
  );
};

export default BookingQuickPreview;