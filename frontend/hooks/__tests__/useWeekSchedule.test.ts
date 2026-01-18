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
});
