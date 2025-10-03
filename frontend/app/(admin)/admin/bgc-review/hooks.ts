'use client';

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from '@tanstack/react-query';

import { httpGet, httpPost } from '@/features/shared/api/http';

export interface BGCReviewItem {
  instructor_id: string;
  name: string;
  email: string;
  bgc_status: string;
  bgc_report_id: string | null;
  bgc_completed_at: string | null;
  created_at: string | null;
  consented_at_recent: boolean;
  checkr_report_url: string | null;
}

export interface BGCReviewPageResult {
  items: BGCReviewItem[];
  next_cursor: string | null;
}

const COUNT_QUERY_KEY: QueryKey = ['admin', 'bgc', 'review', 'count'];
const LIST_QUERY_KEY_PREFIX: QueryKey = ['admin', 'bgc', 'review', 'list'];

export function useBGCReviewCount() {
  return useQuery({
    queryKey: COUNT_QUERY_KEY,
    queryFn: async () => {
      const data = await httpGet<{ count: number }>('/api/admin/bgc/review/count');
      return data?.count ?? 0;
    },
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useBGCReviewList(limit = 50) {
  return useInfiniteQuery<BGCReviewPageResult, Error>({
    queryKey: [...LIST_QUERY_KEY_PREFIX, limit],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      const cursor = (pageParam as string | null) ?? null;
      const cursorParam = cursor ? `&cursor=${encodeURIComponent(cursor)}` : '';
      return httpGet<BGCReviewPageResult>(`/api/admin/bgc/review?limit=${limit}${cursorParam}`);
    },
    getNextPageParam: (lastPage) => lastPage.next_cursor,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useBGCOverride() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'approve' | 'reject' }) =>
      httpPost<{ ok: boolean; new_status: string }>(`/api/admin/bgc/${id}/override`, { action }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: COUNT_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: LIST_QUERY_KEY_PREFIX, exact: false });
    },
  });
}
