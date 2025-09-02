// Generated TypeScript types for InstaInstru API
// DO NOT EDIT - This file is auto-generated from Pydantic schemas

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
  STUDENT_HOME = 'student_home',
  INSTRUCTOR_LOCATION = 'instructor_location',
  NEUTRAL = 'neutral',
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

export interface AvailabilityWindowResponse {
  id: string;
  instructor_id: string;
  specific_date: string;
  start_time: string;
  end_time: string;
}

export interface BlackoutDateCreate {
  date: string;
  reason?: string | null;
}

export interface BlackoutDateResponse {
  id: string;
  instructor_id: string;
  date: string;
  reason?: string | null;
  created_at: string;
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
    [key: string]: unknown;
  }>;
  clear_existing?: boolean;
  week_start?: string | null;
}

export interface CopyWeekRequest {
  from_week_start: string;
  to_week_start: string;
}

export interface ApplyToDateRangeRequest {
  from_week_start: string;
  start_date: string;
  end_date: string;
}

export interface SlotOperation {
  action: string;
  date?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  slot_id?: string | null;
}

export interface BulkUpdateRequest {
  operations: SlotOperation[];
  validate_only?: boolean;
}

export interface OperationResult {
  operation_index: number;
  action: string;
  status: string;
  reason?: string | null;
  slot_id?: string | null;
}

export interface BulkUpdateResponse {
  successful: number;
  failed: number;
  skipped: number;
  results: OperationResult[];
}

export interface ValidationSlotDetail {
  operation_index: number;
  action: string;
  date?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  slot_id?: string | null;
  reason?: string | null;
  conflicts_with?: Array<Record<string, unknown>> | null;
}

export interface ValidationSummary {
  total_operations: number;
  valid_operations: number;
  invalid_operations: number;
  operations_by_type: Record<string, number>;
  has_conflicts: boolean;
  estimated_changes: Record<string, number>;
}

export interface WeekValidationResponse {
  valid: boolean;
  summary: ValidationSummary;
  details: ValidationSlotDetail[];
  warnings?: string[];
}

export interface ValidateWeekRequest {
  current_week: Record<string, TimeSlot[]>;
  saved_week: Record<string, TimeSlot[]>;
  week_start: string;
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

export interface BookingListResponse {
  bookings: BookingResponse[];
  total: number;
  page: number;
  per_page: number;
}

export interface AvailabilityCheckRequest {
  instructor_id: string;
  service_id: string;
  booking_date: string;
  start_time: string;
  end_time: string;
}

export interface AvailabilityCheckResponse {
  available: boolean;
  reason?: string | null;
  min_advance_hours?: number | null;
  conflicts_with?: Array<Record<string, unknown>> | null;
}

export interface BookingStatsResponse {
  total_bookings: number;
  upcoming_bookings: number;
  completed_bookings: number;
  cancelled_bookings: number;
  total_earnings: number;
  this_month_earnings: number;
  average_rating?: number | null;
}


export interface FindBookingOpportunitiesRequest {
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

export interface FindBookingOpportunitiesResponse {
  opportunities: BookingOpportunity[];
  total_found: number;
  search_parameters: Record<string, unknown>;
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
  areas_of_service: string[];
  years_experience: number;
  min_advance_booking_hours?: number;
  buffer_time_minutes?: number;
}

export interface InstructorProfileUpdate {
  bio?: string | null;
  areas_of_service?: string[] | null;
  years_experience?: number | null;
  services?: ServiceCreate[] | null;
}

// From password_reset.py
export interface PasswordResetRequest {
  email: string;
}

export interface PasswordResetConfirm {
  token: string;
  new_password: string;
}

export interface PasswordResetResponse {
  message: string;
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

export interface UserResponse {
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

// Utility Types

export type ApiResponse<T> =
  | {
      data: T;
      error?: never;
    }
  | {
      data?: never;
      error: ErrorResponse;
    };

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface ErrorResponse {
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

export interface ServiceResponse {
  id: string;
  skill: string;
  hourly_rate: Money;
  description?: string | null;
  duration_options: number[];
  duration: number;
}

export interface BookingResponse {
  id: string;
  student_id: string;
  instructor_id: string;
  service_id: string;
  booking_date: string;
  start_time: string;
  end_time: string;
  service_name: string;
  hourly_rate: Money;
  total_price: Money;
  duration_minutes: number;
  status: BookingStatus;
  service_area?: string | null;
  meeting_location?: string | null;
  location_type?: string | null;
  student_note?: string | null;
  instructor_note?: string | null;
  created_at: string;
  confirmed_at?: string | null;
  completed_at?: string | null;
  cancelled_at?: string | null;
  cancelled_by_id?: string | null;
  cancellation_reason?: string | null;
  student?: StudentInfo;
  instructor?: InstructorInfo;
  service?: ServiceInfo;
}

export interface InstructorProfileCreate {
  bio: string;
  areas_of_service: string[];
  years_experience: number;
  min_advance_booking_hours?: number;
  buffer_time_minutes?: number;
  services: ServiceCreate[];
}

export interface InstructorProfileResponse {
  id: string;
  user_id: string;
  created_at: string;
  updated_at?: string | null;
  user: UserBasic;
  services: ServiceResponse[];
  bio: string;
  areas_of_service: string[];
  years_experience: number;
  min_advance_booking_hours?: number;
  buffer_time_minutes?: number;
}

// Date/Time Helpers

export function formatDate(date: Date): DateType {
  return date.toISOString().split('T')[0];
}

export function formatTime(date: Date): TimeType {
  return date.toTimeString().split(' ')[0];
}

export function parseTime(timeStr: TimeType): Date {
  const [hours, minutes, seconds] = timeStr.split(':').map(Number);
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
