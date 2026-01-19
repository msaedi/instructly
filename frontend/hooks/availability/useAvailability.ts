// frontend/hooks/availability/useAvailability.ts

import { useCallback } from 'react';
import { useWeekSchedule } from '@/hooks/availability/useWeekSchedule';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { formatDateForAPI } from '@/lib/availability/dateHelpers';
import { logger } from '@/lib/logger';
import { WeekSchedule, TimeSlot, WeekBits } from '@/types/availability';
import { fromWindows, toWindows } from '@/lib/calendar/bitset';
import type {
  ApiErrorResponse,
  ApplyToDateRangeResponse,
  AvailabilityUpdateErrorResponse,
  WeekValidationResponse,
  WeekAvailabilityUpdateResponse,
  CopyWeekResponse,
} from '@/features/shared/api/types';

export interface SaveWeekOptions {
  clearExisting?: boolean;
  scheduleOverride?: WeekSchedule;
  override?: boolean;
}

export interface SaveWeekResult {
  success: boolean;
  message: string;
  code?: number;
  serverVersion?: string;
  version?: string;
  weekVersion?: string;
}

export interface UseAvailabilityReturn {
  // state from useWeekSchedule
  currentWeekStart: Date;
  weekBits: WeekBits;
  savedWeekBits: WeekBits;
  weekSchedule: WeekSchedule;
  savedWeekSchedule: WeekSchedule;
  hasUnsavedChanges: boolean;
  isLoading: boolean;
  weekDates: Date[];
  message: { type: 'success' | 'error' | 'info'; text: string } | null;

  // actions
  navigateWeek: (dir: 'prev' | 'next') => void;
  setWeekBits: (next: WeekBits | ((prev: WeekBits) => WeekBits)) => void;
  setMessage: (m: { type: 'success' | 'error' | 'info'; text: string } | null) => void;
  refreshSchedule: () => Promise<void>;
  currentWeekDisplay: string;
  version?: string;
  etag?: string;
  lastModified?: string;
  goToCurrentWeek: () => void;
  allowPastEdits?: boolean;

  // API orchestrations (thin)
  saveWeek: (opts?: SaveWeekOptions) => Promise<SaveWeekResult>;
  validateWeek: () => Promise<WeekValidationResponse | null>;
  copyFromPreviousWeek: () => Promise<{ success: boolean; message: string }>;
  applyToFutureWeeks: (
    endISO: string
  ) => Promise<{ success: boolean; message: string; weeksAffected?: number; daysWritten?: number }>;
}

function extractErrorMessage(err: unknown, fallback: string): string {
  if (!err) return fallback;
  const detail = (err as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d: unknown) => (typeof d === 'string' ? d : (d as { msg?: string })?.['msg']))
      .filter(Boolean);
    if (msgs.length) return msgs.join('; ');
  }
  if (typeof (err as Record<string, unknown>)?.['message'] === 'string') return (err as Record<string, unknown>)['message'] as string;
  try {
    return JSON.stringify(err);
  } catch {
    return fallback;
  }
}

function bitsRecordToSchedule(bits: WeekBits): WeekSchedule {
  const schedule: WeekSchedule = {};
  Object.entries(bits).forEach(([date, dayBits]) => {
    const windows = toWindows(dayBits);
    if (windows.length > 0) {
      schedule[date] = windows;
    }
  });
  return schedule;
}

function scheduleToBits(schedule: WeekSchedule): WeekBits {
  const record: WeekBits = {};
  Object.entries(schedule).forEach(([date, windows]) => {
    if (windows && windows.length > 0) {
      record[date] = fromWindows(windows);
    }
  });
  return record;
}

const BYTE_MASK = 0xff;

const countSetBits = (value: number): number => {
  let count = 0;
  let cursor = value & BYTE_MASK;
  while (cursor > 0) {
    count += cursor & 1;
    cursor >>= 1;
  }
  return count;
};

function computeBitsDelta(previous: WeekBits, next: WeekBits): { added: number; removed: number } {
  let added = 0;
  let removed = 0;
  const allDates = new Set([...Object.keys(previous), ...Object.keys(next)]);
  allDates.forEach((date) => {
    const prevBits = previous[date];
    const nextBits = next[date];
    for (let i = 0; i < 6; i += 1) {
      const prevByte = prevBits ? prevBits[i] ?? 0 : 0;
      const nextByte = nextBits ? nextBits[i] ?? 0 : 0;
      const addedMask = nextByte & (~prevByte & BYTE_MASK);
      const removedMask = prevByte & (~nextByte & BYTE_MASK);
      added += countSetBits(addedMask);
      removed += countSetBits(removedMask);
    }
  });
  return { added, removed };
}

export function useAvailability(): UseAvailabilityReturn {
  const {
    currentWeekStart,
    weekBits,
    savedWeekBits,
    weekSchedule,
    savedWeekSchedule,
    hasUnsavedChanges,
    isLoading,
    weekDates,
    message,
    navigateWeek,
    setWeekBits,
    setSavedWeekBits,
    setMessage,
    refreshSchedule,
    goToCurrentWeek,
    currentWeekDisplay,
    version,
    etag,
    lastModified,
    setVersion,
    allowPastEdits,
    setAllowPastEdits,
  } = useWeekSchedule();

  const saveWeek: UseAvailabilityReturn['saveWeek'] = useCallback(
    async (opts: SaveWeekOptions = {}) => {
      const week_start = formatDateForAPI(currentWeekStart);
      const bitsSource: WeekBits = opts.scheduleOverride ? scheduleToBits(opts.scheduleOverride) : weekBits;
      const scheduleSource: WeekSchedule =
        opts.scheduleOverride ?? bitsRecordToSchedule(bitsSource);
      const clearExisting = opts.clearExisting ?? true;
      const override = Boolean(opts.override);

      const schedule: Array<{ date: string; start_time: string; end_time: string }> = [];
      Object.entries(scheduleSource).forEach(([date, slots]) => {
        (slots || []).forEach((slot: TimeSlot) => {
          schedule.push({ date, start_time: slot.start_time, end_time: slot.end_time });
        });
      });

      schedule.sort((a, b) => {
        if (a.date !== b.date) return a.date.localeCompare(b.date);
        if (a.start_time !== b.start_time) return a.start_time.localeCompare(b.start_time);
        return a.end_time.localeCompare(b.end_time);
      });

      const daysCount = Object.keys(scheduleSource).length;
      const bitsDelta = computeBitsDelta(savedWeekBits, bitsSource);

      logger.info('Saving weekly availability snapshot', {
        week_start,
        days: daysCount,
        total_slots: schedule.length,
      });

      try {
        const storedVersion =
          typeof window !== 'undefined'
            ? (window as Window & { __week_version?: string }).__week_version
            : undefined;
        const effectiveVersion = storedVersion || etag || undefined;

        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (effectiveVersion) {
          headers['If-Match'] = effectiveVersion;
        }

        logger.debug(
          `saving If-Match=${effectiveVersion ?? 'none'} days=${daysCount} bitsDelta={added:${bitsDelta.added}, removed:${bitsDelta.removed}}`
        );

        const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK, {
          method: 'POST',
          headers,
          body: JSON.stringify({
            week_start,
            clear_existing: clearExisting,
            schedule,
            base_version: effectiveVersion,
            override,
          }),
        });
        const status = res.status;
        const responseEtag = res.headers?.get?.('ETag') || undefined;
        const allowPastHeader = res.headers?.get?.('X-Allow-Past');
        const responseJson = (await res
          .clone()
          .json()
          .catch(() => undefined)) as
          | WeekAvailabilityUpdateResponse
          | AvailabilityUpdateErrorResponse
          | undefined;

        if (!res.ok) {
          if (typeof allowPastHeader === 'string') {
            const normalizedAllow = allowPastHeader.trim().toLowerCase();
            setAllowPastEdits(
              normalizedAllow === '1' || normalizedAllow === 'true' || normalizedAllow === 'yes'
            );
          }
          const conflictVersion =
            responseJson && 'current_version' in responseJson
              ? responseJson.current_version
              : undefined;
          const serverVersion = typeof conflictVersion === 'string' ? conflictVersion : responseEtag;
          if (serverVersion) {
            if (typeof window !== 'undefined') {
              (window as Window & { __week_version?: string }).__week_version = serverVersion;
            }
            setVersion(serverVersion);
          }
          let message: string;
          const isVersionConflict =
            status === 409 ||
            (responseJson && 'error' in responseJson && responseJson.error === 'version_conflict');
          if (isVersionConflict) {
            message = 'Week availability changed in another session.';
          } else {
            const detail = extractErrorMessage(responseJson, 'Failed to save availability');
            message = `Failed to save availability (${status}): ${detail}`;
          }
          return {
            success: false,
            message,
            code: status,
            ...(serverVersion ? { serverVersion } : {}),
          };
        }

        const newVersion =
          responseEtag ||
          (responseJson && 'week_version' in responseJson ? responseJson.week_version : undefined) ||
          (responseJson && 'version' in responseJson ? responseJson.version : undefined);
        if (typeof allowPastHeader === 'string') {
          const normalizedAllow = allowPastHeader.trim().toLowerCase();
          setAllowPastEdits(
            normalizedAllow === '1' || normalizedAllow === 'true' || normalizedAllow === 'yes'
          );
        }
        if (newVersion && typeof window !== 'undefined') {
          (window as Window & { __week_version?: string }).__week_version = newVersion;
          logger.debug('Updated week version from POST', { newVersion });
        }
        if (newVersion) {
          setVersion(newVersion);
        }
        setWeekBits(bitsSource);
        setSavedWeekBits(bitsSource);

        return {
          success: true,
          message: responseJson?.message || 'Availability saved',
          ...(newVersion ? { version: newVersion, weekVersion: newVersion } : {}),
        };
      } catch (e) {
        logger.error('saveWeek error', e);
        return { success: false, message: 'Network error while saving' };
      }
    },
    [
      currentWeekStart,
      weekBits,
      savedWeekBits,
      etag,
      setVersion,
      setSavedWeekBits,
      setWeekBits,
      setAllowPastEdits,
    ]
  );

  const validateWeek: UseAvailabilityReturn['validateWeek'] = useCallback(async () => {
    try {
      const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_VALIDATE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_week: weekSchedule,
          saved_week: savedWeekSchedule,
          week_start: formatDateForAPI(currentWeekStart),
        }),
      });
      if (!res.ok) return null;
      return (await res.json()) as WeekValidationResponse;
    } catch (e) {
      logger.error('validateWeek error', e);
      return null;
    }
  }, [weekSchedule, savedWeekSchedule, currentWeekStart]);

  const copyFromPreviousWeek: UseAvailabilityReturn['copyFromPreviousWeek'] = useCallback(async () => {
    try {
      const prev = new Date(currentWeekStart);
      prev.setDate(prev.getDate() - 7);
      const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_COPY_WEEK, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from_week_start: formatDateForAPI(prev),
          to_week_start: formatDateForAPI(currentWeekStart),
        }),
      });
      if (!res.ok) {
        const err = (await res.json().catch(() => ({} as ApiErrorResponse))) as ApiErrorResponse;
        return { success: false, message: extractErrorMessage(err, 'Failed to copy week') };
      }
      const payload = (await res.json().catch(() => null)) as CopyWeekResponse | null;
      await refreshSchedule();
      return { success: true, message: payload?.message ?? 'Copied previous week' };
    } catch (e) {
      logger.error('copyFromPreviousWeek error', e);
      return { success: false, message: 'Network error while copying' };
    }
  }, [currentWeekStart, refreshSchedule]);

  const applyToFutureWeeks: UseAvailabilityReturn['applyToFutureWeeks'] = useCallback(
    async (endISO) => {
      try {
        const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_APPLY_RANGE, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            from_week_start: formatDateForAPI(currentWeekStart),
            start_date: formatDateForAPI(currentWeekStart),
            end_date: endISO,
          }),
        });
        const responseJson = (await res
          .clone()
          .json()
          .catch(() => undefined)) as ApplyToDateRangeResponse | ApiErrorResponse | undefined;

        if (!res.ok) {
          return {
            success: false,
            message: extractErrorMessage(responseJson, 'Failed to apply to future weeks'),
          };
        }

        const weeksAffected =
          responseJson && 'weeks_affected' in responseJson && typeof responseJson.weeks_affected === 'number'
            ? responseJson.weeks_affected
            : undefined;
        const daysWritten =
          responseJson && 'days_written' in responseJson && typeof responseJson.days_written === 'number'
            ? responseJson.days_written
            : undefined;

        if (weeksAffected !== undefined || daysWritten !== undefined) {
          logger.info('Applied schedule to future range', {
            end_date: endISO,
            weeksAffected,
            daysWritten,
          });
        }

        return {
          success: true,
          message: responseJson?.message || 'Applied schedule to future range',
          ...(weeksAffected !== undefined ? { weeksAffected } : {}),
          ...(daysWritten !== undefined ? { daysWritten } : {}),
        };
      } catch (e) {
        logger.error('applyToFutureWeeks error', e);
        return { success: false, message: 'Network error while applying' };
      }
    },
    [currentWeekStart]
  );

  return {
    currentWeekStart,
    weekBits,
    savedWeekBits,
    weekSchedule,
    savedWeekSchedule,
    hasUnsavedChanges,
    isLoading,
    weekDates: weekDates.map((info) => info.date),
    message,
    navigateWeek,
    setWeekBits,
    setMessage,
    refreshSchedule,
    goToCurrentWeek,
    currentWeekDisplay,
    ...(version && { version }),
    ...(etag && { etag }),
    ...(lastModified && { lastModified }),
    ...(allowPastEdits !== undefined ? { allowPastEdits } : {}),
    saveWeek,
    validateWeek,
    copyFromPreviousWeek,
    applyToFutureWeeks,
  };
}
