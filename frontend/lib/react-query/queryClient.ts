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
 *
 * CACHE_VERSION: Increment when API endpoints change to bust stale caches.
 * After Phase 13 migration, old cached responses to /bookings/ need to be invalidated.
 */
const CACHE_VERSION = 'v1' as const;

export const queryKeys = {
  // User queries
  user: ['user'] as const,
  users: {
    all: ['users'] as const,
    detail: (id: string) => ['users', id] as const,
  },

  // Booking queries - CACHE_VERSION added to bust stale caches from pre-v1 API
  bookings: {
    all: ['bookings', CACHE_VERSION] as const,
    upcoming: (limit?: number) => ['bookings', CACHE_VERSION, 'upcoming', { limit }] as const,
    history: (page?: number) => ['bookings', CACHE_VERSION, 'history', { page }] as const,
    detail: (id: string) => ['bookings', CACHE_VERSION, id] as const,
    instructor: {
      upcoming: ['bookings', CACHE_VERSION, 'instructor', 'upcoming'] as const,
      past: ['bookings', CACHE_VERSION, 'instructor', 'past'] as const,
    },
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

  // Payments queries
  payments: {
    credits: ['payments', 'credits'] as const,
  },

  // Search queries
  search: {
    recent: ['search', 'recent'] as const,
    suggestions: (query: string) => ['search', 'suggestions', query] as const,
  },

  // Services queries
  services: {
    all: ['services'] as const,
    catalog: ['services', 'catalog'] as const,
    featured: ['services', 'featured'] as const,
    categories: ['services', 'categories'] as const,
    byCategory: (categoryId: string) => ['services', 'category', categoryId] as const,
    withInstructors: ['services', 'with-instructors'] as const,
    topPerCategory: ['services', 'top-per-category'] as const,
    kidsAvailable: ['services', 'kids-available'] as const,
  },

  // 3-level taxonomy queries (ID-based)
  taxonomy: {
    all: ['taxonomy'] as const,
    categoriesWithSubcategories: ['taxonomy', 'categories-browse'] as const,
    categoryTree: (categoryId: string) => ['taxonomy', 'tree', categoryId] as const,
    subcategoriesByCategory: (categoryId: string) => ['taxonomy', 'subcategories', categoryId] as const,
    subcategory: (subcategoryId: string) => ['taxonomy', 'subcategory', subcategoryId] as const,
    subcategoryFilters: (subcategoryId: string) => ['taxonomy', 'filters', subcategoryId] as const,
    servicesByAgeGroup: (ageGroup: string) => ['taxonomy', 'by-age-group', ageGroup] as const,
    filterContext: (serviceId: string) => ['taxonomy', 'filter-context', serviceId] as const,
  },

  // Slug-based catalog browse queries
  catalog: {
    all: ['catalog'] as const,
    categories: ['catalog', 'categories'] as const,
    category: (slug: string) => ['catalog', 'category', slug] as const,
    subcategory: (catSlug: string, subSlug: string) =>
      ['catalog', 'subcategory', catSlug, subSlug] as const,
    service: (id: string) => ['catalog', 'service', id] as const,
    subcategoryServices: (id: string) => ['catalog', 'subcategory-services', id] as const,
    subcategoryFilters: (id: string) => ['catalog', 'subcategory-filters', id] as const,
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
