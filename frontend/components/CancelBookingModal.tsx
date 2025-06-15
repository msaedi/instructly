// frontend/components/CancelBookingModal.tsx
import React, { useState } from 'react';
import { Booking } from '@/types/booking';
import { logger } from '@/lib/logger';

/**
 * CancelBookingModal Component
 * 
 * Modal dialog for booking cancellation with reason requirement.
 * Handles validation, loading states, and error display.
 * 
 * Features:
 * - Required cancellation reason
 * - Loading state during cancellation
 * - Error handling and display
 * - Warning about cancellation policy
 * - Accessible form controls
 * 
 * @component
 * @example
 * ```tsx
 * <CancelBookingModal
 *   booking={bookingToCancel}
 *   isOpen={showCancelModal}
 *   onClose={() => setShowCancelModal(false)}
 *   onConfirm={handleCancelBooking}
 * />
 * ```
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
      // onClose is handled by parent on success
    } catch (err) {
      logger.error('Booking cancellation failed', err, { bookingId: booking.id });
      // Error is now handled by parent component
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

  // Display either validation error or external error
  const displayError = validationError || externalError;

  return (
    <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
      <div className="relative top-20 mx-auto p-5 border w-96 shadow-lg rounded-md bg-white">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Cancel Booking
        </h3>
        
        <div className="mb-4">
          <p className="text-sm text-gray-600 mb-2">
            Are you sure you want to cancel your <strong>{booking.service_name}</strong> lesson on{' '}
            {formatDate(booking.booking_date)}?
          </p>
          
          {/* Cancellation policy warning */}
          <div className="mt-3 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
            <p className="text-sm text-yellow-800">
              <strong>Note:</strong> Cancellations may be subject to the instructor's cancellation policy.
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label 
              htmlFor="reason" 
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              Cancellation reason (required)
            </label>
            <textarea
              id="reason"
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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
              <p id="error-message" className="mt-1 text-sm text-red-600">
                {displayError}
              </p>
            )}
          </div>

          <div className="flex gap-3">
            <button
              type="button"
              onClick={handleClose}
              className="flex-1 px-4 py-2 bg-gray-200 text-gray-800 rounded-md hover:bg-gray-300 transition-colors disabled:opacity-50"
              disabled={isLoading}
            >
              Keep Booking
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="flex-1 px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 transition-colors"
            >
              {isLoading ? 'Cancelling...' : 'Cancel Booking'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};