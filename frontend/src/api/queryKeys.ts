/**
 * Centralized React Query key factory.
 *
 * All query keys should be defined here to ensure consistency
 * and prevent cache key collisions across the application.
 *
 * Pattern:
 * - Domain-first organization (auth, instructors, bookings, etc.)
 * - Hierarchical keys: ['domain', 'operation', ...params]
 * - Use 'as const' for type safety
 *
 * CACHE_VERSION: Increment when API endpoints change to bust stale caches.
 * This prevents React Query from serving cached responses made to old endpoints.
 */
const CACHE_VERSION = 'v1' as const;

export const queryKeys = {
  /**
   * Authentication domain
   */
  auth: {
    /** Current user session - /auth/me */
    me: ['auth', 'me'] as const,
  },

  /**
   * Instructors domain
   */
  instructors: {
    /** List instructors with optional filters */
    list: (filters?: { service_catalog_id?: string; page?: number; per_page?: number }) =>
      ['instructors', 'list', filters ?? {}] as const,

    /** Get instructor by ID */
    detail: (id: string) => ['instructors', 'detail', id] as const,

    /** Current instructor profile - /instructors/me */
    me: ['instructors', 'me'] as const,

    /** Instructor coverage (service areas) */
    coverage: (id: string) => ['instructors', 'coverage', id] as const,
  },

  /**
   * Bookings domain
   * Note: CACHE_VERSION included to bust stale caches after API migrations
   */
  bookings: {
    /** List student bookings */
    student: (filters?: {
      status?: string;
      page?: number;
      per_page?: number;
      upcoming_only?: boolean;
      exclude_future_confirmed?: boolean;
      limit?: number;
    }) =>
      ['bookings', CACHE_VERSION, 'student', filters ?? {}] as const,

    /** List instructor bookings */
    instructor: (filters?: { status?: string }) =>
      ['bookings', CACHE_VERSION, 'instructor', filters ?? {}] as const,

    /** Get booking by ID */
    detail: (id: string) => ['bookings', CACHE_VERSION, 'detail', id] as const,
  },

  /**
   * Services domain
   */
  services: {
    /** All services catalog */
    catalog: ['services', 'catalog'] as const,

    /** Service categories */
    categories: ['services', 'categories'] as const,
  },

  /**
   * Availability domain
   */
  availability: {
    /** Instructor availability windows */
    windows: (instructorId: string, filters?: { start_date?: string; end_date?: string }) =>
      ['availability', 'windows', instructorId, filters ?? {}] as const,

    /** Week availability */
    week: (instructorId: string, weekStart: string) =>
      ['availability', 'week', instructorId, weekStart] as const,
  },

  /**
   * Messages domain (Phase 10)
   */
  messages: {
    /** Message config */
    config: ['messages', 'config'] as const,

    /** Unread count for current user */
    unreadCount: ['messages', 'unread-count'] as const,

    /** Message history for a conversation (Phase 7: preferred over booking-based history) */
    conversationMessages: (conversationId: string, pagination?: { limit?: number; before?: string }) =>
      ['messages', 'conversation', conversationId, pagination ?? {}] as const,
  },
} as const;

/**
 * Type helper to extract query key types
 * Usage: QueryKey<typeof queryKeys.auth.me>
 */
export type QueryKey<T extends readonly unknown[]> = T;
