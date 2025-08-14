import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { BookingPreview, getLocationTypeIcon } from '@/types/booking';
import { fetchBookingPreview } from '@/lib/api';
import Modal from '@/components/Modal';
import { logger } from '@/lib/logger';

interface BookingQuickPreviewProps {
  bookingId: string;
  onClose: () => void;
  onViewFullDetails: () => void;
}

const BookingQuickPreview: React.FC<BookingQuickPreviewProps> = ({
  bookingId,
  onClose,
  onViewFullDetails,
}) => {
  logger.debug('BookingQuickPreview rendering', { bookingId });

  const [booking, setBooking] = useState<BookingPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Fetch preview data
    fetchBookingPreview(bookingId)
      .then((data) => {
        logger.debug('Booking preview loaded', {
          bookingId,
          studentName: `${data.student_first_name} ${data.student_last_name}`,
          serviceName: data.service_name,
        });
        setBooking(data);
        setLoading(false);
      })
      .catch((err) => {
        logger.error('Failed to load booking preview', err, { bookingId });
        setError('Failed to load booking details');
        setLoading(false);
      });
  }, [bookingId]);

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'short',
      day: 'numeric',
    });
  };

  const formatTime = (timeStr: string) => {
    const [hours, minutes] = timeStr.split(':');
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour % 12 || 12;
    return `${displayHour}:${minutes} ${ampm}`;
  };

  return (
    <Modal isOpen={true} onClose={onClose} title="Booking Details" size="sm" showCloseButton={true}>
      <div className="p-4">
        {loading ? (
          <div className="space-y-2">
            <div className="h-4 bg-gray-200 rounded animate-pulse"></div>
            <div className="h-4 bg-gray-200 rounded animate-pulse w-3/4"></div>
            <div className="h-4 bg-gray-200 rounded animate-pulse w-1/2"></div>
          </div>
        ) : error ? (
          <div className="text-red-500 text-sm">{error}</div>
        ) : (
          booking && (
            <div className="space-y-3">
              {/* Student name */}
              <div>
                <span className="text-sm text-gray-500">Student</span>
                <p className="font-medium">
                  {booking.student_first_name} {booking.student_last_name}
                  {booking.student_last_name.length === 1 ? '.' : ''}
                </p>
              </div>

              {/* Service and duration */}
              <div>
                <span className="text-sm text-gray-500">Service</span>
                <p className="font-medium">
                  {booking.service_name} - {booking.duration_minutes} minutes
                </p>
              </div>

              {/* Date and time */}
              <div>
                <span className="text-sm text-gray-500">When</span>
                <p className="font-medium">{formatDate(booking.booking_date)}</p>
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
          )
        )}
      </div>
    </Modal>
  );
};

export default BookingQuickPreview;
