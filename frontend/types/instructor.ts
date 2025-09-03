// frontend/types/instructor.ts

/**
 * Instructor Type Definitions
 *
 * This module contains all TypeScript interfaces and types related to
 * instructors, their profiles, services, and search results.
 *
 * @module instructor
 */

/**
 * Basic instructor information
 *
 * Used in listings, search results, and anywhere a simplified
 * instructor representation is needed.
 *
 * @interface InstructorBasic
 */
export interface InstructorBasic {
  /** Instructor profile ID (ULID string) */
  id: string;

  /** Associated user ID (ULID string) */
  user_id: string;

  /** Instructor's first name */
  first_name: string;

  /** Instructor's last initial for privacy */
  last_initial: string;

  /** Brief bio/description */
  bio: string;

  /** Years of teaching experience */
  years_experience: number;

  /** Areas served in NYC (array of neighborhood names) */
  areas_of_service: string[];

  /** Average rating (optional, for future use) */
  average_rating?: number;

  /** Total number of reviews (optional, for future use) */
  total_reviews?: number;

  /** Profile image URL (optional, for future use) */
  profile_image_url?: string;
}

/**
 * Complete instructor profile with user information
 *
 * Used in instructor dashboard, detailed profile views, and
 * anywhere full instructor information is needed.
 *
 * @interface InstructorProfile
 * @extends InstructorBasic
 */
export interface InstructorProfile {
  /** Instructor profile ID (ULID string) */
  id: string;

  /** Associated user ID (ULID string) */
  user_id: string;

  /** Detailed bio/description */
  bio: string;

  /** Areas served in NYC (stored as comma-separated string in DB, parsed to array) */
  areas_of_service: string[];

  /** Years of teaching experience */
  years_experience: number;

  /** Associated user information */
  user: {
    /** User's first name */
    first_name: string;
    /** User's last initial for privacy */
    last_initial: string;
    // Email removed for privacy
  };

  /** Services offered by this instructor */
  services: InstructorService[];

  /** Whether the current user has favorited this instructor */
  is_favorited?: boolean;

  /** Total number of students who favorited this instructor */
  favorited_count: number;

  /** Verification status (for future use) */
  is_verified?: boolean;

  /** Background check status (for future use) */
  background_check_completed?: boolean;

  /** Date when instructor joined */
  created_at?: string;

  // Onboarding status fields
  skills_configured?: boolean;
  identity_verified_at?: string | null;
  identity_verification_session_id?: string | null;
  background_check_object_key?: string | null;
  background_check_uploaded_at?: string | null;
  onboarding_completed_at?: string | null;
  is_live?: boolean;
}

/**
 * Service offered by an instructor
 *
 * Represents a specific skill/service that an instructor teaches,
 * including pricing and optional details.
 *
 * @interface InstructorService
 */
export interface InstructorService {
  /** Service ID (ULID string) */
  id: string;

  /** Service catalog ID (ULID string) */
  service_catalog_id?: string;

  /** Skill name (e.g., "Piano", "Yoga", "Spanish") */
  skill?: string;

  /** Hourly rate in USD */
  hourly_rate: number;

  /** Optional service description */
  description: string | null;

  /** Available duration options in minutes */
  duration_options?: number[];

  /** Whether this service is currently active */
  is_active?: boolean;

  /** Age groups this service is offered to (e.g., 'kids', 'adults') */
  age_groups?: string[];

  /** Instructor ID (ULID string, when not nested) */
  instructor_id?: string;
}

/**
 * Instructor search/browse result
 *
 * Used in the browse instructors page and search results,
 * combining instructor info with relevant services.
 *
 * @interface InstructorSearchResult
 */
export interface InstructorSearchResult {
  /** Basic instructor information */
  instructor: InstructorBasic;

  /** Services offered (filtered by search if applicable) */
  services: InstructorService[];

  /** Next available slot (ISO datetime) */
  next_available?: string;

  /** Distance from user (for future location-based search) */
  distance_miles?: number;

  /** Match score (for future search ranking) */
  relevance_score?: number;
}

/**
 * Instructor list response from API
 *
 * Paginated response when fetching multiple instructors
 *
 * @interface InstructorListResponse
 */
export interface InstructorListResponse {
  /** Array of instructor results */
  instructors: InstructorSearchResult[];

  /** Total number of results */
  total: number;

  /** Current page number */
  page: number;

  /** Results per page */
  per_page: number;

  /** Total number of pages */
  total_pages: number;
}

/**
 * Request parameters for searching instructors
 *
 * @interface InstructorSearchParams
 */
export interface InstructorSearchParams {
  /** Search query (matches name, bio, skills) */
  query?: string;

  /** Filter by specific skill */
  skill?: string;

  /** Filter by area of service */
  area?: string;

  /** Minimum hourly rate */
  min_rate?: number;

  /** Maximum hourly rate */
  max_rate?: number;

  /** Minimum years of experience */
  min_experience?: number;

  /** Only show instructors with availability */
  available_only?: boolean;

  /** Sort order */
  sort_by?: 'rating' | 'price_low' | 'price_high' | 'experience' | 'distance';

  /** Page number for pagination */
  page?: number;

  /** Results per page */
  per_page?: number;
}

/**
 * Instructor statistics (for dashboard)
 *
 * @interface InstructorStats
 */
export interface InstructorStats {
  /** Total number of bookings */
  total_bookings: number;

  /** Completed bookings */
  completed_bookings: number;

  /** Cancelled bookings */
  cancelled_bookings: number;

  /** No-show bookings */
  no_show_bookings: number;

  /** Total earnings */
  total_earnings: number;

  /** Average rating */
  average_rating: number;

  /** Total reviews */
  total_reviews: number;

  /** This month's earnings */
  monthly_earnings: number;

  /** This week's bookings */
  weekly_bookings: number;

  /** Upcoming bookings count */
  upcoming_bookings: number;
}

/**
 * Favorited instructor from the favorites API
 *
 * @interface FavoritedInstructor
 */
export interface FavoritedInstructor {
  /** Instructor user ID (ULID string) */
  id: string;

  /** Instructor email */
  email: string;

  /** Instructor first name */
  first_name: string;

  /** Instructor last name */
  last_name: string;

  /** Whether the instructor is active */
  is_active: boolean;

  /** Instructor profile details */
  profile?: InstructorProfile;

  /** When this instructor was favorited */
  favorited_at?: string;

  /** Whether instructor has profile picture (optional API field) */
  has_profile_picture?: boolean;

  /** Profile picture version (optional API field) */
  profile_picture_version?: number;
}

/**
 * Favorites list API response
 *
 * @interface FavoritesListResponse
 */
export interface FavoritesListResponse {
  /** List of favorited instructors */
  favorites: FavoritedInstructor[];

  /** Total number of favorites */
  total: number;
}

/**
 * Type guard to check if a user has an instructor profile
 *
 * @param user - User object to check
 * @returns boolean indicating if user is an instructor
 */
export function isInstructor(user: unknown): user is { instructor_profile: InstructorProfile } {
  return Boolean(user && typeof user === 'object' && 'instructor_profile' in user);
}

/**
 * Helper to format instructor display name
 *
 * @param instructor - Instructor data
 * @returns Formatted display name
 */
export function getInstructorDisplayName(instructor: unknown): string {
  const inst = instructor as Record<string, unknown>;
  // For InstructorProfile with nested user object
  if (inst?.['user'] && typeof inst['user'] === 'object') {
    const user = inst['user'] as Record<string, unknown>;
    if (user?.['first_name'] && user?.['last_initial']) {
      const firstName = String(user['first_name']) || '';
      const lastInitial = String(user['last_initial']) || '';
      return lastInitial ? `${firstName} ${lastInitial}.` : firstName;
    }
  }
  // For InstructorBasic with direct fields
  if (inst?.['first_name'] && inst?.['last_initial']) {
    const firstName = String(inst['first_name']) || '';
    const lastInitial = String(inst['last_initial']) || '';
    return lastInitial ? `${firstName} ${lastInitial}.` : firstName;
  }
  // Fallback
  if (inst?.['user_id']) {
    return 'Instructor #' + String(inst['user_id']);
  }
  return 'Instructor';
}

/**
 * Helper to get primary service (lowest priced or first)
 *
 * @param services - Array of services
 * @returns Primary service or null
 */
export function getPrimaryService(services: InstructorService[]): InstructorService | null {
  if (!services || services.length === 0) return null;

  return services.reduce((primary, service) =>
    service.hourly_rate < primary.hourly_rate ? service : primary
  );
}
