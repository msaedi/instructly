import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import RescheduleTimeSelectionModal from './RescheduleTimeSelectionModal';
import { ChatModal } from '@/components/chat/ChatModal';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { Booking } from '@/types/booking';

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
        id: lesson.service?.id || '1',
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
      serviceId: lesson.service?.id,
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

    // Navigate to the booking confirmation page
    onClose();
    router.push('/student/booking/confirm');
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
