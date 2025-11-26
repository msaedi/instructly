'use client';

import { useInfiniteQuery, useQuery } from '@tanstack/react-query';

import { httpGet } from '@/features/shared/api/http';

export interface WebhookLogItem {
  id: string;
  event_type: string;
  delivery_id?: string | null;
  resource_id?: string | null;
  result?: string | null;
  http_status?: number | null;
  signature?: string | null;
  created_at: string;
  payload: Record<string, unknown>;
  instructor_id?: string | null;
  report_id?: string | null;
  candidate_id?: string | null;
  invitation_id?: string | null;
}

export interface WebhookLogResponse {
  items: WebhookLogItem[];
  next_cursor: string | null;
  error_count_24h: number;
}

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
      return httpGet<WebhookLogResponse>(`/api/admin/bgc/webhooks?${params.toString()}`);
    },
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const pages = query.data?.pages ?? [];
  const logs = pages.flatMap((page) => page.items);
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
    queryFn: async () => httpGet<{ error_count_24h: number }>('/api/v1/admin/background-checks/webhooks/stats'),
    refetchInterval: 60_000,
  });
}
