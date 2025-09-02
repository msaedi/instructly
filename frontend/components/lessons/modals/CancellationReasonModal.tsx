import React, { useState } from 'react';
import { logger } from '@/lib/logger';
import { useRouter } from 'next/navigation';
import { CheckCircle } from 'lucide-react';
import Modal from '@/components/Modal';
import { Booking } from '@/types/booking';
import { useCancelLesson } from '@/hooks/useMyLessons';
import { format } from 'date-fns';

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
  const router = useRouter();
  const cancelLesson = useCancelLesson();

  // Calculate hours until lesson
  const lessonDateTime = new Date(`${lesson.booking_date}T${lesson.start_time}`);
  const now = new Date();
  const hoursUntilLesson = (lessonDateTime.getTime() - now.getTime()) / (1000 * 60 * 60);
  const canReschedule = hoursUntilLesson >= 12;

  const handleContinue = async () => {
    if (selectedReason) {
      try {
        await cancelLesson.mutateAsync({ lessonId: lesson.id, reason: selectedReason });
        // Success is handled by showing success state
      } catch (error) {
        logger.error('Failed to cancel lesson', error as Error);
      }
    }
  };

  // Show success state if cancellation was successful
  if (cancelLesson.isSuccess) {
    return (
      <Modal
        isOpen={isOpen}
        onClose={onClose}
        size="md"
        showCloseButton={false}
      >
        <div className="space-y-6 text-center">
          {/* Success Icon */}
          <div className="flex justify-center">
            <CheckCircle className="h-12 w-12 text-purple-700" />
          </div>

          {/* Success Message */}
          <p className="text-2xl font-bold text-gray-900">Your lesson has been cancelled</p>

          {/* Lesson Details */}
          <div className="bg-purple-100 rounded-lg p-4 text-left space-y-2">
            <p className="text-sm">
              <span className="font-medium">Lesson:</span> {lesson.service_name} with{' '}
              {lesson.instructor
                ? `${lesson.instructor.first_name} ${lesson.instructor.last_initial}.`
                : 'Instructor'}
            </p>
            <p className="text-sm">
              <span className="font-medium">Date:</span> {format(lessonDateTime, 'EEEE, MMMM d')} at{' '}
              {format(lessonDateTime, 'h:mm a')}
            </p>
          </div>


          {/* Support Link */}
          <p className="text-sm text-gray-600">
            Questions?{' '}
            <button
              onClick={() => logger.info('Contact support clicked')}
              className="text-purple-700 hover:underline cursor-pointer"
            >
              Contact support
            </button>
          </p>

          {/* Done Button */}
          <button
            onClick={() => {
              onClose();
              router.push('/student/lessons');
            }}
            className="w-full py-3 px-4 bg-[#FFD700] text-black rounded-lg hover:bg-[#FFC700]
                     transition-colors font-medium cursor-pointer"
          >
            Done
          </button>
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="md"
      showCloseButton={false}
    >
        <div className="space-y-4">
          {/* Title */}
          <p className="text-lg font-medium text-gray-900">Please tell us why you&apos;re canceling</p>

          {/* Confirmation warning */}
          <div className="bg-purple-100 rounded-lg p-4">
            <p className="text-sm text-gray-700 font-medium mb-1">Are you sure you want to cancel this lesson?</p>
            <p className="text-sm text-gray-600">This action cannot be undone.</p>
          </div>

          {/* Reschedule Option - only show if more than 12 hours before lesson */}
          {canReschedule && (
            <div className="bg-purple-100 rounded-lg p-4">
              <p className="text-sm text-gray-700">
                Need to reschedule?{' '}
                <button
                  onClick={onReschedule}
                  className="font-medium text-purple-700 underline hover:no-underline cursor-pointer"
                >
                  Reschedule instead
                </button>
              </p>
            </div>
          )}

          {/* Reason Selection */}
          <div>

            <div className="space-y-2">
              {CANCELLATION_REASONS.map((reason) => (
                <label
                  key={reason}
                  className="flex items-start gap-3 p-3 rounded-lg border border-gray-200 cursor-pointer hover:bg-purple-50 transition-colors"
                >
                  <input
                    type="radio"
                    name="cancellation-reason"
                    value={reason}
                    checked={selectedReason === reason}
                    onChange={(e) => setSelectedReason(e.target.value)}
                    className="mt-1 text-purple-700 focus:ring-purple-700"
                  />
                  <span className="text-gray-700">{reason}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex gap-3 mt-6">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-3 px-4 bg-white text-black border-2 border-[#FFD700] rounded-lg
                       hover:bg-[#FFD700]/10 transition-colors font-medium cursor-pointer"
            >
              Keep Lesson
            </button>
            <button
              onClick={handleContinue}
              disabled={!selectedReason || cancelLesson.isPending}
              className="flex-1 py-3 px-4 bg-[#FFD700] text-black rounded-lg hover:bg-[#FFC700]
                       transition-colors font-medium disabled:opacity-50
                       disabled:cursor-not-allowed cursor-pointer"
            >
              {cancelLesson.isPending ? 'Cancelling...' : 'Confirm Cancellation'}
            </button>
          </div>
        </div>
      </Modal>
  );
}
