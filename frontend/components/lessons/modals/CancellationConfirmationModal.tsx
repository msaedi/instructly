import React from 'react';
import { CheckCircle } from 'lucide-react';
import Modal from '@/components/Modal';
import { Booking } from '@/types/booking';
import { useCancelLesson, calculateCancellationFee } from '@/hooks/useMyLessons';
import { format } from 'date-fns';
import { useRouter } from 'next/navigation';
import { logger } from '@/lib/logger';

interface CancellationConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  lesson: Booking;
  reason: string;
}

export function CancellationConfirmationModal({
  isOpen,
  onClose,
  lesson,
  reason,
}: CancellationConfirmationModalProps) {
  const router = useRouter();
  const cancelLesson = useCancelLesson();
  const { fee, percentage } = calculateCancellationFee(lesson);

  const handleConfirmCancellation = async () => {
    try {
      await cancelLesson.mutateAsync({ lessonId: lesson.id, reason });
      // Modal will show success state before closing
    } catch (error) {
      logger.error('Failed to cancel lesson', error as Error);
    }
  };

  const lessonDateTime = new Date(`${lesson.booking_date}T${lesson.start_time}`);

  // If cancellation was successful, show success message
  if (cancelLesson.isSuccess) {
    return (
      <Modal
        isOpen={isOpen}
        onClose={onClose}
        title="Your lesson has been cancelled"
        size="md"
        showCloseButton={false}
        footer={
          <div className="flex justify-center">
            <button
              onClick={() => {
                onClose();
                router.push('/student/lessons');
              }}
              className="px-6 py-3 bg-[#FFD700] text-black rounded-lg hover:bg-[#FFC700]
                       transition-colors font-medium cursor-pointer"
            >
              Done
            </button>
          </div>
        }
      >
        <div className="space-y-6 text-center">
          {/* Success Icon */}
          <div className="flex justify-center">
            <CheckCircle className="h-12 w-12 text-green-500" />
          </div>

          {/* Success Message */}
          <p className="text-lg font-medium text-gray-900">Cancellation confirmed</p>

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

          {/* Fee and Credit Info */}
          {fee > 0 && (
            <div className="border rounded-lg p-4 text-left space-y-2">
              <p className="text-sm">
                <span className="font-medium">Cancellation fee:</span> ${fee.toFixed(2)}
              </p>
              <p className="text-sm">
                <span className="font-medium">Credit issued:</span> ${fee.toFixed(2)}
              </p>
            </div>
          )}

          {/* Credit Notice */}
          <p className="text-sm text-gray-600">
            {fee > 0
              ? 'Your credit will be applied to your next booking automatically.'
              : 'No cancellation fee was charged.'}
          </p>

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
        </div>
      </Modal>
    );
  }

  // Show confirmation dialog
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Confirm Cancellation"
      size="md"
      footer={
        <div className="flex gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={cancelLesson.isPending}
            className="flex-1 py-3 px-4 bg-white text-black border-2 border-[#FFD700] rounded-lg
                     hover:bg-[#FFD700]/10 transition-colors font-medium
                     disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            Keep Lesson
          </button>
          <button
            onClick={handleConfirmCancellation}
            disabled={cancelLesson.isPending}
            className="flex-1 py-3 px-4 bg-[#FFD700] text-black rounded-lg hover:bg-[#FFC700]
                     transition-colors font-medium disabled:opacity-50
                     disabled:cursor-not-allowed cursor-pointer"
          >
            {cancelLesson.isPending ? 'Cancelling...' : 'Confirm Cancellation'}
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        {/* Final Warning */}
        <div className="bg-purple-100 rounded-lg p-4">
          <p className="text-sm text-gray-700 font-medium mb-2">
            Are you sure you want to cancel this lesson?
          </p>
          <p className="text-sm text-gray-600">This action cannot be undone.</p>
        </div>

        {/* Lesson Summary */}
        <div className="rounded-lg p-4 space-y-2 border border-gray-200">
          <p className="text-sm">
            <span className="font-medium">Lesson:</span> {lesson.service_name}
          </p>
          <p className="text-sm">
            <span className="font-medium">Instructor:</span> {lesson.instructor
              ? `${lesson.instructor.first_name} ${lesson.instructor.last_initial}.`
              : 'Instructor'}
          </p>
          <p className="text-sm">
            <span className="font-medium">Date:</span> {format(lessonDateTime, 'EEEE, MMMM d')} at{' '}
            {format(lessonDateTime, 'h:mm a')}
          </p>
        </div>

        {/* Fee Information */}
        {fee > 0 && (
          <div className="border-2 border-amber-200 bg-amber-50 rounded-lg p-4">
            <p className="text-sm font-medium text-amber-900">
              A cancellation fee of ${fee.toFixed(2)} ({percentage}%) will be charged.
            </p>
            <p className="text-sm text-amber-700 mt-1">
              You will receive a credit for this amount to use on future bookings.
            </p>
          </div>
        )}

        {/* Reason */}
        <div>
          <p className="text-sm font-medium text-gray-700 mb-1">Reason for cancellation:</p>
          <p className="text-sm text-gray-600">{reason}</p>
        </div>
      </div>
    </Modal>
  );
}
