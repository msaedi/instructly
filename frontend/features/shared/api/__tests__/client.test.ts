import { cleanFetch, getPlaceDetails, protectedApi, publicApi, PUBLIC_ENDPOINTS, PROTECTED_ENDPOINTS } from '@/features/shared/api/client';
import { getSessionId, refreshSession } from '@/lib/sessionTracking';
import { withApiBase } from '@/lib/apiBase';

jest.mock('@/lib/sessionTracking', () => ({
  getSessionId: jest.fn(),
  refreshSession: jest.fn(),
}));

jest.mock('@/lib/apiBase', () => {
  const withApiBase = jest.fn((endpoint: string) => `/api/proxy${endpoint}`);
  const withApiBaseForRequest = jest.fn((endpoint: string) => {
    if (/^https?:\/\//i.test(endpoint)) {
      return endpoint;
    }
    if (endpoint.startsWith('/api/proxy')) {
      return endpoint;
    }
    return withApiBase(endpoint);
  });
  return { withApiBase, withApiBaseForRequest };
});

describe('protectedApi.getBookings', () => {
  const originalFetch = global.fetch;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;
  });

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error - cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('normalizes lowercase status queries to uppercase BookingStatus', async () => {
    await protectedApi.getBookings({ status: 'completed', limit: 1 });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    const requestUrl = new URL(calledUrl);
    expect(requestUrl.searchParams.get('status')).toBe('COMPLETED');
  });
});

describe('cleanFetch', () => {
  const originalFetch = global.fetch;
  const originalWindow = global.window;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: jest.fn() },
      json: async () => ({}),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;
    (getSessionId as jest.Mock).mockReturnValue('session-123');
    window.history.pushState({}, '', '/search');
  });

  afterEach(() => {
    (withApiBase as jest.Mock).mockClear();
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error - cleanup when fetch was initially undefined
      delete global.fetch;
    }
    global.window = originalWindow;
    document.cookie = '';
  });

  it('builds proxy URL and attaches analytics headers', async () => {
    const response = await cleanFetch('/api/v1/search', { params: { q: 'piano', page: 2 } });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    const requestUrl = new URL(calledUrl);
    expect(requestUrl.pathname).toBe('/api/proxy/api/v1/search');
    expect(requestUrl.searchParams.get('q')).toBe('piano');
    expect(requestUrl.searchParams.get('page')).toBe('2');
    expect(response.status).toBe(200);

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = options.headers as Record<string, string>;
    expect(headers['X-Session-ID']).toBe('session-123');
    expect(headers['X-Search-Origin']).toBe('/search');
    expect(options.credentials).toBe('include');
  });

  it('returns rate limit details on 429', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 429,
      headers: { get: jest.fn(() => '15') },
      json: async () => ({}),
    });

    const response = await cleanFetch('/api/v1/search');

    expect(response.status).toBe(429);
    expect(response.error).toBe('Our hamsters are sprinting. Give them 15s.');
    expect((response as { retryAfterSeconds?: number }).retryAfterSeconds).toBe(15);
  });

  it('stringifies non-string error detail values', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 400,
      headers: { get: jest.fn() },
      json: async () => ({ detail: { message: 'Bad input' } }),
    });

    const response = await cleanFetch('/api/v1/search');

    expect(response.status).toBe(400);
    expect(response.error).toBe(JSON.stringify({ message: 'Bad input' }));
  });

  it('handles network errors', async () => {
    fetchMock.mockRejectedValueOnce(new Error('Network down'));

    const response = await cleanFetch('/api/v1/search');

    expect(response.status).toBe(0);
    expect(response.error).toBe('Network down');
  });

  it('uses absolute URLs without proxy adjustments', async () => {
    await cleanFetch('https://example.com/api/v1/ssr-test');

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toBe('https://example.com/api/v1/ssr-test');
    expect(withApiBase).not.toHaveBeenCalled();
  });
});

describe('publicApi', () => {
  const originalFetch = global.fetch;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: jest.fn() },
      json: async () => ({}),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;
    (refreshSession as jest.Mock).mockClear();
    document.cookie = 'guest_id=guest%20123';
    window.history.pushState({}, '', '/booking');
    Object.defineProperty(window, 'innerWidth', { value: 1024, writable: true });
    Object.defineProperty(window, 'innerHeight', { value: 768, writable: true });
  });

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error - cleanup when fetch was initially undefined
      delete global.fetch;
    }
    document.cookie = '';
  });

  it('records search history with default analytics context', async () => {
    await publicApi.recordSearchHistory({
      search_query: 'piano lessons',
      search_type: 'text',
      results_count: 12,
    });

    expect(refreshSession).toHaveBeenCalled();
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    const body = JSON.parse(options.body as string) as {
      search_context?: { page?: string; viewport?: string; timestamp?: string };
    };
    expect(body.search_context?.page).toBe('/booking');
    expect(body.search_context?.viewport).toBe('1024x768');
    expect(body.search_context?.timestamp).toEqual(expect.any(String));
  });

  it('includes guest session header for unified history', async () => {
    await publicApi.getRecentSearches();

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = options.headers as Record<string, string>;
    expect(headers['X-Guest-Session-ID']).toBe('guest 123');
  });

  it('falls back to sessionStorage for guest session id', async () => {
    document.cookie = 'guest_id=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    const getItemSpy = jest.spyOn(Storage.prototype, 'getItem').mockReturnValue('guest-session');

    await publicApi.getRecentSearches();

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = options.headers as Record<string, string>;
    expect(headers['X-Guest-Session-ID']).toBe('guest-session');
    getItemSpy.mockRestore();
  });

  it('passes taxonomy context params for natural language search', async () => {
    await publicApi.searchWithNaturalLanguage('piano', {
      skill_level: 'beginner,advanced',
      subcategory_id: 'sub-123',
      content_filters: 'goal:enrichment,competition|format:one_on_one',
    });

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    const requestUrl = new URL(calledUrl);
    expect(requestUrl.searchParams.get('q')).toBe('piano');
    expect(requestUrl.searchParams.get('skill_level')).toBe('beginner,advanced');
    expect(requestUrl.searchParams.get('subcategory_id')).toBe('sub-123');
    expect(requestUrl.searchParams.get('content_filters')).toBe(
      'goal:enrichment,competition|format:one_on_one'
    );
  });

  it('passes taxonomy context params for catalog search', async () => {
    await publicApi.searchInstructors({
      service_catalog_id: 'svc-1',
      skill_level: 'intermediate',
      subcategory_id: 'sub-456',
      content_filters: 'style:jazz',
    });

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    const requestUrl = new URL(calledUrl);
    expect(requestUrl.searchParams.get('service_catalog_id')).toBe('svc-1');
    expect(requestUrl.searchParams.get('skill_level')).toBe('intermediate');
    expect(requestUrl.searchParams.get('subcategory_id')).toBe('sub-456');
    expect(requestUrl.searchParams.get('content_filters')).toBe('style:jazz');
  });
});

describe('protectedApi.getInstructorBookings', () => {
  const originalFetch = global.fetch;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: jest.fn() },
      json: async () => ({}),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;
    document.cookie = 'guest_id=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
  });

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error - cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('caps per_page to 100', async () => {
    await protectedApi.getInstructorBookings({ page: 1, per_page: 250 });

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    const requestUrl = new URL(calledUrl);
    expect(requestUrl.searchParams.get('per_page')).toBe('100');
  });
});

describe('getPlaceDetails', () => {
  const originalFetch = global.fetch;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: jest.fn() },
      json: async () => ({}),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;
  });

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error - cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('appends provider query when supplied', async () => {
    await getPlaceDetails({ place_id: 'place-1', provider: 'google' });

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    const requestUrl = new URL(calledUrl);
    expect(requestUrl.pathname).toBe('/api/proxy/api/v1/addresses/places/details');
    expect(requestUrl.searchParams.get('place_id')).toBe('place-1');
    expect(requestUrl.searchParams.get('provider')).toBe('google');
  });
});

describe('cleanFetch — additional branch coverage', () => {
  const originalFetch = global.fetch;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn();
    global.fetch = fetchMock as unknown as typeof global.fetch;
    (getSessionId as jest.Mock).mockReturnValue(null);
  });

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error - cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('skips X-Session-ID header when getSessionId returns null', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: jest.fn() },
      json: async () => ({}),
    });

    await cleanFetch('/api/v1/test');

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = options.headers as Record<string, string>;
    expect(headers['X-Session-ID']).toBeUndefined();
    // X-Search-Origin should still be set in browser
    expect(headers['X-Search-Origin']).toBeDefined();
  });

  it('returns data as null for 204 No Content responses', async () => {
    const jsonFn = jest.fn();
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 204,
      headers: { get: jest.fn() },
      json: jsonFn,
    });

    const response = await cleanFetch('/api/v1/test');

    expect(response.status).toBe(204);
    expect(response.data).toBeNull();
    // json() should NOT have been called for 204
    expect(jsonFn).not.toHaveBeenCalled();
  });

  it('returns data as null for 205 Reset Content responses', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 205,
      headers: { get: jest.fn() },
      json: jest.fn(),
    });

    const response = await cleanFetch('/api/v1/test');

    expect(response.status).toBe(205);
    expect(response.data).toBeNull();
  });

  it('handles JSON parse error on non-ok response by falling back to status code', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 502,
      headers: { get: jest.fn() },
      json: async () => { throw new SyntaxError('Bad Gateway HTML'); },
    });

    const response = await cleanFetch('/api/v1/test');

    // data is null, detail is null, so error should be "Error: 502"
    expect(response.status).toBe(502);
    expect(response.error).toBe('Error: 502');
  });

  it('returns string error detail directly without stringifying', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 403,
      headers: { get: jest.fn() },
      json: async () => ({ detail: 'Access denied' }),
    });

    const response = await cleanFetch('/api/v1/test');

    expect(response.status).toBe(403);
    expect(response.error).toBe('Access denied');
  });

  it('handles non-Error thrown objects in catch block', async () => {
    fetchMock.mockRejectedValueOnce('string error');

    const response = await cleanFetch('/api/v1/test');

    expect(response.status).toBe(0);
    expect(response.error).toBe('Network error');
  });

  it('skips null and undefined param values', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: jest.fn() },
      json: async () => ({}),
    });

    await cleanFetch('/api/v1/test', {
      params: {
        keep: 'yes',
        // @ts-expect-error - testing runtime null handling
        dropNull: null,
        // @ts-expect-error - testing runtime undefined handling
        dropUndefined: undefined,
      },
    });

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    const url = new URL(calledUrl);
    expect(url.searchParams.get('keep')).toBe('yes');
    expect(url.searchParams.has('dropNull')).toBe(false);
    expect(url.searchParams.has('dropUndefined')).toBe(false);
  });

  it('uses default credentials include when not specified', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: jest.fn() },
      json: async () => ({}),
    });

    await cleanFetch('/api/v1/test');

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(options.credentials).toBe('include');
  });

  it('preserves custom credentials when specified', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: jest.fn() },
      json: async () => ({}),
    });

    await cleanFetch('/api/v1/test', { credentials: 'same-origin' });

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(options.credentials).toBe('same-origin');
  });

  it('handles error response with undefined detail (falls back to status)', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 418,
      headers: { get: jest.fn() },
      json: async () => ({ other: 'field' }),
    });

    const response = await cleanFetch('/api/v1/test');

    expect(response.status).toBe(418);
    expect(response.error).toBe('Error: 418');
  });

  it('handles 429 with non-numeric Retry-After header', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 429,
      headers: { get: jest.fn(() => 'invalid') },
      json: async () => ({}),
    });

    const response = await cleanFetch('/api/v1/search');

    expect(response.status).toBe(429);
    // parseInt('invalid', 10) is NaN, !Number.isFinite(NaN) -> secs=undefined
    expect(response.error).toBe('Our hamsters are sprinting. Please try again shortly.');
    expect((response as { retryAfterSeconds?: number }).retryAfterSeconds).toBeUndefined();
  });
});

describe('publicApi — additional branch coverage', () => {
  const originalFetch = global.fetch;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: jest.fn() },
      json: async () => ({}),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;
    (refreshSession as jest.Mock).mockClear();
    document.cookie = 'guest_id=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
  });

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error - cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('preserves user-supplied search_context in recordSearchHistory', async () => {
    const customContext = { page: '/custom', source: 'test' };
    await publicApi.recordSearchHistory({
      search_query: 'drums',
      search_type: 'text',
      search_context: customContext,
    });

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    const body = JSON.parse(options.body as string) as { search_context?: Record<string, unknown> };
    // Should use the user-supplied context, not generate default
    expect(body.search_context).toEqual(customContext);
  });

  it('calls searchWithNaturalLanguage without optional params', async () => {
    await publicApi.searchWithNaturalLanguage('yoga');

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    const requestUrl = new URL(calledUrl);
    expect(requestUrl.searchParams.get('q')).toBe('yoga');
    expect(requestUrl.searchParams.has('skill_level')).toBe(false);
    expect(requestUrl.searchParams.has('subcategory_id')).toBe(false);
  });

  it('omits guest session header when cookie value is empty', async () => {
    document.cookie = 'guest_id=';
    const getItemSpy = jest.spyOn(Storage.prototype, 'getItem').mockReturnValue(null);

    await publicApi.getRecentSearches();

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = options.headers as Record<string, string>;
    // decodeURIComponent('') is '' which is falsy, so header should not be set
    expect(headers['X-Guest-Session-ID']).toBeUndefined();
    getItemSpy.mockRestore();
  });
});

describe('protectedApi — additional branch coverage', () => {
  const originalFetch = global.fetch;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: jest.fn() },
      json: async () => ({}),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;
    document.cookie = 'guest_id=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
  });

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error - cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('getBookings with no params sends no query string', async () => {
    await protectedApi.getBookings();

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    const requestUrl = new URL(calledUrl);
    // No params at all
    expect(Array.from(requestUrl.searchParams.entries())).toHaveLength(0);
  });

  it('getBookings skips status param when undefined', async () => {
    await protectedApi.getBookings({ upcoming: true });

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    const requestUrl = new URL(calledUrl);
    expect(requestUrl.searchParams.get('upcoming')).toBe('true');
    expect(requestUrl.searchParams.has('status')).toBe(false);
  });

  it('getBookings with signal passes AbortSignal', async () => {
    const controller = new AbortController();
    await protectedApi.getBookings({ signal: controller.signal });

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(options.signal).toBe(controller.signal);
  });

  it('getInstructorBookings with no params sends empty options', async () => {
    await protectedApi.getInstructorBookings();

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    const requestUrl = new URL(calledUrl);
    expect(Array.from(requestUrl.searchParams.entries())).toHaveLength(0);
  });

  it('getInstructorBookings passes signal correctly', async () => {
    const controller = new AbortController();
    await protectedApi.getInstructorBookings({ signal: controller.signal });

    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect(options.signal).toBe(controller.signal);
  });

  it('getInstructorBookings with per_page under 100 keeps original value', async () => {
    await protectedApi.getInstructorBookings({ per_page: 25 });

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    const requestUrl = new URL(calledUrl);
    expect(requestUrl.searchParams.get('per_page')).toBe('25');
  });

  it('getPlaceDetails without provider or signal', async () => {
    await getPlaceDetails({ place_id: 'place-2' });

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    const requestUrl = new URL(calledUrl);
    expect(requestUrl.searchParams.get('place_id')).toBe('place-2');
    expect(requestUrl.searchParams.has('provider')).toBe(false);
  });

  it('normalizeBookingStatus returns undefined for empty string', async () => {
    // passing status as '' which is falsy
    await protectedApi.getBookings({ status: '' as unknown as undefined });

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    const requestUrl = new URL(calledUrl);
    expect(requestUrl.searchParams.has('status')).toBe(false);
  });

  it('getInstructorUpcomingBookings caps per_page at 100', async () => {
    await protectedApi.getInstructorUpcomingBookings(1, 200);

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    const requestUrl = new URL(calledUrl);
    expect(requestUrl.searchParams.get('per_page')).toBe('100');
  });

  it('getInstructorCompletedBookings caps per_page at 100', async () => {
    await protectedApi.getInstructorCompletedBookings(1, 150);

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    const requestUrl = new URL(calledUrl);
    expect(requestUrl.searchParams.get('per_page')).toBe('100');
  });
});

describe('API endpoint constants', () => {
  it('exports PUBLIC_ENDPOINTS with expected structure', () => {
    expect(PUBLIC_ENDPOINTS.instructors.list).toBe('/api/v1/instructors');
    expect(PUBLIC_ENDPOINTS.instructors.profile('abc123')).toBe('/api/v1/instructors/abc123');
    expect(PUBLIC_ENDPOINTS.instructors.availability('abc123')).toBe('/api/v1/public/instructors/abc123/availability');
  });

  it('exports PROTECTED_ENDPOINTS with expected structure', () => {
    expect(PROTECTED_ENDPOINTS.bookings.create).toBe('/api/v1/bookings');
    expect(PROTECTED_ENDPOINTS.bookings.list).toBe('/api/v1/bookings');
    expect(PROTECTED_ENDPOINTS.bookings.get('booking123')).toBe('/api/v1/bookings/booking123');
    expect(PROTECTED_ENDPOINTS.bookings.cancel('booking123')).toBe('/api/v1/bookings/booking123/cancel');
    expect(PROTECTED_ENDPOINTS.instructor.bookings.list).toBe('/api/v1/instructor-bookings/');
  });
});

describe('SSR code paths', () => {
  const originalFetch = global.fetch;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: jest.fn() },
      json: async () => ({}),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;
  });

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error - cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('returns null for guest session when document is undefined', async () => {
    const originalDocument = global.document;
    // @ts-expect-error - simulate SSR environment
    delete global.document;

    try {
      // Call publicApi method that uses getGuestSessionId internally
      await publicApi.getRecentSearches();
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const options = fetchMock.mock.calls[0][1] as RequestInit;
      const headers = options.headers as Record<string, string>;
      // Guest session header should not be set when document is undefined
      expect(headers['X-Guest-Session-ID']).toBeUndefined();
    } finally {
      global.document = originalDocument;
    }
  });

  it('handles sessionStorage error in guest session fallback', async () => {
    document.cookie = 'guest_id=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    const getItemSpy = jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('Storage access denied');
    });

    try {
      await publicApi.getRecentSearches();
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const options = fetchMock.mock.calls[0][1] as RequestInit;
      const headers = options.headers as Record<string, string>;
      // Should gracefully handle the error and not set guest header
      expect(headers['X-Guest-Session-ID']).toBeUndefined();
    } finally {
      getItemSpy.mockRestore();
    }
  });

  it('uses proxy-adjusted URL in browser path of cleanFetch', async () => {
    // In jsdom (browser-like environment), cleanFetch goes through the window branch
    // which calls withApiBase to adjust the endpoint with proxy prefix
    await cleanFetch('/api/v1/test-endpoint');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toContain('/api/v1/test-endpoint');
    // withApiBase should be called in browser path
    expect(withApiBase).toHaveBeenCalledWith('/api/v1/test-endpoint');
  });

  it('skips proxy adjustment when endpoint already starts with /api/proxy', async () => {
    await cleanFetch('/api/proxy/api/v1/already-proxied');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    // Should NOT call withApiBase since path already starts with /api/proxy
    expect(withApiBase).not.toHaveBeenCalled();
    expect(calledUrl).toContain('/api/proxy/api/v1/already-proxied');
  });

  it('handles JSON parse failure gracefully', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: jest.fn() },
      json: async () => { throw new SyntaxError('Unexpected end of JSON'); },
    });

    const response = await cleanFetch('/api/v1/test');

    // Should surface a typed error instead of silently returning null data.
    expect(response.status).toBe(200);
    expect(response.error).toBe('Invalid response format');
    expect(response.data).toBeUndefined();
  });

  it('returns 429 without retryAfterSeconds when header is missing', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 429,
      headers: { get: jest.fn(() => null) },
      json: async () => ({}),
    });

    const response = await cleanFetch('/api/v1/search');

    expect(response.status).toBe(429);
    expect(response.error).toBe('Our hamsters are sprinting. Please try again shortly.');
    expect((response as { retryAfterSeconds?: number }).retryAfterSeconds).toBeUndefined();
  });

  it('returns fallback error message when detail is null', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      headers: { get: jest.fn() },
      json: async () => ({ detail: null }),
    });

    const response = await cleanFetch('/api/v1/test');

    expect(response.status).toBe(500);
    expect(response.error).toBe('Error: 500');
  });
});
