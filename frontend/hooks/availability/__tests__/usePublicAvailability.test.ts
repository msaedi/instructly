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
});
