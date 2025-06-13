import { X, Calendar, Clock, MapPin, User, DollarSign, Hash } from 'lucide-react';
import { Booking } from '@/types/booking';

interface BookingDetailsModalProps {
  booking: Booking | null;
  isOpen: boolean;
  onClose: () => void;
}

export default function BookingDetailsModal({ booking, isOpen, onClose }: BookingDetailsModalProps) {
  if (!isOpen || !booking) return null;

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
      year: 'numeric'
    });
  };

  const formatTime = (timeStr: string) => {
    const [hours, minutes] = timeStr.split(':');
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour % 12 || 12;
    return `${displayHour}:${minutes} ${ampm}`;
  };

  const formatPrice = (price: any): string => {
    if (typeof price === 'number') {
    return price.toFixed(2);
    }
    if (typeof price === 'string' && !isNaN(parseFloat(price))) {
    return parseFloat(price).toFixed(2);
    }
    return '0.00';
  };

  const getStatusColor = (status: string) => {
    switch (status.toUpperCase()) {
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

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b px-6 py-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-gray-900">Booking Details</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Status and Confirmation */}
          <div className="flex items-center justify-between">
            <span className={`px-3 py-1 rounded-full text-sm font-medium ${getStatusColor(booking.status)}`}>
              {booking.status}
            </span>
            <div className="flex items-center text-gray-600">
              <Hash className="w-4 h-4 mr-1" />
              <span className="text-sm">Booking #{booking.id}</span>
            </div>
          </div>

            {/* Service Info */}
            <div className="bg-blue-50 rounded-lg p-4">
            <h3 className="font-semibold text-lg text-blue-900 mb-2">
                {booking.service_name}
            </h3>
            <div className="space-y-1">
                <div className="flex items-center text-blue-700">
                <DollarSign className="w-4 h-4 mr-1" />
                <span>Total: ${formatPrice(booking.total_price)}</span>
                </div>
                {booking.service?.hourly_rate && (
                <div className="flex items-center text-blue-600 text-sm">
                    <span className="ml-5">
                    (${
                        typeof booking.service.hourly_rate === 'number'
                        ? booking.service.hourly_rate.toFixed(2)
                        : booking.service.hourly_rate
                    }/hour)
                    </span>
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
                <p className="text-gray-600">{formatDate(booking.booking_date)}</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <Clock className="w-5 h-5 text-gray-400 mt-0.5" />
              <div>
                <p className="font-medium text-gray-900">Time</p>
                <p className="text-gray-600">
                  {formatTime(booking.start_time)} - {formatTime(booking.end_time)}
                </p>
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
                {booking.instructor?.full_name || `Instructor #${booking.instructor_id}`}
            </p>
            {/* Note: Bio would need to be fetched separately from InstructorProfile */}
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
                Location details will be provided by instructor
            </p>
            </div>
        </div>
        </div>

        {/* Student Info (optional - only if viewing as instructor) */}
        {booking.student && (
        <div className="border-t pt-6">
            <div className="flex items-start gap-3">
            <User className="w-5 h-5 text-gray-400 mt-0.5" />
            <div>
                <p className="font-medium text-gray-900">Student</p>
                <p className="text-gray-800">{booking.student.full_name}</p>
                <p className="text-gray-600 text-sm">{booking.student.email}</p>
            </div>
            </div>
        </div>
        )}

        {/* Notes */}
        {booking.notes && (
        <div className="border-t pt-6">
            <p className="font-medium text-gray-900 mb-2">Booking Notes</p>
            <div className="bg-gray-50 rounded-lg p-4">
            <p className="text-gray-700">{booking.notes}</p>
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
                    Cancelled on {formatDate(booking.cancelled_at)}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Booking Metadata */}
          <div className="border-t pt-6 text-sm text-gray-500">
            <p>Booked on {formatDate(booking.created_at)}</p>
            {booking.updated_at !== booking.created_at && (
              <p>Last updated {formatDate(booking.updated_at)}</p>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 bg-gray-50 px-6 py-4 border-t">
          <button
            onClick={onClose}
            className="w-full px-4 py-2 bg-gray-200 text-gray-800 rounded-lg hover:bg-gray-300 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}