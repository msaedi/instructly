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
  INSTRUCTOR_AVAILABILITY: '/instructors/availability',
  
  // Add more as needed
} as const;