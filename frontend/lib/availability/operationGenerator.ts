// frontend/lib/availability/operationGenerator.ts

/**
 * Operation Generator for Availability System
 *
 * This module contains the critical business logic for generating
 * availability operations by comparing current and saved schedules.
 * It handles complex scenarios including booking protection, past dates,
 * and overlapping slots.
 *
 * @module availability/operationGenerator
 */

import {
  SlotOperation,
  WeekSchedule,
  ExistingSlot,
  TimeSlot,
  ScheduleDiff,
  OperationGeneratorOptions,
  WeekDateInfo,
} from '@/types/availability';
import { BookedSlotPreview } from '@/types/booking';
import { isSlotBooked, findSlotId, findOverlappingSlots } from './slotHelpers';
import { isDateInPast, formatDateForAPI } from './dateHelpers';
import { logger } from '@/lib/logger';

/**
 * Generate availability operations by comparing schedules
 *
 * This is the core function that determines what changes need to be made
 * to transform the saved schedule into the current schedule while
 * respecting all business rules.
 *
 * @param currentWeek - The desired week schedule
 * @param savedWeek - The existing saved schedule
 * @param existingSlots - Database records of existing slots
 * @param bookedSlots - Slots that have bookings
 * @param weekDates - Date information for the week
 * @param options - Configuration options
 * @returns Array of operations to perform
 *
 * @example
 * ```ts
 * const operations = generateAvailabilityOperations(
 *   currentSchedule,
 *   savedSchedule,
 *   existingSlots,
 *   bookedSlots,
 *   weekDates,
 *   { skipPastDates: true }
 * );
 * ```
 */
export function generateAvailabilityOperations(
  currentWeek: WeekSchedule,
  savedWeek: WeekSchedule,
  existingSlots: ExistingSlot[],
  bookedSlots: BookedSlotPreview[],
  weekDates: WeekDateInfo[],
  options: OperationGeneratorOptions = {}
): SlotOperation[] {
  const { skipPastDates = true, includeToday = true, preserveBookedSlots = true } = options;

  logger.info('Starting operation generation', {
    weekStart: weekDates[0]?.fullDate,
    currentDates: Object.keys(currentWeek).length,
    savedDates: Object.keys(savedWeek).length,
    existingSlots: existingSlots.length,
    bookedSlots: bookedSlots.length,
    options,
  });

  const operations: SlotOperation[] = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const todayStr = formatDateForAPI(today);

  // Process each date in the week
  weekDates.forEach((dateInfo) => {
    const dateStr = dateInfo.fullDate;
    const currentSlots = currentWeek[dateStr] || [];
    const savedSlots = savedWeek[dateStr] || [];

    logger.debug('Processing date for operations', {
      date: dateStr,
      currentSlots: currentSlots.length,
      savedSlots: savedSlots.length,
    });

    // Skip past dates if requested
    if (skipPastDates) {
      const isPast = dateStr < todayStr;
      const isToday = dateStr === todayStr;

      if (isPast || (isToday && !includeToday)) {
        logger.debug('Skipping date', { date: dateStr, isPast, isToday });
        return;
      }
    }

    // Find slots to remove
    const removeOps = findSlotsToRemove(
      savedSlots,
      currentSlots,
      dateStr,
      existingSlots,
      bookedSlots,
      preserveBookedSlots
    );
    operations.push(...removeOps);

    // Find slots to add
    const addOps = findSlotsToAdd(
      currentSlots,
      savedSlots,
      dateStr,
      bookedSlots,
      preserveBookedSlots
    );
    operations.push(...addOps);
  });

  logger.info('Operation generation completed', {
    totalOperations: operations.length,
    adds: operations.filter((op) => op.action === 'add').length,
    removes: operations.filter((op) => op.action === 'remove').length,
  });

  return operations;
}

/**
 * Find slots that need to be removed
 *
 * @param savedSlots - Currently saved slots
 * @param currentSlots - Desired slots
 * @param date - Date being processed
 * @param existingSlots - Database records
 * @param bookedSlots - Booked slots to protect
 * @param preserveBookedSlots - Whether to skip removal of booked slots
 * @returns Array of remove operations
 */
function findSlotsToRemove(
  savedSlots: TimeSlot[],
  currentSlots: TimeSlot[],
  date: string,
  existingSlots: ExistingSlot[],
  bookedSlots: BookedSlotPreview[],
  preserveBookedSlots: boolean
): SlotOperation[] {
  const operations: SlotOperation[] = [];

  savedSlots.forEach((savedSlot) => {
    // Check if this slot still exists in current
    const stillExists = currentSlots.some(
      (currentSlot) =>
        currentSlot.start_time === savedSlot.start_time &&
        currentSlot.end_time === savedSlot.end_time
    );

    if (!stillExists) {
      // Check if slot has bookings
      if (preserveBookedSlots && hasBookingInSlot(savedSlot, date, bookedSlots)) {
        logger.warn('Skipping removal of slot with booking', {
          date,
          slot: `${savedSlot.start_time} - ${savedSlot.end_time}`,
        });
        return;
      }

      // Find the slot ID
      const slotId = findSlotId(savedSlot, date, existingSlots);

      if (slotId) {
        operations.push({
          action: 'remove',
          slot_id: slotId,
        });

        logger.debug('Marking slot for removal', {
          date,
          slotId,
          time: `${savedSlot.start_time} - ${savedSlot.end_time}`,
        });
      } else {
        // Handle overlapping slots
        const overlapping = findOverlappingSlots(
          date,
          savedSlot.start_time,
          savedSlot.end_time,
          existingSlots
        );

        overlapping.forEach((slot) => {
          // Double-check for bookings
          if (preserveBookedSlots && hasBookingInExistingSlot(slot, bookedSlots)) {
            logger.warn('Skipping removal of overlapping slot with booking', {
              slotId: slot.id,
            });
            return;
          }

          operations.push({
            action: 'remove',
            slot_id: slot.id,
          });
        });
      }
    }
  });

  return operations;
}

/**
 * Find slots that need to be added
 *
 * @param currentSlots - Desired slots
 * @param savedSlots - Currently saved slots
 * @param date - Date being processed
 * @param bookedSlots - Booked slots to check
 * @param preserveBookedSlots - Whether to check for conflicts
 * @returns Array of add operations
 */
function findSlotsToAdd(
  currentSlots: TimeSlot[],
  savedSlots: TimeSlot[],
  date: string,
  bookedSlots: BookedSlotPreview[],
  preserveBookedSlots: boolean
): SlotOperation[] {
  const operations: SlotOperation[] = [];

  currentSlots.forEach((currentSlot) => {
    // Check if this slot already exists in saved
    const existsInSaved = savedSlots.some(
      (savedSlot) =>
        savedSlot.start_time === currentSlot.start_time &&
        savedSlot.end_time === currentSlot.end_time
    );

    if (!existsInSaved) {
      // Check if adding this would conflict with bookings
      if (preserveBookedSlots && hasBookingInSlot(currentSlot, date, bookedSlots)) {
        logger.warn('Skipping add of slot that conflicts with booking', {
          date,
          slot: `${currentSlot.start_time} - ${currentSlot.end_time}`,
        });
        return;
      }

      operations.push({
        action: 'add',
        date: date,
        start_time: currentSlot.start_time,
        end_time: currentSlot.end_time,
      });

      logger.debug('Marking slot for addition', {
        date,
        time: `${currentSlot.start_time} - ${currentSlot.end_time}`,
      });
    }
  });

  return operations;
}

/**
 * Check if a time slot contains any bookings
 *
 * @param slot - Time slot to check
 * @param date - Date of the slot
 * @param bookedSlots - Array of booked slots
 * @returns true if slot contains bookings
 */
function hasBookingInSlot(slot: TimeSlot, date: string, bookedSlots: BookedSlotPreview[]): boolean {
  const startHour = parseInt(slot.start_time.split(':')[0]);
  const endHour = parseInt(slot.end_time.split(':')[0]);

  for (let hour = startHour; hour < endHour; hour++) {
    if (isSlotBooked(date, hour, bookedSlots)) {
      return true;
    }
  }

  return false;
}

/**
 * Check if an existing slot has bookings
 *
 * @param slot - Existing slot from database
 * @param bookedSlots - Array of booked slots
 * @returns true if slot has bookings
 */
function hasBookingInExistingSlot(slot: ExistingSlot, bookedSlots: BookedSlotPreview[]): boolean {
  return bookedSlots.some(
    (booking) =>
      booking.date === slot.date &&
      booking.start_time >= slot.start_time &&
      booking.end_time <= slot.end_time
  );
}

/**
 * Compare two schedules and generate a diff
 *
 * @param current - Current schedule
 * @param saved - Saved schedule
 * @returns ScheduleDiff object
 */
export function compareSchedules(current: WeekSchedule, saved: WeekSchedule): ScheduleDiff {
  const diff: ScheduleDiff = {
    toAdd: [],
    toRemove: [],
  };

  // Get all unique dates
  const allDates = new Set([...Object.keys(current), ...Object.keys(saved)]);

  allDates.forEach((date) => {
    const currentSlots = current[date] || [];
    const savedSlots = saved[date] || [];

    // Find slots to add
    currentSlots.forEach((slot) => {
      const exists = savedSlots.some(
        (s) => s.start_time === slot.start_time && s.end_time === slot.end_time
      );

      if (!exists) {
        diff.toAdd.push({ date, slot });
      }
    });

    // Find slots to remove
    savedSlots.forEach((slot) => {
      const exists = currentSlots.some(
        (s) => s.start_time === slot.start_time && s.end_time === slot.end_time
      );

      if (!exists) {
        diff.toRemove.push({ date, slot });
      }
    });
  });

  return diff;
}

/**
 * Optimize operations by removing redundant ones
 *
 * @param operations - Array of operations
 * @returns Optimized array of operations
 */
export function optimizeOperations(operations: SlotOperation[]): SlotOperation[] {
  // Remove duplicate operations
  const seen = new Set<string>();
  const optimized: SlotOperation[] = [];

  operations.forEach((op) => {
    const key =
      op.action === 'add'
        ? `add-${op.date}-${op.start_time}-${op.end_time}`
        : `remove-${op.slot_id}`;

    if (!seen.has(key)) {
      seen.add(key);
      optimized.push(op);
    }
  });

  logger.debug('Optimized operations', {
    original: operations.length,
    optimized: optimized.length,
    duplicatesRemoved: operations.length - optimized.length,
  });

  return optimized;
}

/**
 * Validate operations before execution
 *
 * @param operations - Array of operations to validate
 * @returns Object with validation result and errors
 */
export function validateOperations(operations: SlotOperation[]): {
  valid: boolean;
  errors: string[];
} {
  const errors: string[] = [];

  operations.forEach((op, index) => {
    if (op.action === 'add') {
      if (!op.date || !op.start_time || !op.end_time) {
        errors.push(`Operation ${index}: Add operation missing required fields`);
      }
    } else if (op.action === 'remove') {
      if (!op.slot_id) {
        errors.push(`Operation ${index}: Remove operation missing slot_id`);
      }
    } else {
      errors.push(`Operation ${index}: Invalid action ${op.action}`);
    }
  });

  return {
    valid: errors.length === 0,
    errors,
  };
}
