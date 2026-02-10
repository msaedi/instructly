import { renderHook, waitFor, act } from '@testing-library/react';
import { usePublicAvailability } from '../usePublicAvailability';

const originalFetch = global.fetch;

const makeResponse = ({ ok, json }: { ok: boolean; json?: unknown }) => ({
  ok,
  json: jest.fn().mockResolvedValue(json),
});

describe('usePublicAvailability', () => {
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn();
    global.fetch = fetchMock as unknown as typeof global.fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('loads availability and exposes date helpers', async () => {
    fetchMock.mockResolvedValueOnce(
      makeResponse({
        ok: true,
        json: {
          availability_by_date: {
            '2025-01-01': {
              is_blackout: false,
              available_slots: [{ start_time: '09:00', end_time: '10:00' }],
            },
            '2025-01-02': {
              is_blackout: true,
              available_slots: [{ start_time: '09:00', end_time: '10:00' }],
            },
          },
        },
      })
    );

    const { result } = renderHook(() => usePublicAvailability('instructor-1'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.error).toBeNull();
    expect(result.current.getAvailableDates()).toEqual(['2025-01-01']);
    expect(result.current.getSlotsForDate('2025-01-01')).toHaveLength(1);
  });

  it('sets error when fetch fails', async () => {
    fetchMock.mockResolvedValueOnce(makeResponse({ ok: false }));

    const { result } = renderHook(() => usePublicAvailability('instructor-2'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.error).toBe('Failed to fetch availability');
    expect(result.current.availability).toBeNull();
  });

  it('refresh triggers a new fetch', async () => {
    fetchMock.mockResolvedValue(
      makeResponse({
        ok: true,
        json: {
          availability_by_date: {},
        },
      })
    );

    const { result } = renderHook(() => usePublicAvailability('instructor-3'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      result.current.refresh();
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('getAvailableDates returns empty array when availability is null', async () => {
    fetchMock.mockResolvedValueOnce(makeResponse({ ok: false }));

    const { result } = renderHook(() => usePublicAvailability('instructor-4'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    // availability is null due to the error
    expect(result.current.availability).toBeNull();
    expect(result.current.getAvailableDates()).toEqual([]);
  });

  it('getAvailableDates filters out blackout days', async () => {
    fetchMock.mockResolvedValueOnce(
      makeResponse({
        ok: true,
        json: {
          availability_by_date: {
            '2025-02-01': {
              is_blackout: true,
              available_slots: [{ start_time: '09:00', end_time: '10:00' }],
            },
            '2025-02-02': {
              is_blackout: false,
              available_slots: [{ start_time: '10:00', end_time: '11:00' }],
            },
          },
        },
      })
    );

    const { result } = renderHook(() => usePublicAvailability('instructor-5'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    const dates = result.current.getAvailableDates();
    expect(dates).toEqual(['2025-02-02']);
    expect(dates).not.toContain('2025-02-01');
  });

  it('getAvailableDates filters out days with empty available_slots', async () => {
    fetchMock.mockResolvedValueOnce(
      makeResponse({
        ok: true,
        json: {
          availability_by_date: {
            '2025-02-03': {
              is_blackout: false,
              available_slots: [],
            },
            '2025-02-04': {
              is_blackout: false,
              available_slots: [{ start_time: '14:00', end_time: '15:00' }],
            },
          },
        },
      })
    );

    const { result } = renderHook(() => usePublicAvailability('instructor-6'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    const dates = result.current.getAvailableDates();
    expect(dates).toEqual(['2025-02-04']);
  });

  it('getAvailableDates handles missing available_slots field (uses ?? [] fallback)', async () => {
    fetchMock.mockResolvedValueOnce(
      makeResponse({
        ok: true,
        json: {
          availability_by_date: {
            '2025-02-05': {
              is_blackout: false,
              // available_slots is missing
            },
          },
        },
      })
    );

    const { result } = renderHook(() => usePublicAvailability('instructor-7'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    // Missing available_slots should be treated as empty via ?? []
    expect(result.current.getAvailableDates()).toEqual([]);
  });

  it('getAvailableDates handles missing availability_by_date (uses ?? {} fallback)', async () => {
    fetchMock.mockResolvedValueOnce(
      makeResponse({
        ok: true,
        json: {
          // availability_by_date is missing entirely
        },
      })
    );

    const { result } = renderHook(() => usePublicAvailability('instructor-8'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.getAvailableDates()).toEqual([]);
  });

  it('getSlotsForDate returns empty array when date does not exist', async () => {
    fetchMock.mockResolvedValueOnce(
      makeResponse({
        ok: true,
        json: {
          availability_by_date: {
            '2025-02-10': {
              is_blackout: false,
              available_slots: [{ start_time: '09:00', end_time: '10:00' }],
            },
          },
        },
      })
    );

    const { result } = renderHook(() => usePublicAvailability('instructor-9'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    // Date that doesn't exist in availability_by_date
    expect(result.current.getSlotsForDate('2025-03-01')).toEqual([]);
  });

  it('getSlotsForDate returns empty array when availability is null', async () => {
    fetchMock.mockResolvedValueOnce(makeResponse({ ok: false }));

    const { result } = renderHook(() => usePublicAvailability('instructor-10'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.getSlotsForDate('2025-02-10')).toEqual([]);
  });

  it('handles non-Error throw by returning "Unknown error"', async () => {
    fetchMock.mockRejectedValueOnce('string error');

    const { result } = renderHook(() => usePublicAvailability('instructor-11'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.error).toBe('Unknown error');
  });

  it('getSlotsForDate uses ?? [] when available_slots is missing for existing date', async () => {
    fetchMock.mockResolvedValueOnce(
      makeResponse({
        ok: true,
        json: {
          availability_by_date: {
            '2025-02-15': {
              is_blackout: false,
              // No available_slots property
            },
          },
        },
      })
    );

    const { result } = renderHook(() => usePublicAvailability('instructor-12'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.getSlotsForDate('2025-02-15')).toEqual([]);
  });
});
