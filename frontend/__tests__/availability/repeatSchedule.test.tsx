import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { formatDateForAPI } from '@/lib/availability/dateHelpers';
import { API_ENDPOINTS, fetchWithAuth } from '@/lib/api';
import { fromWindows, toWindows } from '@/lib/calendar/bitset';
import type { WeekBits, WeekSchedule, WeekTags } from '@/types/availability';
import { useWeekSchedule } from '@/hooks/availability/useWeekSchedule';
import { useAvailability } from '@/hooks/availability/useAvailability';
import { toast } from 'sonner';

jest.mock('@/hooks/availability/useWeekSchedule');

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api');
  return {
    ...actual,
    fetchWithAuth: jest.fn(),
  };
});

const useWeekScheduleMock = useWeekSchedule as unknown as jest.Mock;
const fetchWithAuthMock = fetchWithAuth as unknown as jest.Mock;
const toastSuccessMock = toast.success as jest.Mock;
const toastErrorMock = toast.error as jest.Mock;

let setWeekBitsSpy: jest.Mock;
let setSavedWeekBitsSpy: jest.Mock;
let refreshScheduleSpy: jest.Mock;
let nextWeekBits: WeekBits;
const EMPTY_WEEK_TAGS: WeekTags = {};

const SAMPLE_WINDOWS: WeekSchedule = {
  '2025-10-27': [{ start_time: '09:00:00', end_time: '17:00:00' }],
  '2025-10-28': [{ start_time: '10:00:00', end_time: '16:00:00' }],
  '2025-10-29': [{ start_time: '11:00:00', end_time: '15:00:00' }],
  '2025-10-30': [{ start_time: '12:00:00', end_time: '18:00:00' }],
  '2025-10-31': [{ start_time: '13:00:00', end_time: '19:00:00' }],
  '2025-11-01': [{ start_time: '08:00:00', end_time: '12:00:00' }],
  '2025-11-02': [{ start_time: '14:00:00', end_time: '20:00:00' }],
};

const toWeekBits = (schedule: WeekSchedule): WeekBits => {
  const bits: WeekBits = {};
  Object.entries(schedule).forEach(([isoDate, slots]) => {
    bits[isoDate] = fromWindows(slots);
  });
  return bits;
};

const INITIAL_WEEK_START = new Date('2025-10-27T00:00:00Z');
const NEXT_WEEK_START = new Date('2025-11-03T00:00:00Z');
const INITIAL_WEEK_BITS = toWeekBits(SAMPLE_WINDOWS);

const createMockResponse = (body: unknown) => {
  return {
    ok: true,
    status: 200,
    headers: {
      get: jest.fn().mockReturnValue(undefined),
    },
    json: jest.fn().mockResolvedValue(body),
    clone: jest.fn().mockReturnValue({
      json: jest.fn().mockResolvedValue(body),
    }),
  };
};

beforeEach(() => {
  jest.clearAllMocks();

  setWeekBitsSpy = jest.fn();
  setSavedWeekBitsSpy = jest.fn();
  const setMessageMock = jest.fn();
  const setVersionMock = jest.fn();
  const setAllowPastEditsMock = jest.fn();

  const nextWeekSchedule: WeekSchedule = Object.fromEntries(
    Object.entries(SAMPLE_WINDOWS).map(([iso, slots]) => {
      const date = new Date(`${iso}T00:00:00Z`);
      date.setDate(date.getDate() + 7);
      return [formatDateForAPI(date), slots];
    })
  );
  nextWeekBits = toWeekBits(nextWeekSchedule);

  refreshScheduleSpy = jest.fn(async () => {
    const nextWeekIso = formatDateForAPI(NEXT_WEEK_START);
    await fetchWithAuth(`${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK}?start_date=${nextWeekIso}`);
    setWeekBitsSpy(nextWeekBits);
    setSavedWeekBitsSpy(nextWeekBits);
  });

  useWeekScheduleMock.mockReturnValue({
    currentWeekStart: INITIAL_WEEK_START,
    weekBits: INITIAL_WEEK_BITS,
    savedWeekBits: INITIAL_WEEK_BITS,
    weekTags: EMPTY_WEEK_TAGS,
    savedWeekTags: EMPTY_WEEK_TAGS,
    weekSchedule: SAMPLE_WINDOWS,
    savedWeekSchedule: SAMPLE_WINDOWS,
    hasUnsavedChanges: false,
    isLoading: false,
    weekDates: Array.from({ length: 7 }, (_unused, index) => {
      const date = new Date(INITIAL_WEEK_START);
      date.setDate(INITIAL_WEEK_START.getDate() + index);
      return {
        date,
        dateStr: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        dayOfWeek: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'][index],
        fullDate: formatDateForAPI(date),
      };
    }),
    message: null,
    navigateWeek: jest.fn(),
    setWeekBits: setWeekBitsSpy,
    setSavedWeekBits: setSavedWeekBitsSpy,
    setWeekTags: jest.fn(),
    setSavedWeekTags: jest.fn(),
    setWeekSchedule: jest.fn(),
    setMessage: setMessageMock,
    refreshSchedule: refreshScheduleSpy,
    goToCurrentWeek: jest.fn(),
    isDateInPast: jest.fn().mockReturnValue(false),
    currentWeekDisplay: 'October 2025',
    version: 'v1',
    etag: 'v1',
    lastModified: undefined,
    setVersion: setVersionMock,
    allowPastEdits: true,
    setAllowPastEdits: setAllowPastEditsMock,
  });

  const postBody = {
    message: 'Applied schedule to future range',
    weeks_applied: 1,
    windows_created: 7,
    weeks_affected: 1,
    days_written: 7,
  };

  const nextWeekIso = formatDateForAPI(NEXT_WEEK_START);
  fetchWithAuthMock.mockImplementation((endpoint: string, options?: RequestInit) => {
    if (options?.method === 'POST') {
      return Promise.resolve(createMockResponse(postBody));
    }
    if (endpoint.startsWith(`${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK}?start_date=${nextWeekIso}`)) {
      return Promise.resolve(createMockResponse(nextWeekSchedule));
    }
    return Promise.reject(new Error(`Unhandled request: ${endpoint}`));
  });
});

const RepeatScheduleHarness: React.FC = () => {
  const { applyToFutureWeeks, refreshSchedule } = useAvailability();
  const handleClick = async () => {
    const result = await applyToFutureWeeks(1);
    if (!result.success) {
      toast.error(result.message || 'Failed to apply to future weeks');
      return;
    }
    toast.success(`Applied through ${result.appliedThrough}`);
    await refreshSchedule();
  };
  return (
    <button type="button" onClick={handleClick}>
      Repeat this schedule
    </button>
  );
};

describe('Repeat schedule flow', () => {
  it('regression: repeat 1 week applies full week not single day', async () => {
    render(<RepeatScheduleHarness />);

    fireEvent.click(screen.getByText(/Repeat this schedule/i));

    await waitFor(() =>
      expect(fetchWithAuthMock).toHaveBeenCalledWith(
        API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_APPLY_RANGE,
        expect.objectContaining({
          method: 'POST',
        })
      )
    );

    const requestBody = JSON.parse(
      (fetchWithAuthMock.mock.calls[0]?.[1] as RequestInit).body as string
    ) as { from_week_start: string; start_date: string; end_date: string };

    expect(requestBody).toEqual({
      from_week_start: '2025-10-27',
      start_date: '2025-11-03',
      end_date: '2025-11-09',
    });

    await waitFor(() => {
      expect(toastSuccessMock).toHaveBeenCalledWith('Applied through 2025-11-09');
      expect(toastErrorMock).not.toHaveBeenCalled();
    });

    const nextWeekIso = formatDateForAPI(NEXT_WEEK_START);
    await waitFor(() =>
      expect(fetchWithAuthMock).toHaveBeenNthCalledWith(
        2,
        `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK}?start_date=${nextWeekIso}`
      )
    );

    const lastCall = setWeekBitsSpy.mock.calls[setWeekBitsSpy.mock.calls.length - 1];
    expect(lastCall).toBeTruthy();
    const lastBits = lastCall?.[0] as WeekBits;
    const expectedNextWeekSchedule: WeekSchedule = Object.fromEntries(
      Object.entries(SAMPLE_WINDOWS).map(([iso, slots]) => {
        const date = new Date(`${iso}T00:00:00Z`);
        date.setDate(date.getDate() + 7);
        return [formatDateForAPI(date), slots];
      })
    );

    expect(Object.keys(expectedNextWeekSchedule)).toHaveLength(7);

    Object.entries(expectedNextWeekSchedule).forEach(([isoDate, slots]) => {
      const dayBits = lastBits?.[isoDate];
      expect(dayBits).toBeDefined();
      expect(toWindows(dayBits!)).toEqual(slots);
    });
  });
});
