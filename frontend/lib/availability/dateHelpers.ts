// frontend/lib/availability/dateHelpers.ts

/**
 * Date Helper Utilities for Availability System
 *
 * This module provides date manipulation and formatting utilities
 * specifically for the instructor availability management system.
 * All dates are handled in local time to match user expectations.
 *
 * @module availability/dateHelpers
 */

import { WeekDateInfo, AVAILABILITY_CONSTANTS } from '@/types/availability';
import { logger } from '@/lib/logger';
import { at } from '@/lib/ts/safe';

/**
 * Format a Date object to API format (YYYY-MM-DD)
 *
 * @param date - JavaScript Date object
 * @returns ISO date string in YYYY-MM-DD format
 *
 * @example
 * ```ts
 * formatDateForAPI(new Date('2025-06-15')) // "2025-06-15"
 * ```
 */
export function formatDateForAPI(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');

  const formatted = `${year}-${month}-${day}`;
  logger.debug('Formatted date for API', { input: date.toISOString(), output: formatted });

  return formatted;
}

/**
 * Dev-only warning if a non-YYYY-MM-DD string is about to be sent.
 * No-op in production builds.
 */
export function warnIfNonDateOnly(value: string): void {
  if (process.env.NODE_ENV === 'production') return;
  const ok = /^\d{4}-\d{2}-\d{2}$/.test(value);
  if (!ok) {
    logger.warn('Non date-only string passed to API', { value });
  }
}

/**
 * Get the start of the current week (Monday)
 *
 * @param referenceDate - Optional reference date (defaults to today)
 * @returns Date object set to Monday at 00:00:00
 *
 * @example
 * ```ts
 * // If today is Thursday June 18, 2025
 * getCurrentWeekStart() // Returns Monday June 15, 2025 at 00:00:00
 * ```
 */
export function getCurrentWeekStart(referenceDate: Date = new Date()): Date {
  const date = new Date(referenceDate);
  const dayOfWeek = date.getDay();
  const diff = date.getDate() - dayOfWeek + (dayOfWeek === 0 ? -6 : 1);

  const monday = new Date(date.setDate(diff));
  monday.setHours(0, 0, 0, 0);

  logger.debug('Calculated week start', {
    referenceDate: referenceDate.toISOString(),
    weekStart: monday.toISOString(),
    dayOfWeek,
  });

  return monday;
}

/**
 * Generate array of dates for a week starting from Monday
 *
 * @param weekStart - The Monday date to start from
 * @returns Array of WeekDateInfo objects for the week
 *
 * @example
 * ```ts
 * const weekDates = getWeekDates(new Date('2025-06-15'));
 * // Returns array with 7 WeekDateInfo objects from Mon-Sun
 * ```
 */
export function getWeekDates(weekStart: Date): WeekDateInfo[] {
  const dates: WeekDateInfo[] = [];

  for (let i = 0; i < 7; i++) {
    const date = new Date(weekStart);
    date.setDate(weekStart.getDate() + i);

    dates.push({
      date,
      dateStr: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      dayOfWeek: at(AVAILABILITY_CONSTANTS.DAYS_OF_WEEK, i) as 'monday' | 'tuesday' | 'wednesday' | 'thursday' | 'friday' | 'saturday' | 'sunday',
      fullDate: formatDateForAPI(date),
    });
  }

  logger.debug('Generated week dates', {
    weekStart: formatDateForAPI(weekStart),
    firstDate: at(dates, 0)?.fullDate,
    lastDate: at(dates, 6)?.fullDate,
  });

  return dates;
}

/**
 * Check if a specific time slot is in the past
 *
 * @param dateStr - Date in YYYY-MM-DD format
 * @param hour - Hour of the day (0-23)
 * @returns true if the time slot is before current time
 *
 * @example
 * ```ts
 * // Current time: June 15, 2025 at 2:30 PM
 * isTimeSlotInPast('2025-06-15', 14) // false (current hour)
 * isTimeSlotInPast('2025-06-15', 13) // true (past hour)
 * isTimeSlotInPast('2025-06-14', 16) // true (past date)
 * ```
 */
export function isTimeSlotInPast(dateStr: string, hour: number): boolean {
  const parts = dateStr.split('-');
  const year = parseInt(at(parts, 0) || '0');
  const month = parseInt(at(parts, 1) || '0');
  const day = parseInt(at(parts, 2) || '0');
  const slotDateTime = new Date(year, month - 1, day, hour, 0, 0, 0);
  const now = new Date();

  const isPast = slotDateTime < now;

  logger.debug('Checked if time slot is past', {
    dateStr,
    hour,
    slotTime: slotDateTime.toISOString(),
    currentTime: now.toISOString(),
    isPast,
  });

  return isPast;
}

/**
 * Check if a date is in the past (comparing only dates, not times)
 *
 * @param dateStr - Date in YYYY-MM-DD format
 * @returns true if the date is before today
 *
 * @example
 * ```ts
 * // Today: June 15, 2025
 * isDateInPast('2025-06-14') // true
 * isDateInPast('2025-06-15') // false (today is not past)
 * isDateInPast('2025-06-16') // false
 * ```
 */
export function isDateInPast(dateStr: string): boolean {
  const date = new Date(dateStr);
  const today = new Date();

  // Reset times to midnight for date-only comparison
  today.setHours(0, 0, 0, 0);
  date.setHours(0, 0, 0, 0);

  return date < today;
}

/**
 * Get the end date for a given time period option
 *
 * @param option - The time period option
 * @param customDate - Custom date if option is 'date'
 * @returns ISO date string for the end date
 *
 * @example
 * ```ts
 * getEndDateForOption('end-of-year') // "2025-12-31"
 * getEndDateForOption('date', '2025-08-15') // "2025-08-15"
 * getEndDateForOption('indefinitely') // "2026-06-15" (1 year from now)
 * ```
 */
export function getEndDateForOption(
  option: 'date' | 'end-of-year' | 'indefinitely',
  customDate?: string
): string {
  const today = new Date();

  switch (option) {
    case 'date':
      if (!customDate) {
        logger.warn('No custom date provided for date option, using end of month');
        const endOfMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0);
        return formatDateForAPI(endOfMonth);
      }
      return customDate;

    case 'end-of-year':
      const endOfYear = new Date(today.getFullYear(), 11, 31);
      return formatDateForAPI(endOfYear);

    case 'indefinitely':
      // Default to 1 year from now for "indefinitely"
      const nextYear = new Date();
      nextYear.setFullYear(nextYear.getFullYear() + 1);
      return formatDateForAPI(nextYear);

    default:
      logger.error('Invalid option for end date', null, { option });
      throw new Error(`Invalid option: ${option}`);
  }
}

/**
 * Format a week range for display
 *
 * @param weekStart - The Monday of the week
 * @returns Formatted string like "June 15 - June 21, 2025"
 *
 * @example
 * ```ts
 * formatWeekRange(new Date('2025-06-15'))
 * // "June 15 - June 21, 2025"
 * ```
 */
export function formatWeekRange(weekStart: Date): string {
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekStart.getDate() + 6);

  const startStr = weekStart.toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
  });

  const endStr = weekEnd.toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });

  // If same month, don't repeat it
  const startMonth = weekStart.getMonth();
  const endMonth = weekEnd.getMonth();

  if (startMonth === endMonth) {
    const day = weekStart.getDate();
    const endDay = weekEnd.getDate();
    const month = weekStart.toLocaleDateString('en-US', { month: 'long' });
    const year = weekStart.getFullYear();
    return `${month} ${day} - ${endDay}, ${year}`;
  }

  return `${startStr} - ${endStr}`;
}

/**
 * Calculate the number of weeks between two dates
 *
 * @param startDate - Start date
 * @param endDate - End date
 * @returns Number of weeks (rounded down)
 *
 * @example
 * ```ts
 * const start = new Date('2025-06-15');
 * const end = new Date('2025-07-13');
 * getWeeksBetween(start, end) // 4
 * ```
 */
export function getWeeksBetween(startDate: Date, endDate: Date): number {
  const millisecondsPerWeek = 7 * 24 * 60 * 60 * 1000;
  const diffMs = Math.abs(endDate.getTime() - startDate.getTime());
  return Math.floor(diffMs / millisecondsPerWeek);
}

/**
 * Get the previous Monday from a given date
 *
 * @param date - Reference date
 * @returns Date object for the previous Monday
 */
export function getPreviousMonday(date: Date): Date {
  const monday = getCurrentWeekStart(date);
  monday.setDate(monday.getDate() - 7);
  return monday;
}

/**
 * Get the next Monday from a given date
 *
 * @param date - Reference date
 * @returns Date object for the next Monday
 */
export function getNextMonday(date: Date): Date {
  const monday = getCurrentWeekStart(date);
  monday.setDate(monday.getDate() + 7);
  return monday;
}

/**
 * Parse a time string into hours and minutes
 *
 * @param timeStr - Time in HH:MM:SS format
 * @returns Object with hours and minutes
 *
 * @example
 * ```ts
 * parseTimeString('14:30:00') // { hours: 14, minutes: 30 }
 * ```
 */
export function parseTimeString(timeStr: string): { hours: number; minutes: number } {
  const parts = timeStr.split(':');
  const hours = parseInt(at(parts, 0) || '0');
  const minutes = parseInt(at(parts, 1) || '0');
  return { hours, minutes };
}

/**
 * Format hour for display
 *
 * @param hour - Hour in 24-hour format (0-23)
 * @returns Formatted string like "9:00 AM"
 *
 * @example
 * ```ts
 * formatHourDisplay(9)  // "9:00 AM"
 * formatHourDisplay(14) // "2:00 PM"
 * formatHourDisplay(0)  // "12:00 AM"
 * ```
 */
export function formatHourDisplay(hour: number): string {
  const period = hour >= 12 ? 'PM' : 'AM';
  const displayHour = hour % 12 || 12;
  return `${displayHour}:00 ${period}`;
}
