import {
  __resetSessionRefreshForTests,
  fetchWithSessionRefresh,
} from '@/lib/auth/sessionRefresh';

jest.mock('@/lib/apiBase', () => ({
  withApiBaseForRequest: (path: string) => path,
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    warn: jest.fn(),
  },
}));

describe('session refresh interceptor', () => {
  const originalFetch = global.fetch;
  const makeResponse = (status: number): Response =>
    ({ status, ok: status >= 200 && status < 300 } as unknown as Response);

  beforeEach(() => {
    jest.clearAllMocks();
    __resetSessionRefreshForTests();
  });

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('retries the original request once after successful refresh', async () => {
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce(makeResponse(401))
      .mockResolvedValueOnce(makeResponse(200))
      .mockResolvedValueOnce(makeResponse(200));
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const response = await fetchWithSessionRefresh('/api/v1/auth/me', {
      method: 'GET',
      credentials: 'include',
    });

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/auth/refresh');
  });

  it('queues concurrent 401s and performs exactly one refresh call', async () => {
    let appCalls = 0;
    let resolveRefresh: ((response: Response) => void) | undefined;
    const refreshPromise = new Promise<Response>((resolve) => {
      resolveRefresh = resolve;
    });

    const fetchMock = jest.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.includes('/api/v1/auth/refresh')) {
        return refreshPromise;
      }
      if (url.includes('/api/v1/auth/me')) {
        appCalls += 1;
        if (appCalls <= 2) {
          return Promise.resolve(makeResponse(401));
        }
        return Promise.resolve(makeResponse(200));
      }
      return Promise.resolve(makeResponse(204));
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const first = fetchWithSessionRefresh('/api/v1/auth/me', {
      method: 'GET',
      credentials: 'include',
    });
    const second = fetchWithSessionRefresh('/api/v1/auth/me', {
      method: 'GET',
      credentials: 'include',
    });

    resolveRefresh?.(makeResponse(200));
    const [firstResponse, secondResponse] = await Promise.all([first, second]);

    expect(firstResponse.status).toBe(200);
    expect(secondResponse.status).toBe(200);
    const refreshCalls = fetchMock.mock.calls.filter((call) =>
      String(call[0]).includes('/api/v1/auth/refresh')
    ).length;
    expect(refreshCalls).toBe(1);
  });

  it('does not recurse when /auth/refresh itself returns 401', async () => {
    const fetchMock = jest.fn().mockResolvedValue(makeResponse(401));
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const response = await fetchWithSessionRefresh('/api/v1/auth/refresh', {
      method: 'POST',
      credentials: 'include',
    });

    expect(response.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('dispatches session-expired event when refresh fails', async () => {
    const fetchMock = jest.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.includes('/api/v1/auth/refresh')) {
        return Promise.resolve(makeResponse(401));
      }
      if (url.includes('/api/v1/public/logout')) {
        return Promise.resolve(makeResponse(204));
      }
      return Promise.resolve(makeResponse(401));
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const expiredListener = jest.fn();
    window.addEventListener('instainstru:session-expired', expiredListener as EventListener);

    const response = await fetchWithSessionRefresh('/api/v1/auth/me', {
      method: 'GET',
      credentials: 'include',
    });

    expect(response.status).toBe(401);
    expect(expiredListener).toHaveBeenCalled();
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('/api/v1/public/logout'))).toBe(true);

    window.removeEventListener('instainstru:session-expired', expiredListener as EventListener);
  });
});
