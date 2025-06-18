// frontend/components/modals/CancelBookingModal.tsx
import React, { useState } from 'react';
import { AlertCircle, Calendar, Clock } from 'lucide-react';
import Modal from '@/components/Modal';
import { Booking } from '@/types/booking';
import { logger } from '@/lib/logger';

/**
 * CancelBookingModal Component
 * 
 * Modal dialog for booking cancellation with reason requirement.
 * Updated with professional design system.
 * 
 * @component
 */
interface CancelBookingModalProps {
  /** The booking to cancel (null if none selected) */
  booking: Booking | null;
  /** Whether the modal is open */
  isOpen: boolean;
  /** External error message from parent component */
  error?: string | null;
  /** Callback when modal should close */
  onClose: () => void;
  /** Callback when cancellation is confirmed */
  onConfirm: (reason: string) => Promise<void>;
}

export const CancelBookingModal: React.FC<CancelBookingModalProps> = ({
  booking,
  isOpen,
  error: externalError,
  onClose,
  onConfirm
}) => {
  const [reason, setReason] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [validationError, setValidationError] = useState('');

  // Don't render if not open or no booking
  if (!isOpen || !booking) return null;

  logger.debug('Cancel booking modal opened', { bookingId: booking.id });

  /**
   * Handle form submission
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Validate reason
    if (!reason.trim()) {
      setValidationError('Please provide a reason for cancellation');
      logger.warn('Cancellation attempted without reason', { bookingId: booking.id });
      return;
    }

    setIsLoading(true);
    setValidationError('');

    logger.info('Booking cancellation initiated', { 
      bookingId: booking.id,
      reasonLength: reason.length 
    });

    try {
      await onConfirm(reason);
      setReason(''); // Clear on success
      logger.info('Booking cancellation successful', { bookingId: booking.id });
    } catch (err) {
      logger.error('Booking cancellation failed', err, { bookingId: booking.id });
      setIsLoading(false);
    }
  };

  /**
   * Handle modal close
   */
  const handleClose = () => {
    if (!isLoading) {
      logger.debug('Cancel booking modal closed');
      setReason('');
      setValidationError('');
      onClose();
    }
  };

  /**
   * Format date for display
   */
  const formatDate = (dateStr: string): string => {
    try {
      return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });
    } catch (error) {
      logger.error('Failed to format date in cancel modal', error, { dateStr });
      return dateStr;
    }
  };

  /**
   * Format time for display
   */
  const formatTime = (timeStr: string): string => {
    try {
      const [hours, minutes] = timeStr.split(':');
      const date = new Date();
      date.setHours(parseInt(hours), parseInt(minutes));
      return date.toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
      });
    } catch (error) {
      return timeStr;
    }
  };

  // Display either validation error or external error
  const displayError = validationError || externalError;

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Cancel Booking"
      size="md"
      footer={
        <div className="flex gap-3 justify-end">
          <button
            type="button"
            onClick={handleClose}
            className="px-4 py-2.5 text-gray-700 bg-white border border-gray-300 rounded-lg 
                     hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 
                     focus:ring-gray-500 transition-all duration-150 font-medium"
            disabled={isLoading}
          >
            Keep Booking
          </button>
          <button
            onClick={handleSubmit}
            disabled={isLoading || !reason.trim()}
            className="px-4 py-2.5 bg-red-600 text-white rounded-lg hover:bg-red-700 
                     focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 
                     transition-all duration-150 font-medium disabled:opacity-50 
                     disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isLoading ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                <span>Cancelling...</span>
              </>
            ) : (
              <>
                <AlertCircle className="w-4 h-4" />
                <span>Cancel Booking</span>
              </>
            )}
          </button>
        </div>
      }
    >
      <div className="space-y-6">
        {/* Booking Details */}
        <div className="bg-gray-50 rounded-lg p-4">
          <h4 className="font-medium text-gray-900 mb-3">Booking Details</h4>
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2 text-gray-700">
              <Calendar className="w-4 h-4 text-gray-400" />
              <span>{formatDate(booking.booking_date)}</span>
            </div>
            <div className="flex items-center gap-2 text-gray-700">
              <Clock className="w-4 h-4 text-gray-400" />
              <span>{formatTime(booking.start_time)} - {formatTime(booking.end_time)}</span>
            </div>
            <div className="text-gray-700">
              <span className="font-medium">Service:</span> {booking.service_name}
            </div>
            <div className="text-gray-700">
              <span className="font-medium">{booking.instructor?.full_name || 'Unknown Instructor'}</span>
            </div>
          </div>
        </div>

        {/* Cancellation Policy Warning */}
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm text-amber-900 font-medium">Cancellation Policy</p>
            <p className="text-sm text-amber-700 mt-1">
              Cancellations may be subject to the instructor's cancellation policy. 
              Late cancellations might incur fees.
            </p>
          </div>
        </div>

        {/* Reason Input */}
        <div>
          <label 
            htmlFor="reason" 
            className="block text-sm font-medium text-gray-700 mb-2"
          >
            Cancellation reason <span className="text-red-500">*</span>
          </label>
          <textarea
            id="reason"
            rows={4}
            className={`w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 
                       focus:ring-offset-2 transition-colors ${
                         displayError 
                           ? 'border-red-300 focus:ring-red-500' 
                           : 'border-gray-300 focus:ring-indigo-500'
                       }`}
            placeholder="Please let us know why you need to cancel..."
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              setValidationError(''); // Clear validation error when typing
            }}
            disabled={isLoading}
            aria-describedby={displayError ? "error-message" : undefined}
            aria-invalid={!!displayError}
          />
          {displayError && (
            <p id="error-message" className="mt-2 text-sm text-red-600 flex items-center gap-1">
              <AlertCircle className="w-4 h-4" />
              {displayError}
            </p>
          )}
        </div>
      </div>
    </Modal>
  );
};