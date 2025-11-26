'use client';

import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';

import { httpGet, httpPost } from '@/features/shared/api/http';
import type { BGCInviteResponse } from '@/lib/api/bgc';

export interface BGCCaseItem {
  instructor_id: string;
  name: string;
  email: string;
  bgc_status: string | null;
  bgcIncludesCanceled?: boolean;
  bgc_report_id: string | null;
  bgc_completed_at: string | null;
  bgc_eta: string | null;
  created_at: string | null;
  updated_at: string | null;
  consent_recent: boolean;
  consent_recent_at: string | null;
  checkr_report_url: string | null;
  is_live: boolean;
  in_dispute: boolean;
  dispute_note: string | null;
  dispute_opened_at: string | null;
  dispute_resolved_at: string | null;
  bgc_valid_until: string | null;
  bgc_expires_in_days: number | null;
  bgc_is_expired: boolean;
}

export interface BGCCaseListResult {
  items: BGCCaseItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface BGCCounts {
  review: number;
  pending: number;
}

export interface AdminInstructorDetail {
  id: string;
  name: string;
  email: string;
  is_live: boolean;
  bgc_status: string | null;
  bgcIncludesCanceled?: boolean;
  bgc_report_id: string | null;
  bgc_completed_at: string | null;
  bgc_eta: string | null;
  consent_recent_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  bgc_valid_until: string | null;
  bgc_expires_in_days: number | null;
  bgc_is_expired: boolean;
  bgc_in_dispute: boolean;
  bgc_dispute_note: string | null;
  bgc_dispute_opened_at: string | null;
  bgc_dispute_resolved_at: string | null;
}

const COUNTS_QUERY_KEY: QueryKey = ['admin', 'bgc', 'counts'];
const CASES_QUERY_KEY_PREFIX: QueryKey = ['admin', 'bgc', 'cases'];

type BGCCaseItemApi = Omit<BGCCaseItem, 'bgcIncludesCanceled'> & {
  bgc_includes_canceled?: boolean | null;
};

type BGCCaseListResultApi = Omit<BGCCaseListResult, 'items'> & {
  items: BGCCaseItemApi[];
};

type AdminInstructorDetailApi = Omit<AdminInstructorDetail, 'bgcIncludesCanceled'> & {
  bgc_includes_canceled?: boolean | null;
};

export function useBGCCounts(enabled = true) {
  const isClient = typeof window !== 'undefined';
  return useQuery({
    queryKey: COUNTS_QUERY_KEY,
    queryFn: async () => httpGet<BGCCounts>('/api/v1/admin/background-checks/counts'),
    refetchOnWindowFocus: false,
    retry: 1,
    enabled: isClient && enabled,
  });
}

export function useBGCCases(
  status: 'review' | 'pending' | 'all',
  q = '',
  page = 1,
  pageSize = 50,
  enabled = true,
) {
  const isClient = typeof window !== 'undefined';
  return useQuery({
    queryKey: [...CASES_QUERY_KEY_PREFIX, status, q, page, pageSize],
    queryFn: async () => {
      const params = new URLSearchParams({
        status,
        page: String(page),
        page_size: String(pageSize),
      });
      if (q.trim()) {
        params.set('q', q.trim());
      }
      const url = `/api/v1/admin/background-checks/cases?${params.toString()}`;
      const response = await httpGet<BGCCaseListResultApi>(url);
      return {
        ...response,
        items: response.items.map(({ bgc_includes_canceled, ...rest }) => ({
          ...rest,
          bgcIncludesCanceled: Boolean(bgc_includes_canceled),
        })),
      };
    },
    refetchOnWindowFocus: false,
    retry: 1,
    enabled: isClient && enabled,
  });
}

export function useBGCOverride() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'approve' | 'reject' }) =>
      httpPost<{ ok: boolean; new_status: string }>(`/api/v1/admin/background-checks/${id}/override`, { action }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: COUNTS_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: CASES_QUERY_KEY_PREFIX, exact: false });
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new Event('bgc-review-refresh'));
      }
    },
  });
}

interface DisputePayload {
  id: string;
  note: string | null;
}

function invalidateBackgroundCheckQueries(queryClient: ReturnType<typeof useQueryClient>, instructorId: string) {
  void queryClient.invalidateQueries({ queryKey: COUNTS_QUERY_KEY });
  void queryClient.invalidateQueries({ queryKey: CASES_QUERY_KEY_PREFIX, exact: false });
  void queryClient.invalidateQueries({ queryKey: ['admin', 'instructor', instructorId] });
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('bgc-review-refresh'));
  }
}

type DisputeResponse = {
  ok: boolean;
  in_dispute: boolean;
  dispute_note: string | null;
  dispute_opened_at: string | null;
  dispute_resolved_at: string | null;
};

export function useBGCDisputeOpen() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, note }: DisputePayload) =>
      httpPost<DisputeResponse>(`/api/v1/admin/background-checks/${id}/dispute/open`, { note }),
    onSuccess: (_, variables) => {
      invalidateBackgroundCheckQueries(queryClient, variables.id);
    },
  });
}

export function useBGCDisputeResolve() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, note }: DisputePayload) =>
      httpPost<DisputeResponse>(`/api/v1/admin/background-checks/${id}/dispute/resolve`, { note }),
    onSuccess: (_, variables) => {
      invalidateBackgroundCheckQueries(queryClient, variables.id);
    },
  });
}

export function useBGCRecheck() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string }) =>
      httpPost<BGCInviteResponse>(`/api/v1/instructors/${id}/bgc/recheck`, {}),
    onSuccess: (_, variables) => {
      invalidateBackgroundCheckQueries(queryClient, variables.id);
    },
  });
}

export function useBGCInvite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, packageSlug }: { id: string; packageSlug?: string | null }) =>
      httpPost<BGCInviteResponse>(`/api/v1/instructors/${id}/bgc/invite`, packageSlug ? { package_slug: packageSlug } : {}),
    onSuccess: (_, variables) => {
      invalidateBackgroundCheckQueries(queryClient, variables.id);
    },
  });
}

export function useAdminInstructorDetail(instructorId: string | null) {
  const isClient = typeof window !== 'undefined';
  return useQuery<AdminInstructorDetail | null, Error>({
    queryKey: ['admin', 'instructor', instructorId],
    queryFn: async () => {
      if (!instructorId) return null;
      const detail = await httpGet<AdminInstructorDetailApi>(`/api/v1/admin/instructors/${instructorId}`, {
        credentials: 'include',
      });
      const { bgc_includes_canceled, ...rest } = detail;
      return {
        ...rest,
        bgcIncludesCanceled: Boolean(bgc_includes_canceled),
      };
    },
    enabled: isClient && Boolean(instructorId),
    staleTime: 60_000,
  });
}
