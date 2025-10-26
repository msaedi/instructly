'use client';

import { useEffect, useState } from 'react';

type Key = string | null;

export function useSWRCustom<T>(key: Key, fetcher: (key: string) => Promise<T>, opts?: { dedupingInterval?: number }) {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<unknown>(undefined);
  const [isLoading, setIsLoading] = useState<boolean>(!!key);
  useEffect(() => {
    let cancelled = false;
    let timeout: number | null = null;
    const run = async () => {
      if (!key) {
        setIsLoading(false);
        return;
      }
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
    void run();
    if (opts?.dedupingInterval && opts.dedupingInterval > 0) {
      timeout = window.setInterval(() => {
        void run();
      }, opts.dedupingInterval);
    }
    return () => {
      cancelled = true;
      if (timeout) window.clearInterval(timeout);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return { data, error, isLoading } as const;
}
