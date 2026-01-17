'use client';

import { useInfiniteQuery, useQuery } from '@tanstack/react-query';

import { httpGet } from '@/features/shared/api/http';
import type { components } from '@/features/shared/api/types';

export type WebhookLogItem = components['schemas']['BGCWebhookLogEntry'];
type WebhookLogResponse = components['schemas']['BGCWebhookLogListResponse'];
type WebhookStatsResponse = components['schemas']['BGCWebhookStatsResponse'];

export interface WebhookFilterState {
  events: string[];
  statuses: string[];
  search: string;
  limit: number;
  autoRefresh: boolean;
}

export function useBGCWebhookLogs(filters: WebhookFilterState) {
  const query = useInfiniteQuery({
    queryKey: ['admin', 'bgc', 'webhooks', 'logs', filters],
    initialPageParam: null as string | null,
    refetchInterval: filters.autoRefresh ? 15_000 : false,
    queryFn: async ({ pageParam }) => {
      const params = new URLSearchParams();
      params.set('limit', String(filters.limit));
      filters.events.forEach((value) => params.append('event', value));
      filters.statuses.forEach((value) => params.append('status', value));
      if (filters.search.trim()) {
        params.set('q', filters.search.trim());
      }
      if (pageParam) {
        params.set('cursor', pageParam);
      }
      return httpGet<WebhookLogResponse>(`/api/v1/admin/background-checks/webhooks?${params.toString()}`);
    },
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const pages = query.data?.pages ?? [];
  const logs: WebhookLogItem[] = pages.flatMap((page) => page.items);
  const errorCount24h = pages[0]?.error_count_24h ?? 0;

  return {
    logs,
    errorCount24h,
    fetchNextPage: query.fetchNextPage,
    hasNextPage: Boolean(query.hasNextPage),
    isPending: query.isPending,
    isFetching: query.isFetching,
    isFetchingNextPage: query.isFetchingNextPage,
    refetch: query.refetch,
  };
}

export function useBGCWebhookStats() {
  return useQuery({
    queryKey: ['admin', 'bgc', 'webhooks', 'stats'],
    queryFn: async () => httpGet<WebhookStatsResponse>('/api/v1/admin/background-checks/webhooks/stats'),
    refetchInterval: 60_000,
  });
}
