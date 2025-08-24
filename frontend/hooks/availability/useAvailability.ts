// frontend/hooks/availability/useAvailability.ts

import { useCallback } from 'react';
import { useWeekSchedule } from '@/hooks/availability/useWeekSchedule';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { formatDateForAPI } from '@/lib/availability/dateHelpers';
import { logger } from '@/lib/logger';
import { WeekSchedule } from '@/types/availability';

export interface UseAvailabilityReturn {
  // state from useWeekSchedule
  currentWeekStart: Date;
  weekSchedule: WeekSchedule;
  savedWeekSchedule: WeekSchedule;
  hasUnsavedChanges: boolean;
  isLoading: boolean;
  weekDates: any[];
  message: any;

  // actions
  navigateWeek: (dir: 'prev' | 'next') => void;
  setWeekSchedule: (s: WeekSchedule | ((prev: WeekSchedule) => WeekSchedule)) => void;
  setMessage: (m: any) => void;
  refreshSchedule: () => Promise<void>;
  currentWeekDisplay: string;
  version?: string;
  lastModified?: string;

  // API orchestrations (thin)
  saveWeek: (opts?: { clearExisting?: boolean }) => Promise<{ success: boolean; message: string; code?: number }>;
  validateWeek: () => Promise<any>;
  copyFromPreviousWeek: () => Promise<{ success: boolean; message: string }>;
  applyToFutureWeeks: (endISO: string) => Promise<{ success: boolean; message: string }>;
}

function extractErrorMessage(err: any, fallback: string): string {
  if (!err) return fallback;
  const detail = (err as any).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d: any) => (typeof d === 'string' ? d : d?.msg))
      .filter(Boolean);
    if (msgs.length) return msgs.join('; ');
  }
  if (typeof err.message === 'string') return err.message;
  try {
    return JSON.stringify(err);
  } catch {
    return fallback;
  }
}

export function useAvailability(): UseAvailabilityReturn {
  const {
    currentWeekStart,
    weekSchedule,
    savedWeekSchedule,
    hasUnsavedChanges,
    isLoading,
    existingSlots: _existingSlots,
    weekDates,
    message,
    navigateWeek,
    setWeekSchedule,
    setMessage,
    refreshSchedule,
    currentWeekDisplay,
    version,
    lastModified,
  } = useWeekSchedule();

  const saveWeek: UseAvailabilityReturn['saveWeek'] = useCallback(async (opts) => {
    const week_start = formatDateForAPI(currentWeekStart);
    // 1) Load authoritative server snapshot for the current week to avoid accidental drops
    let serverWeek: WeekSchedule = {};
    try {
      const res = await fetchWithAuth(`${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK}?start_date=${week_start}`);
      if (res.ok) {
        serverWeek = await res.json();
        const etag = res.headers.get('ETag') || undefined;
        if (typeof window !== 'undefined') (window as any).__week_version = etag || undefined;
      }
    } catch (e) {
      logger.warn('Could not load server week before save; proceeding with local snapshot');
    }

    // 2) Build a robust snapshot by overlaying local edits over server snapshot (and saved snapshot)
    const merged: WeekSchedule = { ...(serverWeek as any), ...(savedWeekSchedule as any), ...(weekSchedule as any) } as WeekSchedule;
    // Flatten into list of { date, start_time, end_time } per backend schema
    const schedule: Array<{ date: string; start_time: string; end_time: string }> = [];
    Object.entries(merged).forEach(([date, slots]) => {
      (slots || []).forEach((s: any) => {
        schedule.push({ date, start_time: s.start_time, end_time: s.end_time });
      });
    });

    logger.info('Saving weekly availability snapshot', {
      week_start,
      days: Object.keys(merged).length,
      total_slots: schedule.length,
    });

    try {
      const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          week_start,
          clear_existing: Boolean(opts?.clearExisting),
          schedule,
          version,
        }),
      });
      // Capture new version from response headers if present
      const newVersion = res.headers?.get?.('ETag') || undefined;
      if (newVersion) {
        logger.debug('Updated week version from POST', { newVersion });
      }
      if (!res.ok) {
        const status = (res as any).status;
        const err = await res.json().catch(() => ({} as any));
        return { success: false, message: extractErrorMessage(err, 'Failed to save availability'), code: status };
      }
      await refreshSchedule();
      return { success: true, message: 'Availability saved' };
    } catch (e) {
      logger.error('saveWeek error', e);
      return { success: false, message: 'Network error while saving' };
    }
  }, [currentWeekStart, weekSchedule, refreshSchedule]);

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
      return await res.json();
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
        const err = await res.json().catch(() => ({} as any));
        return { success: false, message: extractErrorMessage(err, 'Failed to copy week') };
      }
      await refreshSchedule();
      return { success: true, message: 'Copied previous week' };
    } catch (e) {
      logger.error('copyFromPreviousWeek error', e);
      return { success: false, message: 'Network error while copying' };
    }
  }, [currentWeekStart, refreshSchedule]);

  const applyToFutureWeeks: UseAvailabilityReturn['applyToFutureWeeks'] = useCallback(async (endISO) => {
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
      if (!res.ok) {
        const err = await res.json().catch(() => ({} as any));
        return { success: false, message: extractErrorMessage(err, 'Failed to apply to future weeks') };
      }
      return { success: true, message: 'Applied schedule to future range' };
    } catch (e) {
      logger.error('applyToFutureWeeks error', e);
      return { success: false, message: 'Network error while applying' };
    }
  }, [currentWeekStart]);

  return {
    currentWeekStart,
    weekSchedule,
    savedWeekSchedule,
    hasUnsavedChanges,
    isLoading,
    weekDates,
    message,
    navigateWeek,
    setWeekSchedule,
    setMessage,
    refreshSchedule,
    currentWeekDisplay,
    version,
    lastModified,
    saveWeek,
    validateWeek,
    copyFromPreviousWeek,
    applyToFutureWeeks,
  };
}
