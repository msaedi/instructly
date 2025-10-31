// frontend/hooks/availability/useWeekSchedule.ts

/**
 * useWeekSchedule Hook
 *
 * Core hook for managing week-based availability schedules.
 * Handles week navigation, data fetching, state management, and
 * unsaved changes tracking.
 *
 * @module hooks/availability/useWeekSchedule
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  WeekSchedule,
  ExistingSlot,
  WeekDateInfo,
  AvailabilityMessage,
  TimeSlot,
} from '@/types/availability';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import {
  getCurrentWeekStart,
  getWeekDates,
  formatDateForAPI,
  getPreviousMonday,
  getNextMonday,
} from '@/lib/availability/dateHelpers';
import { normalizeSchedule } from '@/lib/calendar/normalize';
import { logger } from '@/lib/logger';

/**
 * Hook return type with all schedule management functionality
 */
export interface UseWeekScheduleReturn {
  // State
  /** Current week's Monday date */
  currentWeekStart: Date;
  /** Current week's schedule (modified in UI) */
  weekSchedule: WeekSchedule;
  /** Saved week's schedule (from backend) */
  savedWeekSchedule: WeekSchedule;
  /** Whether schedule has unsaved changes */
  hasUnsavedChanges: boolean;
  /** Loading state for data fetching */
  isLoading: boolean;
  /** Array of existing slots with IDs */
  existingSlots: ExistingSlot[];
  /** Week date information */
  weekDates: WeekDateInfo[];
  /** User feedback message */
  message: AvailabilityMessage | null;

  // Actions
  /** Navigate to previous/next week */
  navigateWeek: (direction: 'prev' | 'next') => void;
  /** Update the week schedule */
  setWeekSchedule: (schedule: WeekSchedule | ((prev: WeekSchedule) => WeekSchedule)) => void;
  /** Set feedback message */
  setMessage: (message: AvailabilityMessage | null) => void;
  /** Refresh schedule from backend */
  refreshSchedule: () => Promise<void>;
  /** Jump to the current week's Monday */
  goToCurrentWeek: () => void;
  /** Check if a date is in the past */
  isDateInPast: (dateStr: string) => boolean;
  /** Format current week for display */
  currentWeekDisplay: string;
  /** ETag/version for optimistic concurrency */
  version?: string;
  /** Server-sourced Last-Modified header for the week */
  lastModified?: string;
}

/**
 * Custom hook for managing week-based availability schedules
 *
 * @param options - Configuration options
 * @returns {UseWeekScheduleReturn} Schedule state and management functions
 *
 * @example
 * ```tsx
 * function AvailabilityPage() {
 *   const {
 *     weekSchedule,
 *     hasUnsavedChanges,
 *     navigateWeek,
 *     setWeekSchedule
 *   } = useWeekSchedule();
 *
 *   // Use the schedule data and functions
 * }
 * ```
 */
export function useWeekSchedule(
  options: {
    /** Auto-hide message timeout in ms (default: 5000) */
    messageTimeout?: number;
  } = {}
): UseWeekScheduleReturn {
  const { messageTimeout = 5000 } = options;

  // Core state
  const [currentWeekStart, setCurrentWeekStart] = useState<Date>(() => {
    const weekStart = getCurrentWeekStart();
    logger.debug('Initializing week start', { weekStart: formatDateForAPI(weekStart) });
    return weekStart;
  });

  const [weekSchedule, setWeekSchedule] = useState<WeekSchedule>({});
  const [savedWeekSchedule, setSavedWeekSchedule] = useState<WeekSchedule>({});
  const [existingSlots, setExistingSlots] = useState<ExistingSlot[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState<AvailabilityMessage | null>(null);
  const [version, setVersion] = useState<string | undefined>(undefined);
  const [lastModified, setLastModified] = useState<string | undefined>(undefined);

  // Computed values
  const weekDates = useMemo(() => {
    return getWeekDates(currentWeekStart);
  }, [currentWeekStart]);

  const hasUnsavedChanges = useMemo(() => {
    const scheduleKeys = Object.keys(weekSchedule);
    const savedKeys = Object.keys(savedWeekSchedule);

    // Different number of days with slots
    if (scheduleKeys.length !== savedKeys.length) {
      return true;
    }

    // Check each day's slots
    for (const date of scheduleKeys) {
      const currentSlots = weekSchedule[date] || [];
      const savedSlots = savedWeekSchedule[date] || [];

      if (currentSlots.length !== savedSlots.length) {
        return true;
      }

      // Check each slot
      for (let i = 0; i < currentSlots.length; i++) {
        const current = currentSlots[i];
        const saved = savedSlots[i];

        if (
          !current ||
          !saved ||
          current.start_time !== saved.start_time ||
          current.end_time !== saved.end_time
        ) {
          return true;
        }
      }
    }

    return false;
  }, [weekSchedule, savedWeekSchedule]);

  const currentWeekDisplay = useMemo(() => {
    const start = weekDates[0]?.date;
    if (!start) return '';
    return start.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  }, [weekDates]);

  /**
   * Check if a date is in the past
   */
  const isDateInPast = useCallback((dateStr: string): boolean => {
    const date = new Date(dateStr);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    date.setHours(0, 0, 0, 0);
    return date < today;
  }, []);

  /**
   * Auto-hide messages after timeout
   */
  useEffect(() => {
    if (message && messageTimeout > 0) {
      const timer = setTimeout(() => {
        setMessage(null);
      }, messageTimeout);

      return () => clearTimeout(timer);
    }
    return undefined;
  }, [message, messageTimeout]);

  /**
   * Fetch week schedule from API
   */
  const fetchWeekSchedule = useCallback(async () => {
    setIsLoading(true);
    logger.time('fetchWeekSchedule');

    try {
      const mondayDate = formatDateForAPI(currentWeekStart);
      const sundayDate = formatDateForAPI(
        new Date(currentWeekStart.getTime() + 6 * 24 * 60 * 60 * 1000)
      );

      logger.info('Fetching week schedule', { mondayDate, sundayDate });

      // Fetch detailed slots with IDs
      const detailedResponse = await fetchWithAuth(
        `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY}?start_date=${mondayDate}&end_date=${sundayDate}`
      );

      if (detailedResponse.ok) {
        const detailedData = await detailedResponse.json();
        logger.debug('Fetched detailed slots', { count: detailedData.length });

        const slots: ExistingSlot[] = detailedData.map((slot: { id: string; specific_date: string; start_time: string; end_time: string }) => ({
          id: slot.id,
          date: slot.specific_date,
          start_time: slot.start_time,
          end_time: slot.end_time,
        }));
        setExistingSlots(slots);
      } else {
        logger.error('Failed to fetch detailed slots', new Error('API error'), {
          status: detailedResponse.status,
        });
      }

      // Fetch week view for display
      const response = await fetchWithAuth(
        `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK}?start_date=${mondayDate}`
      );

      if (!response.ok) {
        throw new Error('Failed to fetch availability');
      }

      const data = await response.json();
      const etag = response.headers.get('ETag') || undefined;
      const lm = response.headers.get('Last-Modified') || undefined;
      setVersion(etag || undefined);
      setLastModified(lm || undefined);

      // Set data directly - API is standardized
      const cleanedData: WeekSchedule = {};
      Object.entries(data).forEach(([date, slots]) => {
        if (slots && Array.isArray(slots) && slots.length > 0) {
          cleanedData[date] = slots as TimeSlot[];
        }
      });

      const normalizedData = normalizeSchedule(cleanedData);

      logger.info('Week schedule loaded successfully', {
        weekStart: mondayDate,
        daysWithAvailability: Object.keys(normalizedData).length,
      });

      setWeekSchedule(normalizedData);
      setSavedWeekSchedule(normalizedData);
    } catch (error) {
      logger.error('Failed to load availability', error);
      setMessage({
        type: 'error',
        text: 'Failed to load availability. Please try again.',
      });
    } finally {
      logger.timeEnd('fetchWeekSchedule');
      setIsLoading(false);
    }
  }, [currentWeekStart]);

  /**
   * Navigate between weeks
   */
  const navigateWeek = useCallback(
    (direction: 'prev' | 'next') => {
      // Autosave is enabled; suppress prompt

      const newDate =
        direction === 'next'
          ? getNextMonday(currentWeekStart)
          : getPreviousMonday(currentWeekStart);

      logger.info('Navigating to week', {
        direction,
        from: formatDateForAPI(currentWeekStart),
        to: formatDateForAPI(newDate),
      });

      setCurrentWeekStart(newDate);
    },
    [currentWeekStart]
  );

  /**
   * Refresh schedule from backend
   */
  const refreshSchedule = useCallback(async () => {
    logger.debug('Refreshing schedule');
    await fetchWeekSchedule();
  }, [fetchWeekSchedule]);

  /**
   * Jump to the current week (Monday as start)
   */
  const goToCurrentWeek = useCallback(() => {
    const wk = getCurrentWeekStart();
    setCurrentWeekStart(wk);
  }, []);

  /**
   * Reset state when week changes
   */
  useEffect(() => {
    logger.debug('Week changed, resetting state', {
      weekStart: formatDateForAPI(currentWeekStart),
    });

    setWeekSchedule({});
    setSavedWeekSchedule({});
    setExistingSlots([]);
    void fetchWeekSchedule();
  }, [currentWeekStart, fetchWeekSchedule]);

  return {
    // State
    currentWeekStart,
    weekSchedule,
    savedWeekSchedule,
    hasUnsavedChanges,
    isLoading,
    existingSlots,
    weekDates,
    message,

    // Actions
    navigateWeek,
    setWeekSchedule,
    setMessage,
    refreshSchedule,
    goToCurrentWeek,
    isDateInPast,
    currentWeekDisplay,
    ...(version && { version }),
    ...(lastModified && { lastModified }),
  };
}
