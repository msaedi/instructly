import { renderHook, act } from '@testing-library/react';
import { useWeekSchedule } from '@/hooks/availability/useWeekSchedule';

// Mock logger to reduce console noise
jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    time: jest.fn(),
    timeEnd: jest.fn(),
  },
}));

const mockFetchWithAuth = jest.fn();

// Basic mock for fetchWithAuth via jest module factory if needed
jest.mock('@/lib/api', () => {
  const original = jest.requireActual('@/lib/api');
  return {
    ...original,
    fetchWithAuth: (...args: Parameters<typeof mockFetchWithAuth>) => mockFetchWithAuth(...args),
  };
});

// Mock date helpers
jest.mock('@/lib/availability/dateHelpers', () => {
  const original = jest.requireActual('@/lib/availability/dateHelpers');
  return {
    ...original,
    getCurrentWeekStart: jest.fn((date?: Date) => {
      const d = date ? new Date(date) : new Date('2030-01-07');
      const day = d.getDay();
      const diff = d.getDate() - day + (day === 0 ? -6 : 1);
      return new Date(d.setDate(diff));
    }),
    getWeekDates: jest.fn((startDate: Date) => {
      const dates = [];
      for (let i = 0; i < 7; i++) {
        const date = new Date(startDate);
        date.setDate(date.getDate() + i);
        dates.push({
          date,
          dateStr: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
          dayOfWeek: date.toLocaleDateString('en-US', { weekday: 'short' }).toLowerCase(),
          fullDate: date.toISOString().slice(0, 10),
        });
      }
      return dates;
    }),
    formatDateForAPI: jest.fn((date: Date) => date.toISOString().slice(0, 10)),
    getPreviousMonday: jest.fn((date: Date) => {
      const d = new Date(date);
      d.setDate(d.getDate() - 7);
      return d;
    }),
    getNextMonday: jest.fn((date: Date) => {
      const d = new Date(date);
      d.setDate(d.getDate() + 7);
      return d;
    }),
  };
});

describe('useWeekSchedule', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchWithAuth.mockImplementation(async (url: string) => {
      if (url.includes('/api/v1/instructors/availability/week')) {
        return {
          ok: true,
          json: async () => ({}),
          headers: {
            get: (name: string) => {
              if (name === 'ETag') return 'abc123';
              if (name === 'Last-Modified') return new Date('2025-08-24T12:00:00Z').toUTCString();
              if (name === 'X-Allow-Past') return null;
              return null;
            },
          },
        } as Partial<Response> as Response;
      }
      return { ok: true, json: async () => ({}) } as Partial<Response> as Response;
    });
  });

  describe('version threading', () => {
    it('captures ETag as version and Last-Modified from headers', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      expect(result.current.version).toBe('abc123');
      expect(result.current.lastModified).toBeDefined();
    });
  });

  describe('week navigation', () => {
    it('navigates to next week', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      const initialWeekStart = result.current.currentWeekStart;

      await act(async () => {
        result.current.navigateWeek('next');
        await new Promise((r) => setTimeout(r, 0));
      });

      expect(result.current.currentWeekStart.getTime()).toBeGreaterThan(initialWeekStart.getTime());
    });

    it('navigates to previous week', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      const initialWeekStart = result.current.currentWeekStart;

      await act(async () => {
        result.current.navigateWeek('prev');
        await new Promise((r) => setTimeout(r, 0));
      });

      expect(result.current.currentWeekStart.getTime()).toBeLessThan(initialWeekStart.getTime());
    });

    it('goes to current week', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      // Navigate away first
      await act(async () => {
        result.current.navigateWeek('next');
        await new Promise((r) => setTimeout(r, 0));
      });

      await act(async () => {
        result.current.goToCurrentWeek();
        await new Promise((r) => setTimeout(r, 0));
      });

      expect(result.current.currentWeekStart).toBeDefined();
    });
  });

  describe('unsaved changes detection', () => {
    it('starts with no unsaved changes', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      expect(result.current.hasUnsavedChanges).toBe(false);
    });

    it('detects unsaved changes when week bits modified', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      await act(async () => {
        result.current.setWeekBits({ '2030-01-07': new Uint8Array([1, 0, 0]) });
      });

      expect(result.current.hasUnsavedChanges).toBe(true);
    });
  });

  describe('message handling', () => {
    it('sets and clears messages', async () => {
      const { result } = renderHook(() => useWeekSchedule({ messageTimeout: 100 }));

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      await act(async () => {
        result.current.setMessage({ type: 'success', text: 'Test message' });
      });

      expect(result.current.message).toEqual({ type: 'success', text: 'Test message' });

      // Wait for timeout
      await act(async () => {
        await new Promise((r) => setTimeout(r, 150));
      });

      expect(result.current.message).toBeNull();
    });

    it('can manually clear message', async () => {
      const { result } = renderHook(() => useWeekSchedule({ messageTimeout: 10000 }));

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      await act(async () => {
        result.current.setMessage({ type: 'error', text: 'Error' });
      });

      expect(result.current.message).not.toBeNull();

      await act(async () => {
        result.current.setMessage(null);
      });

      expect(result.current.message).toBeNull();
    });
  });

  describe('isDateInPast', () => {
    it('returns true for past dates', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      expect(result.current.isDateInPast('2020-01-01')).toBe(true);
    });

    it('returns false for future dates', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      expect(result.current.isDateInPast('2050-01-01')).toBe(false);
    });
  });

  describe('API error handling', () => {
    it('handles API errors gracefully', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => ({ detail: 'Server error' }),
        headers: { get: () => null },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.message?.type).toBe('error');
    });

    it('handles network errors', async () => {
      mockFetchWithAuth.mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.message?.type).toBe('error');
    });
  });

  describe('X-Allow-Past header', () => {
    it('parses X-Allow-Past header when true', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: true,
        json: async () => ({}),
        headers: {
          get: (name: string) => {
            if (name === 'X-Allow-Past') return 'true';
            if (name === 'ETag') return 'xyz';
            return null;
          },
        },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.allowPastEdits).toBe(true);
    });

    it('parses X-Allow-Past header when 1', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: true,
        json: async () => ({}),
        headers: {
          get: (name: string) => {
            if (name === 'X-Allow-Past') return '1';
            if (name === 'ETag') return 'xyz';
            return null;
          },
        },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.allowPastEdits).toBe(true);
    });
  });

  describe('setWeekSchedule', () => {
    it('converts schedule to bits format', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      await act(async () => {
        result.current.setWeekSchedule({
          '2030-01-07': [{ start_time: '09:00:00', end_time: '10:00:00' }],
        });
      });

      // Should now have unsaved changes
      expect(result.current.hasUnsavedChanges).toBe(true);
      expect(result.current.weekSchedule).toBeDefined();
    });

    it('accepts function updater', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      await act(async () => {
        result.current.setWeekSchedule((prev) => ({
          ...prev,
          '2030-01-07': [{ start_time: '10:00:00', end_time: '11:00:00' }],
        }));
      });

      expect(result.current.hasUnsavedChanges).toBe(true);
    });
  });

  describe('setVersion', () => {
    it('updates version state', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      await act(async () => {
        result.current.setVersion('newVersion123');
      });

      expect(result.current.version).toBe('newVersion123');
    });

    it('clears version when undefined', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      await act(async () => {
        result.current.setVersion(undefined);
      });

      expect(result.current.version).toBeUndefined();
    });
  });

  describe('setAllowPastEdits', () => {
    it('updates allowPastEdits state', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      await act(async () => {
        result.current.setAllowPastEdits(true);
      });

      expect(result.current.allowPastEdits).toBe(true);
    });
  });

  describe('refreshSchedule', () => {
    it('refetches the schedule', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      const callCountBefore = mockFetchWithAuth.mock.calls.length;

      await act(async () => {
        await result.current.refreshSchedule();
      });

      expect(mockFetchWithAuth.mock.calls.length).toBeGreaterThan(callCountBefore);
    });
  });

  describe('currentWeekDisplay', () => {
    it('returns formatted month and year', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      expect(result.current.currentWeekDisplay).toMatch(/\w+\s\d{4}/);
    });
  });

  describe('external week selection sync', () => {
    it('syncs with selectedWeekStart prop', async () => {
      const selectedDate = new Date('2030-02-04');
      const { result, rerender } = renderHook(
        ({ selectedWeekStart }) => useWeekSchedule({ selectedWeekStart }),
        { initialProps: { selectedWeekStart: undefined as Date | undefined } }
      );

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      rerender({ selectedWeekStart: selectedDate });

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      // Should have updated to the new week
      expect(result.current.currentWeekStart).toBeDefined();
    });

    it('calls onWeekStartChange callback', async () => {
      const onWeekStartChange = jest.fn();
      const { result } = renderHook(() =>
        useWeekSchedule({ onWeekStartChange })
      );

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      await act(async () => {
        result.current.navigateWeek('next');
        await new Promise((r) => setTimeout(r, 0));
      });

      expect(onWeekStartChange).toHaveBeenCalled();
    });
  });

  describe('extractDetailFromResponse error parsing (lines 49-71)', () => {
    it('handles error with array of objects containing msg field', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        json: async () => ({
          detail: [
            { msg: 'Invalid start time', loc: ['body', 'start_time'] },
            { msg: 'Invalid end time', loc: ['body', 'end_time'] },
          ],
        }),
        headers: { get: () => null },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.message?.type).toBe('error');
      expect(result.current.message?.text).toContain('Invalid start time');
      expect(result.current.message?.text).toContain('Invalid end time');
    });

    it('handles error with array of string details', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({
          detail: ['First error', 'Second error'],
        }),
        headers: { get: () => null },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.message?.type).toBe('error');
      expect(result.current.message?.text).toContain('First error');
    });

    it('handles error with message field instead of detail', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => ({
          message: 'Something went wrong on the server',
        }),
        headers: { get: () => null },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.message?.type).toBe('error');
      expect(result.current.message?.text).toContain('Something went wrong on the server');
    });

    it('handles error response that is just a string', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => 'Plain string error',
        headers: { get: () => null },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.message?.type).toBe('error');
      expect(result.current.message?.text).toContain('Plain string error');
    });

    it('handles error with empty detail array', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({
          detail: [],
        }),
        headers: { get: () => null },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.message?.type).toBe('error');
    });

    it('handles error with null body', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => null,
        headers: { get: () => null },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.message?.type).toBe('error');
      expect(result.current.message?.text).toContain('Internal Server Error');
    });

    it('handles json parse failure', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: false,
        status: 500,
        statusText: 'Server Error',
        json: async () => {
          throw new Error('Invalid JSON');
        },
        headers: { get: () => null },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.message?.type).toBe('error');
    });
  });

  describe('schedule data loading (lines 305-306)', () => {
    it('loads schedule data with actual time slots', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: true,
        json: async () => ({
          '2030-01-07': [
            { start_time: '09:00:00', end_time: '12:00:00' },
            { start_time: '14:00:00', end_time: '17:00:00' },
          ],
          '2030-01-08': [
            { start_time: '10:00:00', end_time: '15:00:00' },
          ],
        }),
        headers: {
          get: (name: string) => {
            if (name === 'ETag') return 'abc123';
            if (name === 'Last-Modified') return new Date().toUTCString();
            return null;
          },
        },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.weekSchedule).toBeDefined();
      expect(Object.keys(result.current.weekSchedule).length).toBeGreaterThan(0);
    });

    it('skips dates with empty slot arrays', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: true,
        json: async () => ({
          '2030-01-07': [],
          '2030-01-08': [{ start_time: '10:00:00', end_time: '11:00:00' }],
        }),
        headers: {
          get: (name: string) => {
            if (name === 'ETag') return 'abc123';
            return null;
          },
        },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      // Empty arrays should be filtered out
      expect(result.current.weekSchedule['2030-01-07']).toBeUndefined();
    });

    it('handles dates with undefined slots', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: true,
        json: async () => ({
          '2030-01-07': undefined,
          '2030-01-08': null,
          '2030-01-09': [{ start_time: '09:00:00', end_time: '10:00:00' }],
        }),
        headers: {
          get: () => null,
        },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      // Undefined/null slots should be filtered out
      expect(result.current.weekSchedule['2030-01-07']).toBeUndefined();
      expect(result.current.weekSchedule['2030-01-08']).toBeUndefined();
    });
  });

  describe('dayBitsEqual edge cases (line 81)', () => {
    it('returns true when both day bits are identical', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      // Set same bits twice
      const testBits = new Uint8Array([1, 2, 3, 0, 0]);

      await act(async () => {
        result.current.setWeekBits({ '2030-01-07': testBits });
      });

      await act(async () => {
        result.current.setSavedWeekBits({ '2030-01-07': testBits.slice() });
      });

      // Now they should be equal
      expect(result.current.hasUnsavedChanges).toBe(false);
    });

    it('returns true when both day bits are empty', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      // Both start empty
      expect(result.current.hasUnsavedChanges).toBe(false);
    });
  });

  describe('X-Allow-Past header yes value', () => {
    it('parses X-Allow-Past header when yes', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: true,
        json: async () => ({}),
        headers: {
          get: (name: string) => {
            if (name === 'X-Allow-Past') return ' YES ';
            if (name === 'ETag') return 'xyz';
            return null;
          },
        },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.allowPastEdits).toBe(true);
    });
  });

  describe('extractDetailFromResponse — uncovered branches', () => {
    it('handles detail array with entries that have no string/msg (returns undefined)', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        json: async () => ({
          // Array where entries are neither strings nor have a msg field
          detail: [{ code: 123 }, { loc: ['body'] }],
        }),
        headers: { get: () => null },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      // Since collected is empty (no strings, no msg fields), falls through
      // to the 'message' field check, then to JSON.stringify
      expect(result.current.message?.type).toBe('error');
      // Should contain the JSON stringified version of the detail array
      expect(result.current.message?.text).toContain('detail');
    });

    it('handles non-Error thrown in catch block', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => {
        throw 'string-thrown-error';
      });

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.message?.type).toBe('error');
      // The fallback is: error instanceof Error ? error.message : 'Unexpected error'
      expect(result.current.message?.text).toContain('Unexpected error');
    });
  });

  describe('dayBitsEqual / weekBitsEqual edge cases', () => {
    it('detects inequality when one week has extra date key', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      // Set weekBits with an extra date that savedWeekBits doesn't have
      await act(async () => {
        result.current.setWeekBits({
          '2030-01-07': new Uint8Array([1, 0, 0]),
          '2030-01-08': new Uint8Array([2, 0, 0]),
        });
      });

      await act(async () => {
        result.current.setSavedWeekBits({
          '2030-01-07': new Uint8Array([1, 0, 0]),
        });
      });

      // weekBitsEqual should return false because of the extra key
      expect(result.current.hasUnsavedChanges).toBe(true);
    });

    it('dayBitsEqual treats undefined bits as all zeros', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      // weekBits has a key with all-zero bits, savedWeekBits doesn't have the key
      await act(async () => {
        result.current.setWeekBits({
          '2030-01-07': new Uint8Array(180).fill(0),
        });
      });

      // savedWeekBits is empty - dayBitsEqual(zeros, undefined) should be true
      expect(result.current.hasUnsavedChanges).toBe(false);
    });
  });

  describe('setWeekBits function updater', () => {
    it('passes previous bits to the updater function', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      // Set initial bits
      await act(async () => {
        result.current.setWeekBits({ '2030-01-07': new Uint8Array([1]) });
      });

      // Use function updater form
      await act(async () => {
        result.current.setWeekBits((prev) => ({
          ...prev,
          '2030-01-08': new Uint8Array([2]),
        }));
      });

      expect(result.current.hasUnsavedChanges).toBe(true);
    });
  });

  describe('setSavedWeekBits function updater', () => {
    it('passes previous saved bits to the updater function', async () => {
      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      // Use function updater form
      await act(async () => {
        result.current.setSavedWeekBits((prev) => ({
          ...prev,
          '2030-01-07': new Uint8Array([5]),
        }));
      });

      // Since weekBits is empty but savedWeekBits has data, should differ
      expect(result.current.hasUnsavedChanges).toBe(true);
    });
  });

  describe('X-Allow-Past false values', () => {
    it('parses X-Allow-Past header "false" as false', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: true,
        json: async () => ({}),
        headers: {
          get: (name: string) => {
            if (name === 'X-Allow-Past') return 'false';
            if (name === 'ETag') return 'xyz';
            return null;
          },
        },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.allowPastEdits).toBe(false);
    });

    it('parses X-Allow-Past header "0" as false', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: true,
        json: async () => ({}),
        headers: {
          get: (name: string) => {
            if (name === 'X-Allow-Past') return '0';
            if (name === 'ETag') return 'xyz';
            return null;
          },
        },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.allowPastEdits).toBe(false);
    });
  });

  describe('conditional return fields', () => {
    it('omits version, etag, lastModified when not present', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: true,
        json: async () => ({}),
        headers: {
          get: () => null,
        },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.version).toBeUndefined();
      expect(result.current.etag).toBeUndefined();
      expect(result.current.lastModified).toBeUndefined();
      // allowPastEdits should also be undefined since header is null
      expect(result.current.allowPastEdits).toBeUndefined();
    });
  });

  describe('selectedWeekStart sync — no-op when already equal', () => {
    it('does not re-set currentWeekStart when normalized equals current', async () => {
      // Initialize with a specific date that normalizes to itself
      const selectedDate = new Date('2030-01-07'); // This is a Monday

      const { result, rerender } = renderHook(
        ({ selectedWeekStart }) => useWeekSchedule({ selectedWeekStart }),
        { initialProps: { selectedWeekStart: selectedDate } }
      );

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      const initialWeekStart = result.current.currentWeekStart;

      // Re-render with same date — should be a no-op
      rerender({ selectedWeekStart: new Date('2030-01-07') });

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.currentWeekStart.getTime()).toBe(initialWeekStart.getTime());
    });
  });

  describe('fetchWeekSchedule error detail fallback chain', () => {
    it('uses statusText when detail extraction returns undefined', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: false,
        status: 503,
        statusText: 'Service Unavailable',
        json: async () => undefined,
        headers: { get: () => null },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.message?.type).toBe('error');
      expect(result.current.message?.text).toContain('Service Unavailable');
    });

    it('uses "Unknown error" when both detail and statusText are empty', async () => {
      mockFetchWithAuth.mockImplementationOnce(async () => ({
        ok: false,
        status: 500,
        statusText: '',
        json: async () => undefined,
        headers: { get: () => null },
      }));

      const { result } = renderHook(() => useWeekSchedule());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.message?.type).toBe('error');
      expect(result.current.message?.text).toContain('Unknown error');
    });
  });

  describe('messageTimeout edge case', () => {
    it('does not clear message when timeout is 0', async () => {
      const { result } = renderHook(() => useWeekSchedule({ messageTimeout: 0 }));

      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      await act(async () => {
        result.current.setMessage({ type: 'info', text: 'Persistent message' });
      });

      expect(result.current.message).toEqual({ type: 'info', text: 'Persistent message' });

      // Wait a bit to ensure it doesn't auto-clear
      await act(async () => {
        await new Promise((r) => setTimeout(r, 100));
      });

      expect(result.current.message).toEqual({ type: 'info', text: 'Persistent message' });
    });
  });
});
