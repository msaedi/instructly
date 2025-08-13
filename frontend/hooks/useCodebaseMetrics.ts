'use client';

import { useCallback, useEffect, useState } from 'react';
import { analyticsApi, CodebaseMetricsResponse, CodebaseHistoryEntry } from '@/lib/analyticsApi';

interface UseCodebaseMetricsReturn {
  data: CodebaseMetricsResponse | null;
  history: CodebaseHistoryEntry[] | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useCodebaseMetrics(token: string | null): UseCodebaseMetricsReturn {
  const [data, setData] = useState<CodebaseMetricsResponse | null>(null);
  const [history, setHistory] = useState<CodebaseHistoryEntry[] | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [snapshot, hist] = await Promise.all([
        analyticsApi.getCodebaseMetrics(token),
        analyticsApi.getCodebaseHistory(token),
      ]);
      setData(snapshot);
      setHistory(hist.items || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch codebase metrics');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-refresh every 10 minutes
  useEffect(() => {
    const id = setInterval(fetchData, 10 * 60 * 1000);
    return () => clearInterval(id);
  }, [fetchData]);

  return { data, history, loading, error, refetch: fetchData };
}
