// frontend/hooks/availability/useWeekSchedule.ts

import { useState, useEffect, useCallback, useMemo } from 'react';

import type {
  WeekBits,
  WeekSchedule,
  ExistingSlot,
  WeekDateInfo,
  AvailabilityMessage,
  TimeSlot,
} from '@/types/availability';
import type { DayBits } from '@/lib/calendar/bitset';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import {
  getCurrentWeekStart,
  getWeekDates,
  formatDateForAPI,
  getPreviousMonday,
  getNextMonday,
} from '@/lib/availability/dateHelpers';
import { fromWindows, newEmptyBits, toWindows } from '@/lib/calendar/bitset';
import { logger } from '@/lib/logger';
import type { ApiErrorResponse, components } from '@/features/shared/api/types';

type WeekAvailabilityResponse = components['schemas']['WeekAvailabilityResponse'];

type WeekBitsSetter = WeekBits | ((prev: WeekBits) => WeekBits);

const ZERO_DAY: DayBits = newEmptyBits();

function cloneDayBits(bits: DayBits): DayBits {
  return bits.slice();
}

function cloneWeekBits(source: WeekBits): WeekBits {
  const next: WeekBits = {};
  Object.entries(source).forEach(([date, bits]) => {
    next[date] = cloneDayBits(bits);
  });
  return next;
}

function extractDetailFromResponse(payload: unknown): string | undefined {
  if (!payload) return undefined;
  if (typeof payload === 'string') return payload;
  const record = payload as Record<string, unknown>;
  if (typeof record?.['detail'] === 'string') {
    return record['detail'] as string;
  }
  const detailField = record?.['detail'];
  if (Array.isArray(detailField)) {
    const collected = detailField
      .map((entry) => {
        if (typeof entry === 'string') return entry;
        const entryRecord = entry as Record<string, unknown> | undefined;
        if (entryRecord && typeof entryRecord['msg'] === 'string') {
          return entryRecord['msg'] as string;
        }
        return undefined;
      })
      .filter(Boolean) as string[];
    if (collected.length) {
      return collected.join('; ');
    }
  }
  if (typeof record?.['message'] === 'string') {
    return record['message'] as string;
  }
  try {
    return JSON.stringify(payload);
  } catch {
    return undefined;
  }
}

function dayBitsEqual(a?: DayBits, b?: DayBits): boolean {
  for (let i = 0; i < ZERO_DAY.length; i += 1) {
    const av = a ? a[i] ?? 0 : 0;
    const bv = b ? b[i] ?? 0 : 0;
    if (av !== bv) return false;
  }
  return true;
}

function weekBitsEqual(a: WeekBits, b: WeekBits): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const key of keys) {
    if (!dayBitsEqual(a[key], b[key])) return false;
  }
  return true;
}

function scheduleToBits(schedule: WeekSchedule): WeekBits {
  const next: WeekBits = {};
  Object.entries(schedule).forEach(([date, windows]) => {
    if (windows && windows.length > 0) {
      next[date] = fromWindows(windows);
    }
  });
  return next;
}

function bitsToSchedule(bitsRecord: WeekBits): WeekSchedule {
  const schedule: WeekSchedule = {};
  Object.entries(bitsRecord).forEach(([date, bits]) => {
    const windows = toWindows(bits);
    if (windows.length > 0) {
      schedule[date] = windows;
    }
  });
  return schedule;
}

/**
 * Hook return type with all schedule management functionality
 */
export interface UseWeekScheduleReturn {
  currentWeekStart: Date;
  weekBits: WeekBits;
  savedWeekBits: WeekBits;
  weekSchedule: WeekSchedule;
  savedWeekSchedule: WeekSchedule;
  hasUnsavedChanges: boolean;
  isLoading: boolean;
  existingSlots: ExistingSlot[];
  weekDates: WeekDateInfo[];
  message: AvailabilityMessage | null;

  navigateWeek: (direction: 'prev' | 'next') => void;
  setWeekBits: (next: WeekBitsSetter) => void;
  setSavedWeekBits: (next: WeekBitsSetter) => void;
  setWeekSchedule: (schedule: WeekSchedule | ((prev: WeekSchedule) => WeekSchedule)) => void;
  setMessage: (message: AvailabilityMessage | null) => void;
  refreshSchedule: () => Promise<void>;
  goToCurrentWeek: () => void;
  isDateInPast: (dateStr: string) => boolean;
  currentWeekDisplay: string;
  version?: string;
  etag?: string;
  lastModified?: string;
  setVersion: (next?: string) => void;
  allowPastEdits?: boolean;
  setAllowPastEdits: (next?: boolean) => void;
}

export function useWeekSchedule(
  options: {
    messageTimeout?: number;
    selectedWeekStart?: Date;
    onWeekStartChange?: (weekStart: Date) => void;
  } = {}
): UseWeekScheduleReturn {
  const { messageTimeout = 5000, selectedWeekStart, onWeekStartChange } = options;

  const [currentWeekStart, setCurrentWeekStart] = useState<Date>(() => {
    const initial = selectedWeekStart
      ? getCurrentWeekStart(selectedWeekStart)
      : getCurrentWeekStart();
    logger.debug('Initializing week start', {
      weekStart: formatDateForAPI(initial),
      source: selectedWeekStart ? 'external' : 'today',
      ...(selectedWeekStart
        ? { selectedInput: formatDateForAPI(selectedWeekStart) }
        : {}),
    });
    return initial;
  });

  const [weekBitsState, setWeekBitsState] = useState<WeekBits>({});
  const [savedWeekBitsState, setSavedWeekBitsState] = useState<WeekBits>({});
  const [existingSlots, setExistingSlots] = useState<ExistingSlot[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState<AvailabilityMessage | null>(null);
  const [etag, setEtag] = useState<string | undefined>(undefined);
  const [lastModified, setLastModified] = useState<string | undefined>(undefined);
  const [allowPastEdits, setAllowPastEditsState] = useState<boolean | undefined>(undefined);

  const currentWeekStartMs = currentWeekStart.getTime();

  useEffect(() => {
    if (!selectedWeekStart) return;
    const normalized = getCurrentWeekStart(selectedWeekStart);
    if (normalized.getTime() === currentWeekStartMs) return;
    logger.debug('Syncing week start from external selection', {
      previous: formatDateForAPI(currentWeekStart),
      next: formatDateForAPI(normalized),
    });
    setCurrentWeekStart(normalized);
  }, [selectedWeekStart, currentWeekStartMs, currentWeekStart]);

  const weekDates = useMemo(() => getWeekDates(currentWeekStart), [currentWeekStart]);

  const weekSchedule = useMemo(
    () => bitsToSchedule(weekBitsState),
    [weekBitsState]
  );

  const savedWeekSchedule = useMemo(
    () => bitsToSchedule(savedWeekBitsState),
    [savedWeekBitsState]
  );

  const hasUnsavedChanges = useMemo(
    () => !weekBitsEqual(weekBitsState, savedWeekBitsState),
    [weekBitsState, savedWeekBitsState]
  );

  const currentWeekDisplay = useMemo(() => {
    const start = weekDates[0]?.date;
    if (!start) return '';
    return start.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  }, [weekDates]);

  const isDateInPast = useCallback((dateStr: string): boolean => {
    const date = new Date(dateStr);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    date.setHours(0, 0, 0, 0);
    return date < today;
  }, []);

  useEffect(() => {
    if (message && messageTimeout > 0) {
      const timer = setTimeout(() => setMessage(null), messageTimeout);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [message, messageTimeout]);

  const setWeekBits = useCallback((next: WeekBitsSetter) => {
    setWeekBitsState((prev) => {
      const resolved = typeof next === 'function' ? (next as (p: WeekBits) => WeekBits)(prev) : next;
      return cloneWeekBits(resolved);
    });
  }, []);

  const setSavedWeekBits = useCallback((next: WeekBitsSetter) => {
    setSavedWeekBitsState((prev) => {
      const resolved = typeof next === 'function' ? (next as (p: WeekBits) => WeekBits)(prev) : next;
      return cloneWeekBits(resolved);
    });
  }, []);

  const setVersion = useCallback((next?: string) => {
    setEtag(next);
    if (typeof window !== 'undefined') {
      const win = window as Window & { __week_version?: string };
      if (next) {
        win.__week_version = next;
      } else {
        delete win.__week_version;
      }
    }
  }, []);

  const setAllowPastEdits = useCallback((next?: boolean) => {
    setAllowPastEditsState(next);
  }, []);

  const setWeekSchedule = useCallback(
    (next: WeekSchedule | ((prev: WeekSchedule) => WeekSchedule)) => {
      setWeekBitsState((prev) => {
        const currentSchedule = bitsToSchedule(prev);
        const resolved =
          typeof next === 'function' ? (next as (p: WeekSchedule) => WeekSchedule)(currentSchedule) : next;
        return cloneWeekBits(scheduleToBits(resolved));
      });
    },
    []
  );

  const fetchWeekSchedule = useCallback(async () => {
    setIsLoading(true);
    logger.time('fetchWeekSchedule');

    try {
      const mondayDate = formatDateForAPI(currentWeekStart);
      logger.info('Fetching week schedule', { mondayDate });

      const response = await fetchWithAuth(
        `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK}?start_date=${mondayDate}`
      );

      if (!response.ok) {
        const errorBody = (await response.json().catch(() => undefined)) as ApiErrorResponse | undefined;
        const detail = extractDetailFromResponse(errorBody) || response.statusText || 'Unknown error';
        const messageText = `Failed to load availability (${response.status}): ${detail}`;
        logger.error('Failed to fetch weekly availability', new Error(messageText), {
          status: response.status,
          detail: errorBody,
        });
        setMessage({
          type: 'error',
          text: messageText,
        });
        return;
      }

      const data = (await response.json()) as WeekAvailabilityResponse;
      const headerEtag = response.headers.get('ETag') || undefined;
      const headerLastModified = response.headers.get('Last-Modified') || undefined;
      const allowPastHeader = response.headers.get('X-Allow-Past');

      const cleaned: WeekSchedule = {};
      Object.entries(data as Record<string, TimeSlot[] | undefined>).forEach(([date, slots]) => {
        if (slots && Array.isArray(slots) && slots.length > 0) {
          cleaned[date] = slots;
        }
      });

      const nextBits = scheduleToBits(cleaned);

      logger.info('Week schedule loaded successfully', {
        weekStart: mondayDate,
        daysWithAvailability: Object.keys(nextBits).length,
      });

      setWeekBits(nextBits);
      setSavedWeekBits(nextBits);
      setVersion(headerEtag || undefined);
      setLastModified(headerLastModified);
      if (allowPastHeader !== null) {
        const normalized = allowPastHeader.trim().toLowerCase();
        setAllowPastEdits(
          normalized === '1' || normalized === 'true' || normalized === 'yes'
        );
      }
    } catch (error) {
      const fallback = error instanceof Error ? error.message : 'Unexpected error';
      const messageText = `Failed to load availability: ${fallback}`;
      logger.error('Failed to load availability', error);
      setMessage({
        type: 'error',
        text: messageText,
      });
    } finally {
      logger.timeEnd('fetchWeekSchedule');
      setIsLoading(false);
    }
  }, [currentWeekStart, setWeekBits, setSavedWeekBits, setVersion, setAllowPastEdits]);

  const updateWeekStart = useCallback(
    (next: Date) => {
      const normalized = getCurrentWeekStart(next);
      setCurrentWeekStart(normalized);
      onWeekStartChange?.(normalized);
    },
    [onWeekStartChange]
  );

  const navigateWeek = useCallback(
    (direction: 'prev' | 'next') => {
      const newDate =
        direction === 'next'
          ? getNextMonday(currentWeekStart)
          : getPreviousMonday(currentWeekStart);

      logger.info('Navigating to week', {
        direction,
        from: formatDateForAPI(currentWeekStart),
        to: formatDateForAPI(newDate),
      });

      updateWeekStart(newDate);
    },
    [currentWeekStart, updateWeekStart]
  );

  const refreshSchedule = useCallback(async () => {
    logger.debug('Refreshing schedule');
    await fetchWeekSchedule();
  }, [fetchWeekSchedule]);

  const goToCurrentWeek = useCallback(() => {
    const wk = getCurrentWeekStart();
    updateWeekStart(wk);
  }, [updateWeekStart]);

  useEffect(() => {
    logger.debug('Week changed, resetting state', {
      weekStart: formatDateForAPI(currentWeekStart),
    });

    setWeekBits({});
    setSavedWeekBits({});
    setExistingSlots([]);
    void fetchWeekSchedule();
  }, [currentWeekStart, fetchWeekSchedule, setWeekBits, setSavedWeekBits]);

  return {
    currentWeekStart,
    weekBits: weekBitsState,
    savedWeekBits: savedWeekBitsState,
    weekSchedule,
    savedWeekSchedule,
    hasUnsavedChanges,
    isLoading,
    existingSlots,
    weekDates,
    message,
    navigateWeek,
    setWeekBits,
    setSavedWeekBits,
    setWeekSchedule,
    setMessage,
    refreshSchedule,
    goToCurrentWeek,
    isDateInPast,
    currentWeekDisplay,
    ...(etag ? { version: etag, etag } : {}),
    ...(lastModified ? { lastModified } : {}),
    setVersion,
    ...(allowPastEdits !== undefined ? { allowPastEdits } : {}),
    setAllowPastEdits,
  };
}
