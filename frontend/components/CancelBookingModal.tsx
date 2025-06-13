// frontend/components/CancelBookingModal.tsx
import React, { useState } from 'react';
import { Booking } from '@/types/booking';

interface CancelBookingModalProps {
    booking: Booking | null;
    isOpen: boolean;
    error?: string | null;
    onClose: () => void;
    onConfirm: (reason: string) => Promise<void>;
}

export const CancelBookingModal: React.FC<CancelBookingModalProps> = ({
  booking,
  isOpen,
  error: externalError,  // Rename to avoid conflict
  onClose,
  onConfirm
}) => {
  const [reason, setReason] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [validationError, setValidationError] = useState('');  // Renamed for clarity

  if (!isOpen || !booking) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!reason.trim()) {
      setValidationError('Please provide a reason for cancellation');
      return;
    }

    setIsLoading(true);
    setValidationError('');

    try {
      await onConfirm(reason);
      setReason('');
      // onClose is handled by parent on success
    } catch (err) {
      // Error is now handled by parent component
      setIsLoading(false);
    }
  };

  const handleClose = () => {
    if (!isLoading) {
      setReason('');
      setValidationError('');
      onClose();
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
            Are you sure you want to cancel your {booking.service_name} lesson on{' '}
            {new Date(booking.booking_date + 'T00:00:00').toLocaleDateString('en-US', {
              weekday: 'long',
              year: 'numeric',
              month: 'long',
              day: 'numeric'
            })}?
          </p>
          
          <div className="mt-3 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
            <p className="text-sm text-yellow-800">
              <strong>Note:</strong> Cancellations may be subject to the instructor's cancellation policy.
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label htmlFor="reason" className="block text-sm font-medium text-gray-700 mb-2">
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
            />
            {displayError && (
              <p className="mt-1 text-sm text-red-600">{displayError}</p>
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