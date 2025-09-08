// frontend/hooks/useDatabaseData.ts
/**
 * Hook for fetching and managing database monitoring data
 */

import { useState, useEffect, useCallback } from 'react';
import { logger } from '@/lib/logger';
import { databaseApi } from '@/lib/databaseApi';
import type { DatabaseStats } from '@/lib/databaseApi';

interface UseDatabaseDataReturn {
  data: DatabaseStats | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useDatabaseData(token: string | null): UseDatabaseDataReturn {
  const [data, setData] = useState<DatabaseStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const stats = await databaseApi.getStats(token ?? '');
      setData(stats);
    } catch (err) {
      logger.error('Failed to fetch database data', err as Error);
      setError(err instanceof Error ? err.message : 'Failed to fetch database data');
    } finally {
      setLoading(false);
    }
  }, [token]);

  // Fetch data on mount
  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      void fetchData();
    }, 30 * 1000);

    return () => clearInterval(interval);
  }, [fetchData]);

  return {
    data,
    loading,
    error,
    refetch: fetchData,
  };
}
