'use client';

import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';

import { httpGet, httpPost } from '@/features/shared/api/http';
import type { BGCInviteResponse } from '@/lib/api/bgc';

export interface BGCCaseItem {
  instructor_id: string;
  name: string;
  email: string;
  bgc_status: string | null;
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
  next_cursor: string | null;
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

export function useBGCCounts(enabled = true) {
  const isClient = typeof window !== 'undefined';
  return useQuery({
    queryKey: COUNTS_QUERY_KEY,
    queryFn: async () => httpGet<BGCCounts>('/api/admin/bgc/counts'),
    refetchOnWindowFocus: false,
    retry: 1,
    enabled: isClient && enabled,
  });
}

export function useBGCCases(
  status: 'review' | 'pending' | 'all',
  q = '',
  limit = 50,
  enabled = true,
) {
  const isClient = typeof window !== 'undefined';
  return useQuery({
    queryKey: [...CASES_QUERY_KEY_PREFIX, status, q, limit],
    queryFn: async () => {
      const params = new URLSearchParams({ status, limit: String(limit) });
      if (q.trim()) {
        params.set('q', q.trim());
      }
      return httpGet<BGCCaseListResult>(`/api/admin/bgc/cases?${params.toString()}`);
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
      httpPost<{ ok: boolean; new_status: string }>(`/api/admin/bgc/${id}/override`, { action }),
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
      httpPost<DisputeResponse>(`/api/admin/bgc/${id}/dispute/open`, { note }),
    onSuccess: (_, variables) => {
      invalidateBackgroundCheckQueries(queryClient, variables.id);
    },
  });
}

export function useBGCDisputeResolve() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, note }: DisputePayload) =>
      httpPost<DisputeResponse>(`/api/admin/bgc/${id}/dispute/resolve`, { note }),
    onSuccess: (_, variables) => {
      invalidateBackgroundCheckQueries(queryClient, variables.id);
    },
  });
}

export function useBGCRecheck() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string }) =>
      httpPost<BGCInviteResponse>(`/api/instructors/${id}/bgc/recheck`, {}),
    onSuccess: (_, variables) => {
      invalidateBackgroundCheckQueries(queryClient, variables.id);
    },
  });
}

export function useBGCInvite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, packageSlug }: { id: string; packageSlug?: string | null }) =>
      httpPost<BGCInviteResponse>(`/api/instructors/${id}/bgc/invite`, packageSlug ? { package_slug: packageSlug } : {}),
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
      return httpGet<AdminInstructorDetail>(`/api/admin/instructors/${instructorId}`, {
        credentials: 'include',
      });
    },
    enabled: isClient && Boolean(instructorId),
    staleTime: 60_000,
  });
}
