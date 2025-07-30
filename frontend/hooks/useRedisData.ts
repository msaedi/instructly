// frontend/hooks/useRedisData.ts
/**
 * Hook for fetching and managing Redis monitoring data
 */

import { useState, useEffect, useCallback } from 'react';
import { redisApi } from '@/lib/redisApi';
import type { RedisHealth, RedisStats, CeleryQueues } from '@/lib/redisApi';

interface RedisData {
  health: RedisHealth | null;
  stats: RedisStats | null;
  queues: CeleryQueues | null;
  testConnection: {
    status: string;
    ping: boolean;
    message: string;
  } | null;
}

interface UseRedisDataReturn {
  data: RedisData;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useRedisData(token: string | null): UseRedisDataReturn {
  const [data, setData] = useState<RedisData>({
    health: null,
    stats: null,
    queues: null,
    testConnection: null,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAllData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      // Fetch health and test connection without auth
      const [health, testConnection] = await Promise.all([
        redisApi.getHealth(),
        redisApi.testConnection(),
      ]);

      // Fetch authenticated data if token is available
      let stats = null;
      let queues = null;

      if (token) {
        [stats, queues] = await Promise.all([
          redisApi.getStats(token),
          redisApi.getCeleryQueues(token),
        ]);
      }

      setData({
        health,
        stats,
        queues,
        testConnection,
      });
    } catch (err) {
      console.error('Failed to fetch Redis data:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch Redis data');
    } finally {
      setLoading(false);
    }
  }, [token]);

  // Fetch data on mount
  useEffect(() => {
    fetchAllData();
  }, [fetchAllData]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetchAllData();
    }, 30 * 1000);

    return () => clearInterval(interval);
  }, [fetchAllData]);

  return {
    data,
    loading,
    error,
    refetch: fetchAllData,
  };
}
