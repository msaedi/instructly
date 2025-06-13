// frontend/lib/api/bookings.ts
import { fetchWithAuth } from '../api';

// Types for API responses and requests
export interface BookingCreateRequest {
  instructor_id: number;
  service_id: number;
  availability_slot_id: number;
  notes?: string;
}

export interface BookingFilters {
  status?: 'CONFIRMED' | 'COMPLETED' | 'CANCELLED' | 'NO_SHOW';
  upcoming?: boolean;  // This will be converted to upcoming_only in the API call
  page?: number;
  per_page?: number;
}

export interface AvailabilityCheckRequest {
  availability_slot_id: number;
  service_id: number;
}

export interface CancelBookingRequest {
  cancellation_reason: string;
}

// API functions
export const bookingsApi = {
  // Check if a slot is available before booking
  checkAvailability: async (data: AvailabilityCheckRequest) => {
    const response = await fetchWithAuth('/bookings/check-availability', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to check availability');
    }
    return response.json();
  },

  // Create an instant booking
  createBooking: async (data: BookingCreateRequest) => {
    const response = await fetchWithAuth('/bookings/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to create booking');
    }
    return response.json();
  },

  // Get current user's bookings (student or instructor)
  getMyBookings: async (filters?: BookingFilters) => {
    const params = new URLSearchParams();
    if (filters?.status) params.append('status', filters.status);
    if (filters?.upcoming !== undefined) params.append('upcoming_only', filters.upcoming.toString());
    if (filters?.page) params.append('page', filters.page.toString());
    if (filters?.per_page) params.append('per_page', filters.per_page.toString());
    
    const response = await fetchWithAuth(`/bookings/?${params.toString()}`);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to fetch bookings');
    }
    return response.json();
  },

  // Get a specific booking by ID
  getBooking: async (bookingId: number) => {
    const response = await fetchWithAuth(`/bookings/${bookingId}`);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to fetch booking');
    }
    return response.json();
  },

  // Cancel a booking (student or instructor)
  cancelBooking: async (bookingId: number, data: CancelBookingRequest) => {
    const response = await fetchWithAuth(`/bookings/${bookingId}/cancel`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        reason: data.cancellation_reason  // Map cancellation_reason to reason
      }),
    });
    
    if (!response.ok) {
      let errorDetail = 'Failed to cancel booking';
      try {
        const error = await response.json();
        
        if (error.detail) {
          if (typeof error.detail === 'string') {
            errorDetail = error.detail;
          } else if (Array.isArray(error.detail)) {
            errorDetail = error.detail.map((e: any) => 
              `${e.loc?.join(' > ') || 'Field'}: ${e.msg}`
            ).join(', ');
          }
        }
      } catch (e) {
        // Silently handle JSON parse errors
      }
      
      throw new Error(errorDetail);
    }
    
    return response.json();
  },

  // Mark a booking as complete (instructor only)
  completeBooking: async (bookingId: number) => {
    const response = await fetchWithAuth(`/bookings/${bookingId}/complete`, {
      method: 'POST',
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to complete booking');
    }
    return response.json();
  },

  // Mark a booking as no-show (instructor only)
  markNoShow: async (bookingId: number) => {
    const response = await fetchWithAuth(`/bookings/${bookingId}/no-show`, {
      method: 'POST',
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to mark as no-show');
    }
    return response.json();
  },

  // Get booking statistics (instructor only)
  getBookingStats: async () => {
    const response = await fetchWithAuth('/bookings/stats');
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to fetch booking stats');
    }
    return response.json();
  },

  // Get upcoming bookings with limit
  getUpcomingBookings: async (limit: number = 5) => {
    const response = await fetchWithAuth(`/bookings/upcoming?limit=${limit}`);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to fetch upcoming bookings');
    }
    return response.json();
  }
};

// Additional availability-related API calls
export const availabilityApi = {
  // Get instructor's availability for a date range
  getInstructorAvailability: async (instructorId: number, startDate: string, endDate: string) => {
    const params = new URLSearchParams({
      start_date: startDate,
      end_date: endDate
    });
    
    const response = await fetchWithAuth(`/availability/instructor/${instructorId}?${params.toString()}`);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to fetch availability');
    }
    return response.json();
  },

  // Get available slots for a specific date
  getAvailableSlots: async (instructorId: number, date: string, serviceId?: number) => {
    const params = new URLSearchParams({ date });
    if (serviceId) params.append('service_id', serviceId.toString());
    
    const response = await fetchWithAuth(`/availability/instructor/${instructorId}/slots?${params.toString()}`);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to fetch available slots');
    }
    return response.json();
  }
};