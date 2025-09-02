// frontend/types/common.ts

/**
 * Common Type Definitions
 *
 * This module contains shared TypeScript interfaces and types used
 * throughout the application for common patterns like pagination,
 * errors, date/time handling, and API responses.
 *
 * @module common
 */

/**
 * Generic paginated response wrapper
 *
 * @interface PaginatedResponse
 * @template T - The type of items in the response
 */
export interface PaginatedResponse<T> {
  /** Array of items for the current page */
  items: T[];

  /** Total number of items across all pages */
  total: number;

  /** Current page number (1-based) */
  page: number;

  /** Number of items per page */
  per_page: number;

  /** Total number of pages */
  total_pages: number;

  /** Whether there's a next page */
  has_next?: boolean;

  /** Whether there's a previous page */
  has_prev?: boolean;
}

/**
 * Alternative pagination format (used by some endpoints)
 *
 * @interface PaginatedList
 * @template T - The type of items in the list
 */
export interface PaginatedList<T> {
  /** Named array of items (e.g., bookings, instructors) */
  [key: string]: T[] | number;

  /** Total count */
  total: number;

  /** Current page */
  page: number;

  /** Items per page */
  per_page: number;
}

/**
 * Standard API error response
 *
 * @interface APIError
 */
export interface APIError {
  /** Error message */
  detail: string | ValidationError[];

  /** HTTP status code */
  status_code?: number;

  /** Error type/code for programmatic handling */
  error_code?: string;

  /** Additional error context */
  context?: Record<string, unknown>;
}

/**
 * Validation error structure
 *
 * @interface ValidationError
 */
export interface ValidationError {
  /** Field location path */
  loc: (string | number)[];

  /** Error message */
  msg: string;

  /** Error type */
  type: string;

  /** Additional context */
  ctx?: Record<string, unknown>;
}

/**
 * Date range for filtering
 *
 * @interface DateRange
 */
export interface DateRange {
  /** Start date (ISO format: YYYY-MM-DD) */
  start_date: string;

  /** End date (ISO format: YYYY-MM-DD) */
  end_date: string;
}

/**
 * Time range within a day
 *
 * @interface TimeRange
 */
export interface TimeRange {
  /** Start time (HH:MM:SS format) */
  start_time: string;

  /** End time (HH:MM:SS format) */
  end_time: string;
}

/**
 * Sort order options
 */
export type SortOrder = 'asc' | 'desc';

/**
 * Common sort options
 */
export enum SortBy {
  DATE = 'date',
  NAME = 'name',
  PRICE = 'price',
  RATING = 'rating',
  CREATED_AT = 'created_at',
  UPDATED_AT = 'updated_at',
}

/**
 * Generic filter parameters
 *
 * @interface FilterParams
 */
export interface FilterParams {
  /** Search query */
  q?: string;

  /** Sort field */
  sort_by?: string;

  /** Sort order */
  order?: SortOrder;

  /** Page number */
  page?: number;

  /** Items per page */
  per_page?: number;

  /** Date range filter */
  date_range?: DateRange;

  /** Additional filters */
  [key: string]: unknown;
}

/**
 * Location type for bookings
 */
export enum LocationType {
  STUDENT_HOME = 'student_home',
  INSTRUCTOR_LOCATION = 'instructor_location',
  NEUTRAL = 'neutral',
}

/**
 * Generic status enum for various entities
 */
export enum Status {
  ACTIVE = 'active',
  INACTIVE = 'inactive',
  PENDING = 'pending',
  APPROVED = 'approved',
  REJECTED = 'rejected',
  ARCHIVED = 'archived',
}

/**
 * Days of the week
 */
export enum DayOfWeek {
  MONDAY = 'monday',
  TUESDAY = 'tuesday',
  WEDNESDAY = 'wednesday',
  THURSDAY = 'thursday',
  FRIDAY = 'friday',
  SATURDAY = 'saturday',
  SUNDAY = 'sunday',
}

/**
 * Address/Location information
 *
 * @interface Address
 */
export interface Address {
  /** Street address line 1 */
  street_1: string;

  /** Street address line 2 (optional) */
  street_2?: string;

  /** City */
  city: string;

  /** State/Province */
  state: string;

  /** ZIP/Postal code */
  zip_code: string;

  /** Country (default: USA) */
  country?: string;

  /** Latitude for mapping */
  latitude?: number;

  /** Longitude for mapping */
  longitude?: number;
}

/**
 * File upload information
 *
 * @interface FileUpload
 */
export interface FileUpload {
  /** File ID */
  id: string;

  /** Original filename */
  filename: string;

  /** MIME type */
  mime_type: string;

  /** File size in bytes */
  size: number;

  /** Storage URL */
  url: string;

  /** Upload timestamp */
  uploaded_at: string;
}

/**
 * Type guard to check if error is an API error
 *
 * @param error - Error to check
 * @returns boolean indicating if error is APIError
 */
export function isAPIError(error: unknown): error is APIError {
  return Boolean(error && typeof error === 'object' && 'detail' in error);
}

/**
 * Extract error message from various error types
 *
 * @param error - Error object
 * @returns Human-readable error message
 */
export function getErrorMessage(error: unknown): string {
  // Handle string errors
  if (typeof error === 'string') return error;

  // Handle API errors
  if (isAPIError(error)) {
    // Handle string detail
    if (typeof error.detail === 'string') return error.detail;

    // Handle validation error array
    if (Array.isArray(error.detail)) {
      return error.detail.map((e) => e.msg).join(', ');
    }

    // Handle rate limit error object
    if (error.detail && typeof error.detail === 'object' && 'message' in error.detail) {
      const detail = error.detail as Record<string, unknown>;

      // For rate limiting, show retry time
      if (detail.code === 'RATE_LIMIT_EXCEEDED' && detail.retry_after) {
        const retryAfter = Number(detail.retry_after);
        if (!isNaN(retryAfter)) {
          const minutes = Math.ceil(retryAfter / 60);
          return `${detail.message} (Try again in ${minutes} minute${minutes > 1 ? 's' : ''})`;
        }
      }

      return String(detail.message);
    }
  }

  // Handle standard Error objects
  if (error instanceof Error) return error.message;

  // Handle objects with message property
  if (error && typeof error === 'object' && 'message' in error) {
    const errorObj = error as { message: unknown };
    return String(errorObj.message);
  }

  // Default fallback
  return 'An unexpected error occurred';
}

/**
 * Format date for display
 *
 * @param dateStr - ISO date string
 * @param options - Intl.DateTimeFormat options
 * @returns Formatted date string
 */
export function formatDate(dateStr: string, options?: Intl.DateTimeFormatOptions): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString(
    'en-US',
    options || {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    }
  );
}

/**
 * Format time for display
 *
 * @param timeStr - Time string (HH:MM:SS)
 * @returns Formatted time (12-hour format)
 */
export function formatTime(timeStr: string): string {
  const [hours, minutes] = timeStr.split(':');
  const hour = parseInt(hours);
  const ampm = hour >= 12 ? 'PM' : 'AM';
  const displayHour = hour % 12 || 12;
  return `${displayHour}:${minutes} ${ampm}`;
}

/**
 * Create a date range for the current week
 *
 * @param startOfWeek - Day to start week (0 = Sunday, 1 = Monday)
 * @returns DateRange object
 */
export function getCurrentWeekRange(startOfWeek: number = 1): DateRange {
  const today = new Date();
  const currentDay = today.getDay();
  const diff = currentDay < startOfWeek ? 7 - startOfWeek + currentDay : currentDay - startOfWeek;

  const monday = new Date(today);
  monday.setDate(today.getDate() - diff);

  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);

  return {
    start_date: monday.toISOString().split('T')[0],
    end_date: sunday.toISOString().split('T')[0],
  };
}

/**
 * Rate limit error detail structure
 */
export interface RateLimitErrorDetail {
  message: string;
  code: 'RATE_LIMIT_EXCEEDED';
  retry_after: number;
}

/**
 * Check if an error is a rate limit error
 * @param error - Error to check
 * @returns boolean indicating if it's a rate limit error
 */
export function isRateLimitError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  if (!('detail' in error)) return false;

  const detail = error.detail;
  if (!detail || typeof detail !== 'object') return false;
  if (!('code' in detail)) return false;

  return (detail as Record<string, unknown>).code === 'RATE_LIMIT_EXCEEDED';
}

/**
 * Get retry time in seconds from a rate limit error
 * @param error - Error to check
 * @returns Number of seconds to wait, or null if not a rate limit error
 */
export function getRateLimitRetryTime(error: unknown): number | null {
  if (!isRateLimitError(error)) return null;

  const apiError = error as { detail: Record<string, unknown> };
  const detail = apiError.detail;
  return typeof detail.retry_after === 'number' ? detail.retry_after : null;
}
