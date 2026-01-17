import { httpGet, httpPost } from '@/features/shared/api/http';
import type { components } from '@/features/shared/api/types';

export type BGCStatus = components['schemas']['BackgroundCheckStatusResponse']['status'];
export type BGCEnv = components['schemas']['BackgroundCheckStatusResponse']['env'];

export type BGCInviteResponse = components['schemas']['BackgroundCheckInviteResponse'];

export type BGCStatusResponse = Omit<
  components['schemas']['BackgroundCheckStatusResponse'],
  'bgc_includes_canceled'
> & {
  bgcIncludesCanceled?: boolean;
};

type RawBGCStatusResponse = components['schemas']['BackgroundCheckStatusResponse'];

export async function bgcInvite(instructorId: string): Promise<BGCInviteResponse> {
  return httpPost<BGCInviteResponse>(`/api/v1/instructors/${instructorId}/bgc/invite`, {});
}

export async function bgcStatus(instructorId: string): Promise<BGCStatusResponse> {
  const response = await httpGet<RawBGCStatusResponse>(`/api/v1/instructors/${instructorId}/bgc/status`, {
    cache: 'no-store',
    headers: {
      'Cache-Control': 'no-cache',
      Pragma: 'no-cache',
    },
  });
  const { bgc_includes_canceled, ...rest } = response;
  return {
    ...rest,
    bgcIncludesCanceled: Boolean(bgc_includes_canceled),
  };
}

export async function bgcRecheck(instructorId: string): Promise<BGCInviteResponse> {
  return httpPost<BGCInviteResponse>(`/api/v1/instructors/${instructorId}/bgc/recheck`, {});
}

export type BGCConsentPayload = components['schemas']['ConsentPayload'];

export async function bgcConsent(
  instructorId: string,
  payload: BGCConsentPayload
): Promise<components['schemas']['ConsentResponse']> {
  return httpPost<components['schemas']['ConsentResponse']>(
    `/api/v1/instructors/${instructorId}/bgc/consent`,
    payload
  );
}
