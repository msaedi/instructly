import { cleanFetch, publicApi, protectedApi } from '@/features/shared/api/client';
import { getSessionId, refreshSession } from '@/lib/sessionTracking';

jest.mock('@/lib/sessionTracking', () => ({
  getSessionId: jest.fn(),
  refreshSession: jest.fn(),
}));

jest.mock('@/lib/apiBase', () => ({
  withApiBase: (path: string) => path,
}));

const getSessionIdMock = getSessionId as jest.Mock;
const refreshSessionMock = refreshSession as jest.Mock;

describe('client.cleanFetch', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('returns data for successful responses', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ hello: 'world' }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const response = await cleanFetch<{ hello: string }>('https://example.com/api/test');

    expect(response.data).toEqual({ hello: 'world' });
    expect(response.status).toBe(200);
  });

  it('normalizes 429 responses with retry-after', async () => {
    const headers = new Headers({ 'Retry-After': '120' });
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: async () => ({ detail: 'rate limit' }),
      headers,
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const response = await cleanFetch('https://example.com/api/limited');

    expect(response.status).toBe(429);
    expect(response.error).toContain('120s');
    expect((response as { retryAfterSeconds?: number }).retryAfterSeconds).toBe(120);
  });

  it('serializes non-string error details', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: { reason: 'bad' } }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const response = await cleanFetch('https://example.com/api/error');

    expect(response.status).toBe(400);
    expect(response.error).toBe(JSON.stringify({ reason: 'bad' }));
  });

  it('returns network error on fetch failures', async () => {
    const fetchMock = jest.fn().mockRejectedValue(new Error('Network down'));
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const response = await cleanFetch('https://example.com/api/fail');

    expect(response.status).toBe(0);
    expect(response.error).toBe('Network down');
  });
});

describe('publicApi', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    getSessionIdMock.mockReturnValue('session-1');
    document.cookie = 'guest_id=guest-123';
  });

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('adds guest and analytics headers for recent searches', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ([]),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getRecentSearches(2);

    const [url, options] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(requestUrl.searchParams.get('limit')).toBe('2');

    const headers = (options as RequestInit).headers as Record<string, string>;
    expect(headers['X-Guest-Session-ID']).toBe('guest-123');
    expect(headers['X-Session-ID']).toBe('session-1');
    expect(headers['X-Search-Origin']).toBe(window.location.pathname);
  });

  it('records search history with default context', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 1 }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    Object.defineProperty(window, 'innerWidth', { value: 800, writable: true });
    Object.defineProperty(window, 'innerHeight', { value: 600, writable: true });

    await publicApi.recordSearchHistory({
      search_query: 'piano',
      search_type: 'lesson',
      results_count: 2,
    });

    expect(refreshSessionMock).toHaveBeenCalled();

    const [, options] = fetchMock.mock.calls[0];
    const body = JSON.parse((options as RequestInit).body as string) as {
      search_context?: { page?: string; viewport?: string; timestamp?: string };
    };

    expect(body.search_context?.page).toBe(window.location.pathname);
    expect(body.search_context?.viewport).toBe('800x600');
    expect(body.search_context?.timestamp).toBeDefined();
  });

  it('passes query params for natural language search', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ results: [] }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.searchWithNaturalLanguage('piano lessons');

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(requestUrl.searchParams.get('q')).toBe('piano lessons');
  });

  it('adds category param when fetching catalog services', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ([]),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getCatalogServices('music');

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(requestUrl.searchParams.get('category')).toBe('music');
  });
});

describe('protectedApi', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('caps per_page when fetching instructor upcoming bookings', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await protectedApi.getInstructorUpcomingBookings(1, 500);

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(requestUrl.searchParams.get('per_page')).toBe('100');
  });

  it('normalizes instructor booking params', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await protectedApi.getInstructorBookings({ per_page: 250, page: 2, upcoming: true });

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(requestUrl.searchParams.get('per_page')).toBe('100');
    expect(requestUrl.searchParams.get('page')).toBe('2');
    expect(requestUrl.searchParams.get('upcoming')).toBe('true');
  });

  it('posts cancellation payload for cancelBooking', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await protectedApi.cancelBooking('booking-1', 'No longer needed');

    const [, options] = fetchMock.mock.calls[0];
    const request = options as RequestInit;
    expect(request.method).toBe('POST');
    expect(request.body).toBe(JSON.stringify({ reason: 'No longer needed' }));
  });

  it('posts reschedule payload for rescheduleBooking', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await protectedApi.rescheduleBooking('booking-1', {
      booking_date: '2025-01-01',
      start_time: '10:00:00',
      selected_duration: 60,
      instructor_service_id: 'svc-1',
    });

    const [, options] = fetchMock.mock.calls[0];
    const request = options as RequestInit;
    expect(request.method).toBe('POST');
    expect(request.body).toBe(
      JSON.stringify({
        booking_date: '2025-01-01',
        start_time: '10:00:00',
        selected_duration: 60,
        instructor_service_id: 'svc-1',
      })
    );
  });
});
