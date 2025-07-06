// frontend/types/booking.ts

// Booking status enum
export type BookingStatus = 'CONFIRMED' | 'COMPLETED' | 'CANCELLED' | 'NO_SHOW';
export type LocationType = 'student_home' | 'instructor_location' | 'neutral';

// Main booking interface matching backend schema
export interface Booking {
  id: number;
  student_id: number;
  instructor_id: number;
  service_id: number;
  // REMOVED: availability_slot_id - no longer exists in backend

  // Date and time fields
  booking_date: string; // ISO date string (YYYY-MM-DD)
  start_time: string; // Time string (HH:MM:SS)
  end_time: string; // Time string (HH:MM:SS)

  // Booking details
  status: BookingStatus;
  service_name: string; // Snapshot of service name at booking time
  hourly_rate: number;
  total_price: number;
  duration_minutes: number;

  // Location fields
  service_area?: string;
  meeting_location?: string;
  location_type?: LocationType;

  // Notes
  student_note?: string;
  instructor_note?: string;

  // Timestamps
  created_at: string; // ISO datetime string
  updated_at: string; // ISO datetime string
  confirmed_at?: string;
  completed_at?: string;
  cancelled_at?: string; // ISO datetime string

  // Cancellation fields
  cancelled_by?: 'STUDENT' | 'INSTRUCTOR';
  cancelled_by_id?: number;
  cancellation_reason?: string;

  // Relations (populated in detailed views)
  student?: User;
  instructor?: User;
  service?: Service;
  // REMOVED: availability_slot relation
}

// User type for relations
export interface User {
  id: number;
  email: string;
  full_name: string;
  role: 'STUDENT' | 'INSTRUCTOR';
  created_at: string;
}

// Service offered by instructor
export interface Service {
  id: number;
  instructor_profile_id: number;
  name: string;
  description: string;
  hourly_rate: number;
  typical_duration?: number; // in minutes
  created_at: string;
  updated_at: string;
}

// Instructor profile extension
export interface InstructorProfile {
  id: number;
  user_id: number;
  bio: string;
  experience_years: number;
  areas_of_service: string[]; // NYC neighborhoods
  min_advance_booking_hours: number;
  buffer_time_minutes: number;
  created_at: string;
  updated_at: string;

  // Relations
  user?: User;
  services?: Service[];
}

// Single-table availability slot (Work Stream #10)
export interface AvailabilitySlot {
  id: number;
  instructor_id: number; // Direct reference, no availability_id
  date: string; // YYYY-MM-DD
  start_time: string; // HH:MM:SS
  end_time: string; // HH:MM:SS
  created_at: string;
  updated_at: string;
}

// REMOVED: InstructorAvailability type - table no longer exists in backend

// Blackout date
export interface BlackoutDate {
  id: number;
  instructor_id: number;
  date: string; // YYYY-MM-DD
  reason?: string;
  created_at: string;
}

// API Response wrappers
export interface PaginatedResponse<T> {
  bookings: T[]; // Changed from 'items' to match backend
  total: number;
  page: number;
  per_page: number;
}

export interface BookingListResponse extends PaginatedResponse<Booking> {}

export interface AvailabilityResponse {
  instructor_id: number;
  start_date: string;
  end_date: string;
  availabilities: AvailabilitySlot[]; // Direct slots, no wrapper
  blackout_dates: BlackoutDate[];
}

// NEW: Time-based booking creation
export interface BookingCreate {
  instructor_id: number;
  service_id: number;
  booking_date: string; // ISO date: "2025-07-15"
  start_time: string; // 24hr format: "09:00"
  end_time: string; // 24hr format: "10:00"
  student_note?: string;
  meeting_location?: string;
  location_type?: LocationType;
}

// Form/UI specific types
export interface TimeSlot {
  id: number;
  date: string;
  start_time: string;
  end_time: string;
}

// Booking creation response
export interface BookingCreateResponse {
  booking: Booking;
  message: string;
}

// NEW: Time-based availability check
export interface AvailabilityCheckRequest {
  instructor_id: number;
  service_id: number;
  booking_date: string; // ISO date
  start_time: string; // 24hr format
  end_time: string; // 24hr format
}

export interface AvailabilityCheckResponse {
  available: boolean;
  reason?: string;
  time_info?: {
    date: string;
    start_time: string;
    end_time: string;
    instructor_id: number;
  };
  min_advance_hours?: number;
}

export interface BookedSlotPreview {
  booking_id: number;
  date: string;
  start_time: string;
  end_time: string;
  student_first_name: string;
  student_last_initial: string;
  service_name: string;
  service_area_short: string;
  duration_minutes: number;
  location_type: LocationType;
}

export interface BookedSlotsResponse {
  booked_slots: BookedSlotPreview[];
}

export interface BookingPreview {
  booking_id: number;
  student_name: string;
  instructor_name: string;
  service_name: string;
  booking_date: string;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  location_type: LocationType;
  location_type_display: string;
  meeting_location?: string;
  service_area?: string;
  status: string;
  student_note?: string;
  total_price: number;
}

// Add location type display helper
export const getLocationTypeDisplay = (locationType: LocationType): string => {
  switch (locationType) {
    case 'student_home':
      return "Student's Home";
    case 'instructor_location':
      return "Instructor's Location";
    case 'neutral':
      return 'Neutral Location';
    default:
      return 'Location TBD';
  }
};

// Add location type icon helper
export const getLocationTypeIcon = (locationType: LocationType): string => {
  switch (locationType) {
    case 'student_home':
      return '🏠';
    case 'instructor_location':
      return '🏫';
    case 'neutral':
      return '📍';
    default:
      return '📍';
  }
};

/**
 * Filters for querying bookings
 */
export interface BookingFilters {
  /** Filter by booking status */
  status?: BookingStatus;
  /** Filter for upcoming bookings only */
  upcoming?: boolean;
  /** Page number for pagination */
  page?: number;
  /** Number of items per page */
  per_page?: number;
}

/**
 * Request payload for cancelling a booking
 */
export interface CancelBookingRequest {
  /** Reason for cancellation */
  cancellation_reason: string;
}

/**
 * Response for booking list queries
 */
export interface BookingListResponse {
  /** Array of bookings */
  bookings: Booking[];
  /** Total number of bookings (for pagination) */
  total: number;
  /** Current page number */
  page: number;
  /** Items per page */
  per_page: number;
  /** Total number of pages */
  pages: number;
}

/**
 * Response for booking statistics
 */
export interface BookingStatsResponse {
  /** Total number of bookings */
  total_bookings: number;
  /** Number of completed bookings */
  completed_bookings: number;
  /** Number of cancelled bookings */
  cancelled_bookings?: number;
  /** Number of no-show bookings */
  no_show_bookings?: number;
  /** Total revenue earned */
  total_revenue?: number;
  /** Average booking value */
  average_booking_value?: number;
}

/**
 * Response for availability slot queries
 */
export interface AvailabilitySlotResponse {
  /** Slot ID */
  id: number;
  /** Date of the slot */
  date: string;
  /** Start time */
  start_time: string;
  /** End time */
  end_time: string;
}
