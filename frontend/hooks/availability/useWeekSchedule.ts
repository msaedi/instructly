// frontend/hooks/availability/useWeekSchedule.ts

import { useState, useEffect, useCallback, useMemo } from 'react';

import type {
  WeekBits,
  WeekTags,
  WeekSchedule,
  ExistingSlot,
  WeekDateInfo,
  AvailabilityMessage,
} from '@/types/availability';
import type { DayBits, DayTags } from '@/lib/calendar/bitset';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import {
  getCurrentWeekStart,
  getWeekDates,
  formatDateForAPI,
  getPreviousMonday,
  getNextMonday,
} from '@/lib/availability/dateHelpers';
import { fromWindows, newEmptyBits, newEmptyTags, toWindows, BYTES_PER_DAY, TAG_BYTES_PER_DAY } from '@/lib/calendar/bitset';
import { decodeBase64ToUint8Array } from '@/lib/calendar/bitmapBase64';
import { logger } from '@/lib/logger';
import { isRecord, isUnknownArray } from '@/lib/typesafe';
import type { ApiErrorResponse, WeekBitmapResponse } from '@/features/shared/api/types';

type WeekBitsSetter = WeekBits | ((prev: WeekBits) => WeekBits);
type WeekTagsSetter = WeekTags | ((prev: WeekTags) => WeekTags);

const ZERO_DAY: DayBits = newEmptyBits();
const ZERO_TAGS: DayTags = newEmptyTags();

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

function cloneDayTags(tags: DayTags): DayTags {
  return tags.slice();
}

function cloneWeekTags(source: WeekTags): WeekTags {
  const next: WeekTags = {};
  Object.entries(source).forEach(([date, tags]) => {
    next[date] = cloneDayTags(tags);
  });
  return next;
}

function extractDetailFromResponse(payload: unknown): string | undefined {
  if (!payload) return undefined;
  if (typeof payload === 'string') return payload;
  if (!isRecord(payload)) return undefined;
  if (typeof payload['detail'] === 'string') {
    return payload['detail'];
  }
  const detailField = payload['detail'];
  if (isUnknownArray(detailField)) {
    const collected = detailField
      .map((entry) => {
        if (typeof entry === 'string') return entry;
        if (isRecord(entry) && typeof entry['msg'] === 'string') {
          return entry['msg'];
        }
        return undefined;
      })
      .filter((s): s is string => typeof s === 'string');
    if (collected.length) {
      return collected.join('; ');
    }
  }
  if (typeof payload['message'] === 'string') {
    return payload['message'];
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

function dayTagsEqual(a?: DayTags, b?: DayTags): boolean {
  for (let i = 0; i < ZERO_TAGS.length; i += 1) {
    const av = a ? a[i] ?? 0 : 0;
    const bv = b ? b[i] ?? 0 : 0;
    if (av !== bv) return false;
  }
  return true;
}

function weekTagsEqual(a: WeekTags, b: WeekTags): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const key of keys) {
    if (!dayTagsEqual(a[key], b[key])) return false;
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
  weekTags: WeekTags;
  savedWeekTags: WeekTags;
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
  setWeekTags: (next: WeekTagsSetter) => void;
  setSavedWeekTags: (next: WeekTagsSetter) => void;
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
  const [weekTagsState, setWeekTagsState] = useState<WeekTags>({});
  const [savedWeekTagsState, setSavedWeekTagsState] = useState<WeekTags>({});
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
    () => !weekBitsEqual(weekBitsState, savedWeekBitsState) || !weekTagsEqual(weekTagsState, savedWeekTagsState),
    [weekBitsState, savedWeekBitsState, weekTagsState, savedWeekTagsState]
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

  const setWeekTags = useCallback((next: WeekTagsSetter) => {
    setWeekTagsState((prev) => {
      const resolved = typeof next === 'function' ? (next as (p: WeekTags) => WeekTags)(prev) : next;
      return cloneWeekTags(resolved);
    });
  }, []);

  const setSavedWeekTags = useCallback((next: WeekTagsSetter) => {
    setSavedWeekTagsState((prev) => {
      const resolved = typeof next === 'function' ? (next as (p: WeekTags) => WeekTags)(prev) : next;
      return cloneWeekTags(resolved);
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

      const data = (await response.json()) as WeekBitmapResponse;
      const headerEtag = response.headers.get('ETag') || undefined;
      const headerLastModified = response.headers.get('Last-Modified') || undefined;
      const allowPastHeader = response.headers.get('X-Allow-Past');
      const nextBits: WeekBits = {};
      const nextTags: WeekTags = {};
      for (const day of data.days ?? []) {
        nextBits[day.date] = decodeBase64ToUint8Array(day.bits, BYTES_PER_DAY);
        nextTags[day.date] = decodeBase64ToUint8Array(day.format_tags, TAG_BYTES_PER_DAY);
      }

      logger.info('Week schedule loaded successfully', {
        weekStart: mondayDate,
        daysWithAvailability: Object.keys(nextBits).length,
      });

      setWeekBits(nextBits);
      setSavedWeekBits(nextBits);
      setWeekTags(nextTags);
      setSavedWeekTags(nextTags);
      setVersion(headerEtag || data.version || undefined);
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
  }, [
    currentWeekStart,
    setWeekBits,
    setSavedWeekBits,
    setWeekTags,
    setSavedWeekTags,
    setVersion,
    setAllowPastEdits,
  ]);

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
    setWeekTags({});
    setSavedWeekTags({});
    setExistingSlots([]);
    void fetchWeekSchedule();
  }, [
    currentWeekStart,
    fetchWeekSchedule,
    setWeekBits,
    setSavedWeekBits,
    setWeekTags,
    setSavedWeekTags,
  ]);

  return {
    currentWeekStart,
    weekBits: weekBitsState,
    savedWeekBits: savedWeekBitsState,
    weekTags: weekTagsState,
    savedWeekTags: savedWeekTagsState,
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
    setWeekTags,
    setSavedWeekTags,
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
