// frontend/legacy-patterns/useAvailabilityOperations.ts

/**
 * useAvailabilityOperations Hook
 *
 * Manages availability save operations, validation, and bulk updates.
 * Handles the complex logic of generating operations, validating changes,
 * and applying updates to the backend.
 *
 * @module hooks/availability/useAvailabilityOperations
 */

import { useState, useCallback } from 'react';
import {
  SlotOperation,
  WeekSchedule,
  ExistingSlot,
  WeekValidationResponse,
  BulkUpdateRequest,
  BulkUpdateResponse,
  WeekDateInfo,
  TimeSlot,
} from '@/types/availability';
import { BookedSlotPreview } from '@/types/booking';
import { fetchWithAuth, API_ENDPOINTS, validateWeekChanges } from '@/lib/api';
import {
  generateAvailabilityOperations,
  validateOperations,
} from '@/legacy-patterns/operationGenerator';
import { formatDateForAPI } from '@/lib/availability/dateHelpers';
import { logger } from '@/lib/logger';

/**
 * Hook return type with operation management functionality
 */
export interface UseAvailabilityOperationsReturn {
  // State
  /** Whether a save operation is in progress */
  isSaving: boolean;
  /** Whether validation is in progress */
  isValidating: boolean;
  /** Validation results from last check */
  validationResults: WeekValidationResponse | null;
  /** Whether validation preview modal should be shown */
  showValidationPreview: boolean;
  /** Pending operations to be applied */
  pendingOperations: SlotOperation[];

  // Actions
  /** Save the current week schedule */
  saveWeekSchedule: (options?: SaveOptions) => Promise<SaveResult>;
  /** Validate changes without saving */
  validateChanges: () => Promise<WeekValidationResponse | null>;
  /** Copy schedule from previous week */
  copyFromPreviousWeek: () => Promise<CopyResult>;
  /** Apply schedule to future weeks */
  applyToFutureWeeks: (endDate: string) => Promise<ApplyResult>;
  /** Clear validation state */
  clearValidation: () => void;
  /** Set validation preview visibility */
  setShowValidationPreview: (show: boolean) => void;
}

/**
 * Options for save operation
 */
export interface SaveOptions {
  /** Skip validation before saving */
  skipValidation?: boolean;
  /** Force save even with conflicts */
  forceConflicts?: boolean;
  /** Custom success message */
  successMessage?: string;
}

/**
 * Result of save operation
 */
export interface SaveResult {
  success: boolean;
  message: string;
  operations?: number;
  conflicts?: number;
}

/**
 * Result of copy operation
 */
export interface CopyResult {
  success: boolean;
  message: string;
  copiedSlots?: number;
  preservedBookings?: number;
}

/**
 * Result of apply to future operation
 */
export interface ApplyResult {
  success: boolean;
  message: string;
  weeksAffected?: number;
  slotsCreated?: number;
}

/**
 * Custom hook for managing availability operations
 *
 * @param deps - Dependencies required for operations
 * @returns {UseAvailabilityOperationsReturn} Operation management functions
 *
 * @example
 * ```tsx
 * function AvailabilityPage() {
 *   const { saveWeekSchedule, validateChanges } = useAvailabilityOperations({
 *     weekSchedule,
 *     savedWeekSchedule,
 *     currentWeekStart,
 *     existingSlots,
 *     bookedSlots,
 *     weekDates,
 *     onSaveSuccess: () => refreshSchedule()
 *   });
 *
 *   const handleSave = async () => {
 *     const result = await saveWeekSchedule();
 *     if (result.success) {
 *       showSuccessMessage(result.message);
 *     }
 *   };
 * }
 * ```
 */
export function useAvailabilityOperations(deps: {
  /** Current week schedule */
  weekSchedule: WeekSchedule;
  /** Saved week schedule */
  savedWeekSchedule: WeekSchedule;
  /** Current week start date */
  currentWeekStart: Date;
  /** Existing slots from database */
  existingSlots: ExistingSlot[];
  /** Booked slots */
  bookedSlots: BookedSlotPreview[];
  /** Week date information */
  weekDates: WeekDateInfo[];
  /** Callback after successful save */
  onSaveSuccess?: () => void | Promise<void>;
  /** Callback after save error */
  onSaveError?: (error: Error) => void;
  /** Callback to update schedule locally */
  onScheduleUpdate?: (schedule: WeekSchedule) => void;
}): UseAvailabilityOperationsReturn {
  const {
    weekSchedule,
    savedWeekSchedule,
    currentWeekStart,
    existingSlots,
    bookedSlots,
    weekDates,
    onSaveSuccess,
    onSaveError,
    onScheduleUpdate,
  } = deps;

  // State
  const [isSaving, setIsSaving] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [validationResults, setValidationResults] = useState<WeekValidationResponse | null>(null);
  const [showValidationPreview, setShowValidationPreview] = useState(false);
  const [pendingOperations, setPendingOperations] = useState<SlotOperation[]>([]);

  /**
   * Validate changes without saving
   */
  const validateChanges = useCallback(async (): Promise<WeekValidationResponse | null> => {
    setIsValidating(true);
    logger.info('Starting validation for week changes');

    try {
      const validation = await validateWeekChanges(
        weekSchedule,
        savedWeekSchedule,
        currentWeekStart
      );

      setValidationResults(validation);

      logger.info('Validation completed', {
        valid: validation.valid,
        warnings: validation.warnings.length,
        operations: validation.summary.total_operations,
        conflicts: validation.summary.invalid_operations,
      });

      return validation;
    } catch (error) {
      logger.error('Validation failed', error);
      return null;
    } finally {
      setIsValidating(false);
    }
  }, [weekSchedule, savedWeekSchedule, currentWeekStart]);

  /**
   * Generate operations for saving
   */
  const generateOperations = useCallback(async (): Promise<SlotOperation[]> => {
    logger.group('Generating save operations', () => {
      logger.debug('Current week state', {
        dates: Object.keys(weekSchedule),
        totalSlots: Object.values(weekSchedule).flat().length,
      });
      logger.debug('Saved week state', {
        dates: Object.keys(savedWeekSchedule),
        totalSlots: Object.values(savedWeekSchedule).flat().length,
      });
    });

    // Fetch fresh slot IDs to ensure accuracy
    const mondayDate = formatDateForAPI(currentWeekStart);
    const sundayDate = formatDateForAPI(
      new Date(currentWeekStart.getTime() + 6 * 24 * 60 * 60 * 1000)
    );

    let currentExistingSlots = existingSlots;

    try {
      const response = await fetchWithAuth(
        `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY}?start_date=${mondayDate}&end_date=${sundayDate}`
      );

      if (response.ok) {
        const data = await response.json();
        currentExistingSlots = data.map((slot: { id: string; specific_date: string; start_time: string; end_time: string }) => ({
          id: slot.id,
          date: slot.specific_date,
          start_time: slot.start_time,
          end_time: slot.end_time,
        }));
        logger.debug('Fetched fresh slot IDs', { count: currentExistingSlots.length });
      }
    } catch (error) {
      logger.warn('Failed to fetch fresh slot IDs, using cached', {
        error: error instanceof Error ? error.message : 'Unknown error',
      });
    }

    // Generate operations
    const operations = generateAvailabilityOperations(
      weekSchedule,
      savedWeekSchedule,
      currentExistingSlots,
      bookedSlots,
      weekDates,
      { skipPastDates: true, includeToday: true }
    );

    return operations;
  }, [weekSchedule, savedWeekSchedule, existingSlots, bookedSlots, weekDates, currentWeekStart]);

  /**
   * Save week schedule
   */
  const saveWeekSchedule = useCallback(
    async (options: SaveOptions = {}): Promise<SaveResult> => {
      const { skipValidation = false, forceConflicts = false } = options;

      logger.time('saveWeekSchedule');
      setIsSaving(true);

      try {
        let operations: SlotOperation[];

        // Use pending operations if skipping validation (from preview)
        if (skipValidation && pendingOperations.length > 0) {
          operations = pendingOperations;
          logger.debug('Using pending operations from validation', {
            count: operations.length,
          });
        } else {
          // Validate first if not skipping
          if (!skipValidation) {
            const validation = await validateChanges();

            if (validation && !validation.valid && !forceConflicts) {
              setShowValidationPreview(true);
              setIsSaving(false);
              return {
                success: false,
                message: 'Validation failed - please review conflicts',
                conflicts: validation.summary.invalid_operations,
              };
            }
          }

          // Generate operations
          operations = await generateOperations();

          if (operations.length === 0) {
            logger.info('No changes to save');
            return {
              success: true,
              message: 'No changes to save',
              operations: 0,
            };
          }

          setPendingOperations(operations);
        }

        // Validate operations structure
        const operationValidation = validateOperations(operations);
        if (!operationValidation.valid) {
          throw new Error(`Invalid operations: ${operationValidation.errors.join(', ')}`);
        }

        // Apply operations
        const request: BulkUpdateRequest = {
          operations,
          validate_only: false,
        };

        logger.debug('Sending bulk update request', {
          operationCount: operations.length,
        });

        const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_BULK_UPDATE, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(request),
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || 'Failed to save changes');
        }

        const result: BulkUpdateResponse = await response.json();

        logger.info('Save operation completed', {
          successful: result.successful,
          failed: result.failed,
          skipped: result.skipped,
        });

        // Clear pending operations on success
        setPendingOperations([]);

        // Call success callback
        if (onSaveSuccess) {
          await onSaveSuccess();
        }

        return {
          success: result.successful > 0,
          message: formatSaveMessage(result),
          operations: result.successful,
        };
      } catch (error) {
        logger.error('Save operation failed', error);

        if (onSaveError) {
          onSaveError(error as Error);
        }

        return {
          success: false,
          message: error instanceof Error ? error.message : 'Failed to save schedule',
        };
      } finally {
        logger.timeEnd('saveWeekSchedule');
        setIsSaving(false);
      }
    },
    [pendingOperations, validateChanges, generateOperations, onSaveSuccess, onSaveError]
  );

  /**
   * Copy schedule from previous week
   */
  const copyFromPreviousWeek = useCallback(async (): Promise<CopyResult> => {
    logger.time('copyFromPreviousWeek');

    try {
      const previousWeek = new Date(currentWeekStart);
      previousWeek.setDate(previousWeek.getDate() - 7);

      logger.info('Fetching previous week schedule', {
        previousWeek: formatDateForAPI(previousWeek),
      });

      // Instead of calling the copy endpoint (which auto-saves),
      // we'll fetch the previous week's schedule and apply it locally
      const response = await fetchWithAuth(
        `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK}?start_date=${formatDateForAPI(previousWeek)}`
      );

      if (!response.ok) {
        throw new Error('Failed to fetch previous week schedule');
      }

      const previousWeekData = await response.json();

      // Get current week's booked slots to preserve them
      const bookedHours = new Set<string>();
      bookedSlots.forEach((slot) => {
        const startHour = parseInt(slot.start_time.split(':')[0]);
        const endHour = parseInt(slot.end_time.split(':')[0]);
        for (let hour = startHour; hour < endHour; hour++) {
          bookedHours.add(`${slot.date}-${hour}`);
        }
      });

      // Build new schedule preserving bookings
      const copiedSchedule: WeekSchedule = {};
      let copiedSlots = 0;
      let preservedBookings = 0;

      weekDates.forEach((dateInfo, index) => {
        const currentDateStr = dateInfo.fullDate;
        const prevDate = new Date(previousWeek);
        prevDate.setDate(prevDate.getDate() + index);
        const prevDateStr = formatDateForAPI(prevDate);

        // Check if this date has any bookings
        const hasBookingsOnDate = bookedSlots.some((slot) => slot.date === currentDateStr);

        if (hasBookingsOnDate) {
          // Preserve existing slots with bookings, add non-conflicting slots from previous week
          const existingSlots = weekSchedule[currentDateStr] || [];
          const preservedSlots: TimeSlot[] = [];

          // Keep slots that contain bookings
          existingSlots.forEach((slot) => {
            const slotStartHour = parseInt(slot.start_time.split(':')[0]);
            const slotEndHour = parseInt(slot.end_time.split(':')[0]);

            let hasBookingInSlot = false;
            for (let hour = slotStartHour; hour < slotEndHour; hour++) {
              if (bookedHours.has(`${currentDateStr}-${hour}`)) {
                hasBookingInSlot = true;
                break;
              }
            }

            if (hasBookingInSlot) {
              preservedSlots.push(slot);
              preservedBookings++;
            }
          });

          // Add non-conflicting slots from previous week
          if (previousWeekData[prevDateStr]) {
            previousWeekData[prevDateStr].forEach((prevSlot: TimeSlot) => {
              const prevStartHour = parseInt(prevSlot.start_time.split(':')[0]);
              const prevEndHour = parseInt(prevSlot.end_time.split(':')[0]);

              let conflictsWithBooking = false;
              for (let hour = prevStartHour; hour < prevEndHour; hour++) {
                if (bookedHours.has(`${currentDateStr}-${hour}`)) {
                  conflictsWithBooking = true;
                  break;
                }
              }

              if (!conflictsWithBooking) {
                preservedSlots.push(prevSlot);
                copiedSlots++;
              }
            });
          }

          copiedSchedule[currentDateStr] = preservedSlots;
        } else {
          // No bookings - safe to copy directly
          if (previousWeekData[prevDateStr]) {
            copiedSchedule[currentDateStr] = previousWeekData[prevDateStr];
            copiedSlots += previousWeekData[prevDateStr].length;
          } else {
            copiedSchedule[currentDateStr] = [];
          }
        }
      });

      logger.info('Copy from previous week completed (local)', {
        preservedBookings,
        copiedSlots,
        totalDates: weekDates.length,
      });

      // Update local state - this will trigger hasUnsavedChanges
      if (onScheduleUpdate) {
        onScheduleUpdate(copiedSchedule);
      }

      return {
        success: true,
        message: 'Copied schedule from previous week. Remember to save!',
        copiedSlots,
        preservedBookings,
      };
    } catch (error) {
      logger.error('Failed to copy from previous week', error);

      return {
        success: false,
        message: 'Failed to copy from previous week',
      };
    } finally {
      logger.timeEnd('copyFromPreviousWeek');
    }
  }, [currentWeekStart, weekSchedule, bookedSlots, weekDates, onScheduleUpdate]);

  /**
   * Apply schedule to future weeks
   */
  const applyToFutureWeeks = useCallback(
    async (endDate: string): Promise<ApplyResult> => {
      logger.time('applyToFutureWeeks');
      setIsSaving(true);

      try {
        // Save current week first if there are changes
        const hasChanges =
          Object.keys(weekSchedule).length !== Object.keys(savedWeekSchedule).length ||
          JSON.stringify(weekSchedule) !== JSON.stringify(savedWeekSchedule);

        if (hasChanges) {
          logger.info('Saving current week before applying to future');
          await saveWeekSchedule({ skipValidation: true });
        }

        const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_APPLY_RANGE, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            from_week_start: formatDateForAPI(currentWeekStart),
            start_date: formatDateForAPI(
              new Date(currentWeekStart.getTime() + 7 * 24 * 60 * 60 * 1000)
            ),
            end_date: endDate,
          }),
        });

        if (!response.ok) {
          throw new Error('Failed to apply to future weeks');
        }

        const result = await response.json();

        logger.info('Applied to future weeks', {
          endDate,
          slotsCreated: result.slots_created,
        });

        return {
          success: true,
          message: `Schedule applied to future weeks through ${new Date(
            endDate
          ).toLocaleDateString()}`,
          slotsCreated: result.slots_created,
          weeksAffected: result.weeks_affected,
        };
      } catch (error) {
        logger.error('Failed to apply to future weeks', error);

        return {
          success: false,
          message: 'Failed to apply to future weeks',
        };
      } finally {
        logger.timeEnd('applyToFutureWeeks');
        setIsSaving(false);
      }
    },
    [weekSchedule, savedWeekSchedule, currentWeekStart, saveWeekSchedule]
  );

  /**
   * Clear validation state
   */
  const clearValidation = useCallback(() => {
    setValidationResults(null);
    setShowValidationPreview(false);
    setPendingOperations([]);
  }, []);

  return {
    // State
    isSaving,
    isValidating,
    validationResults,
    showValidationPreview,
    pendingOperations,

    // Actions
    saveWeekSchedule,
    validateChanges,
    copyFromPreviousWeek,
    applyToFutureWeeks,
    clearValidation,
    setShowValidationPreview,
  };
}

/**
 * Format save result message
 */
function formatSaveMessage(result: BulkUpdateResponse): string {
  if (result.successful === result.successful + result.failed + result.skipped) {
    return result.successful === 1
      ? 'Successfully saved the change!'
      : `Successfully saved all ${result.successful} changes!`;
  }

  const parts = [];
  if (result.successful > 0) {
    parts.push(`${result.successful} saved`);
  }
  if (result.failed > 0) {
    parts.push(`${result.failed} failed`);
  }
  if (result.skipped > 0) {
    parts.push(`${result.skipped} skipped`);
  }

  return `Operation completed: ${parts.join(', ')}`;
}
