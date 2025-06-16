// frontend/lib/availability/constants.ts

/**
 * Constants for Availability System
 * 
 * This module contains all constant values used throughout the
 * availability management system, including preset schedules,
 * configuration values, and system limits.
 * 
 * @module availability/constants
 */

import { PresetSchedule, DayOfWeek } from '@/types/availability';

/**
 * Ordered days of the week
 * Used for consistent ordering in calendar displays
 */
export const DAYS: DayOfWeek[] = [
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
  'sunday'
];

/**
 * Default calendar hour range
 */
export const DEFAULT_START_HOUR = 8;  // 8 AM
export const DEFAULT_END_HOUR = 20;   // 8 PM

/**
 * Preset schedule templates
 * 
 * These provide quick options for instructors to set common
 * availability patterns without manual configuration.
 */
export const PRESET_SCHEDULES: Record<string, PresetSchedule> = {
  /**
   * Standard Monday-Friday 9 AM to 5 PM schedule
   * Weekends off
   */
  'weekday_9_to_5': {
    monday: [{ start_time: '09:00:00', end_time: '17:00:00', is_available: true }],
    tuesday: [{ start_time: '09:00:00', end_time: '17:00:00', is_available: true }],
    wednesday: [{ start_time: '09:00:00', end_time: '17:00:00', is_available: true }],
    thursday: [{ start_time: '09:00:00', end_time: '17:00:00', is_available: true }],
    friday: [{ start_time: '09:00:00', end_time: '17:00:00', is_available: true }],
    saturday: [],
    sunday: []
  },

  /**
   * Morning schedule - 8 AM to 12 PM every day
   * Good for instructors who prefer morning sessions
   */
  'mornings_only': {
    monday: [{ start_time: '08:00:00', end_time: '12:00:00', is_available: true }],
    tuesday: [{ start_time: '08:00:00', end_time: '12:00:00', is_available: true }],
    wednesday: [{ start_time: '08:00:00', end_time: '12:00:00', is_available: true }],
    thursday: [{ start_time: '08:00:00', end_time: '12:00:00', is_available: true }],
    friday: [{ start_time: '08:00:00', end_time: '12:00:00', is_available: true }],
    saturday: [{ start_time: '08:00:00', end_time: '12:00:00', is_available: true }],
    sunday: [{ start_time: '08:00:00', end_time: '12:00:00', is_available: true }]
  },

  /**
   * Evening schedule - 5 PM to 9 PM on weekdays
   * Good for instructors with day jobs
   */
  'evenings_only': {
    monday: [{ start_time: '17:00:00', end_time: '21:00:00', is_available: true }],
    tuesday: [{ start_time: '17:00:00', end_time: '21:00:00', is_available: true }],
    wednesday: [{ start_time: '17:00:00', end_time: '21:00:00', is_available: true }],
    thursday: [{ start_time: '17:00:00', end_time: '21:00:00', is_available: true }],
    friday: [{ start_time: '17:00:00', end_time: '21:00:00', is_available: true }],
    saturday: [],
    sunday: []
  },

  /**
   * Weekend only schedule - 9 AM to 5 PM on weekends
   * Good for instructors with weekday commitments
   */
  'weekends_only': {
    monday: [],
    tuesday: [],
    wednesday: [],
    thursday: [],
    friday: [],
    saturday: [{ start_time: '09:00:00', end_time: '17:00:00', is_available: true }],
    sunday: [{ start_time: '09:00:00', end_time: '17:00:00', is_available: true }]
  }
};

/**
 * Get a human-readable name for a preset
 * 
 * @param presetKey - The preset key
 * @returns Formatted preset name
 */
export function getPresetDisplayName(presetKey: string): string {
  const names: Record<string, string> = {
    'weekday_9_to_5': 'Weekday 9-5',
    'mornings_only': 'Mornings Only',
    'evenings_only': 'Evenings Only',
    'weekends_only': 'Weekends Only'
  };
  
  return names[presetKey] || presetKey.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

/**
 * UI Configuration
 */
export const UI_CONFIG = {
  /** Auto-hide message timeout in milliseconds */
  MESSAGE_TIMEOUT: 5000,
  
  /** Debounce delay for search inputs */
  SEARCH_DEBOUNCE_MS: 300,
  
  /** Number of hours to show in mobile view */
  MOBILE_HOURS_PER_ROW: 3,
  
  /** Minimum booking duration in minutes */
  MIN_BOOKING_DURATION: 60,
  
  /** Maximum weeks to show in future */
  MAX_FUTURE_WEEKS: 52,
  
  /** Animation durations */
  ANIMATION_DURATION: {
    FAST: 150,
    NORMAL: 300,
    SLOW: 500
  }
} as const;

/**
 * API Configuration
 */
export const API_CONFIG = {
  /** Maximum operations per bulk update */
  MAX_BULK_OPERATIONS: 100,
  
  /** Retry attempts for failed requests */
  MAX_RETRIES: 3,
  
  /** Timeout for API requests in milliseconds */
  REQUEST_TIMEOUT: 30000,
  
  /** Delay between retries in milliseconds */
  RETRY_DELAY: 1000
} as const;

/**
 * Validation Rules
 */
export const VALIDATION_RULES = {
  /** Maximum hours an instructor can be available per day */
  MAX_HOURS_PER_DAY: 12,
  
  /** Maximum consecutive hours without a break */
  MAX_CONSECUTIVE_HOURS: 4,
  
  /** Minimum break duration in minutes */
  MIN_BREAK_DURATION: 30,
  
  /** Maximum future date for scheduling (days) */
  MAX_FUTURE_DAYS: 365
} as const;

/**
 * Error Messages
 */
export const ERROR_MESSAGES = {
  PAST_SLOT: 'Cannot modify availability for past time slots.',
  BOOKED_SLOT: 'Cannot modify time slots that have existing bookings. Please cancel the booking first.',
  NETWORK_ERROR: 'Network error. Please check your connection and try again.',
  SAVE_FAILED: 'Failed to save schedule. Please try again.',
  LOAD_FAILED: 'Failed to load availability. Please refresh and try again.',
  VALIDATION_FAILED: 'Please fix the validation errors before saving.',
  NO_CHANGES: 'No changes to save.',
  FUTURE_WEEKS_FAILED: 'Failed to apply to future weeks. Please try again.'
} as const;

/**
 * Success Messages
 */
export const SUCCESS_MESSAGES = {
  SAVED: 'Schedule saved successfully!',
  COPIED: 'Copied schedule from previous week. Remember to save!',
  APPLIED: 'Schedule applied to future weeks.',
  CLEARED: 'Week cleared. Remember to save your changes.',
  PRESET_APPLIED: (name: string) => `${name} schedule applied. Don't forget to save!`
} as const;

/**
 * Warning Messages
 */
export const WARNING_MESSAGES = {
  UNSAVED_CHANGES: 'You have unsaved changes. Are you sure you want to leave without saving?',
  CLEAR_WEEK: 'Are you sure you want to clear all availability for this week? This action cannot be undone.',
  BOOKED_SLOTS_PRESERVED: (count: number) => 
    `Week cleared except for ${count} slot(s) with bookings.`
} as const;

/**
 * Get all preset keys
 */
export function getPresetKeys(): string[] {
  return Object.keys(PRESET_SCHEDULES);
}

/**
 * Check if a preset exists
 */
export function isValidPreset(presetKey: string): boolean {
  return presetKey in PRESET_SCHEDULES;
}