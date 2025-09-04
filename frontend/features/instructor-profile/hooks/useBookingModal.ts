import { useState } from 'react';

interface BookingModalState {
  isOpen: boolean;
  selectedDate?: string;
  selectedTime?: string;
  selectedService?: unknown;
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
    service?: unknown;
    duration?: number;
  }) => {
    setModalState({
      isOpen: true,
      ...(options?.date !== undefined && { selectedDate: options.date }),
      ...(options?.time !== undefined && { selectedTime: options.time }),
      ...(options?.service !== undefined && { selectedService: options.service }),
      ...(options?.duration !== undefined && { selectedDuration: options.duration }),
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
