import { useState } from 'react';
import { useRouter } from 'next/navigation';
import RescheduleTimeSelectionModal from './RescheduleTimeSelectionModal';
import { ChatModal } from '@/components/chat/ChatModal';
import { useAuth } from '@/features/shared/hooks/useAuth';
import type { Booking } from '@/features/shared/api/types';
import { toast } from 'sonner';

interface RescheduleModalProps {
  isOpen: boolean;
  onClose: () => void;
  lesson: Booking;
}

export function RescheduleModal({ isOpen, onClose, lesson }: RescheduleModalProps) {
  const { user } = useAuth();
  const router = useRouter();
  const [showChatModal, setShowChatModal] = useState(false);

  // Create instructor object for the time selection modal
  const instructor = {
    user_id: lesson.instructor_id,
    user: {
      first_name: lesson.instructor?.first_name || 'Instructor',
      last_initial: lesson.instructor?.last_initial || '',
    },
    services: [
      {
        id: (lesson as unknown as { service?: { id?: string } }).service?.id || '1',
        duration_options: [lesson.duration_minutes], // Use the current lesson duration
        hourly_rate: lesson.hourly_rate,
        skill: lesson.service_name,
      },
    ],
  };

  const handleTimeSelected = (selection: { date: string; time: string; duration: number }) => {
    // Store the reschedule data in session storage for the confirmation page
    const rescheduleData = {
      originalBookingId: lesson.id,
      instructorId: lesson.instructor_id,
      instructorName: lesson.instructor?.first_name || 'Instructor',
      // Use the authoritative instructor_service_id from the original booking
      serviceId: lesson.instructor_service_id,
      serviceName: lesson.service_name,
      date: selection.date,
      time: selection.time,
      duration: selection.duration,
      hourlyRate: lesson.hourly_rate,
      originalDate: lesson.booking_date,
      originalTime: lesson.start_time,
      isReschedule: true
    };

    sessionStorage.setItem('rescheduleData', JSON.stringify(rescheduleData));

    // Server-orchestrated reschedule: cancel old, create new, then navigate to new booking details
    // Keep modal open until we know the outcome
    try {
      // Convert time like "8:00am" to HH:MM
      const lower = selection.time.toLowerCase();
      const core = lower.replace(/am|pm/g, '').trim();
      const [hh, mm] = core.split(':');
      let hour = parseInt(hh || '0', 10);
      const minute = parseInt(mm || '0', 10);
      const isPM = lower.includes('pm');
      const isAM = lower.includes('am');
      if (isPM && hour !== 12) hour += 12;
      if (isAM && hour === 12) hour = 0;
      const startHHMM = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;

      // Call v1 bookings service
      import('@/src/api/services/bookings').then(async ({ rescheduleBookingImperative }) => {
        try {
          const result = await rescheduleBookingImperative(lesson.id, {
            booking_date: selection.date,
            start_time: startHHMM,
            selected_duration: selection.duration,
            instructor_service_id: lesson.instructor_service_id,
          });

          toast.success('Rescheduled successfully');
          onClose();

          // Immediately refresh bookings caches so Upcoming reflects changes without manual refresh
          try {
            const { queryClient, queryKeys } = await import('@/lib/react-query/queryClient');
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.history() });
            await queryClient.invalidateQueries({ queryKey: ['bookings'] });
          } catch {}

          router.push(result.id ? `/student/lessons/${result.id}` : '/student/lessons');
        } catch (err) {
          // Handle API errors
          const errMsg = err instanceof Error ? err.message.toLowerCase() : '';

          // Handle payment-related errors
          if (errMsg.includes('payment_method_required') || errMsg.includes('payment method')) {
            toast.error(
              'A payment method is required to reschedule this lesson. Please add a payment method in Settings and try again.'
            );
            onClose();
            router.push('/student/settings?tab=payment');
            return;
          }

          if (errMsg.includes('payment_confirmation_failed') || errMsg.includes('payment failed')) {
            toast.error(
              "We couldn't process your payment method. Please update your payment method and try again."
            );
            return; // Keep modal open for retry
          }

          // Handle conflict errors (409)
          if (errMsg.includes('409') || errMsg.includes('conflict')) {
            if (errMsg.includes('student') || errMsg.includes('already have a booking')) {
              toast.error('You have another booking at that time. Please pick another time.');
            } else {
              toast.error('That time is no longer available. Please pick another time.');
            }
            return; // keep modal open for re-selection
          }

          // Generic error
          toast.error(err instanceof Error ? err.message : 'Unable to reschedule. Please try again.');
        }
      }).catch(() => {
        toast.error('Network error while rescheduling. Please try again.');
      });
    } catch {
      toast.error('Unexpected error while rescheduling.');
    }
  };

  const handleOpenChat = () => {
    setShowChatModal(true);
  };

  const handleCloseChat = () => {
    setShowChatModal(false);
    onClose(); // Also close the reschedule modal
  };

  // Go straight to the time selection modal
  return (
    <>
      <RescheduleTimeSelectionModal
        isOpen={isOpen && !showChatModal}
        onClose={onClose}
        instructor={instructor}
        onTimeSelected={handleTimeSelected}
        onOpenChat={handleOpenChat}
        currentLesson={{
          date: lesson.booking_date,
          time: lesson.start_time,
          service: lesson.service_name,
        }}
      />

      {/* Chat Modal */}
      {user && lesson.instructor && (
        <ChatModal
          isOpen={showChatModal}
          onClose={handleCloseChat}
          bookingId={lesson.id}
          instructorId={lesson.instructor_id}
          currentUserId={user.id}
          currentUserName={user.first_name}
          otherUserName={lesson.instructor.first_name || 'Instructor'}
          lessonTitle={lesson.service_name}
          lessonDate={`${lesson.booking_date}`}
          isReadOnly={false}
        />
      )}
    </>
  );
}
