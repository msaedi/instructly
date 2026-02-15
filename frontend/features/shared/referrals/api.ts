import { withApiBaseForRequest } from '@/lib/apiBase';
import { fetchAPI } from '@/lib/api';
import type {
  components,
  ReferralLedgerResponse,
  ReferralCheckoutApplyResponse,
  ReferralErrorResponse,
  ReferralSendResponse,
  ApiErrorResponse,
} from '@/features/shared/api/types';

export const REFERRALS_ME_KEY = '/api/v1/referrals/me';

export type RewardOut = components['schemas']['RewardOut'];
export type ReferralLedger = ReferralLedgerResponse;

export type ApplyReferralErrorType = 'promo_conflict' | 'below_min_basket' | 'no_unlocked_credit' | 'disabled';
export interface ApplyReferralError {
  type: ApplyReferralErrorType;
  message?: string;
}

export interface ReferralSummary {
  code: string;
  share_url: string;
  pending: RewardOut[];
  unlocked: RewardOut[];
  redeemed: RewardOut[];
  expiry_notice_days?: ReferralLedgerResponse['expiry_notice_days'];
}

function buildUrl(path: string, method: string = 'GET'): string {
  return withApiBaseForRequest(path, method);
}

function isReferralError(data: unknown): data is ReferralErrorResponse {
  return Boolean(data) && typeof (data as ReferralErrorResponse).reason === 'string';
}

function normalizeError(reason: string, fallbackMessage?: string): ApplyReferralError {
  const allowed: ApplyReferralErrorType[] = ['promo_conflict', 'below_min_basket', 'no_unlocked_credit', 'disabled'];
  const normalized = allowed.includes(reason as ApplyReferralErrorType)
    ? (reason as ApplyReferralErrorType)
    : 'disabled';
  return {
    type: normalized,
    ...(fallbackMessage ? { message: fallbackMessage } : {}),
  };
}

export async function fetchMyReferrals({ signal }: { signal?: AbortSignal } = {}): Promise<ReferralSummary> {
  const data = await fetchReferralLedger(signal);
  return toReferralSummary(data);
}

export async function fetchReferralLedger(signal?: AbortSignal): Promise<ReferralLedgerResponse> {
  const requestInit: RequestInit = {
    method: 'GET',
    credentials: 'include',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  };

  if (signal) {
    requestInit.signal = signal;
  }

  const response = await fetch(buildUrl(REFERRALS_ME_KEY), requestInit);

  if (!response.ok) {
    throw new Error('Failed to load referral summary');
  }

  return (await response.json()) as ReferralLedgerResponse;
}

export function toReferralSummary(data: ReferralLedgerResponse): ReferralSummary {
  return {
    code: data.code,
    share_url: data.share_url,
    pending: data.pending ?? [],
    unlocked: data.unlocked ?? [],
    redeemed: data.redeemed ?? [],
    ...(data.expiry_notice_days ? { expiry_notice_days: data.expiry_notice_days } : {}),
  };
}

export async function applyReferralCredit(orderId: string): Promise<ReferralCheckoutApplyResponse | ApplyReferralError> {
  if (!orderId) {
    return normalizeError('disabled', 'Order ID is required');
  }

  const response = await fetch(buildUrl('/api/v1/referrals/checkout/apply-referral', 'POST'), {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ order_id: orderId }),
  });

  let payload: unknown = null;
  try {
    payload = (await response.json()) as ReferralCheckoutApplyResponse | ReferralErrorResponse | ApiErrorResponse;
  } catch (error) {
    if (response.ok) {
      throw error instanceof Error ? error : new Error('Unexpected response when applying referral credit');
    }
  }

  if (!response.ok || isReferralError(payload)) {
    const errorBody = isReferralError(payload)
      ? payload
      : { reason: response.status === 409 ? 'promo_conflict' : 'disabled' };
    return normalizeError(errorBody.reason, (payload as ApiErrorResponse | undefined)?.message);
  }

  return payload as ReferralCheckoutApplyResponse;
}

interface SendReferralInvitesArgs {
  emails: string[];
  shareUrl: string;
  fromName?: string;
}

export async function sendReferralInvites({ emails, shareUrl, fromName }: SendReferralInvitesArgs): Promise<number> {
  if (!emails.length) {
    throw new Error('At least one email address is required.');
  }

  if (!shareUrl) {
    throw new Error('Referral link not available. Please try again.');
  }

  const response = await fetchAPI('/api/v1/public/referrals/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      emails,
      referral_link: shareUrl,
      ...(fromName ? { from_name: fromName } : {}),
    }),
  });

  let payload: ReferralSendResponse | ApiErrorResponse | null = null;
  try {
    payload = (await response.json()) as ReferralSendResponse;
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const errorPayload = payload as ApiErrorResponse | null;
    throw new Error(errorPayload?.detail || errorPayload?.message || 'Failed to send invites');
  }

  const sendPayload = payload as ReferralSendResponse | null;
  return sendPayload?.sent ?? emails.length;
}
