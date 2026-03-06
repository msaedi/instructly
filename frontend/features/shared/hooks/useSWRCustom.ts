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
  const lastFetchKeyRef = useRef<Key>(null);
  const inFlightPromiseRef = useRef<Promise<T> | null>(null);
  const inFlightKeyRef = useRef<Key>(null);
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
      const shouldDedupe =
        !skipDedupe &&
        key === lastFetchKeyRef.current &&
        now - lastFetchRef.current < dedupingInterval;
      const inFlightForKey =
        shouldDedupe &&
        inFlightKeyRef.current === key &&
        inFlightPromiseRef.current;

      if (shouldDedupe && !inFlightForKey) {
        return;
      }

      let fetchPromise = inFlightForKey;
      if (!fetchPromise) {
        lastFetchRef.current = now;
        lastFetchKeyRef.current = key;
        fetchPromise = fetcher(key);
        inFlightKeyRef.current = key;
        inFlightPromiseRef.current = fetchPromise;
      }

      setIsLoading(true);
      try {
        const result = await fetchPromise;
        if (!cancelled) setData(result);
      } catch (e) {
        if (!cancelled) setError(e);
      } finally {
        if (inFlightPromiseRef.current === fetchPromise) {
          inFlightPromiseRef.current = null;
          inFlightKeyRef.current = null;
        }
        if (!cancelled) setIsLoading(false);
      }
    };

    // Initial fetch participates in dedupe so rapid rerenders don't double-request.
    void run();

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
