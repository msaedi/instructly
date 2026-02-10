'use client';

import { useEffect, useRef, useState } from 'react';

type Key = string | null;

/**
 * Lightweight SWR-like hook for data fetching.
 *
 * Options:
 * - dedupingInterval: Time window (ms) during which duplicate requests to the same key are ignored.
 *   This does NOT cause polling - it only prevents re-fetching if called multiple times in quick succession.
 * - refreshInterval: If provided, refetch data at this interval (ms). Use sparingly.
 */
export function useSWRCustom<T>(
  key: Key,
  fetcher: (key: string) => Promise<T>,
  opts?: { dedupingInterval?: number; refreshInterval?: number }
) {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<unknown>(undefined);
  const [isLoading, setIsLoading] = useState<boolean>(!!key);

  // Track last fetch time for deduplication
  const lastFetchRef = useRef<number>(0);
  const dedupingInterval = opts?.dedupingInterval ?? 2000;
  const refreshInterval = opts?.refreshInterval;

  useEffect(() => {
    let cancelled = false;
    let refreshTimeout: ReturnType<typeof setInterval> | null = null;

    const run = async (skipDedupe = false) => {
      if (!key) {
        setIsLoading(false);
        return;
      }

      // Dedupe: skip if we fetched recently (unless skipDedupe is true)
      const now = Date.now();
      if (!skipDedupe && now - lastFetchRef.current < dedupingInterval) {
        return;
      }
      lastFetchRef.current = now;

      setIsLoading(true);
      try {
        const result = await fetcher(key);
        if (!cancelled) setData(result);
      } catch (e) {
        if (!cancelled) setError(e);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    // Initial fetch (skip dedupe check for first fetch)
    void run(true);

    // Optional polling if refreshInterval is explicitly set
    if (refreshInterval && refreshInterval > 0) {
      refreshTimeout = setInterval(() => {
        void run(true);
      }, refreshInterval);
    }

    return () => {
      cancelled = true;
      if (refreshTimeout) clearInterval(refreshTimeout);
    };
  }, [dedupingInterval, fetcher, key, refreshInterval]);

  return { data, error, isLoading } as const;
}
