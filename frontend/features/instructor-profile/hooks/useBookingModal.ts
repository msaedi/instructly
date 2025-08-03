import { useState } from 'react';
import type { InstructorService } from '@/types/instructor';

interface BookingModalState {
  isOpen: boolean;
  selectedDate?: string;
  selectedTime?: string;
  selectedService?: InstructorService;
  selectedDuration?: number;
}

/**
 * Hook to manage booking modal state for instructor profile
 */
export function useBookingModal() {
  const [modalState, setModalState] = useState<BookingModalState>({
    isOpen: false,
  });

  const openBookingModal = (options?: {
    date?: string;
    time?: string;
    service?: InstructorService;
    duration?: number;
  }) => {
    setModalState({
      isOpen: true,
      selectedDate: options?.date,
      selectedTime: options?.time,
      selectedService: options?.service,
      selectedDuration: options?.duration,
    });
  };

  const closeBookingModal = () => {
    setModalState({
      isOpen: false,
    });
  };

  return {
    ...modalState,
    openBookingModal,
    closeBookingModal,
  };
}
