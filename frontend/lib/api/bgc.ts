import { httpGet, httpPost } from '@/features/shared/api/http';

export type BGCStatus = 'pending' | 'review' | 'consider' | 'passed' | 'failed' | 'canceled';
export type BGCEnv = 'sandbox' | 'production';

export interface BGCInviteResponse {
  ok: boolean;
  status: BGCStatus;
  report_id?: string | null;
  candidate_id?: string | null;
  invitation_id?: string | null;
  already_in_progress?: boolean;
}

export interface BGCStatusResponse {
  status: BGCStatus;
  report_id?: string | null;
  completed_at?: string | null;
  env: BGCEnv;
  consent_recent?: boolean;
  consent_recent_at?: string | null;
  valid_until?: string | null;
  expires_in_days?: number | null;
  is_expired?: boolean;
  eta?: string | null;
  bgcIncludesCanceled?: boolean;
}

type RawBGCStatusResponse = Omit<BGCStatusResponse, 'bgcIncludesCanceled'> & {
  bgc_includes_canceled?: boolean | null;
};

export async function bgcInvite(instructorId: string): Promise<BGCInviteResponse> {
  return httpPost<BGCInviteResponse>(`/api/v1/instructors/${instructorId}/bgc/invite`, {});
}

export async function bgcStatus(instructorId: string): Promise<BGCStatusResponse> {
  const response = await httpGet<RawBGCStatusResponse>(`/api/v1/instructors/${instructorId}/bgc/status`);
  const { bgc_includes_canceled, ...rest } = response;
  return {
    ...rest,
    bgcIncludesCanceled: Boolean(bgc_includes_canceled),
  };
}

export async function bgcRecheck(instructorId: string): Promise<BGCInviteResponse> {
  return httpPost<BGCInviteResponse>(`/api/v1/instructors/${instructorId}/bgc/recheck`, {});
}

export interface BGCConsentPayload {
  consent_version: string;
  disclosure_version: string;
  user_agent?: string;
}

export async function bgcConsent(
  instructorId: string,
  payload: BGCConsentPayload
): Promise<{ ok: boolean }> {
  return httpPost<{ ok: boolean }>(`/api/v1/instructors/${instructorId}/bgc/consent`, payload);
}
