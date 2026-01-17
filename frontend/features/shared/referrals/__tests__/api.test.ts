import {
  REFERRALS_ME_KEY,
  fetchMyReferrals,
  fetchReferralLedger,
  toReferralSummary,
  applyReferralCredit,
  sendReferralInvites,
} from '../api';
import { fetchAPI } from '@/lib/api';
import { withApiBase } from '@/lib/apiBase';
import type { ReferralLedgerResponse, components } from '@/features/shared/api/types';

jest.mock('@/lib/api', () => ({
  fetchAPI: jest.fn(),
}));

jest.mock('@/lib/apiBase', () => ({
  withApiBase: jest.fn((path: string) => `https://api.test${path}`),
}));

type MockResponse = {
  ok: boolean;
  status?: number;
  json: jest.Mock;
};

const makeResponse = ({ ok, status, json, jsonThrows }: { ok: boolean; status?: number; json?: unknown; jsonThrows?: boolean }): MockResponse => {
  return {
    ok,
    status: status ?? (ok ? 200 : 400),
    json: jsonThrows ? jest.fn().mockRejectedValue(new Error('bad json')) : jest.fn().mockResolvedValue(json),
  };
};

const fetchApiMock = fetchAPI as jest.Mock;
const withApiBaseMock = withApiBase as jest.Mock;

type RewardOut = components['schemas']['RewardOut'];

const createReward = (overrides: Partial<RewardOut> = {}): RewardOut => ({
  amount_cents: 100,
  created_at: '2024-01-01T00:00:00Z',
  id: 'reward-1',
  side: 'student',
  status: 'pending',
  ...overrides,
});

const createLedger = (overrides: Partial<ReferralLedgerResponse> = {}): ReferralLedgerResponse => ({
  code: 'CODE',
  share_url: 'https://share',
  expiry_notice_days: [],
  pending: [],
  unlocked: [],
  redeemed: [],
  ...overrides,
});

describe('fetchReferralLedger', () => {
  const originalFetch = global.fetch;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn();
    global.fetch = fetchMock as unknown as typeof global.fetch;
    withApiBaseMock.mockClear();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('fetches the referral ledger', async () => {
    const payload = createLedger({ code: 'ABC123', share_url: 'https://example.com' });
    fetchMock.mockResolvedValueOnce(makeResponse({ ok: true, json: payload }));

    const result = await fetchReferralLedger();

    expect(result).toEqual(payload);
    expect(withApiBaseMock).toHaveBeenCalledWith(REFERRALS_ME_KEY);
    expect(fetchMock).toHaveBeenCalledWith(
      `https://api.test${REFERRALS_ME_KEY}`,
      expect.objectContaining({
        method: 'GET',
        credentials: 'include',
        cache: 'no-store',
      })
    );
  });

  it('passes AbortSignal when provided', async () => {
    const payload = createLedger({ code: 'ABC123', share_url: 'https://example.com' });
    fetchMock.mockResolvedValueOnce(makeResponse({ ok: true, json: payload }));
    const controller = new AbortController();

    await fetchReferralLedger(controller.signal);

    expect(fetchMock).toHaveBeenCalledWith(
      `https://api.test${REFERRALS_ME_KEY}`,
      expect.objectContaining({ signal: controller.signal })
    );
  });

  it('throws when the response is not ok', async () => {
    fetchMock.mockResolvedValueOnce(makeResponse({ ok: false, json: { message: 'error' } }));

    await expect(fetchReferralLedger()).rejects.toThrow('Failed to load referral summary');
  });
});

describe('fetchMyReferrals', () => {
  const originalFetch = global.fetch;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn();
    global.fetch = fetchMock as unknown as typeof global.fetch;
    withApiBaseMock.mockClear();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('returns normalized referral summary with defaults', async () => {
    const payload = createLedger({ code: 'CODE1', share_url: 'https://share' });
    fetchMock.mockResolvedValueOnce(makeResponse({ ok: true, json: payload }));

    const result = await fetchMyReferrals();

    expect(result).toEqual({
      code: 'CODE1',
      share_url: 'https://share',
      expiry_notice_days: [],
      pending: [],
      unlocked: [],
      redeemed: [],
    });
  });

  it('includes expiry_notice_days when provided', async () => {
    const payload = createLedger({
      code: 'CODE2',
      share_url: 'https://share',
      expiry_notice_days: [7],
    });
    fetchMock.mockResolvedValueOnce(makeResponse({ ok: true, json: payload }));

    const result = await fetchMyReferrals();

    expect(result.expiry_notice_days).toEqual([7]);
  });

  it('throws when the ledger request fails', async () => {
    fetchMock.mockResolvedValueOnce(makeResponse({ ok: false, json: { message: 'error' } }));

    await expect(fetchMyReferrals()).rejects.toThrow('Failed to load referral summary');
  });
});

describe('toReferralSummary', () => {
  it('defaults missing arrays to empty', () => {
    const result = toReferralSummary({
      code: 'CODE3',
      share_url: 'https://share',
    } as unknown as ReferralLedgerResponse);

    expect(result).toEqual({
      code: 'CODE3',
      share_url: 'https://share',
      pending: [],
      unlocked: [],
      redeemed: [],
    });
  });

  it('preserves reward arrays when provided', () => {
    const result = toReferralSummary(
      createLedger({
        code: 'CODE4',
        share_url: 'https://share',
        pending: [createReward({ id: '1' })],
        unlocked: [createReward({ id: '2', status: 'unlocked' })],
        redeemed: [createReward({ id: '3', status: 'redeemed' })],
      })
    );

    expect(result.pending).toHaveLength(1);
    expect(result.unlocked).toHaveLength(1);
    expect(result.redeemed).toHaveLength(1);
  });

  it('includes expiry notice when present', () => {
    const result = toReferralSummary(
      createLedger({
        code: 'CODE5',
        share_url: 'https://share',
        expiry_notice_days: [14],
      })
    );

    expect(result.expiry_notice_days).toEqual([14]);
  });
});

describe('applyReferralCredit', () => {
  const originalFetch = global.fetch;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn();
    global.fetch = fetchMock as unknown as typeof global.fetch;
    withApiBaseMock.mockClear();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('returns a disabled error when orderId is missing', async () => {
    const result = await applyReferralCredit('');

    expect(result).toEqual({ type: 'disabled', message: 'Order ID is required' });
  });

  it('returns a normalized promo conflict on 409', async () => {
    fetchMock.mockResolvedValueOnce(
      makeResponse({
        ok: false,
        status: 409,
        json: { message: 'Promo conflict' },
      })
    );

    const result = await applyReferralCredit('order-1');

    expect(result).toEqual({ type: 'promo_conflict', message: 'Promo conflict' });
  });

  it('returns success payload when response is ok', async () => {
    const payload = { applied: true, credits_applied: 20 };
    fetchMock.mockResolvedValueOnce(makeResponse({ ok: true, json: payload }));

    const result = await applyReferralCredit('order-2');

    expect(result).toEqual(payload);
  });
});

describe('sendReferralInvites', () => {
  beforeEach(() => {
    fetchApiMock.mockReset();
  });

  it('throws when no emails are provided', async () => {
    await expect(sendReferralInvites({ emails: [], shareUrl: 'https://share' })).rejects.toThrow(
      'At least one email address is required.'
    );
  });

  it('throws when shareUrl is missing', async () => {
    await expect(sendReferralInvites({ emails: ['test@example.com'], shareUrl: '' })).rejects.toThrow(
      'Referral link not available. Please try again.'
    );
  });

  it('returns the sent count from the API', async () => {
    fetchApiMock.mockResolvedValueOnce(makeResponse({ ok: true, json: { sent: 2 } }));

    const result = await sendReferralInvites({
      emails: ['one@example.com', 'two@example.com'],
      shareUrl: 'https://share',
      fromName: 'Instructor',
    });

    expect(result).toBe(2);
    expect(fetchApiMock).toHaveBeenCalledWith(
      '/api/v1/public/referrals/send',
      expect.objectContaining({
        method: 'POST',
      })
    );
  });

  it('throws with API error message on failure', async () => {
    fetchApiMock.mockResolvedValueOnce(makeResponse({ ok: false, json: { detail: 'Send failed' } }));

    await expect(
      sendReferralInvites({ emails: ['one@example.com'], shareUrl: 'https://share' })
    ).rejects.toThrow('Send failed');
  });
});
