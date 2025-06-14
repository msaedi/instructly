import { WeekSchedule, WeekValidationResponse } from '@/types/availability';
import { BookingPreview } from '@/types/booking';

// frontend/lib/api.ts
export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Helper function for authenticated requests
export const fetchWithAuth = async (endpoint: string, options: RequestInit = {}) => {
  const token = localStorage.getItem('access_token');
  
  return fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': token ? `Bearer ${token}` : '',
    },
  });
};

// Helper function for unauthenticated requests
export const fetchAPI = async (endpoint: string, options: RequestInit = {}) => {
  return fetch(`${API_URL}${endpoint}`, options);
};

// Common API endpoints as constants
export const API_ENDPOINTS = {
  // Auth
  LOGIN: '/auth/login',
  REGISTER: '/auth/register',
  ME: '/auth/me',
  
  // Instructors
  INSTRUCTORS: '/instructors',
  INSTRUCTOR_PROFILE: '/instructors/profile',

  // Availability Management
  INSTRUCTOR_AVAILABILITY_WEEKLY: '/instructors/availability-windows/weekly',
  INSTRUCTOR_AVAILABILITY_PRESET: '/instructors/availability-windows/preset',
  INSTRUCTOR_AVAILABILITY_SPECIFIC: '/instructors/availability-windows/specific-date',
  INSTRUCTOR_BLACKOUT_DATES: '/instructors/availability-windows/blackout-dates',

  // Week-specific availability
  INSTRUCTOR_AVAILABILITY_WEEK: '/instructors/availability-windows/week',
  INSTRUCTOR_AVAILABILITY_COPY_WEEK: '/instructors/availability-windows/copy-week',
  INSTRUCTOR_AVAILABILITY_APPLY_RANGE: '/instructors/availability-windows/apply-to-date-range',
  INSTRUCTOR_AVAILABILITY_BULK_UPDATE: '/instructors/availability-windows/bulk-update',
  INSTRUCTOR_AVAILABILITY: '/instructors/availability-windows/',
  INSTRUCTOR_AVAILABILITY_VALIDATE: '/instructors/availability-windows/week/validate-changes',

  // For students to check availability
  CHECK_AVAILABILITY: '/api/availability/slots',

  // Bookings
  BOOKINGS: '/bookings',
  
  // Add more as needed
} as const;

// Availability validation
export async function validateWeekChanges(
  currentWeek: WeekSchedule,
  savedWeek: WeekSchedule,
  weekStart: Date
): Promise<WeekValidationResponse> {
  const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_VALIDATE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      current_week: currentWeek,
      saved_week: savedWeek,
      week_start: weekStart.toISOString().split('T')[0]
    })
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to validate changes');
  }

  return response.json();
}

export async function fetchBookingPreview(bookingId: number): Promise<BookingPreview> {
  const response = await fetchWithAuth(`${API_ENDPOINTS.BOOKINGS}/${bookingId}/preview`);
  
  if (!response.ok) {
    throw new Error('Failed to fetch booking preview');
  }
  
  return response.json();
}