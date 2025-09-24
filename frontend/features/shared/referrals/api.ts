import { API_BASE as apiBaseUrl } from '@/lib/publicEnv';
import type {
  components,
  ReferralLedgerResponse,
  ReferralCheckoutApplyResponse,
  ReferralErrorResponse,
} from '@/features/shared/api/types';

export type RewardOut = components['schemas']['RewardOut'];

export type ApplyReferralErrorType = 'promo_conflict' | 'below_min_basket' | 'no_unlocked_credit' | 'disabled';
export interface ApplyReferralError {
  type: ApplyReferralErrorType;
  message?: string;
}

interface ReferralSummary {
  code: string;
  share_url: string;
  pending: RewardOut[];
  unlocked: RewardOut[];
  redeemed: RewardOut[];
  expiry_notice_days?: ReferralLedgerResponse['expiry_notice_days'];
}

function buildUrl(path: string): string {
  const base = apiBaseUrl?.replace(/\/+$/, '') ?? '';
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${base}${cleanPath}`;
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

export async function fetchMyReferrals(): Promise<ReferralSummary> {
  const response = await fetch(buildUrl('/api/referrals/me'), {
    method: 'GET',
    credentials: 'include',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  });

  if (!response.ok) {
    throw new Error('Failed to load referral summary');
  }

  const data = (await response.json()) as ReferralLedgerResponse;

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

  const response = await fetch(buildUrl('/api/referrals/checkout/apply-referral'), {
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
    payload = await response.json();
  } catch (error) {
    if (response.ok) {
      throw error instanceof Error ? error : new Error('Unexpected response when applying referral credit');
    }
  }

  if (!response.ok || isReferralError(payload)) {
    const errorBody = isReferralError(payload)
      ? payload
      : { reason: response.status === 409 ? 'promo_conflict' : 'disabled' };
    return normalizeError(errorBody.reason, (payload as { message?: string })?.message);
  }

  return payload as ReferralCheckoutApplyResponse;
}
