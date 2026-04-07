'use client';

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { analyticsApi } from '@/lib/analyticsApi';
import type { CodebaseHistoryEntry } from '@/lib/analyticsApi';
import { queryKeys } from '@/lib/react-query/queryClient';

async function fetchCodebaseMetrics(): Promise<CodebaseHistoryEntry[]> {
  return analyticsApi.getCodebaseMetrics();
}

export function useCodebaseMetrics(): UseQueryResult<CodebaseHistoryEntry[], Error> {
  return useQuery({
    queryKey: queryKeys.analytics.codebaseMetrics,
    queryFn: fetchCodebaseMetrics,
    refetchInterval: 10 * 60 * 1000,
    staleTime: 5 * 60 * 1000,
  });
}
