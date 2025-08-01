import React, { useState } from 'react';
import Modal from '@/components/Modal';
import { Booking } from '@/types/booking';
import { CancellationConfirmationModal } from './CancellationConfirmationModal';

interface CancellationReasonModalProps {
  isOpen: boolean;
  onClose: () => void;
  lesson: Booking;
  onReschedule: () => void;
}

const CANCELLATION_REASONS = [
  'Lesson was booked by mistake',
  'My schedule changed or conflict',
  "Instructor's schedule changed",
  'Found another instructor',
  'Instructor cancelled or no-show',
  'I changed my mind / no longer need',
  'Emergency or unexpected event',
  'Other reason',
];

export function CancellationReasonModal({
  isOpen,
  onClose,
  lesson,
  onReschedule,
}: CancellationReasonModalProps) {
  const [selectedReason, setSelectedReason] = useState<string | null>(null);
  const [showConfirmationModal, setShowConfirmationModal] = useState(false);

  const handleContinue = () => {
    if (selectedReason) {
      setShowConfirmationModal(true);
    }
  };

  return (
    <>
      <Modal
        isOpen={isOpen && !showConfirmationModal}
        onClose={onClose}
        title="Why do you want to cancel?"
        size="md"
        footer={
          <div className="flex gap-3 justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2.5 text-gray-700 bg-white border border-gray-300 rounded-lg
                       hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2
                       focus:ring-gray-500 transition-all duration-150 font-medium"
            >
              Back
            </button>
            <button
              onClick={handleContinue}
              disabled={!selectedReason}
              className="px-4 py-2.5 bg-red-600 text-white rounded-lg hover:bg-red-700
                       focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500
                       transition-all duration-150 font-medium disabled:opacity-50
                       disabled:cursor-not-allowed"
            >
              Continue
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          {/* Reschedule Option */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <p className="text-sm text-blue-900">
              Need to reschedule instead?{' '}
              <button onClick={onReschedule} className="font-medium underline hover:no-underline">
                Reschedule
              </button>
            </p>
          </div>

          {/* Reason Selection */}
          <div>
            <p className="text-gray-700 mb-4">Still want to cancel? Please let us know why.</p>

            <div className="space-y-2">
              {CANCELLATION_REASONS.map((reason) => (
                <label
                  key={reason}
                  className="flex items-start gap-3 p-3 rounded-lg border cursor-pointer hover:bg-gray-50 transition-colors"
                >
                  <input
                    type="radio"
                    name="cancellation-reason"
                    value={reason}
                    checked={selectedReason === reason}
                    onChange={(e) => setSelectedReason(e.target.value)}
                    className="mt-1 text-primary focus:ring-primary"
                  />
                  <span className="text-gray-700">{reason}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Feedback Note */}
          <p className="text-sm text-gray-600 text-center">
            This feedback helps improve InstaInstru.
          </p>
        </div>
      </Modal>

      {/* Confirmation Modal */}
      <CancellationConfirmationModal
        isOpen={showConfirmationModal}
        onClose={() => {
          setShowConfirmationModal(false);
          onClose();
        }}
        lesson={lesson}
        reason={selectedReason || ''}
      />
    </>
  );
}
