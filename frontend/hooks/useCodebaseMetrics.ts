'use client';

import { useCallback, useEffect, useState } from 'react';
import { analyticsApi } from '@/lib/analyticsApi';
import type { CodebaseHistoryEntry } from '@/lib/analyticsApi';

interface UseCodebaseMetricsReturn {
  data: CodebaseHistoryEntry | null;
  history: CodebaseHistoryEntry[] | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useCodebaseMetrics(token?: string | null): UseCodebaseMetricsReturn {
  const [data, setData] = useState<CodebaseHistoryEntry | null>(null);
  const [history, setHistory] = useState<CodebaseHistoryEntry[] | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const entries = await analyticsApi.getCodebaseMetrics(token ?? '');
      const nextHistory = Array.isArray(entries) ? entries : [];
      setHistory(nextHistory);
      setData(nextHistory.at(-1) ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch codebase metrics');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  // Auto-refresh every 10 minutes
  useEffect(() => {
    const id = setInterval(() => { void fetchData(); }, 10 * 60 * 1000);
    return () => clearInterval(id);
  }, [fetchData]);

  return { data, history, loading, error, refetch: fetchData };
}
