import React, { useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';
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
  const [showFullPolicy, setShowFullPolicy] = useState(false);

  const { fee, percentage, hoursUntil } = calculateCancellationFee(lesson);
  const lessonDateTime = new Date(`${lesson.booking_date}T${lesson.start_time}`);

  // Format time until lesson display
  const getTimeUntilDisplay = () => {
    if (hoursUntil > 24) {
      return '> 24 hours';
    } else if (hoursUntil > 12) {
      return '> 12 hours';
    } else {
      return '< 12 hours';
    }
  };

  const handleContinueCancel = () => {
    setShowReasonModal(true);
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Cancel Warning Modal */}
      <div
        className={`fixed inset-0 z-50 overflow-y-auto ${!showReasonModal ? '' : 'hidden'}`}
        style={{ backgroundColor: 'rgba(0, 0, 0, 0.5)' }}
      >
        <div className="flex min-h-full items-center justify-center p-4">
          <div className="bg-white rounded-xl p-6 max-w-md w-full shadow-xl">
            {/* Header */}
            <div className="flex items-center gap-3 mb-4">
              <AlertTriangle className="h-6 w-6 text-yellow-400" />
              <h2 className="text-xl font-semibold text-gray-900">Cancel my lesson</h2>
            </div>

            {/* Lesson Details */}
            <div className="bg-purple-100 rounded-lg p-4 mb-4">
              <p className="text-sm mb-1">
                <span className="font-medium text-gray-700">Your lesson</span>{' '}
                <span className="text-gray-900">
                  {format(lessonDateTime, 'EEEE, MMMM d')} at {format(lessonDateTime, 'h:mm a')}
                </span>
              </p>
              <p className="text-sm">
                <span className="font-medium text-gray-700">Time until Lesson</span>{' '}
                <span className="text-gray-900">{getTimeUntilDisplay()}</span>
              </p>
            </div>

            {/* Cancellation Fee Warning */}
            <div className="mb-4">
              {hoursUntil < 12 ? (
                <p className="text-sm text-gray-700">
                  To respect our instructors&apos; time, unfortunately cancellations made less than 12 hours before a lesson can&apos;t be rescheduled and will be charged in full.
                </p>
              ) : hoursUntil > 24 ? (
                <p className="text-sm text-gray-700">
                  Life happens! You can cancel your session free of charge. Would you like to{' '}
                  <button
                    onClick={onReschedule}
                    className="text-purple-600 hover:text-purple-700 font-medium underline cursor-pointer"
                  >
                    reschedule
                  </button>{' '}
                  instead?
                </p>
              ) : (
                <>
                  <p className="text-lg font-semibold text-gray-900 mb-1">
                    Cancellation fee: ${fee.toFixed(2)}
                  </p>
                  <p className="text-sm text-gray-600">
                    {percentage}% of lesson price will be charged
                  </p>
                </>
              )}
            </div>

            {/* Cancellation Policy Accordion */}
            <div className="mb-6">
              <button
                onClick={() => setShowFullPolicy(!showFullPolicy)}
                className="flex items-center gap-1 text-xs text-gray-600 hover:text-gray-700 transition-colors"
              >
                See full cancellation policy
                {showFullPolicy ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </button>

              {showFullPolicy && (
                <div className="mt-3 text-xs text-gray-600 bg-gray-50 rounded-lg p-4">
                  <p className="font-medium mb-2">Cancellation policy:</p>
                  <ul className="space-y-2 text-gray-500">
                    <li>
                      <span className="font-medium text-gray-600">More than 24 hours before:</span> No worries — cancel or reschedule free of charge.
                    </li>
                    <li>
                      <span className="font-medium text-gray-600">12–24 hours before:</span> We&apos;ll charge your lesson, but don&apos;t worry — the full amount will be added as credit to your account for an easy rebook.
                    </li>
                    <li>
                      <span className="font-medium text-gray-600">Less than 12 hours before:</span> At this point rescheduling isn&apos;t possible, and the full lesson amount will be charged.
                    </li>
                  </ul>
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3">
              <button
                onClick={onClose}
                className="flex-1 py-3 px-4 bg-white text-black border-2 border-[#FFD700] rounded-lg hover:bg-[#FFD700]/10 transition-colors font-medium"
              >
                Keep My Lesson
              </button>
              <button
                onClick={handleContinueCancel}
                className="flex-1 py-3 px-4 bg-[#FFD700] text-black rounded-lg hover:bg-[#FFC700] transition-colors font-medium"
              >
                Continue
              </button>
            </div>
          </div>
        </div>
      </div>

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
