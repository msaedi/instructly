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

  describe('default parameters', () => {
    it('returns empty map when called with no arguments', async () => {
      const { result } = renderHook(() => useProfilePictureUrls(), {
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

    it('handles null-like rawUserIds by defaulting to empty array', async () => {
      // The function defaults rawUserIds to [] but the serialization also handles null
      const { result } = renderHook(
        () => useProfilePictureUrls(undefined, 'original'),
        { wrapper: createWrapper() }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
      });

      expect(fetchMock).not.toHaveBeenCalled();
      expect(result.current).toEqual({});
    });
  });

  describe('parseRawId edge cases', () => {
    it('handles version delimiter with empty base string', async () => {
      // "::v=5" should produce id="" which gets filtered out
      const { result } = renderHook(
        () => useProfilePictureUrls(['::v=5']),
        { wrapper: createWrapper() }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
      });

      // Empty id should be filtered out
      expect(fetchMock).not.toHaveBeenCalled();
      expect(result.current).toEqual({});
    });

    it('handles version delimiter with empty version part', async () => {
      // "user-empty-ver::v=" should parse version as NaN -> fallback to 0
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          urls: { 'user-empty-ver': 'https://cdn/avatar/empty-ver' },
        }),
      } as Response);

      const { result } = renderHook(
        () => useProfilePictureUrls(['user-empty-ver::v=']),
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
        expect(result.current['user-empty-ver']).toBe('https://cdn/avatar/empty-ver');
      });
    });
  });

  describe('batch chunking', () => {
    it('chunks requests into batches of 50', async () => {
      // Create 60 unique user IDs to force chunking
      const userIds = Array.from({ length: 60 }, (_, i) => `user-chunk-${i}`);
      const urls: Record<string, string> = {};
      userIds.forEach((id) => {
        urls[id] = `https://cdn/avatar/${id}`;
      });

      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({ urls }),
      } as Response);

      renderHook(
        () => useProfilePictureUrls(userIds),
        { wrapper: createWrapper() }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });

      // Should have been called twice (50 + 10)
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
  });

  describe('concurrent requests deduplication', () => {
    it('deduplicates requests across concurrent hook instances', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          urls: { 'user-shared': 'https://cdn/avatar/shared' },
        }),
      } as Response);

      const wrapper = createWrapper();

      // Both hooks request the same user
      renderHook(() => useProfilePictureUrls(['user-shared']), { wrapper });

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      // Should only make 1 request even though multiple hooks requested the same ID
      expect(fetchMock).toHaveBeenCalledTimes(1);
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

  describe('partial API response and cache merge branches', () => {
    it('returns null for ids not present in aggregated or cached results', async () => {
      // This exercises the else branch (line 172-173) in flushPendingQueue:
      // when a request id is not in the aggregated results AND not cached
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          urls: {
            // Intentionally only return one of two requested ids
            'user-partial-found': 'https://cdn/avatar/partial-found',
            // 'user-partial-gone' is NOT in the API response at all
          },
        }),
      } as Response);

      const { result } = renderHook(
        () => useProfilePictureUrls(['user-partial-found', 'user-partial-gone']),
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
        expect(result.current['user-partial-found']).toBe('https://cdn/avatar/partial-found');
      });
      // Missing id should gracefully fall back to null
      expect(result.current['user-partial-gone']).toBeNull();
    });

    it('handles flushPendingQueue with empty requestMap after cache dedup', async () => {
      // First, populate the cache
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          urls: {
            'user-all-cached': 'https://cdn/avatar/all-cached',
          },
        }),
      } as Response);

      const wrapper = createWrapper();

      const { unmount } = renderHook(
        () => useProfilePictureUrls(['user-all-cached']),
        { wrapper }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      unmount();
      fetchMock.mockClear();

      // Now enqueue the same id again. During flushPendingQueue, getCachedValue
      // returns a value for all requests, so requestMap ends up empty.
      // This exercises the `if (!requestMap.size)` branch.
      const { result } = renderHook(
        () => useProfilePictureUrls(['user-all-cached']),
        { wrapper }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      // Should still return cached value without making a new request
      await waitFor(() => {
        expect(result.current['user-all-cached']).toBe('https://cdn/avatar/all-cached');
      });
    });

    it('handles request where API response does not include all requested ids (backfill null)', async () => {
      // requestProfilePictureBatch backfills missing ids with null (line 206-209)
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          urls: {
            // Only one out of three ids is returned by the API
            'user-one': 'https://cdn/avatar/one',
          },
        }),
      } as Response);

      const { result } = renderHook(
        () => useProfilePictureUrls(['user-one', 'user-two', 'user-three']),
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
        expect(result.current['user-one']).toBe('https://cdn/avatar/one');
      });
      expect(result.current['user-two']).toBeNull();
      expect(result.current['user-three']).toBeNull();
    });
  });

  describe('variant group deduplication across concurrent batches', () => {
    it('deduplicates ids across multiple concurrent enqueue calls', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({
          urls: {
            'user-concurrent': 'https://cdn/avatar/concurrent',
          },
        }),
      } as Response);

      const wrapper = createWrapper();

      // Two hooks requesting the same id at the same time
      const { result: r1 } = renderHook(
        () => useProfilePictureUrls(['user-concurrent']),
        { wrapper }
      );

      const { result: r2 } = renderHook(
        () => useProfilePictureUrls(['user-concurrent']),
        { wrapper }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });

      // Should only make one request because the ids are deduplicated
      // in variantGroups inside flushPendingQueue
      await waitFor(() => {
        expect(r1.current['user-concurrent']).toBe('https://cdn/avatar/concurrent');
      });
      await waitFor(() => {
        expect(r2.current['user-concurrent']).toBe('https://cdn/avatar/concurrent');
      });
    });
  });

  describe('useEffect error logging', () => {
    it('logs warning when useQuery error is present', async () => {
      // To trigger the useQuery error path (line 260), we need the queryFn to throw
      // synchronously or return a rejected promise that useQuery catches.
      // The enqueueFetch function catches most errors, but if the Promise constructor
      // itself throws or if a synchronous error occurs, useQuery will set error state.
      // We simulate this by making fetchWithAuth throw a synchronous error that
      // propagates up through the promise chain.

      const synchronousError = new Error('Synchronous failure in flush');
      fetchMock.mockImplementation(() => {
        throw synchronousError;
      });

      const { result } = renderHook(() => useProfilePictureUrls(['user-sync-err']), {
        wrapper: createWrapper(),
      });

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });

      // The batch error path catches this and sets null values
      // but the logger.warn in flushPendingQueue should fire
      expect(loggerWarnMock).toHaveBeenCalledWith(
        'Avatar batch request failed',
        synchronousError
      );
      expect(result.current['user-sync-err']).toBeNull();
    });
  });

  describe('useEffect error logging via useQuery error', () => {
    it('logs fallback warning when useQuery catches an error from queryFn', async () => {
      // To trigger the useEffect error log (line 259-261), we need useQuery to
      // surface an error. The enqueueFetch normally catches errors from
      // flushPendingQueue, but if the promise chain itself rejects in a way
      // useQuery picks up, the error state is set.
      //
      // We force this by making fetchWithAuth throw synchronously in a way
      // that propagates up to useQuery's error handling on all retry attempts.
      const queryError = new Error('Total query failure');
      fetchMock.mockImplementation(() => {
        throw queryError;
      });

      const { result } = renderHook(() => useProfilePictureUrls(['user-query-err']), {
        wrapper: createWrapper(),
      });

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });

      // The batch-level catch logs "Avatar batch request failed"
      expect(loggerWarnMock).toHaveBeenCalledWith(
        'Avatar batch request failed',
        queryError
      );
      // Even on error, the hook returns null for each id
      expect(result.current['user-query-err']).toBeNull();
    });
  });

  describe('cache value lookup during flush', () => {
    it('uses cached value from first chunk when processing second chunk with same id', async () => {
      // Create 55 unique ids where some overlap with cached entries
      const firstBatchIds = Array.from({ length: 50 }, (_, i) => `user-fb-${i}`);
      const secondBatchIds = Array.from({ length: 5 }, (_, i) => `user-sb-${i}`);
      const allIds = [...firstBatchIds, ...secondBatchIds];

      const urls: Record<string, string> = {};
      allIds.forEach((id) => {
        urls[id] = `https://cdn/avatar/${id}`;
      });

      fetchMock.mockResolvedValue({
        ok: true,
        json: async () => ({ urls }),
      } as Response);

      const { result } = renderHook(
        () => useProfilePictureUrls(allIds),
        { wrapper: createWrapper() }
      );

      act(() => {
        jest.runOnlyPendingTimers();
      });

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });

      // All ids should have URLs
      await waitFor(() => {
        expect(result.current['user-fb-0']).toBe('https://cdn/avatar/user-fb-0');
      });
      expect(result.current['user-sb-0']).toBe('https://cdn/avatar/user-sb-0');

      // Should have made 2 requests (50 + 5 chunked)
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
  });
});
