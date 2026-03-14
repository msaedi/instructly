// frontend/hooks/availability/useAvailability.ts

import { useCallback } from 'react';
import { useWeekSchedule } from '@/hooks/availability/useWeekSchedule';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { formatDateForAPI } from '@/lib/availability/dateHelpers';
import { logger } from '@/lib/logger';
import { isRecord, isUnknownArray } from '@/lib/typesafe';
import { WeekSchedule, WeekBits, WeekTags } from '@/types/availability';
import { fromWindows, newEmptyTags } from '@/lib/calendar/bitset';
import { encodeUint8ArrayToBase64 } from '@/lib/calendar/bitmapBase64';
import { computeBitsDelta } from '@/hooks/availability/bitsDelta';
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
  weekTags: WeekTags;
  savedWeekTags: WeekTags;
  weekSchedule: WeekSchedule;
  savedWeekSchedule: WeekSchedule;
  hasUnsavedChanges: boolean;
  isLoading: boolean;
  weekDates: Date[];
  message: { type: 'success' | 'error' | 'info'; text: string } | null;

  // actions
  navigateWeek: (dir: 'prev' | 'next') => void;
  setWeekBits: (next: WeekBits | ((prev: WeekBits) => WeekBits)) => void;
  setWeekTags: (next: WeekTags | ((prev: WeekTags) => WeekTags)) => void;
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
  if (!isRecord(err)) return fallback;
  const detail: unknown = err['detail'];
  if (typeof detail === 'string') return detail;
  if (isUnknownArray(detail)) {
    const msgs = detail
      .map((d) => {
        if (typeof d === 'string') return d;
        if (isRecord(d) && typeof d['msg'] === 'string') return d['msg'];
        return undefined;
      })
      .filter((s): s is string => typeof s === 'string');
    if (msgs.length) return msgs.join('; ');
  }
  if (typeof err['message'] === 'string') return err['message'];
  try {
    return JSON.stringify(err);
  } catch {
    return fallback;
  }
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

function normalizeWeekTagsForBits(bits: WeekBits, tags: WeekTags): WeekTags {
  const next: WeekTags = {};
  Object.keys(bits).forEach((date) => {
    next[date] = tags[date]?.slice() ?? newEmptyTags();
  });
  return next;
}


export function useAvailability(): UseAvailabilityReturn {
  const {
    currentWeekStart,
    weekBits,
    savedWeekBits,
    weekTags,
    savedWeekTags,
    weekSchedule,
    savedWeekSchedule,
    hasUnsavedChanges,
    isLoading,
    weekDates,
    message,
    navigateWeek,
    setWeekBits,
    setSavedWeekBits,
    setWeekTags,
    setSavedWeekTags,
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
      const tagsSource: WeekTags =
        opts.scheduleOverride ? normalizeWeekTagsForBits(bitsSource, weekTags) : weekTags;
      const clearExisting = opts.clearExisting ?? true;
      const override = Boolean(opts.override);
      const days = Object.entries(bitsSource)
        .sort(([dateA], [dateB]) => dateA.localeCompare(dateB))
        .map(([date, dayBits]) => ({
          date,
          bits: encodeUint8ArrayToBase64(dayBits),
          format_tags: encodeUint8ArrayToBase64(tagsSource[date] ?? newEmptyTags()),
        }));

      const daysCount = days.length;
      const bitsDelta = computeBitsDelta(savedWeekBits, bitsSource);

      logger.info('Saving weekly availability snapshot', {
        week_start,
        days: daysCount,
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
            days,
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
            responseJson && typeof responseJson === 'object' && 'current_version' in responseJson
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
            (responseJson && typeof responseJson === 'object' && 'error' in responseJson && responseJson.error === 'version_conflict');
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
        setWeekTags(tagsSource);
        setSavedWeekTags(tagsSource);

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
      weekTags,
      etag,
      setVersion,
      setSavedWeekBits,
      setWeekBits,
      setSavedWeekTags,
      setWeekTags,
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
    weekTags,
    savedWeekTags,
    weekSchedule,
    savedWeekSchedule,
    hasUnsavedChanges,
    isLoading,
    weekDates: weekDates.map((info) => info.date),
    message,
    navigateWeek,
    setWeekBits,
    setWeekTags,
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
