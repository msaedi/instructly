import { cleanFetch, getPlaceDetails, protectedApi, publicApi, PUBLIC_ENDPOINTS, PROTECTED_ENDPOINTS } from '@/features/shared/api/client';
import { getSessionId, refreshSession } from '@/lib/sessionTracking';
import { withApiBase } from '@/lib/apiBase';

jest.mock('@/lib/sessionTracking', () => ({
  getSessionId: jest.fn(),
  refreshSession: jest.fn(),
}));

jest.mock('@/lib/apiBase', () => ({
  withApiBase: jest.fn((endpoint: string) => `/api/proxy${endpoint}`),
}));

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
});
