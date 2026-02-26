// frontend/types/availability.ts

/**
 * Availability Type Definitions
 *
 * This module contains all TypeScript interfaces and types related to
 * instructor availability management, including bulk operations,
 * validation, week-based scheduling, and UI state management.
 *
 * @module availability
 */

import type { DayBits } from '@/lib/calendar/bitset';

// Import types from generated OpenAPI shim
import type {
  WeekValidationResponse as GeneratedWeekValidationResponse,
  ValidateWeekRequest as GeneratedValidateWeekRequest,
  TimeSlot as GeneratedTimeSlot,
} from '@/features/shared/api/types';

// Re-export generated types for convenience
export type WeekValidationResponse = GeneratedWeekValidationResponse;
export type ValidateWeekRequest = GeneratedValidateWeekRequest;
export type TimeSlot = GeneratedTimeSlot;

/**
 * Possible actions for slot operations
 * - 'add': Create a new availability slot
 * - 'remove': Delete an existing slot
 * - 'update': Modify an existing slot
 */
export type SlotAction = 'add' | 'remove' | 'update';

/**
 * Days of the week type
 * Used for consistent day naming across the availability system
 */
export type DayOfWeek =
  | 'monday'
  | 'tuesday'
  | 'wednesday'
  | 'thursday'
  | 'friday'
  | 'saturday'
  | 'sunday';

/**
 * Represents a single operation on an availability slot
 *
 * @interface SlotOperation
 * @example
 * ```ts
 * // Add operation
 * const addOp: SlotOperation = {
 *   action: 'add',
 *   date: '2025-06-15',
 *   start_time: '09:00:00',
 *   end_time: '10:00:00'
 * };
 *
 * // Remove operation
 * const removeOp: SlotOperation = {
 *   action: 'remove',
 *   slot_id: '01ABC...'
 * };
 * ```
 */
export interface SlotOperation {
  /** The type of operation to perform */
  action: SlotAction;

  /** Date for add/update operations (ISO format: YYYY-MM-DD) */
  date?: string;

  /** Start time for add/update operations (HH:MM:SS format) */
  start_time?: string;

  /** End time for add/update operations (HH:MM:SS format) */
  end_time?: string;

  /** Slot ID for remove/update operations */
  slot_id?: string;
}

/**
 * Result of a single slot operation (frontend-specific, not in generated OpenAPI)
 *
 * @interface OperationResult
 */
export interface OperationResult {
  /** Index of the operation in the request array */
  operation_index: number;

  /** The action that was attempted */
  action: string;

  /** Status of the operation */
  status: 'success' | 'failed' | 'skipped';

  /** Reason for failure or skip (if applicable) */
  reason?: string;

  /** ID of the affected slot (for successful operations) */
  slot_id?: string;
}


/**
 * Represents an existing availability slot from the database
 * Used for tracking current state during updates
 *
 * @interface ExistingSlot
 */
export interface ExistingSlot {
  /** Unique identifier of the slot */
  id: string;

  /** Date of the slot (ISO format: YYYY-MM-DD) */
  date: string;

  /** Start time (HH:MM:SS format) */
  start_time: string;

  /** End time (HH:MM:SS format) */
  end_time: string;
}

/**
 * Bitmap representation of a week's availability.
 * Keys are ISO dates, values are 6-byte (48 half-hour) bitmaps.
 */
export type WeekBits = Record<string, DayBits>;

/**
 * Detailed information about a validation operation
 * Note: Optional fields use `| null` to match generated OpenAPI types
 *
 * @interface ValidationSlotDetail
 */
export interface ValidationSlotDetail {
  /** Index of the operation being validated */
  operation_index: number;

  /** The action being validated */
  action: string;

  /** Date for the operation (if applicable) */
  date?: string | null;

  /** Start time for the operation (if applicable) */
  start_time?: string | null;

  /** End time for the operation (if applicable) */
  end_time?: string | null;

  /** Slot ID for the operation (if applicable) */
  slot_id?: string | null;

  /** Reason for validation failure */
  reason?: string | null;

  /** Bookings that conflict with this operation */
  conflicts_with?: Array<{
    /** ID of the conflicting booking */
    booking_id?: string | null;
    /** Start time of the conflicting booking */
    start_time?: string | null;
    /** End time of the conflicting booking */
    end_time?: string | null;
  }> | null;
}

/**
 * Summary of validation results
 *
 * @interface ValidationSummary
 */
export interface ValidationSummary {
  /** Total number of operations to validate */
  total_operations: number;

  /** Number of valid operations */
  valid_operations: number;

  /** Number of invalid operations */
  invalid_operations: number;

  /** Count of operations by type (add, remove, update) */
  operations_by_type: Record<string, number>;

  /** Whether any operations have booking conflicts */
  has_conflicts: boolean;

  /** Estimated changes if operations are applied */
  estimated_changes: {
    /** Number of slots that would be added */
    slots_added: number;
    /** Number of slots that would be removed */
    slots_removed: number;
    /** Number of conflicts preventing changes */
    conflicts: number;
  };
}

// WeekValidationResponse - now imported from shim (see top of file)
// TimeSlot - now imported from shim (see top of file)

/**
 * Represents a week's worth of availability
 * Keys are ISO date strings (YYYY-MM-DD), values are arrays of time slots
 *
 * @interface WeekSchedule
 * @example
 * ```ts
 * const weekSchedule: WeekSchedule = {
 *   '2025-06-15': [
 *     { start_time: '09:00:00', end_time: '10:00:00'},
 *     { start_time: '10:00:00', end_time: '11:00:00'}
 *   ],
 *   '2025-06-16': [
 *     { start_time: '14:00:00', end_time: '15:00:00'}
 *   ]
 * };
 * ```
 */
export interface WeekSchedule {
  [date: string]: TimeSlot[];
}

// ValidateWeekRequest - now imported from shim (see top of file)

// ===== NEW TYPES FOR WORK STREAM #3 =====

/**
 * Extended date information for week calendar display
 * Provides all necessary date formats for UI rendering
 *
 * @interface WeekDateInfo
 * @example
 * ```ts
 * const dateInfo: WeekDateInfo = {
 *   date: new Date('2025-06-15'),
 *   dateStr: 'Jun 15',
 *   dayOfWeek: 'monday',
 *   fullDate: '2025-06-15'
 * };
 * ```
 */
export interface WeekDateInfo {
  /** JavaScript Date object */
  date: Date;

  /** Formatted date string for display (e.g., "Jun 15") */
  dateStr: string;

  /** Day of the week */
  dayOfWeek: DayOfWeek;

  /** Full date in ISO format (YYYY-MM-DD) */
  fullDate: string;
}

/**
 * Preset schedule template
 * Maps days of the week to their default time slots
 *
 * @interface PresetSchedule
 * @example
 * ```ts
 * const weekdaySchedule: PresetSchedule = {
 *   monday: [{ start_time: '09:00:00', end_time: '17:00:00'}],
 *   tuesday: [{ start_time: '09:00:00', end_time: '17:00:00'}],
 *   // ... other days
 * };
 * ```
 */
export interface PresetSchedule {
  [key: string]: TimeSlot[];
}

/**
 * UI message for user feedback
 * Used for success, error, and informational messages
 *
 * @interface AvailabilityMessage
 */
export interface AvailabilityMessage {
  /** Message severity/type */
  type: 'success' | 'error' | 'info';

  /** Message text to display */
  text: string;
}

/**
 * Options for applying schedule to future weeks
 * Determines the end date for bulk schedule application
 *
 * @interface ApplyToFutureOptions
 */
export interface ApplyToFutureOptions {
  /** The selected option type */
  option: 'date' | 'end-of-year' | 'indefinitely';

  /** Specific end date if 'date' option is selected */
  untilDate?: string;
}

/**
 * Constants for availability system
 * Centralized configuration values
 */
export const AVAILABILITY_CONSTANTS = {
  /** Default start hour for calendar grid */
  DEFAULT_START_HOUR: 8,

  /** Default end hour for calendar grid */
  DEFAULT_END_HOUR: 20,

  /** Ordered days of the week */
  DAYS_OF_WEEK: [
    'monday',
    'tuesday',
    'wednesday',
    'thursday',
    'friday',
    'saturday',
    'sunday',
  ] as const,

  /** Maximum weeks to apply schedule in future */
  MAX_FUTURE_WEEKS: 52,

  /** Auto-hide message timeout in milliseconds */
  MESSAGE_TIMEOUT: 5000,
} as const;

/**
 * Type guard to check if a string is a valid day of week
 *
 * @param day - String to check
 * @returns boolean indicating if day is valid
 */
export function isDayOfWeek(day: string): day is DayOfWeek {
  return AVAILABILITY_CONSTANTS.DAYS_OF_WEEK.includes(day as DayOfWeek);
}

/**
 * Helper to create an empty week schedule
 *
 * @param weekDates - Array of dates for the week
 * @returns Empty WeekSchedule object
 */
export function createEmptyWeekSchedule(weekDates: WeekDateInfo[]): WeekSchedule {
  const schedule: WeekSchedule = {};
  weekDates.forEach((dateInfo) => {
    schedule[dateInfo.fullDate] = [];
  });
  return schedule;
}
