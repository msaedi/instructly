// frontend/legacy-patterns/slotHelpers.ts

/**
 * Slot Helper Utilities for Availability System
 *
 * This module provides utilities for managing availability time slots,
 * including booking checks, slot merging, and time range operations.
 * These functions ensure business rules are properly enforced.
 *
 * UPDATED: Removed is_available concept - if slot exists, it's available
 *
 * @module availability/slotHelpers
 */

import { TimeSlot, WeekSchedule, ExistingSlot } from '@/types/availability';
import { BookedSlotPreview } from '@/types/booking';
import { logger } from '@/lib/logger';

/**
 * Check if a specific time slot has a booking
 *
 * @param date - Date in YYYY-MM-DD format
 * @param hour - Hour of the day (0-23)
 * @param bookedSlots - Array of booked slots
 * @returns true if the slot has a booking
 *
 * @example
 * ```ts
 * const booked = isSlotBooked('2025-06-15', 10, bookedSlots);
 * // Returns true if there's a booking at 10 AM on June 15
 * ```
 */
export function isSlotBooked(
  date: string,
  hour: number,
  bookedSlots: BookedSlotPreview[]
): boolean {
  const hasBooking = bookedSlots.some((slot) => {
    if (slot.date !== date) return false;

    const slotStartHour = parseInt(slot.start_time.split(':')[0]);
    const slotEndHour = parseInt(slot.end_time.split(':')[0]);

    return hour >= slotStartHour && hour < slotEndHour;
  });

  logger.debug('Checked if slot is booked', {
    date,
    hour,
    hasBooking,
    totalBookedSlots: bookedSlots.length,
  });

  return hasBooking;
}

/**
 * Check if a time slot exists for a given hour
 *
 * @param date - Date in YYYY-MM-DD format
 * @param hour - Hour of the day (0-23)
 * @param schedule - Week schedule object
 * @returns true if a slot exists for this hour (existence = availability)
 *
 * @example
 * ```ts
 * // If schedule has 9:00-12:00 slot on this date
 * isHourInTimeRange('2025-06-15', 10, schedule) // true
 * isHourInTimeRange('2025-06-15', 13, schedule) // false
 * ```
 */
export function isHourInTimeRange(date: string, hour: number, schedule: WeekSchedule): boolean {
  const daySlots = schedule[date] || [];

  // If slot exists for this hour, it's available
  const inRange = daySlots.some((range) => {
    const startHour = parseInt(range.start_time.split(':')[0]);
    const endHour = parseInt(range.end_time.split(':')[0]);
    return hour >= startHour && hour < endHour;
  });

  logger.debug('Checked if hour is in time range', {
    date,
    hour,
    inRange,
    slotsForDay: daySlots.length,
  });

  return inRange;
}

/**
 * Get the booking information for a specific time slot
 *
 * @param date - Date in YYYY-MM-DD format
 * @param hour - Hour of the day (0-23)
 * @param bookedSlots - Array of booked slots
 * @returns BookedSlotPreview if found, null otherwise
 *
 * @example
 * ```ts
 * const booking = getBookingForSlot('2025-06-15', 10, bookedSlots);
 * if (booking) {
 *   console.log(`Booking with ${booking.student_first_name}`);
 * }
 * ```
 */
export function getBookingForSlot(
  date: string,
  hour: number,
  bookedSlots: BookedSlotPreview[]
): BookedSlotPreview | null {
  const booking = bookedSlots.find((slot) => {
    if (slot.date !== date) return false;

    const slotStartHour = parseInt(slot.start_time.split(':')[0]);
    const slotEndHour = parseInt(slot.end_time.split(':')[0]);

    return hour >= slotStartHour && hour < slotEndHour;
  });

  return booking || null;
}

/**
 * Merge adjacent time slots while respecting booking boundaries
 *
 * This function is critical for maintaining data integrity. It ensures
 * that available slots are merged for efficiency, but never across bookings.
 *
 * @param slots - Array of time slots to merge
 * @param date - Date of the slots (for booking checks)
 * @param bookedSlots - Array of booked slots to respect
 * @returns Merged array of time slots
 *
 * @example
 * ```ts
 * // Input: [9-10], [10-11], [11-12]
 * // With no bookings: Returns [9-12]
 * // With booking at 10-11: Returns [9-10], [10-11], [11-12]
 * ```
 */
export function mergeAdjacentSlots(
  slots: TimeSlot[],
  date: string,
  bookedSlots: BookedSlotPreview[]
): TimeSlot[] {
  if (slots.length === 0) return [];

  logger.debug('Starting slot merge operation', {
    date,
    inputSlots: slots.length,
    bookedSlots: bookedSlots.filter((b) => b.date === date).length,
  });

  // Sort by start time
  const sorted = [...slots].sort((a, b) => a.start_time.localeCompare(b.start_time));

  const merged: TimeSlot[] = [];
  let current = { ...sorted[0] };

  for (let i = 1; i < sorted.length; i++) {
    const next = sorted[i];
    const currentEndHour = parseInt(current.end_time.split(':')[0]);
    const nextStartHour = parseInt(next.start_time.split(':')[0]);

    // Check if there's a booking between current and next
    let hasBookingBetween = false;
    for (let hour = currentEndHour; hour < nextStartHour; hour++) {
      if (isSlotBooked(date, hour, bookedSlots)) {
        hasBookingBetween = true;
        break;
      }
    }

    // Check if we can merge (all slots are available now, just check adjacency)
    const canMerge = current.end_time === next.start_time && !hasBookingBetween;

    if (canMerge) {
      // Extend current slot
      current.end_time = next.end_time;
      logger.debug('Merged slots', {
        date,
        mergedRange: `${current.start_time} - ${current.end_time}`,
      });
    } else {
      // Can't merge - save current and start new
      merged.push(current);
      current = { ...next };
    }
  }

  // Don't forget the last slot
  merged.push(current);

  logger.info('Completed slot merge', {
    date,
    inputSlots: slots.length,
    outputSlots: merged.length,
    reduction: slots.length - merged.length,
  });

  return merged;
}

/**
 * Find the database ID for a time slot
 *
 * @param slot - Time slot to find
 * @param date - Date of the slot
 * @param existingSlots - Array of existing slots from database
 * @returns Slot ID if found, null otherwise
 */
export function findSlotId(
  slot: TimeSlot,
  date: string,
  existingSlots: ExistingSlot[]
): number | null {
  const existing = existingSlots.find(
    (s) => s.date === date && s.start_time === slot.start_time && s.end_time === slot.end_time
  );

  return existing?.id || null;
}

/**
 * Find overlapping slots for a given time range
 *
 * Used for finding slots that need to be removed when a new slot
 * partially overlaps with existing ones.
 *
 * @param date - Date to check
 * @param startTime - Start time of the range
 * @param endTime - End time of the range
 * @param existingSlots - Array of existing slots
 * @returns Array of overlapping slots
 */
export function findOverlappingSlots(
  date: string,
  startTime: string,
  endTime: string,
  existingSlots: ExistingSlot[]
): ExistingSlot[] {
  return existingSlots.filter((slot) => {
    if (slot.date !== date) return false;

    // Check if there's any overlap
    return slot.start_time < endTime && slot.end_time > startTime;
  });
}

/**
 * Split a time slot at a specific hour
 *
 * Used when toggling availability for a single hour within a larger slot.
 *
 * @param slot - Time slot to split
 * @param hour - Hour at which to split
 * @returns Array of split slots (1-3 slots depending on the hour)
 *
 * @example
 * ```ts
 * // Split 9:00-12:00 at hour 10
 * splitSlotAtHour(slot, 10)
 * // Returns: [9:00-10:00, 10:00-11:00, 11:00-12:00]
 * ```
 */
export function splitSlotAtHour(slot: TimeSlot, hour: number): TimeSlot[] {
  const startHour = parseInt(slot.start_time.split(':')[0]);
  const endHour = parseInt(slot.end_time.split(':')[0]);

  if (hour <= startHour || hour >= endHour) {
    return [slot]; // No split needed
  }

  const splits: TimeSlot[] = [];

  // Before the hour
  if (hour > startHour) {
    splits.push({
      start_time: slot.start_time,
      end_time: `${hour.toString().padStart(2, '0')}:00:00`,
    });
  }

  // The hour itself
  splits.push({
    start_time: `${hour.toString().padStart(2, '0')}:00:00`,
    end_time: `${(hour + 1).toString().padStart(2, '0')}:00:00`,
  });

  // After the hour
  if (hour + 1 < endHour) {
    splits.push({
      start_time: `${(hour + 1).toString().padStart(2, '0')}:00:00`,
      end_time: slot.end_time,
    });
  }

  return splits;
}

/**
 * Create a new time slot for a single hour
 *
 * @param hour - Hour of the day (0-23)
 * @returns TimeSlot object (always available)
 */
export function createHourSlot(hour: number): TimeSlot {
  return {
    start_time: `${hour.toString().padStart(2, '0')}:00:00`,
    end_time: `${(hour + 1).toString().padStart(2, '0')}:00:00`,
  };
}

/**
 * Check if a booking would span across a merged slot
 *
 * @param startHour - Start hour of potential merged slot
 * @param endHour - End hour of potential merged slot
 * @param date - Date to check
 * @param bookedSlots - Array of booked slots
 * @returns true if merging would span a booking
 */
export function wouldSpanBooking(
  startHour: number,
  endHour: number,
  date: string,
  bookedSlots: BookedSlotPreview[]
): boolean {
  for (let hour = startHour; hour < endHour; hour++) {
    if (isSlotBooked(date, hour, bookedSlots)) {
      return true;
    }
  }
  return false;
}

/**
 * Get a map of booked hours for efficient lookup
 *
 * @param bookedSlots - Array of booked slots
 * @returns Map with keys as "date-hour" strings
 */
export function createBookedHoursMap(bookedSlots: BookedSlotPreview[]): Set<string> {
  const bookedHours = new Set<string>();

  bookedSlots.forEach((slot) => {
    const startHour = parseInt(slot.start_time.split(':')[0]);
    const endHour = parseInt(slot.end_time.split(':')[0]);

    for (let hour = startHour; hour < endHour; hour++) {
      bookedHours.add(`${slot.date}-${hour}`);
    }
  });

  logger.debug('Created booked hours map', {
    totalBookings: bookedSlots.length,
    totalBookedHours: bookedHours.size,
  });

  return bookedHours;
}

/**
 * Validate that a time slot has valid times
 *
 * @param slot - Time slot to validate
 * @returns true if valid
 */
export function isValidTimeSlot(slot: TimeSlot): boolean {
  const startHour = parseInt(slot.start_time.split(':')[0]);
  const endHour = parseInt(slot.end_time.split(':')[0]);

  return startHour >= 0 && startHour <= 23 && endHour >= 0 && endHour <= 24 && startHour < endHour;
}
