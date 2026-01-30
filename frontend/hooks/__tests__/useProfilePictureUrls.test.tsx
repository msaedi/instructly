import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { fetchWithAuth } from '@/lib/api';
import { logger } from '@/lib/logger';
import {
  useProfilePictureUrls,
  __clearAvatarCacheForTesting,
} from '../useProfilePictureUrls';

jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    warn: jest.fn(),
  },
}));

const fetchMock = fetchWithAuth as jest.MockedFunction<typeof fetchWithAuth>;
const loggerWarnMock = logger.warn as jest.Mock;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'QueryClientWrapper';
  return Wrapper;
};

describe('useProfilePictureUrls', () => {
  beforeEach(() => {
    __clearAvatarCacheForTesting();
    jest.useFakeTimers();
    fetchMock.mockReset();
    loggerWarnMock.mockReset();
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  it('batches multiple ids into a single request', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        urls: {
          'user-a': 'https://cdn/avatar/a',
          'user-b': null,
        },
      }),
    } as Response);

    const { result } = renderHook(() => useProfilePictureUrls(['user-a', 'user-b']), {
      wrapper: createWrapper(),
    });

    expect(result.current['user-a']).toBeNull();
    expect(result.current['user-b']).toBeNull();

    act(() => {
      jest.runOnlyPendingTimers();
    });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const firstCall = fetchMock.mock.calls[0];
    if (!firstCall) {
      throw new Error('fetchWithAuth was not called');
    }
    const [requestUrl] = firstCall;
    expect(requestUrl).toContain('/api/v1/users/profile-picture-urls?');
    await waitFor(() => {
      expect(result.current['user-a']).toBe('https://cdn/avatar/a');
    });
    expect(result.current['user-b']).toBeNull();
  });

  it('falls back to placeholders when the request fails', async () => {
    fetchMock.mockRejectedValue(new Error('network error'));

    const { result } = renderHook(() => useProfilePictureUrls(['user-x']), {
      wrapper: createWrapper(),
    });

    act(() => {
      jest.runOnlyPendingTimers();
    });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current['user-x']).toBeNull();
  });

  describe('edge cases', () => {
    it('returns empty map for empty user ids array', async () => {
      const { result } = renderHook(() => useProfilePictureUrls([]), {
        wrapper: createWrapper(),
      });

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
      });

      expect(fetchMock).not.toHaveBeenCalled();
      expect(result.current).toEqual({});
    });

    it('handles empty string user id gracefully', async () => {
      const { result } = renderHook(() => useProfilePictureUrls(['']), {
        wrapper: createWrapper(),
      });

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
      });

      // Empty ids are filtered out
      expect(fetchMock).not.toHaveBeenCalled();
      expect(result.current).toEqual({});
    });

    it('handles user ids with version delimiter', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          urls: {
            'user-versioned': 'https://cdn/avatar/versioned',
          },
        }),
      } as Response);

      const { result } = renderHook(
        () => useProfilePictureUrls(['user-versioned::v=2']),
        { wrapper: createWrapper() }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(fetchMock).toHaveBeenCalledTimes(1);
      await waitFor(() => {
        expect(result.current['user-versioned']).toBe('https://cdn/avatar/versioned');
      });
    });

    it('handles malformed version in delimiter', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          urls: {
            'user-bad': 'https://cdn/avatar/bad',
          },
        }),
      } as Response);

      const { result } = renderHook(
        () => useProfilePictureUrls(['user-bad::v=not-a-number']),
        { wrapper: createWrapper() }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(fetchMock).toHaveBeenCalledTimes(1);
      await waitFor(() => {
        expect(result.current['user-bad']).toBe('https://cdn/avatar/bad');
      });
    });

    it('deduplicates identical user ids', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          urls: {
            'user-dup': 'https://cdn/avatar/dup',
          },
        }),
      } as Response);

      renderHook(
        () => useProfilePictureUrls(['user-dup', 'user-dup', 'user-dup']),
        { wrapper: createWrapper() }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(fetchMock).toHaveBeenCalledTimes(1);
      // Should only request one id
      const firstCall = fetchMock.mock.calls[0];
      if (!firstCall) throw new Error('fetchWithAuth was not called');
      const [requestUrl] = firstCall;
      expect(requestUrl).toContain('ids=user-dup');
      expect(requestUrl).not.toContain('user-dup,user-dup');
    });
  });

  describe('error handling', () => {
    it('handles HTTP error response', async () => {
      fetchMock.mockResolvedValue({
        ok: false,
        status: 500,
      } as Response);

      const { result } = renderHook(() => useProfilePictureUrls(['user-err']), {
        wrapper: createWrapper(),
      });

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      // Should fall back to null
      expect(result.current['user-err']).toBeNull();
    });

    it('handles timeout via AbortController', async () => {
      // Create a mock that never resolves to simulate timeout
      fetchMock.mockImplementation(() => {
        return new Promise((_, reject) => {
          // The abort signal should cause rejection
          setTimeout(() => reject(new Error('Aborted')), 100);
        });
      });

      const { result } = renderHook(() => useProfilePictureUrls(['user-timeout']), {
        wrapper: createWrapper(),
      });

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(result.current['user-timeout']).toBeNull();
    });

    it('logs warning when batch request fails', async () => {
      const testError = new Error('batch failure');
      fetchMock.mockRejectedValue(testError);

      const { result } = renderHook(() => useProfilePictureUrls(['user-log']), {
        wrapper: createWrapper(),
      });

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(loggerWarnMock).toHaveBeenCalledWith(
        'Avatar batch request failed',
        testError
      );
      expect(result.current['user-log']).toBeNull();
    });
  });

  describe('caching behavior', () => {
    it('uses cached values on subsequent renders', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          urls: {
            'user-cache': 'https://cdn/avatar/cache',
          },
        }),
      } as Response);

      const wrapper = createWrapper();

      // First render
      const { result, rerender } = renderHook(
        () => useProfilePictureUrls(['user-cache']),
        { wrapper }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      await waitFor(() => {
        expect(result.current['user-cache']).toBe('https://cdn/avatar/cache');
      });
      expect(fetchMock).toHaveBeenCalledTimes(1);

      // Second render - should use cache
      rerender();

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
      });

      // Should still have cached value
      expect(result.current['user-cache']).toBe('https://cdn/avatar/cache');
    });

    it('handles response missing some requested ids', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          urls: {
            'user-found': 'https://cdn/avatar/found',
            // user-missing is not in the response
          },
        }),
      } as Response);

      const { result } = renderHook(
        () => useProfilePictureUrls(['user-found', 'user-missing']),
        { wrapper: createWrapper() }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      await waitFor(() => {
        expect(result.current['user-found']).toBe('https://cdn/avatar/found');
      });
      // Missing id should be set to null
      expect(result.current['user-missing']).toBeNull();
    });

    it('returns all cached values without making a request', async () => {
      // First, populate the cache
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          urls: {
            'user-cached-a': 'https://cdn/avatar/a',
            'user-cached-b': 'https://cdn/avatar/b',
          },
        }),
      } as Response);

      const wrapper = createWrapper();

      // First render to populate cache
      const { result: firstResult, unmount } = renderHook(
        () => useProfilePictureUrls(['user-cached-a', 'user-cached-b']),
        { wrapper }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      await waitFor(() => {
        expect(firstResult.current['user-cached-a']).toBe('https://cdn/avatar/a');
      });
      expect(fetchMock).toHaveBeenCalledTimes(1);

      unmount();
      fetchMock.mockClear();

      // Second render with same ids - should use cache completely
      const { result: secondResult } = renderHook(
        () => useProfilePictureUrls(['user-cached-a', 'user-cached-b']),
        { wrapper }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      // Values should be available from cache
      await waitFor(() => {
        expect(secondResult.current['user-cached-a']).toBe('https://cdn/avatar/a');
      });
      expect(secondResult.current['user-cached-b']).toBe('https://cdn/avatar/b');
    });

    it('handles expired cache entries', async () => {
      // Mock Date.now to control time
      const originalDateNow = Date.now;
      let currentTime = 1000000;
      Date.now = () => currentTime;

      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          urls: {
            'user-expire': 'https://cdn/avatar/expire',
          },
        }),
      } as Response);

      const wrapper = createWrapper();

      // First render
      const { result, unmount } = renderHook(
        () => useProfilePictureUrls(['user-expire']),
        { wrapper }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      await waitFor(() => {
        expect(result.current['user-expire']).toBe('https://cdn/avatar/expire');
      });
      expect(fetchMock).toHaveBeenCalledTimes(1);

      unmount();
      fetchMock.mockClear();

      // Advance time past cache TTL (10 minutes = 600000ms)
      currentTime += 700000;

      // Fresh render after cache expiry
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          urls: {
            'user-expire': 'https://cdn/avatar/expire-new',
          },
        }),
      } as Response);

      const { result: expiredResult } = renderHook(
        () => useProfilePictureUrls(['user-expire']),
        { wrapper }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      // Should have fetched again due to cache expiry
      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledTimes(1);
      });

      await waitFor(() => {
        expect(expiredResult.current['user-expire']).toBe('https://cdn/avatar/expire-new');
      });

      // Restore Date.now
      Date.now = originalDateNow;
    });

    it('handles mixed cached and uncached ids', async () => {
      // This test exercises the path where some ids are cached and some need fetching
      const wrapper = createWrapper();

      // First, populate cache with one id
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          urls: {
            'user-partial-a': 'https://cdn/avatar/partial-a',
          },
        }),
      } as Response);

      const { result: firstResult, unmount } = renderHook(
        () => useProfilePictureUrls(['user-partial-a']),
        { wrapper }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      await waitFor(() => {
        expect(firstResult.current['user-partial-a']).toBe('https://cdn/avatar/partial-a');
      });

      unmount();
      fetchMock.mockClear();

      // Now request both cached and new id
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          urls: {
            'user-partial-b': 'https://cdn/avatar/partial-b',
          },
        }),
      } as Response);

      const { result: secondResult } = renderHook(
        () => useProfilePictureUrls(['user-partial-a', 'user-partial-b']),
        { wrapper }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      // Cached value should be present immediately
      await waitFor(() => {
        expect(secondResult.current['user-partial-a']).toBe('https://cdn/avatar/partial-a');
      });
      await waitFor(() => {
        expect(secondResult.current['user-partial-b']).toBe('https://cdn/avatar/partial-b');
      });
    });
  });

  describe('variant support', () => {
    it('requests with default thumb variant', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          urls: { 'user-thumb': 'https://cdn/avatar/thumb' },
        }),
      } as Response);

      renderHook(() => useProfilePictureUrls(['user-thumb']), {
        wrapper: createWrapper(),
      });

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const firstCall = fetchMock.mock.calls[0];
      if (!firstCall) throw new Error('fetchWithAuth was not called');
      const [requestUrl] = firstCall;
      expect(requestUrl).toContain('variant=thumb');
    });

    it('requests with display variant', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          urls: { 'user-display': 'https://cdn/avatar/display' },
        }),
      } as Response);

      renderHook(() => useProfilePictureUrls(['user-display'], 'display'), {
        wrapper: createWrapper(),
      });

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const firstCall = fetchMock.mock.calls[0];
      if (!firstCall) throw new Error('fetchWithAuth was not called');
      const [requestUrl] = firstCall;
      expect(requestUrl).toContain('variant=display');
    });

    it('requests with original variant', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          urls: { 'user-original': 'https://cdn/avatar/original' },
        }),
      } as Response);

      renderHook(() => useProfilePictureUrls(['user-original'], 'original'), {
        wrapper: createWrapper(),
      });

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const firstCall = fetchMock.mock.calls[0];
      if (!firstCall) throw new Error('fetchWithAuth was not called');
      const [requestUrl] = firstCall;
      expect(requestUrl).toContain('variant=original');
    });
  });

  describe('test helper', () => {
    it('__clearAvatarCacheForTesting clears all state', () => {
      // This is implicitly tested by beforeEach, but let's be explicit
      expect(() => __clearAvatarCacheForTesting()).not.toThrow();
    });

    it('clears pending timer when called before flush', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          urls: { 'user-timer-test': 'https://cdn/avatar/timer' },
        }),
      } as Response);

      // Start a request but DON'T run the timer (leaves pending timer)
      renderHook(() => useProfilePictureUrls(['user-timer-test']), {
        wrapper: createWrapper(),
      });

      // Clear before timer fires - this should clear the pending timer (lines 276-277)
      expect(() => __clearAvatarCacheForTesting()).not.toThrow();

      // Run any remaining timers (there shouldn't be any)
      act(() => {
        jest.runOnlyPendingTimers();
      });

      // Should NOT have made a request since we cleared before flush
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('clears cache between test runs allowing fresh fetches', async () => {
      // First test: fetch and cache
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          urls: { 'user-clear-test': 'https://cdn/avatar/first' },
        }),
      } as Response);

      const wrapper1 = createWrapper();
      const { result: firstResult, unmount } = renderHook(
        () => useProfilePictureUrls(['user-clear-test']),
        { wrapper: wrapper1 }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      await waitFor(() => {
        expect(firstResult.current['user-clear-test']).toBe('https://cdn/avatar/first');
      });
      expect(fetchMock).toHaveBeenCalledTimes(1);

      unmount();

      // Clear module-level cache
      __clearAvatarCacheForTesting();
      fetchMock.mockClear();

      // Second test with fresh QueryClient: should fetch again because cache was cleared
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          urls: { 'user-clear-test': 'https://cdn/avatar/second' },
        }),
      } as Response);

      // Create fresh wrapper (new QueryClient)
      const wrapper2 = createWrapper();
      const { result: secondResult } = renderHook(
        () => useProfilePictureUrls(['user-clear-test']),
        { wrapper: wrapper2 }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      // Should have fetched again since both caches were cleared
      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledTimes(1);
      });
      await waitFor(() => {
        expect(secondResult.current['user-clear-test']).toBe('https://cdn/avatar/second');
      });
    });
  });
});
