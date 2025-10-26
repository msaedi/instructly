import { QueryClient } from '@tanstack/react-query';

/**
 * React Query client configuration optimized for InstaInstru marketplace
 *
 * Key design decisions:
 * - 5 minute staleTime: Most data (instructors, availability) changes moderately
 * - 30 minute gcTime: Keep data in memory for smooth back navigation
 * - Smart retry: Skip 4xx errors (user errors), retry 5xx/network errors
 * - Disable refetchOnWindowFocus: Prevents annoying reloads when switching tabs
 * - Enable refetchOnReconnect: Important for mobile users
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Data is considered fresh for 5 minutes
      staleTime: 1000 * 60 * 5,

      // Keep data in cache for 30 minutes (even if stale)
      gcTime: 1000 * 60 * 30,

      // Smart retry logic: no retries for client errors
      retry: (failureCount, error: unknown) => {
        // Don't retry on 4xx errors (client errors)
        if (error && typeof error === 'object' && 'status' in error) {
          const status = error.status;
          if (typeof status === 'number' && status >= 400 && status < 500) {
            return false;
          }
        }
        // Retry up to 3 times for server/network errors
        return failureCount < 3;
      },

      // Disable automatic refetch when window gains focus
      refetchOnWindowFocus: false,

      // Enable refetch when internet connection is restored
      refetchOnReconnect: true,
    },
    mutations: {
      // Don't retry failed mutations by default
      retry: false,
    },
  },
});

/**
 * Cache time configurations for different data types
 * Use these constants for consistency across the app
 */
export const CACHE_TIMES = {
  // Session-long data (user profile, settings)
  SESSION: Infinity,

  // Very fresh data (upcoming lessons widget)
  FAST: 1000 * 60, // 1 minute

  // Frequently changing data (availability, bookings)
  FREQUENT: 1000 * 60 * 5, // 5 minutes

  // Slowly changing data (instructor profiles, services)
  SLOW: 1000 * 60 * 15, // 15 minutes

  // Real-time critical data (current availability slots)
  REALTIME: 1000 * 60, // 1 minute

  // Static data (service categories, locations)
  STATIC: 1000 * 60 * 60, // 1 hour
} as const;

/**
 * Query key factory for consistent key generation
 * Follows hierarchical structure for easy invalidation
 */
export const queryKeys = {
  // User queries
  user: ['user'] as const,
  users: {
    all: ['users'] as const,
    detail: (id: string) => ['users', id] as const,
  },

  // Booking queries
  bookings: {
    all: ['bookings'] as const,
    upcoming: (limit?: number) => ['bookings', 'upcoming', { limit }] as const,
    history: (page?: number) => ['bookings', 'history', { page }] as const,
    detail: (id: string) => ['bookings', id] as const,
  },

  // Instructor queries
  instructors: {
    all: ['instructors'] as const,
    search: (filters: Record<string, unknown>) => ['instructors', 'search', filters] as const,
    detail: (id: string) => ['instructors', id] as const,
    availability: (id: string, date?: string) => ['instructors', id, 'availability', date] as const,
  },

  // Availability queries
  availability: {
    all: ['availability'] as const,
    week: (instructorId: string, startDate: string) =>
      ['availability', 'week', instructorId, startDate] as const,
    booked: (instructorId: string, date: string) =>
      ['availability', 'booked', instructorId, date] as const,
  },

  // Search queries
  search: {
    recent: ['search', 'recent'] as const,
    suggestions: (query: string) => ['search', 'suggestions', query] as const,
  },

  // Services queries
  services: {
    all: ['services'] as const,
    featured: ['services', 'featured'] as const,
    categories: ['services', 'categories'] as const,
    byCategory: (categorySlug: string) => ['services', 'category', categorySlug] as const,
    withInstructors: ['services', 'with-instructors'] as const,
    topPerCategory: ['services', 'top-per-category'] as const,
    kidsAvailable: ['services', 'kids-available'] as const,
  },

  // Notifications queries
  notifications: {
    current: ['notifications', 'current'] as const,
    unread: ['notifications', 'unread'] as const,
  },

  // Badge queries
  badges: {
    student: ['badges', 'student'] as const,
    admin: (params: Record<string, unknown>) => ['badges', 'admin', params] as const,
  },
} as const;
