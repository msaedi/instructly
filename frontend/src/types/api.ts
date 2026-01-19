/**
 * TypeScript types for InstaInstru API
 *
 * MIGRATION NOTE: Types ending in *Request/*Response should come from
 * the generated shim at @/features/shared/api/types. This file contains:
 * - Enums and non-API types
 * - Utility types (renamed to avoid *Request/*Response pattern)
 * - Re-exports from the shim for backward compatibility
 */

import type { ServiceAreaNeighborhood } from '@/types/instructor';

// Re-export generated types from shim for backward compatibility
export type {
  AvailabilityWindowResponse,
  BlackoutDateResponse,
  CopyWeekRequest,
  ApplyToDateRangeRequest,
  BulkUpdateRequest,
  BulkUpdateResponse,
  WeekValidationResponse,
  ValidateWeekRequest,
  AvailabilityCheckRequest,
  AvailabilityCheckResponse,
  BookingStatsResponse,
  PasswordResetRequest,
  PasswordResetResponse,
  ServiceResponse,
  AuthUserResponse,
} from '@/features/shared/api/types';

// Import Gen namespace for type aliases
import type { Gen } from '@/features/shared/api/types';

// Enums
export enum UserRole {
  STUDENT = 'student',
  INSTRUCTOR = 'instructor',
}

export enum BookingStatus {
  PENDING = 'PENDING',
  CONFIRMED = 'CONFIRMED',
  COMPLETED = 'COMPLETED',
  CANCELLED = 'CANCELLED',
  NO_SHOW = 'NO_SHOW',
}

export enum LocationType {
  STUDENT_LOCATION = 'student_location',
  INSTRUCTOR_LOCATION = 'instructor_location',
  ONLINE = 'online',
  NEUTRAL_LOCATION = 'neutral_location',
}

// Interfaces

// From availability.py
export interface AvailabilitySlotBase {
  start_time: string;
  end_time: string;
}

export interface AvailabilitySlotUpdate {
  start_time?: string | null;
  end_time?: string | null;
}

// From availability_window.py
export interface TimeSlot {
  start_time: string;
  end_time: string;
}

export interface AvailabilityWindowBase {
  start_time: string;
  end_time: string;
}

export interface AvailabilityWindowUpdate {
  start_time?: string | null;
  end_time?: string | null;
}

export interface BlackoutDateCreate {
  date: string;
  reason?: string | null;
}

export interface TimeRange {
  start_time: string;
  end_time: string;
}

export interface WeekSpecificScheduleCreate {
  schedule: Array<{
    date: string;
    start_time: string;
    end_time: string;
  }>;
  clear_existing?: boolean;
  week_start?: string | null;
}

export interface SlotOperation {
  action: string;
  date?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  slot_id?: string | null;
}

export interface OperationResult {
  operation_index: number;
  action: string;
  status: string;
  reason?: string | null;
  slot_id?: string | null;
}

export interface ValidationSlotDetail {
  operation_index: number;
  action: string;
  date?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  slot_id?: string | null;
  reason?: string | null;
  conflicts_with?: Array<{
    booking_id?: string | null;
    start_time?: string | null;
    end_time?: string | null;
  }> | null;
}

export interface ValidationSummary {
  total_operations: number;
  valid_operations: number;
  invalid_operations: number;
  operations_by_type: Record<string, number>;
  has_conflicts: boolean;
  estimated_changes: Record<string, number>;
}

// From base.py
// From booking.py
export interface BookingCreate {
  instructor_id: string;
  service_id: string;
  booking_date: string;
  start_time: string;
  end_time: string;
  selected_duration: number;
  student_note?: string | null;
  meeting_location?: string | null;
  location_type?: string | null;
  location_address?: string | null;
  location_lat?: number | null;
  location_lng?: number | null;
  location_place_id?: string | null;
}

export interface BookingUpdate {
  instructor_note?: string | null;
  meeting_location?: string | null;
}

export interface BookingCancel {
  reason: string;
}

export interface BookingBase {
  id: string;
  student_id: string;
  instructor_id: string;
  service_id: string;
  booking_date: string;
  start_time: string;
  end_time: string;
  service_name: string;
  hourly_rate: number;
  total_price: number;
  duration_minutes: number;
  status: BookingStatus;
  service_area: string | null;
  meeting_location: string | null;
  location_type: string | null;
  location_address: string | null;
  location_lat: number | null;
  location_lng: number | null;
  location_place_id: string | null;
  student_note: string | null;
  instructor_note: string | null;
  created_at: string;
  confirmed_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  cancelled_by_id: string | null;
  cancellation_reason: string | null;
}

export interface StudentInfo {
  id: string;
  full_name: string;
  email: string;
}

export interface InstructorInfo {
  id: string;
  full_name: string;
  email: string;
}

export interface ServiceInfo {
  id: string;
  skill: string;
  description: string | null;
}

// Renamed from BookingListResponse (not in generated API)
export interface BookingListData {
  bookings: BookingResponseType[];
  total: number;
  page: number;
  per_page: number;
}
/** @deprecated Use BookingListData instead */
export type BookingListResult = BookingListData;

// Renamed from FindBookingOpportunitiesRequest (not in generated API)
export interface BookingOpportunitiesParams {
  instructor_id: string;
  service_id: string;
  date_range_start: string;
  date_range_end: string;
  preferred_times?: string[] | null;
}

export interface BookingOpportunity {
  date: string;
  start_time: string;
  end_time: string;
  available?: boolean;
}

// Renamed from FindBookingOpportunitiesResponse (not in generated API)
export interface BookingOpportunitiesResult {
  opportunities: BookingOpportunity[];
  total_found: number;
  search_parameters: {
    instructor_id: string;
    instructor_service_id: string;
    date_range_start: string;
    date_range_end: string;
    preferred_times?: string[] | null;
  };
}

// From instructor.py
export interface ServiceBase {
  skill: string;
  hourly_rate: number;
  description?: string | null;
  duration_options: number[];
}

export interface UserBasic {
  full_name: string;
  email: string;
}

export interface InstructorProfileBase {
  bio: string;
  service_area_boroughs?: string[];
  service_area_neighborhoods?: ServiceAreaNeighborhood[];
  service_area_summary?: string | null;
  years_experience: number;
  min_advance_booking_hours?: number;
  buffer_time_minutes?: number;
}

export interface InstructorProfileUpdate {
  bio?: string | null;
  service_area_boroughs?: string[] | null;
  years_experience?: number | null;
  services?: ServiceCreate[] | null;
}

// From password_reset.py
export interface PasswordResetConfirm {
  token: string;
  new_password: string;
}

export interface PasswordResetToken {
  id: string;
  user_id: string;
  token: string;
  expires_at: string;
  used?: boolean;
  created_at: string;
}

// From public_availability.py
export interface PublicTimeSlot {
  start_time?: string;
  end_time?: string;
}

export interface PublicDayAvailability {
  date?: string;
  available_slots?: PublicTimeSlot[];
  is_blackout?: boolean;
}

export interface PublicInstructorAvailability {
  instructor_id: string;
  instructor_first_name?: string | null;
  instructor_last_initial?: string | null;
  availability_by_date?: Record<string, PublicDayAvailability>;
  timezone?: string;
  total_available_slots?: number;
  earliest_available_date?: string | null;
}

export interface PublicAvailabilityQuery {
  start_date?: string;
  end_date?: string | null;
}

export interface PublicAvailabilityMinimal {
  instructor_id: string;
  instructor_first_name?: string | null;
  instructor_last_initial?: string | null;
  has_availability: boolean;
  earliest_available_date?: string | null;
  timezone?: string;
}

export interface PublicAvailabilitySummary {
  instructor_id: string;
  instructor_first_name?: string | null;
  instructor_last_initial?: string | null;
  availability_summary: Record<string, Record<string, unknown>>;
  timezone?: string;
  total_available_days: number;
  detail_level?: 'summary';
}

// From user.py
export interface UserBase {
  email: string;
  full_name?: string | null;
  role: UserRole;
  is_active?: boolean | null;
}

export interface UserLogin {
  email: string;
  password: string;
}

// Renamed from UserResponse (not matching generated AuthUserResponse shape)
export interface UserData {
  id: string;
  email: string;
  full_name?: string | null;
  role: UserRole;
  is_active?: boolean | null;
}

export interface Token {
  access_token: string;
  token_type: string;
}

// Utility Types (renamed to avoid *Request/*Response pattern)

/** Result wrapper for API calls */
export type ApiResult<T> =
  | {
      data: T;
      error?: never;
    }
  | {
      data?: never;
      error: ApiError;
    };

/** Paginated data wrapper */
export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

/** API error structure */
export interface ApiError {
  detail: string;
  code?: string;
  field?: string;
}

export interface RateLimitError {
  detail: {
    message: string;
    code: 'RATE_LIMIT_EXCEEDED';
    retry_after: number;
  };
}

// Authentication Types

export interface AuthToken {
  access_token: string;
  token_type: 'bearer';
}

export interface AuthHeaders {
  Authorization: string;
}

export function getAuthHeaders(token: string): AuthHeaders {
  return {
    Authorization: `Bearer ${token}`,
  };
}

// Custom Type Aliases
export type Money = number; // Monetary values (serialized as float)
export type DateType = string; // ISO date string (YYYY-MM-DD)
export type TimeType = string; // Time string (HH:MM:SS)
export type DateTimeType = string; // ISO datetime string

// Missing Interfaces (manually added)

export interface ServiceCreate {
  skill: string;
  hourly_rate: Money;
  description?: string | null;
  duration_options?: number[] | null;
}

// Type alias to generated type - use Booking from shim instead
export type BookingResponseType = Gen.components['schemas']['BookingResponse'];

export interface InstructorProfileCreate {
  bio: string;
  years_experience: number;
  min_advance_booking_hours?: number;
  buffer_time_minutes?: number;
  services: ServiceCreate[];
  service_area_summary?: string | null;
  service_area_boroughs?: string[];
  service_area_neighborhoods?: ServiceAreaNeighborhood[];
}

// Type alias to generated type - use InstructorProfile from shim instead
export type InstructorProfileResponseType = Gen.components['schemas']['InstructorProfileResponse'];

// Date/Time Helpers

export function formatDate(date: Date): DateType {
  return date.toISOString().split('T')[0] || '';
}

export function formatTime(date: Date): TimeType {
  return date.toTimeString().split(' ')[0] || '';
}

export function parseTime(timeStr: TimeType): Date {
  const timeParts = timeStr.split(':');
  const hours = parseInt(timeParts[0] || '0', 10);
  const minutes = parseInt(timeParts[1] || '0', 10);
  const seconds = parseInt(timeParts[2] || '0', 10);
  const date = new Date();
  date.setHours(hours, minutes, seconds || 0, 0);
  return date;
}

export function parseDate(dateStr: DateType): Date {
  return new Date(dateStr + 'T00:00:00');
}

export function parseDateTime(dateTimeStr: DateTimeType): Date {
  return new Date(dateTimeStr);
}
