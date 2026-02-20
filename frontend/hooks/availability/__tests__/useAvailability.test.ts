import { renderHook, act } from '@testing-library/react';
import { useAvailability } from '../useAvailability';
import type { WeekBits, WeekSchedule } from '@/types/availability';

// Type for operation results
type OperationResult = { success: boolean; message: string } | undefined;

// Mock the logger
jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
  },
}));

// Mock the API
jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(),
  API_ENDPOINTS: {
    INSTRUCTOR_AVAILABILITY_WEEK: '/api/v1/instructors/me/availability/week',
    INSTRUCTOR_AVAILABILITY_VALIDATE: '/api/v1/instructors/me/availability/validate',
    INSTRUCTOR_AVAILABILITY_COPY_WEEK: '/api/v1/instructors/me/availability/copy-week',
    INSTRUCTOR_AVAILABILITY_APPLY_RANGE: '/api/v1/instructors/me/availability/apply-range',
  },
}));

// Create mock week schedule state
const createMockWeekScheduleState = () => ({
  currentWeekStart: new Date('2025-01-13'),
  weekBits: {} as WeekBits,
  savedWeekBits: {} as WeekBits,
  weekSchedule: {} as WeekSchedule,
  savedWeekSchedule: {} as WeekSchedule,
  hasUnsavedChanges: false,
  isLoading: false,
  weekDates: [
    { date: new Date('2025-01-13'), day: 'Mon' },
    { date: new Date('2025-01-14'), day: 'Tue' },
    { date: new Date('2025-01-15'), day: 'Wed' },
    { date: new Date('2025-01-16'), day: 'Thu' },
    { date: new Date('2025-01-17'), day: 'Fri' },
    { date: new Date('2025-01-18'), day: 'Sat' },
    { date: new Date('2025-01-19'), day: 'Sun' },
  ],
  message: null,
  navigateWeek: jest.fn(),
  setWeekBits: jest.fn(),
  setSavedWeekBits: jest.fn(),
  setMessage: jest.fn(),
  refreshSchedule: jest.fn().mockResolvedValue(undefined),
  goToCurrentWeek: jest.fn(),
  currentWeekDisplay: 'Jan 13 - 19, 2025',
  version: 'v1',
  etag: 'etag-123',
  lastModified: '2025-01-13T00:00:00Z',
  setVersion: jest.fn(),
  allowPastEdits: false,
  setAllowPastEdits: jest.fn(),
});

let mockWeekScheduleState = createMockWeekScheduleState();

// Mock useWeekSchedule
jest.mock('@/hooks/availability/useWeekSchedule', () => ({
  useWeekSchedule: () => mockWeekScheduleState,
}));

// Mock date helpers
jest.mock('@/lib/availability/dateHelpers', () => ({
  formatDateForAPI: jest.fn((date: Date) => date.toISOString().split('T')[0]),
}));

// Mock bitset helpers
jest.mock('@/lib/calendar/bitset', () => ({
  fromWindows: jest.fn(() => new Uint8Array(6)),
  toWindows: jest.fn(() => []),
}));

const { fetchWithAuth } = jest.requireMock('@/lib/api');

describe('useAvailability', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockWeekScheduleState = createMockWeekScheduleState();
    // Reset window.__week_version
    if (typeof window !== 'undefined') {
      delete (window as Window & { __week_version?: string }).__week_version;
    }
  });

  describe('initialization', () => {
    it('returns state from useWeekSchedule', () => {
      const { result } = renderHook(() => useAvailability());

      expect(result.current.currentWeekStart).toEqual(new Date('2025-01-13'));
      expect(result.current.isLoading).toBe(false);
      expect(result.current.hasUnsavedChanges).toBe(false);
      expect(result.current.weekDates).toHaveLength(7);
    });

    it('exposes navigation functions', () => {
      const { result } = renderHook(() => useAvailability());

      expect(typeof result.current.navigateWeek).toBe('function');
      expect(typeof result.current.goToCurrentWeek).toBe('function');
      expect(typeof result.current.setWeekBits).toBe('function');
      expect(typeof result.current.setMessage).toBe('function');
    });

    it('exposes API orchestration functions', () => {
      const { result } = renderHook(() => useAvailability());

      expect(typeof result.current.saveWeek).toBe('function');
      expect(typeof result.current.validateWeek).toBe('function');
      expect(typeof result.current.copyFromPreviousWeek).toBe('function');
      expect(typeof result.current.applyToFutureWeeks).toBe('function');
    });
  });

  describe('saveWeek', () => {
    it('saves availability successfully', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: {
          get: (name: string) => (name === 'ETag' ? 'new-etag' : null),
        },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved successfully', version: 'v2' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; message: string };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult!.success).toBe(true);
      expect(saveResult!.message).toBe('Saved successfully');
      expect(fetchWithAuth).toHaveBeenCalledWith(
        '/api/v1/instructors/me/availability/week',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      );
    });

    it('handles version conflict (409)', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 409,
        headers: {
          get: (name: string) => (name === 'ETag' ? 'server-version' : null),
        },
        clone: () => ({
          json: () => Promise.resolve({ error: 'version_conflict', current_version: 'v3' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; message: string; code?: number };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult!.success).toBe(false);
      expect(saveResult!.code).toBe(409);
      expect(saveResult!.message).toContain('changed in another session');
    });

    it('handles network error', async () => {
      fetchWithAuth.mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; message: string };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult!.success).toBe(false);
      expect(saveResult!.message).toBe('Network error while saving');
    });

    it('handles API error with detail message', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ detail: 'Invalid schedule data' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; message: string };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult!.success).toBe(false);
      expect(saveResult!.message).toContain('Invalid schedule data');
    });

    it('uses schedule override when provided', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      const customSchedule: WeekSchedule = {
        '2025-01-15': [{ start_time: '09:00', end_time: '10:00' }],
      };

      await act(async () => {
        await result.current.saveWeek({ scheduleOverride: customSchedule });
      });

      expect(fetchWithAuth).toHaveBeenCalledWith(
        '/api/v1/instructors/me/availability/week',
        expect.objectContaining({
          body: expect.stringContaining('2025-01-15'),
        })
      );
    });

    it('sets clearExisting option correctly', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek({ clearExisting: false });
      });

      expect(fetchWithAuth).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: expect.stringContaining('"clear_existing":false'),
        })
      );
    });

    it('updates state after successful save', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: {
          get: (name: string) => (name === 'ETag' ? 'new-etag' : null),
        },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved', version: 'v2' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek();
      });

      expect(mockWeekScheduleState.setVersion).toHaveBeenCalled();
      expect(mockWeekScheduleState.setWeekBits).toHaveBeenCalled();
      expect(mockWeekScheduleState.setSavedWeekBits).toHaveBeenCalled();
    });
  });

  describe('validateWeek', () => {
    it('returns validation response on success', async () => {
      const validationResponse = {
        valid: true,
        conflicts: [],
        warnings: [],
      };

      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(validationResponse),
      });

      const { result } = renderHook(() => useAvailability());

      let validation;
      await act(async () => {
        validation = await result.current.validateWeek();
      });

      expect(validation).toEqual(validationResponse);
    });

    it('returns null on API failure', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        json: () => Promise.resolve({ error: 'Server error' }),
      });

      const { result } = renderHook(() => useAvailability());

      let validation;
      await act(async () => {
        validation = await result.current.validateWeek();
      });

      expect(validation).toBeNull();
    });

    it('returns null on network error', async () => {
      fetchWithAuth.mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(() => useAvailability());

      let validation;
      await act(async () => {
        validation = await result.current.validateWeek();
      });

      expect(validation).toBeNull();
    });
  });

  describe('copyFromPreviousWeek', () => {
    it('copies from previous week successfully', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ message: 'Week copied successfully' }),
      });

      const { result } = renderHook(() => useAvailability());

      let copyResult: OperationResult;
      await act(async () => {
        copyResult = await result.current.copyFromPreviousWeek();
      });

      expect(copyResult).toEqual({
        success: true,
        message: 'Week copied successfully',
      });
      expect(mockWeekScheduleState.refreshSchedule).toHaveBeenCalled();
    });

    it('handles copy failure', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        json: () => Promise.resolve({ detail: 'No availability in previous week' }),
      });

      const { result } = renderHook(() => useAvailability());

      let copyResult: OperationResult;
      await act(async () => {
        copyResult = await result.current.copyFromPreviousWeek();
      });

      expect(copyResult?.success).toBe(false);
      expect(copyResult?.message).toContain('No availability in previous week');
    });

    it('handles network error', async () => {
      fetchWithAuth.mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(() => useAvailability());

      let copyResult: OperationResult;
      await act(async () => {
        copyResult = await result.current.copyFromPreviousWeek();
      });

      expect(copyResult).toEqual({
        success: false,
        message: 'Network error while copying',
      });
    });

    it('sends correct date parameters', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ message: 'Copied' }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.copyFromPreviousWeek();
      });

      expect(fetchWithAuth).toHaveBeenCalledWith(
        '/api/v1/instructors/me/availability/copy-week',
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('from_week_start'),
        })
      );
    });
  });

  describe('applyToFutureWeeks', () => {
    it('applies to future weeks successfully', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        clone: () => ({
          json: () =>
            Promise.resolve({
              message: 'Applied to 12 weeks',
              weeks_affected: 12,
              days_written: 84,
            }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let applyResult: OperationResult;
      await act(async () => {
        applyResult = await result.current.applyToFutureWeeks('2025-04-15');
      });

      expect(applyResult).toEqual({
        success: true,
        message: 'Applied to 12 weeks',
        weeksAffected: 12,
        daysWritten: 84,
      });
    });

    it('handles apply failure', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        clone: () => ({
          json: () => Promise.resolve({ detail: 'Invalid date range' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let applyResult: OperationResult;
      await act(async () => {
        applyResult = await result.current.applyToFutureWeeks('2025-04-15');
      });

      expect(applyResult?.success).toBe(false);
      expect(applyResult?.message).toContain('Invalid date range');
    });

    it('handles network error', async () => {
      fetchWithAuth.mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(() => useAvailability());

      let applyResult: OperationResult;
      await act(async () => {
        applyResult = await result.current.applyToFutureWeeks('2025-04-15');
      });

      expect(applyResult).toEqual({
        success: false,
        message: 'Network error while applying',
      });
    });

    it('sends correct parameters', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        clone: () => ({
          json: () => Promise.resolve({ message: 'Applied' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.applyToFutureWeeks('2025-12-31');
      });

      expect(fetchWithAuth).toHaveBeenCalledWith(
        '/api/v1/instructors/me/availability/apply-range',
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('2025-12-31'),
        })
      );
    });
  });

  describe('navigation', () => {
    it('calls navigateWeek with correct direction', () => {
      const { result } = renderHook(() => useAvailability());

      result.current.navigateWeek('next');
      expect(mockWeekScheduleState.navigateWeek).toHaveBeenCalledWith('next');

      result.current.navigateWeek('prev');
      expect(mockWeekScheduleState.navigateWeek).toHaveBeenCalledWith('prev');
    });

    it('calls goToCurrentWeek', () => {
      const { result } = renderHook(() => useAvailability());

      result.current.goToCurrentWeek();
      expect(mockWeekScheduleState.goToCurrentWeek).toHaveBeenCalled();
    });
  });

  describe('error message extraction', () => {
    it('extracts detail string from error response', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ detail: 'Specific error message' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: OperationResult;
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult?.message).toContain('Specific error message');
    });

    it('extracts detail array from error response', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: { get: () => null },
        clone: () => ({
          json: () =>
            Promise.resolve({
              detail: [{ msg: 'Error 1' }, { msg: 'Error 2' }],
            }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: OperationResult;
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult?.message).toContain('Error 1');
      expect(saveResult?.message).toContain('Error 2');
    });

    it('extracts message field from error response', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 500,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Server error occurred' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: OperationResult;
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult?.message).toContain('Server error occurred');
    });

    it('stringifies error when no standard fields present', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 500,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ code: 'UNKNOWN_ERROR', data: { foo: 'bar' } }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: OperationResult;
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult?.message).toContain('UNKNOWN_ERROR');
    });

    it('uses fallback when error is null or undefined', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 500,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve(null),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: OperationResult;
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult?.message).toContain('Failed to save availability');
    });
  });

  describe('allowPastEdits header handling', () => {
    it('sets allowPastEdits to true when X-Allow-Past header is "1"', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: {
          get: (name: string) => (name === 'X-Allow-Past' ? '1' : null),
        },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek();
      });

      expect(mockWeekScheduleState.setAllowPastEdits).toHaveBeenCalledWith(true);
    });

    it('sets allowPastEdits to true when X-Allow-Past header is "true"', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: {
          get: (name: string) => (name === 'X-Allow-Past' ? 'true' : null),
        },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek();
      });

      expect(mockWeekScheduleState.setAllowPastEdits).toHaveBeenCalledWith(true);
    });

    it('sets allowPastEdits to false for other header values', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: {
          get: (name: string) => (name === 'X-Allow-Past' ? 'false' : null),
        },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek();
      });

      expect(mockWeekScheduleState.setAllowPastEdits).toHaveBeenCalledWith(false);
    });

    it('handles X-Allow-Past header on error response', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: {
          get: (name: string) => (name === 'X-Allow-Past' ? 'yes' : null),
        },
        clone: () => ({
          json: () => Promise.resolve({ detail: 'Error' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek();
      });

      expect(mockWeekScheduleState.setAllowPastEdits).toHaveBeenCalledWith(true);
    });
  });

  describe('override option in saveWeek', () => {
    it('sets override flag when passed in options', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek({ override: true });
      });

      expect(fetchWithAuth).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: expect.stringContaining('"override":true'),
        })
      );
    });

    it('defaults override to false when not specified', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek();
      });

      expect(fetchWithAuth).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: expect.stringContaining('"override":false'),
        })
      );
    });
  });

  describe('version management', () => {
    it('updates window.__week_version on successful save', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: {
          get: (name: string) => (name === 'ETag' ? 'new-version-123' : null),
        },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek();
      });

      expect((window as Window & { __week_version?: string }).__week_version).toBe('new-version-123');
    });

    it('uses stored window version as If-Match header', async () => {
      (window as Window & { __week_version?: string }).__week_version = 'stored-version';

      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek();
      });

      expect(fetchWithAuth).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'If-Match': 'stored-version',
          }),
        })
      );
    });

    it('updates version on conflict response', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 409,
        headers: {
          get: (name: string) => (name === 'ETag' ? 'conflict-version' : null),
        },
        clone: () => ({
          json: () => Promise.resolve({ error: 'version_conflict', current_version: 'server-v2' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: OperationResult;
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult?.success).toBe(false);
      expect(mockWeekScheduleState.setVersion).toHaveBeenCalled();
    });

    it('returns serverVersion on conflict', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 409,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ error: 'version_conflict', current_version: 'server-v3' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; serverVersion?: string };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult!.serverVersion).toBe('server-v3');
    });
  });

  describe('applyToFutureWeeks edge cases', () => {
    it('returns success without weeksAffected/daysWritten when not in response', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        clone: () => ({
          json: () => Promise.resolve({ message: 'Applied successfully' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let applyResult: OperationResult;
      await act(async () => {
        applyResult = await result.current.applyToFutureWeeks('2025-04-15');
      });

      expect(applyResult).toEqual({
        success: true,
        message: 'Applied successfully',
      });
    });

    it('falls back to default message when response has no message', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        clone: () => ({
          json: () => Promise.resolve({}),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let applyResult: OperationResult;
      await act(async () => {
        applyResult = await result.current.applyToFutureWeeks('2025-04-15');
      });

      expect(applyResult?.message).toBe('Applied schedule to future range');
    });

    it('includes only weeksAffected when daysWritten is not present', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        clone: () => ({
          json: () => Promise.resolve({
            message: 'Applied',
            weeks_affected: 5,
          }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let applyResult: { success: boolean; weeksAffected?: number; daysWritten?: number };
      await act(async () => {
        applyResult = await result.current.applyToFutureWeeks('2025-04-15');
      });

      expect(applyResult!.weeksAffected).toBe(5);
      expect(applyResult!.daysWritten).toBeUndefined();
    });

    it('handles null JSON response from clone', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        clone: () => ({
          json: () => Promise.resolve(undefined),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let applyResult: OperationResult;
      await act(async () => {
        applyResult = await result.current.applyToFutureWeeks('2025-04-15');
      });

      expect(applyResult?.success).toBe(true);
    });
  });

  describe('saveWeek version resolution', () => {
    it('uses week_version from response body when ETag is absent', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved', week_version: 'wv-42' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; version?: string; weekVersion?: string };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult!.version).toBe('wv-42');
      expect(saveResult!.weekVersion).toBe('wv-42');
      expect(mockWeekScheduleState.setVersion).toHaveBeenCalledWith('wv-42');
    });

    it('uses response.version when week_version and ETag are absent', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved', version: 'resp-v3' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; version?: string };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult!.version).toBe('resp-v3');
    });

    it('handles response with no version information at all', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; version?: string };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult!.success).toBe(true);
      expect(saveResult!.version).toBeUndefined();
    });

    it('falls back to etag as If-Match when window.__week_version is not set', async () => {
      // etag is set via mock state but window.__week_version is not
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek();
      });

      expect(fetchWithAuth).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'If-Match': 'etag-123',
          }),
        })
      );
    });
  });

  describe('copyFromPreviousWeek edge cases', () => {
    it('handles null JSON response gracefully', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(null),
      });

      const { result } = renderHook(() => useAvailability());

      let copyResult: OperationResult;
      await act(async () => {
        copyResult = await result.current.copyFromPreviousWeek();
      });

      expect(copyResult?.success).toBe(true);
      expect(copyResult?.message).toBe('Copied previous week');
    });

    it('handles error response with array of messages', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        json: () => Promise.resolve({ detail: ['Error one', 'Error two'] }),
      });

      const { result } = renderHook(() => useAvailability());

      let copyResult: OperationResult;
      await act(async () => {
        copyResult = await result.current.copyFromPreviousWeek();
      });

      expect(copyResult?.success).toBe(false);
      expect(copyResult?.message).toContain('Error one');
      expect(copyResult?.message).toContain('Error two');
    });
  });

  describe('extractErrorMessage edge cases', () => {
    it('handles error response with non-stringifiable circular reference', async () => {
      // When JSON.stringify throws, extractErrorMessage should return the fallback
      const circularObj: Record<string, unknown> = {};
      circularObj['self'] = circularObj;

      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 500,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve(circularObj),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: OperationResult;
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult?.success).toBe(false);
      // Should use fallback message since JSON.stringify would throw
      expect(saveResult?.message).toContain('Failed to save availability');
    });

    it('handles error with detail array containing objects with msg field', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 422,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({
            detail: [
              { msg: 'field required', loc: ['body', 'name'] },
              { msg: 'invalid format', loc: ['body', 'email'] },
            ],
          }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: OperationResult;
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult?.message).toContain('field required');
      expect(saveResult?.message).toContain('invalid format');
    });

    it('handles error with detail array containing empty entries', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 422,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({
            detail: [null, '', { msg: 'only valid' }],
          }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: OperationResult;
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult?.message).toContain('only valid');
    });
  });

  describe('weekDates transformation', () => {
    it('maps weekDates info objects to Date objects', () => {
      const { result } = renderHook(() => useAvailability());

      expect(result.current.weekDates).toHaveLength(7);
      expect(result.current.weekDates[0]).toEqual(new Date('2025-01-13'));
    });
  });

  describe('optional fields in return value', () => {
    it('includes version when present', () => {
      mockWeekScheduleState.version = 'v1';
      const { result } = renderHook(() => useAvailability());
      expect(result.current.version).toBe('v1');
    });

    it('includes etag when present', () => {
      mockWeekScheduleState.etag = 'etag-abc';
      const { result } = renderHook(() => useAvailability());
      expect(result.current.etag).toBe('etag-abc');
    });

    it('includes lastModified when present', () => {
      mockWeekScheduleState.lastModified = '2025-01-13T00:00:00Z';
      const { result } = renderHook(() => useAvailability());
      expect(result.current.lastModified).toBe('2025-01-13T00:00:00Z');
    });

    it('includes allowPastEdits when defined', () => {
      mockWeekScheduleState.allowPastEdits = true;
      const { result } = renderHook(() => useAvailability());
      expect(result.current.allowPastEdits).toBe(true);
    });
  });

  describe('409 version conflict edge cases', () => {
    it('uses current_version from response body over ETag when both present', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 409,
        headers: {
          get: (name: string) => (name === 'ETag' ? 'etag-version' : null),
        },
        clone: () => ({
          json: () => Promise.resolve({ error: 'version_conflict', current_version: 'body-version' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; serverVersion?: string };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult!.success).toBe(false);
      expect(saveResult!.serverVersion).toBe('body-version');
      expect(mockWeekScheduleState.setVersion).toHaveBeenCalledWith('body-version');
      expect(
        (window as Window & { __week_version?: string }).__week_version
      ).toBe('body-version');
    });

    it('falls back to ETag when current_version is not a string', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 409,
        headers: {
          get: (name: string) => (name === 'ETag' ? 'etag-fallback' : null),
        },
        clone: () => ({
          json: () => Promise.resolve({ error: 'version_conflict', current_version: 42 }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; serverVersion?: string };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult!.success).toBe(false);
      expect(saveResult!.serverVersion).toBe('etag-fallback');
      expect(mockWeekScheduleState.setVersion).toHaveBeenCalledWith('etag-fallback');
    });

    it('does not update version when neither current_version nor ETag is present', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 409,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ error: 'version_conflict' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek();
      });

      expect(mockWeekScheduleState.setVersion).not.toHaveBeenCalled();
    });

    it('detects version conflict via error field even when status is not 409', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ error: 'version_conflict', current_version: 'sv5' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; message: string };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      // version_conflict error field triggers the special message
      expect(saveResult!.message).toContain('changed in another session');
    });
  });

  describe('optional fields omitted from return when empty', () => {
    it('omits version when undefined', () => {
      mockWeekScheduleState.version = undefined as unknown as string;
      mockWeekScheduleState.etag = undefined as unknown as string;
      mockWeekScheduleState.lastModified = undefined as unknown as string;
      mockWeekScheduleState.allowPastEdits = undefined as unknown as boolean;

      const { result } = renderHook(() => useAvailability());

      expect(result.current.version).toBeUndefined();
      expect(result.current.etag).toBeUndefined();
      expect(result.current.lastModified).toBeUndefined();
      expect(result.current.allowPastEdits).toBeUndefined();
    });

    it('omits version and etag when empty string (falsy)', () => {
      mockWeekScheduleState.version = '';
      mockWeekScheduleState.etag = '';
      mockWeekScheduleState.lastModified = '';

      const { result } = renderHook(() => useAvailability());

      // Empty strings are falsy, so the spread doesn't include them
      expect(result.current.version).toBeUndefined();
      expect(result.current.etag).toBeUndefined();
      expect(result.current.lastModified).toBeUndefined();
    });
  });

  describe('computeBitsDelta edge cases', () => {
    it('handles dates present only in previous (all removed)', async () => {
      const prevBits = new Uint8Array([0b11111111, 0, 0, 0, 0, 0]);
      mockWeekScheduleState.savedWeekBits = { '2025-01-13': prevBits } as unknown as WeekBits;
      // Next has no bits at all - everything was removed
      mockWeekScheduleState.weekBits = {} as WeekBits;

      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; message: string };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult!.success).toBe(true);
      // The debug log should show removed bits
      const { logger } = jest.requireMock('@/lib/logger');
      expect(logger.debug).toHaveBeenCalledWith(
        expect.stringContaining('bitsDelta')
      );
    });

    it('handles dates present only in next (all added)', async () => {
      mockWeekScheduleState.savedWeekBits = {} as WeekBits;
      const nextBits = new Uint8Array([0b00001111, 0, 0, 0, 0, 0]);
      mockWeekScheduleState.weekBits = { '2025-01-13': nextBits } as unknown as WeekBits;

      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; message: string };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult!.success).toBe(true);
    });
  });

  describe('saveWeek with non-empty weekBits', () => {
    it('computes bits delta and logs it', async () => {
      const bits = new Uint8Array([0b11110000, 0, 0, 0, 0, 0]);
      const savedBits = new Uint8Array([0b00001111, 0, 0, 0, 0, 0]);
      mockWeekScheduleState.weekBits = { '2025-01-13': bits } as unknown as WeekBits;
      mockWeekScheduleState.savedWeekBits = { '2025-01-13': savedBits } as unknown as WeekBits;

      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; message: string };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult!.success).toBe(true);
      // The logger.debug should have been called with bits delta info
      const { logger } = jest.requireMock('@/lib/logger');
      expect(logger.debug).toHaveBeenCalledWith(
        expect.stringContaining('bitsDelta')
      );
    });
  });

  describe('saveWeek JSON parse failure', () => {
    it('handles clone().json() throwing gracefully', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.reject(new Error('Malformed JSON')),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; message: string };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      // responseJson will be undefined due to .catch(() => undefined)
      // The fallback message 'Availability saved' should be used
      expect(saveResult!.success).toBe(true);
      expect(saveResult!.message).toBe('Availability saved');
    });

    it('handles clone().json() throwing on error response', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 500,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.reject(new Error('Malformed JSON')),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; message: string };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      // responseJson is undefined, extractErrorMessage receives undefined -> fallback
      expect(saveResult!.success).toBe(false);
      expect(saveResult!.message).toContain('Failed to save availability');
    });
  });

  describe('applyToFutureWeeks partial stats', () => {
    it('includes only daysWritten when weeksAffected is not present', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        clone: () => ({
          json: () => Promise.resolve({
            message: 'Applied',
            days_written: 42,
          }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let applyResult: { success: boolean; weeksAffected?: number; daysWritten?: number };
      await act(async () => {
        applyResult = await result.current.applyToFutureWeeks('2025-06-30');
      });

      expect(applyResult!.daysWritten).toBe(42);
      expect(applyResult!.weeksAffected).toBeUndefined();
    });

    it('handles non-numeric weeks_affected gracefully', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        clone: () => ({
          json: () => Promise.resolve({
            message: 'Applied',
            weeks_affected: 'many',
            days_written: 10,
          }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let applyResult: { success: boolean; weeksAffected?: number; daysWritten?: number };
      await act(async () => {
        applyResult = await result.current.applyToFutureWeeks('2025-06-30');
      });

      // 'many' is not a number, so weeksAffected should be undefined
      expect(applyResult!.weeksAffected).toBeUndefined();
      expect(applyResult!.daysWritten).toBe(10);
    });

    it('handles clone().json() throwing in applyToFutureWeeks', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        clone: () => ({
          json: () => Promise.reject(new Error('Parse error')),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let applyResult: { success: boolean; message: string };
      await act(async () => {
        applyResult = await result.current.applyToFutureWeeks('2025-06-30');
      });

      // responseJson is undefined, falls back to default message
      expect(applyResult!.success).toBe(true);
      expect(applyResult!.message).toBe('Applied schedule to future range');
    });
  });

  describe('copyFromPreviousWeek JSON error on failure path', () => {
    it('stringifies empty object when error response JSON parse fails', async () => {
      // When res.json() rejects, the .catch returns {} as ApiErrorResponse.
      // extractErrorMessage({}, fallback) has no detail or message field,
      // so it falls through to JSON.stringify({}) which returns "{}".
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        json: () => Promise.reject(new Error('Parse error')),
      });

      const { result } = renderHook(() => useAvailability());

      let copyResult: OperationResult;
      await act(async () => {
        copyResult = await result.current.copyFromPreviousWeek();
      });

      expect(copyResult?.success).toBe(false);
      expect(copyResult?.message).toBe('{}');
    });
  });

  describe('saveWeek clearExisting default behavior', () => {
    it('defaults clearExisting to true when not specified', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek();
      });

      expect(fetchWithAuth).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: expect.stringContaining('"clear_existing":true'),
        })
      );
    });
  });

  describe('allowPastEdits header on non-409 error response', () => {
    it('does not set allowPastEdits when X-Allow-Past header is null on error', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ detail: 'Some error' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek();
      });

      // When allowPastHeader is null (not a string), setAllowPastEdits should NOT be called
      expect(mockWeekScheduleState.setAllowPastEdits).not.toHaveBeenCalled();
    });

    it('does not set allowPastEdits when X-Allow-Past header is null on success', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek();
      });

      expect(mockWeekScheduleState.setAllowPastEdits).not.toHaveBeenCalled();
    });
  });

  describe('extractErrorMessage — empty detail array with only non-message entries', () => {
    it('falls through to JSON.stringify when detail array has no valid entries', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 422,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({
            // All entries filter to empty because they have no string value and no msg field
            detail: [{ code: 1 }, { loc: ['x'] }, { type: 'error' }],
          }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: OperationResult;
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      // msgs.length is 0, so falls through to JSON.stringify
      expect(saveResult?.message).toContain('detail');
    });

    it('handles empty detail array that filters to zero valid entries', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 422,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ detail: [] }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: OperationResult;
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      // Empty array -> msgs.length is 0 -> falls through to message check -> JSON.stringify
      expect(saveResult?.message).toContain('detail');
    });
  });

  describe('saveWeek — schedule slots with null/empty windows', () => {
    it('handles null slot entries in schedule source gracefully', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      // Schedule with a date that has a falsy/undefined slots value
      const customSchedule: WeekSchedule = {
        '2025-01-15': [{ start_time: '09:00', end_time: '10:00' }],
      };
      // Manually add a date with undefined slots to exercise the `|| []` guard
      (customSchedule as Record<string, unknown>)['2025-01-16'] = undefined;

      await act(async () => {
        await result.current.saveWeek({ scheduleOverride: customSchedule });
      });

      const body = JSON.parse(
        (fetchWithAuth.mock.calls[0] as [string, { body: string }])[1].body
      ) as { schedule: Array<{ date: string }> };

      // Only '2025-01-15' should have entries since '2025-01-16' has undefined slots
      expect(body.schedule.every((s) => s.date === '2025-01-15')).toBe(true);
    });
  });

  describe('saveWeek — allowPastEdits on error with non-truthy value', () => {
    it('sets allowPastEdits to false for X-Allow-Past "no" on error response', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: {
          get: (name: string) => (name === 'X-Allow-Past' ? 'no' : null),
        },
        clone: () => ({
          json: () => Promise.resolve({ detail: 'Error' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek();
      });

      expect(mockWeekScheduleState.setAllowPastEdits).toHaveBeenCalledWith(false);
    });
  });

  describe('saveWeek — no version on conflict when both serverVersion and etag are null', () => {
    it('does not set serverVersion in result when no version sources are available', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ detail: 'Bad request' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; serverVersion?: string };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      // No serverVersion should be in the result
      expect(saveResult!.serverVersion).toBeUndefined();
      // setVersion should NOT have been called
      expect(mockWeekScheduleState.setVersion).not.toHaveBeenCalled();
    });
  });

  describe('saveWeek — non-409 non-version-conflict error', () => {
    it('returns generic error message for regular API errors', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: false,
        status: 500,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ detail: 'Internal error' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      let saveResult: { success: boolean; message: string; code?: number };
      await act(async () => {
        saveResult = await result.current.saveWeek();
      });

      expect(saveResult!.success).toBe(false);
      expect(saveResult!.code).toBe(500);
      expect(saveResult!.message).toContain('Internal error');
      // Should NOT contain the version conflict message
      expect(saveResult!.message).not.toContain('changed in another session');
    });
  });

  describe('saveWeek with scheduleOverride triggers scheduleToBits', () => {
    it('converts schedule override to bits and back', async () => {
      const { fromWindows, toWindows } = jest.requireMock('@/lib/calendar/bitset');
      const mockBits = new Uint8Array([1, 2, 3, 4, 5, 6]);
      fromWindows.mockReturnValue(mockBits);
      toWindows.mockReturnValue([{ start_time: '09:00', end_time: '17:00' }]);

      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      const customSchedule: WeekSchedule = {
        '2025-01-15': [{ start_time: '09:00', end_time: '17:00' }],
      };

      await act(async () => {
        await result.current.saveWeek({ scheduleOverride: customSchedule });
      });

      // fromWindows should be called to convert schedule to bits
      expect(fromWindows).toHaveBeenCalledWith([{ start_time: '09:00', end_time: '17:00' }]);
      expect(fetchWithAuth).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: expect.stringContaining('"date":"2025-01-15"'),
        })
      );
    });

    it('skips dates with empty or null windows in scheduleOverride', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      const customSchedule: WeekSchedule = {
        '2025-01-15': [{ start_time: '09:00', end_time: '10:00' }],
        '2025-01-16': [],
      };

      await act(async () => {
        await result.current.saveWeek({ scheduleOverride: customSchedule });
      });

      const body = JSON.parse(
        (fetchWithAuth.mock.calls[0] as [string, { body: string }])[1].body
      ) as { schedule: Array<{ date: string }> };

      // Only the date with actual slots should be in the schedule
      expect(body.schedule).toHaveLength(1);
      expect(body.schedule[0]?.date).toBe('2025-01-15');
    });
  });

  describe('bitsRecordToSchedule', () => {
    it('excludes days where toWindows returns empty array from the schedule', async () => {
      const { toWindows } = jest.requireMock<{ toWindows: jest.Mock }>('@/lib/calendar/bitset');
      // Day 1 has windows, Day 2 has bits set but toWindows returns [] (bug-hunting edge case)
      const bitsDay1 = new Uint8Array([0b00000011, 0, 0, 0, 0, 0]);
      const bitsDay2 = new Uint8Array([0b11000000, 0, 0, 0, 0, 0]);
      mockWeekScheduleState.weekBits = {
        '2025-01-13': bitsDay1,
        '2025-01-14': bitsDay2,
      } as unknown as WeekBits;

      // toWindows returns slots for first call, empty for second
      toWindows
        .mockReturnValueOnce([{ start_time: '09:00', end_time: '10:00' }])
        .mockReturnValueOnce([]);

      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek();
      });

      const body = JSON.parse(
        (fetchWithAuth.mock.calls[0] as [string, { body: string }])[1].body
      ) as { schedule: Array<{ date: string }> };

      // Only day 1 should appear because day 2 had empty windows from toWindows
      expect(body.schedule).toHaveLength(1);
      expect(body.schedule[0]?.date).toBe('2025-01-13');
    });

    it('includes all days that have non-empty windows from toWindows', async () => {
      const { toWindows } = jest.requireMock<{ toWindows: jest.Mock }>('@/lib/calendar/bitset');
      const bits = new Uint8Array([0b00000001, 0, 0, 0, 0, 0]);
      mockWeekScheduleState.weekBits = {
        '2025-01-13': bits,
        '2025-01-14': bits,
        '2025-01-15': bits,
      } as unknown as WeekBits;

      toWindows
        .mockReturnValueOnce([{ start_time: '08:00', end_time: '08:30' }])
        .mockReturnValueOnce([{ start_time: '09:00', end_time: '09:30' }])
        .mockReturnValueOnce([{ start_time: '10:00', end_time: '10:30' }]);

      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      await act(async () => {
        await result.current.saveWeek();
      });

      const body = JSON.parse(
        (fetchWithAuth.mock.calls[0] as [string, { body: string }])[1].body
      ) as { schedule: Array<{ date: string }> };

      expect(body.schedule).toHaveLength(3);
    });
  });

  describe('saveWeek schedule sorting', () => {
    it('sorts schedule entries by date then start_time then end_time', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      const customSchedule: WeekSchedule = {
        '2025-01-16': [{ start_time: '14:00', end_time: '15:00' }],
        '2025-01-15': [
          { start_time: '10:00', end_time: '12:00' },
          { start_time: '09:00', end_time: '10:00' },
        ],
      };

      await act(async () => {
        await result.current.saveWeek({ scheduleOverride: customSchedule });
      });

      const body = JSON.parse(
        (fetchWithAuth.mock.calls[0] as [string, { body: string }])[1].body
      ) as { schedule: Array<{ date: string; start_time: string; end_time: string }> };

      // Should be sorted: first by date, then by start_time
      expect(body.schedule[0]?.date).toBe('2025-01-15');
      expect(body.schedule[0]?.start_time).toBe('09:00');
      expect(body.schedule[1]?.date).toBe('2025-01-15');
      expect(body.schedule[1]?.start_time).toBe('10:00');
      expect(body.schedule[2]?.date).toBe('2025-01-16');
    });

    it('breaks ties on end_time when date and start_time are identical', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      // Two slots on same date with same start_time but different end_times
      const customSchedule: WeekSchedule = {
        '2025-01-15': [
          { start_time: '09:00', end_time: '11:00' },
          { start_time: '09:00', end_time: '10:00' },
        ],
      };

      await act(async () => {
        await result.current.saveWeek({ scheduleOverride: customSchedule });
      });

      const body = JSON.parse(
        (fetchWithAuth.mock.calls[0] as [string, { body: string }])[1].body
      ) as { schedule: Array<{ date: string; start_time: string; end_time: string }> };

      // end_time '10:00' should sort before '11:00' via localeCompare
      expect(body.schedule[0]?.end_time).toBe('10:00');
      expect(body.schedule[1]?.end_time).toBe('11:00');
    });

    it('handles schedule with entries across many dates in reverse order', async () => {
      fetchWithAuth.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        clone: () => ({
          json: () => Promise.resolve({ message: 'Saved' }),
        }),
      });

      const { result } = renderHook(() => useAvailability());

      // Dates intentionally out of order to verify localeCompare sorts ISO dates correctly
      const customSchedule: WeekSchedule = {
        '2025-01-19': [{ start_time: '09:00', end_time: '10:00' }],
        '2025-01-13': [{ start_time: '09:00', end_time: '10:00' }],
        '2025-01-17': [{ start_time: '09:00', end_time: '10:00' }],
      };

      await act(async () => {
        await result.current.saveWeek({ scheduleOverride: customSchedule });
      });

      const body = JSON.parse(
        (fetchWithAuth.mock.calls[0] as [string, { body: string }])[1].body
      ) as { schedule: Array<{ date: string }> };

      expect(body.schedule[0]?.date).toBe('2025-01-13');
      expect(body.schedule[1]?.date).toBe('2025-01-17');
      expect(body.schedule[2]?.date).toBe('2025-01-19');
    });
  });
});
