import { cleanFetch, publicApi, protectedApi, getPlaceDetails } from '@/features/shared/api/client';
import { getSessionId, refreshSession } from '@/lib/sessionTracking';
import { __resetSessionRefreshForTests } from '@/lib/auth/sessionRefresh';

jest.mock('@/lib/sessionTracking', () => ({
  getSessionId: jest.fn(),
  refreshSession: jest.fn(),
}));

jest.mock('@/lib/apiBase', () => ({
  withApiBase: (path: string) => path,
  withApiBaseForRequest: (path: string) => path,
}));

const getSessionIdMock = getSessionId as jest.Mock;
const refreshSessionMock = refreshSession as jest.Mock;

describe('client.cleanFetch', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    __resetSessionRefreshForTests();
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

  it('refreshes session and retries once on 401', async () => {
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Unauthorized' }),
        headers: new Headers(),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ message: 'Session refreshed' }),
        headers: new Headers(),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ hello: 'after-refresh' }),
        headers: new Headers(),
      });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const response = await cleanFetch<{ hello: string }>('/api/v1/auth/me');

    expect(response.status).toBe(200);
    expect(response.data).toEqual({ hello: 'after-refresh' });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain('/api/v1/auth/refresh');
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

  it('adds category_id param when fetching catalog services', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ([]),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getCatalogServices('01HABCTESTCAT0000000000001');

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(requestUrl.searchParams.get('category_id')).toBe('01HABCTESTCAT0000000000001');
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

  it('creates a booking with createBooking', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: 'booking-123' }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const result = await protectedApi.createBooking({
      instructor_id: 'inst-1',
      instructor_service_id: 'svc-1',
      booking_date: '2025-01-15',
      start_time: '14:00:00',
      selected_duration: 60,
      location_type: 'online',
    });

    expect(result.status).toBe(201);
    expect(result.data).toEqual({ id: 'booking-123' });
    const [, options] = fetchMock.mock.calls[0];
    expect((options as RequestInit).method).toBe('POST');
  });

  it('gets a single booking with getBooking', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'booking-123', status: 'CONFIRMED' }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const result = await protectedApi.getBooking('booking-123');

    expect(result.data).toEqual({ id: 'booking-123', status: 'CONFIRMED' });
    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/bookings/booking-123');
  });

  it('fetches instructor completed bookings', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [], total: 0 }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await protectedApi.getInstructorCompletedBookings(1, 50);

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(requestUrl.pathname).toContain('completed');
    expect(requestUrl.searchParams.get('per_page')).toBe('50');
  });

  it('passes signal to getBookings', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [] }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const controller = new AbortController();
    await protectedApi.getBookings({ signal: controller.signal, limit: 10 });

    const [, options] = fetchMock.mock.calls[0];
    expect((options as RequestInit).signal).toBe(controller.signal);
  });

  it('passes signal to getInstructorBookings', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [] }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const controller = new AbortController();
    await protectedApi.getInstructorBookings({ signal: controller.signal });

    const [, options] = fetchMock.mock.calls[0];
    expect((options as RequestInit).signal).toBe(controller.signal);
  });
});

describe('cleanFetch edge cases', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('handles non-JSON response gracefully', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => {
        throw new Error('Invalid JSON');
      },
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const response = await cleanFetch('https://example.com/api/text');

    expect(response.status).toBe(200);
    expect(response.data).toBeUndefined();
  });

  it('handles 429 without Retry-After header', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: async () => ({}),
      headers: new Headers(), // No Retry-After
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const response = await cleanFetch('https://example.com/api/limited');

    expect(response.status).toBe(429);
    expect(response.error).toContain('shortly');
    expect((response as { retryAfterSeconds?: number }).retryAfterSeconds).toBeUndefined();
  });

  it('handles error without detail field', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}), // No detail field
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const response = await cleanFetch('https://example.com/api/error');

    expect(response.status).toBe(500);
    expect(response.error).toBe('Error: 500');
  });

  it('handles non-Error exceptions in fetch', async () => {
    const fetchMock = jest.fn().mockRejectedValue('string error');
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const response = await cleanFetch('https://example.com/api/fail');

    expect(response.status).toBe(0);
    expect(response.error).toBe('Network error');
  });

  it('appends query params excluding undefined and null', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await cleanFetch('https://example.com/api/test', {
      params: {
        valid: 'yes',
        empty: undefined as unknown as string,
        nullish: null as unknown as string,
        numeric: 42,
        bool: true,
      },
    });

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string);
    expect(requestUrl.searchParams.get('valid')).toBe('yes');
    expect(requestUrl.searchParams.get('numeric')).toBe('42');
    expect(requestUrl.searchParams.get('bool')).toBe('true');
    expect(requestUrl.searchParams.has('empty')).toBe(false);
    expect(requestUrl.searchParams.has('nullish')).toBe(false);
  });
});

describe('publicApi additional methods', () => {
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

  it('deletes search history', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => undefined,
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.deleteSearchHistory(123);

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/search-history/123');
    expect((options as RequestInit).method).toBe('DELETE');
  });

  it('searches instructors with filters', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [], total: 0 }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.searchInstructors({
      service_catalog_id: 'svc-123',
      min_price: 30,
      max_price: 100,
      page: 1,
    });

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(requestUrl.searchParams.get('service_catalog_id')).toBe('svc-123');
    expect(requestUrl.searchParams.get('min_price')).toBe('30');
    expect(requestUrl.searchParams.get('max_price')).toBe('100');
  });

  it('gets instructor profile', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'inst-1', bio: 'Hello' }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const result = await publicApi.getInstructorProfile('inst-1');

    expect(result.data).toEqual({ id: 'inst-1', bio: 'Hello' });
    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/instructors/inst-1');
  });

  it('gets instructor availability', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ instructor_id: 'inst-1', availability_by_date: {} }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getInstructorAvailability('inst-1', {
      start_date: '2025-01-01',
      end_date: '2025-01-07',
    });

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(url).toContain('/api/v1/public/instructors/inst-1/availability');
    expect(requestUrl.searchParams.get('start_date')).toBe('2025-01-01');
    expect(requestUrl.searchParams.get('end_date')).toBe('2025-01-07');
  });

  it('gets service categories', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [{ id: 'cat-1', name: 'Music' }],
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const result = await publicApi.getServiceCategories();

    expect(result.data).toEqual([{ id: 'cat-1', name: 'Music' }]);
    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/services/categories');
  });

  it('gets catalog services without category filter', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getCatalogServices();

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(requestUrl.searchParams.has('category')).toBe(false);
  });

  it('gets top services per category', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ categories: [] }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getTopServicesPerCategory();

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/services/catalog/top-per-category');
  });

  it('gets all services with instructors', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ categories: [] }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getAllServicesWithInstructors();

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/services/catalog/all-with-instructors');
  });

  it('gets kids available services', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [{ id: 'svc-1', name: 'Piano', slug: 'piano' }],
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const result = await publicApi.getKidsAvailableServices();

    expect(result.data).toEqual([{ id: 'svc-1', name: 'Piano', slug: 'piano' }]);
    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/services/catalog/kids-available');
  });

  // Legacy deprecated methods
  it('records guest search history (deprecated)', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 1, guest_session_id: 'guest-123' }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.recordGuestSearchHistory({
      guest_session_id: 'guest-123',
      search_query: 'piano',
      search_type: 'lesson',
    });

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/search-history/guest');
    expect((options as RequestInit).method).toBe('POST');
  });

  it('gets guest recent searches (deprecated)', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getGuestRecentSearches('guest-123', 5);

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(url).toContain('/api/v1/search-history/guest/guest-123');
    expect(requestUrl.searchParams.get('limit')).toBe('5');
  });

  it('deletes guest search history (deprecated)', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => undefined,
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.deleteGuestSearchHistory('guest-123', 456);

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/search-history/guest/guest-123/456');
    expect((options as RequestInit).method).toBe('DELETE');
  });
});

describe('getPlaceDetails', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('fetches place details with place_id', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ place_id: 'abc', formatted_address: '123 Main St' }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const result = await getPlaceDetails({ place_id: 'abc123' });

    expect(result.data).toEqual({ place_id: 'abc', formatted_address: '123 Main St' });
    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('place_id=abc123');
  });

  it('includes provider param when specified', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await getPlaceDetails({ place_id: 'abc', provider: 'google' });

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('provider=google');
  });

  it('passes abort signal when provided', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const controller = new AbortController();
    await getPlaceDetails({ place_id: 'abc', signal: controller.signal });

    const [, options] = fetchMock.mock.calls[0];
    expect((options as RequestInit).signal).toBe(controller.signal);
  });
});

describe('getGuestSessionId', () => {
  const originalSessionStorage = window.sessionStorage;

  afterEach(() => {
    document.cookie = 'guest_id=; expires=Thu, 01 Jan 1970 00:00:00 UTC';
    Object.defineProperty(window, 'sessionStorage', {
      value: originalSessionStorage,
      writable: true,
    });
  });

  it('falls back to sessionStorage when cookie not present', async () => {
    // Clear cookie
    document.cookie = 'guest_id=; expires=Thu, 01 Jan 1970 00:00:00 UTC';

    // Mock sessionStorage
    const mockSessionStorage = {
      getItem: jest.fn().mockReturnValue('session-guest-456'),
      setItem: jest.fn(),
      removeItem: jest.fn(),
      clear: jest.fn(),
      length: 0,
      key: jest.fn(),
    };
    Object.defineProperty(window, 'sessionStorage', {
      value: mockSessionStorage,
      writable: true,
    });

    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getRecentSearches();

    const [, options] = fetchMock.mock.calls[0];
    const headers = (options as RequestInit).headers as Record<string, string>;
    expect(headers['X-Guest-Session-ID']).toBe('session-guest-456');
  });

  it('handles sessionStorage exception gracefully', async () => {
    // Clear cookie
    document.cookie = 'guest_id=; expires=Thu, 01 Jan 1970 00:00:00 UTC';

    // Mock sessionStorage to throw
    const mockSessionStorage = {
      getItem: jest.fn().mockImplementation(() => {
        throw new Error('Storage disabled');
      }),
      setItem: jest.fn(),
      removeItem: jest.fn(),
      clear: jest.fn(),
      length: 0,
      key: jest.fn(),
    };
    Object.defineProperty(window, 'sessionStorage', {
      value: mockSessionStorage,
      writable: true,
    });

    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getRecentSearches();

    const [, options] = fetchMock.mock.calls[0];
    const headers = (options as RequestInit).headers as Record<string, string>;
    // Should not have guest session ID when sessionStorage throws
    expect(headers['X-Guest-Session-ID']).toBeUndefined();
  });

  it('uses cookie value when present', async () => {
    document.cookie = 'guest_id=cookie-guest-789';

    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getRecentSearches();

    const [, options] = fetchMock.mock.calls[0];
    const headers = (options as RequestInit).headers as Record<string, string>;
    expect(headers['X-Guest-Session-ID']).toBe('cookie-guest-789');
  });
});

describe('publicApi 3-level taxonomy endpoints', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('getCategoriesWithSubcategories calls browse endpoint', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [{ id: 'cat-1', subcategories: [] }],
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const result = await publicApi.getCategoriesWithSubcategories();

    expect(result.data).toEqual([{ id: 'cat-1', subcategories: [] }]);
    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/services/categories/browse');
  });

  it('getCategoryTree calls tree endpoint with category ID', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'cat-1', children: [] }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getCategoryTree('cat-123');

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/services/categories/cat-123/tree');
  });

  it('getSubcategoriesByCategory calls subcategories endpoint', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getSubcategoriesByCategory('cat-456');

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/services/categories/cat-456/subcategories');
  });

  it('getSubcategoryWithServices calls subcategory detail endpoint', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'sub-1', services: [] }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getSubcategoryWithServices('sub-123');

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/services/subcategories/sub-123');
  });

  it('getSubcategoryFilters calls filters endpoint', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getSubcategoryFilters('sub-456');

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/services/subcategories/sub-456/filters');
  });

  it('getServicesByAgeGroup calls by-age-group endpoint', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getServicesByAgeGroup('kids');

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/services/catalog/by-age-group/kids');
  });

  it('getServiceFilterContext calls filter-context endpoint', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ filters: [], selections: {} }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getServiceFilterContext('svc-123');

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/services/catalog/svc-123/filter-context');
  });
});

describe('publicApi slug-based catalog endpoints', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('listCatalogCategories calls catalog categories endpoint', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.listCatalogCategories();

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/catalog/categories');
  });

  it('getCatalogCategory calls category-by-slug endpoint', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ slug: 'music', subcategories: [] }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getCatalogCategory('music');

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/catalog/categories/music');
  });

  it('getCatalogSubcategory calls subcategory-by-slugs endpoint', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ slug: 'piano' }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getCatalogSubcategory('music', 'piano');

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/catalog/categories/music/piano');
  });

  it('getCatalogService calls service-by-id endpoint', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'svc-1', name: 'Piano Lessons' }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getCatalogService('svc-1');

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/catalog/services/svc-1');
  });

  it('listCatalogSubcategoryServices calls subcategory services endpoint', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.listCatalogSubcategoryServices('sub-1');

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/catalog/subcategories/sub-1/services');
  });

  it('getCatalogSubcategoryFilters calls subcategory filters endpoint', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getCatalogSubcategoryFilters('sub-2');

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/catalog/subcategories/sub-2/filters');
  });
});

describe('protectedApi filter management', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('updateFilterSelections sends PUT request with data', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'isvc-1', filter_selections: {} }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await protectedApi.updateFilterSelections('isvc-1', {
      filter_selections: { style: ['jazz', 'classical'] },
    } as Parameters<typeof protectedApi.updateFilterSelections>[1]);

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/services/instructor/services/isvc-1/filters');
    expect((options as RequestInit).method).toBe('PUT');
  });

  it('validateFilterSelections sends POST request with data', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ valid: true, errors: [] }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await protectedApi.validateFilterSelections({
      service_catalog_id: 'svc-1',
      filter_selections: { style: ['jazz'] },
    } as Parameters<typeof protectedApi.validateFilterSelections>[0]);

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain('/api/v1/services/instructor/services/validate-filters');
    expect((options as RequestInit).method).toBe('POST');
  });
});

describe('protectedApi booking edge cases', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('getBookings with no params sends no query string', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [] }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await protectedApi.getBookings();

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(requestUrl.searchParams.toString()).toBe('');
  });

  it('getBookings with uppercase status passes through', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [] }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await protectedApi.getBookings({ status: 'CONFIRMED' });

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(requestUrl.searchParams.get('status')).toBe('CONFIRMED');
  });

  it('getBookings omits undefined status', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [] }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await protectedApi.getBookings({ status: undefined, page: 2 });

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(requestUrl.searchParams.has('status')).toBe(false);
    expect(requestUrl.searchParams.get('page')).toBe('2');
  });

  it('getInstructorBookings with no params sends no query string', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [] }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await protectedApi.getInstructorBookings();

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(requestUrl.searchParams.toString()).toBe('');
  });

  it('getInstructorUpcomingBookings caps perPage to 100', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await protectedApi.getInstructorUpcomingBookings(1, 200);

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(requestUrl.searchParams.get('per_page')).toBe('100');
  });

  it('getInstructorCompletedBookings caps perPage to 100', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await protectedApi.getInstructorCompletedBookings(1, 300);

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(requestUrl.searchParams.get('per_page')).toBe('100');
  });
});

describe('cleanFetch URL routing', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('skips proxy for endpoints already prefixed with /api/proxy', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await cleanFetch('/api/proxy/api/v1/test');

    const [url] = fetchMock.mock.calls[0];
    // Should not double-prefix with proxy
    expect(url).toContain('/api/proxy/api/v1/test');
    expect(url).not.toContain('/api/proxy/api/proxy');
  });

  it('handles error response with string detail value', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'Invalid input parameters' }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const response = await cleanFetch('https://example.com/api/v1/test');

    expect(response.error).toBe('Invalid input parameters');
  });

  it('handles error response with null detail value', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ detail: null }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const response = await cleanFetch('https://example.com/api/v1/test');

    expect(response.error).toBe('Error: 500');
  });

  it('includes credentials: include by default', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await cleanFetch('https://example.com/api/v1/test');

    const [, options] = fetchMock.mock.calls[0];
    expect((options as RequestInit).credentials).toBe('include');
  });
});

describe('publicApi search context', () => {
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

  it('recordSearchHistory preserves provided search_context', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 1 }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const customContext = { page: '/custom', source: 'deeplink' };
    await publicApi.recordSearchHistory({
      search_query: 'guitar',
      search_type: 'text',
      search_context: customContext,
    });

    const [, options] = fetchMock.mock.calls[0];
    const body = JSON.parse((options as RequestInit).body as string) as {
      search_context?: Record<string, unknown>;
    };
    // Should keep the provided context, not generate default
    expect(body.search_context).toEqual(customContext);
  });

  it('searchWithNaturalLanguage omits empty filter params', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ results: [] }),
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.searchWithNaturalLanguage('piano', {});

    const [url] = fetchMock.mock.calls[0];
    const requestUrl = new URL(url as string, window.location.origin);
    expect(requestUrl.searchParams.get('q')).toBe('piano');
    expect(requestUrl.searchParams.has('skill_level')).toBe(false);
    expect(requestUrl.searchParams.has('subcategory_id')).toBe(false);
    expect(requestUrl.searchParams.has('content_filters')).toBe(false);
  });
});

describe('analytics headers', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('excludes X-Session-ID when getSessionId returns null', async () => {
    getSessionIdMock.mockReturnValue(null);
    document.cookie = 'guest_id=guest-123';

    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
      headers: new Headers(),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await publicApi.getRecentSearches();

    const [, options] = fetchMock.mock.calls[0];
    const headers = (options as RequestInit).headers as Record<string, string>;
    expect(headers['X-Session-ID']).toBeUndefined();
    expect(headers['X-Search-Origin']).toBe(window.location.pathname);
  });
});
