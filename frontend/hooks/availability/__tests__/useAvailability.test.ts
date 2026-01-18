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
});
