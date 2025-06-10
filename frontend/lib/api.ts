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

  // For students to check availability
  CHECK_AVAILABILITY: '/api/availability/slots',
  
  // Add more as needed
} as const;