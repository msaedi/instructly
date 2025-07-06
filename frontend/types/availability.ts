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
 *   slot_id: 123
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
  slot_id?: number;
}

/**
 * Request payload for bulk updating availability slots
 *
 * @interface BulkUpdateRequest
 * @example
 * ```ts
 * const request: BulkUpdateRequest = {
 *   operations: [
 *     { action: 'add', date: '2025-06-15', start_time: '09:00:00', end_time: '10:00:00' },
 *     { action: 'remove', slot_id: 456 }
 *   ],
 *   validate_only: true // Preview changes without applying
 * };
 * ```
 */
export interface BulkUpdateRequest {
  /** Array of operations to perform */
  operations: SlotOperation[];

  /** If true, only validate without applying changes */
  validate_only?: boolean;
}

/**
 * Result of a single slot operation
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
  slot_id?: number;
}

/**
 * Response from bulk update operations
 *
 * @interface BulkUpdateResponse
 * @example
 * ```ts
 * const response: BulkUpdateResponse = {
 *   successful: 5,
 *   failed: 1,
 *   skipped: 0,
 *   results: [
 *     { operation_index: 0, action: 'add', status: 'success', slot_id: 789 },
 *     { operation_index: 1, action: 'remove', status: 'failed', reason: 'Slot has active booking' }
 *   ]
 * };
 * ```
 */
export interface BulkUpdateResponse {
  /** Number of successful operations */
  successful: number;

  /** Number of failed operations */
  failed: number;

  /** Number of skipped operations */
  skipped: number;

  /** Detailed results for each operation */
  results: OperationResult[];
}

/**
 * Represents an existing availability slot from the database
 * Used for tracking current state during updates
 *
 * @interface ExistingSlot
 */
export interface ExistingSlot {
  /** Unique identifier of the slot */
  id: number;

  /** Date of the slot (ISO format: YYYY-MM-DD) */
  date: string;

  /** Start time (HH:MM:SS format) */
  start_time: string;

  /** End time (HH:MM:SS format) */
  end_time: string;
}

/**
 * Detailed information about a validation operation
 *
 * @interface ValidationSlotDetail
 */
export interface ValidationSlotDetail {
  /** Index of the operation being validated */
  operation_index: number;

  /** The action being validated */
  action: string;

  /** Date for the operation (if applicable) */
  date?: string;

  /** Start time for the operation (if applicable) */
  start_time?: string;

  /** End time for the operation (if applicable) */
  end_time?: string;

  /** Slot ID for the operation (if applicable) */
  slot_id?: number;

  /** Reason for validation failure */
  reason?: string;

  /** Bookings that conflict with this operation */
  conflicts_with?: Array<{
    /** ID of the conflicting booking */
    booking_id: number;
    /** Start time of the conflicting booking */
    start_time: string;
    /** End time of the conflicting booking */
    end_time: string;
  }>;
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

/**
 * Response from week validation endpoint
 *
 * @interface WeekValidationResponse
 * @example
 * ```ts
 * const validation: WeekValidationResponse = {
 *   valid: false,
 *   summary: {
 *     total_operations: 10,
 *     valid_operations: 8,
 *     invalid_operations: 2,
 *     operations_by_type: { add: 5, remove: 3, update: 2 },
 *     has_conflicts: true,
 *     estimated_changes: {
 *       slots_added: 5,
 *       slots_removed: 2,
 *       conflicts: 1
 *     }
 *   },
 *   details: [...],
 *   warnings: ['Removing slot with upcoming booking']
 * };
 * ```
 */
export interface WeekValidationResponse {
  /** Whether all operations are valid */
  valid: boolean;

  /** Summary of validation results */
  summary: ValidationSummary;

  /** Detailed results for each operation */
  details: ValidationSlotDetail[];

  /** Warning messages for the user */
  warnings: string[];
}

/**
 * Represents a single time slot within a day
 *
 * @interface TimeSlot
 */
export interface TimeSlot {
  /** Start time in HH:MM:SS format */
  start_time: string;

  /** End time in HH:MM:SS format */
  end_time: string;
}

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

/**
 * Request payload for validating week changes
 *
 * @interface ValidateWeekRequest
 * @example
 * ```ts
 * const validateRequest: ValidateWeekRequest = {
 *   current_week: currentSchedule,  // Modified schedule from UI
 *   saved_week: savedSchedule,      // Original schedule from backend
 *   week_start: '2025-06-15'        // Monday of the week
 * };
 * ```
 */
export interface ValidateWeekRequest {
  /** The current week schedule (as modified in the UI) */
  current_week: WeekSchedule;

  /** The saved week schedule (from the backend) */
  saved_week: WeekSchedule;

  /** Start date of the week (ISO format: YYYY-MM-DD) */
  week_start: string;
}

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
 * Difference between two schedules
 * Used for generating operations during save
 *
 * @interface ScheduleDiff
 */
export interface ScheduleDiff {
  /** Slots to be added */
  toAdd: Array<{
    date: string;
    slot: TimeSlot;
  }>;

  /** Slots to be removed */
  toRemove: Array<{
    date: string;
    slot: TimeSlot;
    slotId?: number;
  }>;
}

/**
 * Options for operation generation
 * Controls how operations are generated from schedule differences
 *
 * @interface OperationGeneratorOptions
 */
export interface OperationGeneratorOptions {
  /** Skip operations for dates in the past */
  skipPastDates?: boolean;

  /** Include today's date in operations */
  includeToday?: boolean;

  /** Preserve slots with bookings */
  preserveBookedSlots?: boolean;
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
 * Type guard to check if an operation is valid
 *
 * @param operation - Operation to validate
 * @returns boolean indicating if operation has required fields
 */
export function isValidOperation(operation: SlotOperation): boolean {
  if (operation.action === 'add') {
    return !!(operation.date && operation.start_time && operation.end_time);
  }
  if (operation.action === 'remove') {
    return !!operation.slot_id;
  }
  return false;
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
