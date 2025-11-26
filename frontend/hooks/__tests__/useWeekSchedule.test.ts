import { renderHook, act } from '@testing-library/react';
import { useWeekSchedule } from '@/hooks/availability/useWeekSchedule';

// Basic mock for fetchWithAuth via jest module factory if needed
jest.mock('@/lib/api', () => {
  const original = jest.requireActual('@/lib/api');
  return {
    ...original,
    fetchWithAuth: jest.fn(async (url: string) => {
      // Return minimal successful shapes for week and detailed endpoints
      if (url.includes('/api/v1/instructors/availability/week')) {
        return {
          ok: true,
          json: async () => ({}),
          headers: new Map([
            ['ETag', 'abc123'],
            ['Last-Modified', new Date('2025-08-24T12:00:00Z').toUTCString()],
          ]) as unknown as Headers,
        } as Partial<Response> as Response;
      }
      if (url.includes('/api/v1/instructors/availability/?')) {
        return {
          ok: true,
          json: async () => [],
          headers: new Map() as unknown as Headers,
        } as Partial<Response> as Response;
      }
      return { ok: true, json: async () => ({}) } as Partial<Response> as Response;
    }),
  };
});

describe('useWeekSchedule version threading', () => {
  it('captures ETag as version and Last-Modified from headers', async () => {
    const { result } = renderHook(() => useWeekSchedule());

    // Initial fetch runs in effect; let it settle
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(result.current.version).toBe('abc123');
    expect(result.current.lastModified).toBeDefined();
  });
});
