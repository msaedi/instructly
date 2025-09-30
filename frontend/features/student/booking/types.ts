// frontend/features/student/booking/types.ts

import type { ServiceAreaNeighborhood } from '@/types/instructor';

export interface Service {
  id: string;
  skill: string;
  hourly_rate: number;
  description?: string;
  duration_options: number[];
  duration: number;
  is_active?: boolean;
}

export interface Instructor {
  id?: string; // Optional for compatibility with different data sources
  user_id: string;
  user: {
    first_name: string;
    last_initial: string;  // Privacy protected
    // Email removed for privacy
  };
  bio: string;
  service_area_boroughs?: string[];
  service_area_neighborhoods?: ServiceAreaNeighborhood[];
  service_area_summary?: string | null;
  years_experience: number;
  services: Service[];
  rating?: number;
  total_reviews?: number;
  verified?: boolean;
  // Additional fields that might come from the API
  min_advance_booking_hours?: number;
  buffer_time_minutes?: number;
  created_at?: string;
  updated_at?: string;
  total_hours_taught?: number;
  education?: string;
  languages?: string[];
}

export interface BookingFlowState {
  instructor: Instructor;
  selectedDate: string;
  selectedTime: string;
  selectedService?: Service;
  duration: number;
  totalPrice: number;
  userInfo?: {
    name: string;
    email: string;
    phone: string;
    notes: string;
  };
}

export interface BookingModalProps {
  isOpen: boolean;
  onClose: () => void;
  instructor: Instructor;
  selectedDate: string;
  selectedTime: string;
  onContinueToBooking: (bookingData: BookingFlowState) => void;
}

export interface TimeSlot {
  start_time: string;
  end_time: string;
  is_available?: boolean;
}

export interface AvailabilityDay {
  date: string;
  slots: TimeSlot[];
}
