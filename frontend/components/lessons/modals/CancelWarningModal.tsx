import React, { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import Modal from '@/components/Modal';
import { Booking } from '@/types/booking';
import { calculateCancellationFee } from '@/hooks/useMyLessons';
import { format } from 'date-fns';
import { CancellationReasonModal } from './CancellationReasonModal';

interface CancelWarningModalProps {
  isOpen: boolean;
  onClose: () => void;
  lesson: Booking;
  onReschedule: () => void;
}

export function CancelWarningModal({
  isOpen,
  onClose,
  lesson,
  onReschedule,
}: CancelWarningModalProps) {
  const [showReasonModal, setShowReasonModal] = useState(false);

  const { fee, percentage, hoursUntil } = calculateCancellationFee(lesson);
  const lessonDateTime = new Date(`${lesson.booking_date}T${lesson.start_time}`);

  const handleContinueCancel = () => {
    setShowReasonModal(true);
  };

  return (
    <>
      <Modal
        isOpen={isOpen && !showReasonModal}
        onClose={onClose}
        title="Cancel lesson"
        size="md"
        footer={
          <div className="flex gap-3 justify-end">
            <button
              type="button"
              onClick={onReschedule}
              className="px-4 py-2.5 bg-primary text-white rounded-lg hover:bg-primary/90
                       focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary
                       transition-all duration-150 font-medium cursor-pointer"
            >
              Reschedule lesson
            </button>
            <button
              onClick={handleContinueCancel}
              className="px-4 py-2.5 text-red-600 bg-white border border-red-300 rounded-lg
                       hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-offset-2
                       focus:ring-red-500 transition-all duration-150 font-medium cursor-pointer"
            >
              Cancel lesson
            </button>
          </div>
        }
      >
        <div className="space-y-6">
          {/* Warning Icon and Title */}
          <div className="flex items-start gap-4">
            <div className="flex-shrink-0">
              <AlertTriangle className="h-6 w-6 text-amber-500" />
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-medium text-gray-900 mb-1">Cancellation Policy</h3>
            </div>
          </div>

          {/* Lesson Details */}
          <div className="bg-gray-50 rounded-lg p-4 space-y-2">
            <p className="text-sm">
              <span className="font-medium">Your lesson:</span>{' '}
              {format(lessonDateTime, 'EEEE, MMMM d')} at {format(lessonDateTime, 'h:mm a')}
            </p>
            <p className="text-sm">
              <span className="font-medium">Time until lesson:</span> {Math.floor(hoursUntil)} hours
            </p>
          </div>

          {/* Cancellation Fee */}
          <div className="border-2 border-amber-200 bg-amber-50 rounded-lg p-4">
            <p className="text-lg font-semibold text-amber-900 mb-1">
              Cancellation fee: ${fee.toFixed(2)}
            </p>
            <p className="text-sm text-amber-700">({percentage}% of lesson price)</p>
          </div>

          {/* Tip to Avoid Fee */}
          <div className="flex items-start gap-3">
            <span className="text-2xl">💡</span>
            <p className="text-gray-700">Avoid the fee by rescheduling instead.</p>
          </div>

          {/* Fee Structure Info */}
          <div className="text-sm text-gray-600 bg-gray-50 rounded-lg p-3">
            <p className="font-medium mb-2">Cancellation fee structure:</p>
            <ul className="space-y-1">
              <li>• More than 24 hours: No fee</li>
              <li>• 12-24 hours: 50% of lesson price</li>
              <li>• Less than 12 hours: 100% of lesson price</li>
            </ul>
          </div>
        </div>
      </Modal>

      {/* Reason Modal */}
      <CancellationReasonModal
        isOpen={showReasonModal}
        onClose={() => {
          setShowReasonModal(false);
          onClose();
        }}
        lesson={lesson}
        onReschedule={() => {
          setShowReasonModal(false);
          onClose();
          onReschedule();
        }}
      />
    </>
  );
}
