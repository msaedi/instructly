import { httpGet, httpPost } from '@/features/shared/api/http';

export type BGCStatus = 'pending' | 'review' | 'passed' | 'failed';
export type BGCEnv = 'sandbox' | 'production';

export interface BGCInviteResponse {
  ok: boolean;
  status: BGCStatus;
  report_id?: string | null;
  already_in_progress?: boolean;
}

export interface BGCStatusResponse {
  status: BGCStatus;
  report_id?: string | null;
  completed_at?: string | null;
  env: BGCEnv;
}

export async function bgcInvite(instructorId: string): Promise<BGCInviteResponse> {
  return httpPost<BGCInviteResponse>(`/api/instructors/${instructorId}/bgc/invite`, {});
}

export async function bgcStatus(instructorId: string): Promise<BGCStatusResponse> {
  return httpGet<BGCStatusResponse>(`/api/instructors/${instructorId}/bgc/status`);
}

export async function bgcConsent(
  instructorId: string,
  payload: { consent_version: string }
): Promise<{ ok: boolean }> {
  return httpPost<{ ok: boolean }>(`/api/instructors/${instructorId}/bgc/consent`, payload);
}
