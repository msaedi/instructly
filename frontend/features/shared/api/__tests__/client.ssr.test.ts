/**
 * @jest-environment node
 *
 * Tests for SSR-only code paths in client.ts where `typeof window === 'undefined'`.
 * These branches are unreachable in the default jsdom environment.
 */

// Must mock BEFORE importing the module under test
jest.mock('@/lib/sessionTracking', () => ({
  getSessionId: jest.fn().mockReturnValue(null),
  refreshSession: jest.fn(),
}));

jest.mock('@/lib/apiBase', () => ({
  withApiBase: jest.fn((path: string) => path),
  withApiBaseForRequest: jest.fn((path: string) => path),
}));

jest.mock('@/lib/env', () => ({
  NEXT_PUBLIC_APP_URL: 'https://ssr-app.example.com',
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    error: jest.fn(),
    warn: jest.fn(),
    info: jest.fn(),
    debug: jest.fn(),
  },
}));

import { cleanFetch } from '@/features/shared/api/client';

describe('cleanFetch SSR code paths (node environment)', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error - cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('uses getRequestOrigin SSR fallback when window is undefined', async () => {
    // In node environment, typeof window === 'undefined'
    // This exercises lines 62-65 (getRequestOrigin) and 198-199 (SSR path in cleanFetch)
    expect(typeof globalThis.window).toBe('undefined');

    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ssr: true }),
      headers: { get: jest.fn() },
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const response = await cleanFetch<{ ssr: boolean }>('/api/v1/ssr-test');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0]?.[0] as string;
    // Should use the APP_URL from env as the base URL
    expect(calledUrl).toBe('https://ssr-app.example.com/api/v1/ssr-test');
    expect(response.status).toBe(200);
    expect(response.data).toEqual({ ssr: true });
  });

  it('falls back to localhost when APP_URL is not set', async () => {
    // Override the env mock temporarily
    jest.resetModules();
    jest.doMock('@/lib/env', () => ({
      NEXT_PUBLIC_APP_URL: '',
    }));
    jest.doMock('@/lib/sessionTracking', () => ({
      getSessionId: jest.fn().mockReturnValue(null),
      refreshSession: jest.fn(),
    }));
    jest.doMock('@/lib/apiBase', () => ({
      withApiBase: jest.fn((path: string) => path),
      withApiBaseForRequest: jest.fn((path: string) => path),
    }));
    jest.doMock('@/lib/logger', () => ({
      logger: {
        error: jest.fn(),
        warn: jest.fn(),
        info: jest.fn(),
        debug: jest.fn(),
      },
    }));

    const { cleanFetch: ssrCleanFetch } = require('@/features/shared/api/client') as { cleanFetch: typeof cleanFetch };

    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
      headers: { get: jest.fn() },
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await ssrCleanFetch('/api/v1/fallback-test');

    const calledUrl = fetchMock.mock.calls[0]?.[0] as string;
    // Should fall back to http://localhost:3000
    expect(calledUrl).toBe('http://localhost:3000/api/v1/fallback-test');
  });

  it('does not include analytics headers in SSR (no window)', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
      headers: { get: jest.fn() },
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await cleanFetch('/api/v1/no-analytics');

    const options = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const headers = options.headers as Record<string, string>;
    // No window means no X-Session-ID or X-Search-Origin
    expect(headers['X-Session-ID']).toBeUndefined();
    expect(headers['X-Search-Origin']).toBeUndefined();
  });

  it('handles SSR query params correctly', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
      headers: { get: jest.fn() },
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    await cleanFetch('/api/v1/with-params', {
      params: { q: 'test', page: 1 },
    });

    const calledUrl = fetchMock.mock.calls[0]?.[0] as string;
    const url = new URL(calledUrl);
    expect(url.searchParams.get('q')).toBe('test');
    expect(url.searchParams.get('page')).toBe('1');
  });

  it('handles error responses in SSR environment', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'Internal server error' }),
      headers: { get: jest.fn() },
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const response = await cleanFetch('/api/v1/ssr-error');

    expect(response.status).toBe(500);
    expect(response.error).toBe('Internal server error');
  });

  it('handles network error in SSR environment', async () => {
    const fetchMock = jest.fn().mockRejectedValue(new Error('ECONNREFUSED'));
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const response = await cleanFetch('/api/v1/ssr-network-fail');

    expect(response.status).toBe(0);
    expect(response.error).toBe('ECONNREFUSED');
  });
});
