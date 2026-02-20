import {
  REFERRALS_ME_KEY,
  fetchMyReferrals,
  fetchReferralLedger,
  toReferralSummary,
  applyReferralCredit,
  sendReferralInvites,
} from '../api';
import { fetchAPI } from '@/lib/api';
import { withApiBaseForRequest } from '@/lib/apiBase';
import type { ReferralLedgerResponse, components } from '@/features/shared/api/types';

jest.mock('@/lib/api', () => ({
  fetchAPI: jest.fn(),
}));

jest.mock('@/lib/apiBase', () => ({
  withApiBase: jest.fn((path: string) => `https://api.test${path}`),
  withApiBaseForRequest: jest.fn((path: string) => `https://api.test${path}`),
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
const withApiBaseForRequestMock = withApiBaseForRequest as jest.Mock;

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
    withApiBaseForRequestMock.mockClear();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('fetches the referral ledger', async () => {
    const payload = createLedger({ code: 'ABC123', share_url: 'https://example.com' });
    fetchMock.mockResolvedValueOnce(makeResponse({ ok: true, json: payload }));

    const result = await fetchReferralLedger();

    expect(result).toEqual(payload);
    expect(withApiBaseForRequestMock).toHaveBeenCalledWith(REFERRALS_ME_KEY, 'GET');
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
    withApiBaseForRequestMock.mockClear();
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
    withApiBaseForRequestMock.mockClear();
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

  it('rethrows when response is ok but json parsing fails', async () => {
    fetchMock.mockResolvedValueOnce(makeResponse({ ok: true, jsonThrows: true }));

    await expect(applyReferralCredit('order-3')).rejects.toThrow('bad json');
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

  it('handles json parse failure gracefully and returns email count', async () => {
    fetchApiMock.mockResolvedValueOnce(makeResponse({ ok: true, jsonThrows: true }));

    const result = await sendReferralInvites({
      emails: ['one@example.com', 'two@example.com'],
      shareUrl: 'https://share',
    });

    // Falls back to emails.length
    expect(result).toBe(2);
  });

  it('throws fallback error when API fails with no detail', async () => {
    fetchApiMock.mockResolvedValueOnce(makeResponse({ ok: false, json: {} }));

    await expect(
      sendReferralInvites({ emails: ['one@example.com'], shareUrl: 'https://share' })
    ).rejects.toThrow('Failed to send invites');
  });

  it('throws fallback when response fails and json parse also fails (null payload)', async () => {
    // response.ok = false AND json throws -> payload stays null
    // errorPayload = null -> extractApiErrorMessage({}, 'Failed to send invites')
    fetchApiMock.mockResolvedValueOnce(makeResponse({ ok: false, jsonThrows: true }));

    await expect(
      sendReferralInvites({ emails: ['one@example.com'], shareUrl: 'https://share' })
    ).rejects.toThrow('Failed to send invites');
  });

  it('omits from_name when not provided', async () => {
    fetchApiMock.mockResolvedValueOnce(makeResponse({ ok: true, json: { sent: 1 } }));

    await sendReferralInvites({
      emails: ['test@example.com'],
      shareUrl: 'https://share',
      // fromName is not provided
    });

    const body = JSON.parse(fetchApiMock.mock.calls[0][1].body as string);
    expect(body).not.toHaveProperty('from_name');
  });
});

describe('applyReferralCredit edge cases', () => {
  const originalFetch = global.fetch;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn();
    global.fetch = fetchMock as unknown as typeof global.fetch;
    withApiBaseForRequestMock.mockClear();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('returns normalized error when payload is a ReferralError with known reason', async () => {
    // response.ok = false AND isReferralError(payload) = true
    // This exercises lines 115-117 where payload IS a referral error
    fetchMock.mockResolvedValueOnce(
      makeResponse({
        ok: false,
        status: 400,
        json: { reason: 'no_unlocked_credit', message: 'No unlocked credit available' },
      })
    );

    const result = await applyReferralCredit('order-100');

    expect(result).toEqual({ type: 'no_unlocked_credit', message: 'No unlocked credit available' });
  });

  it('returns normalized error when payload is a ReferralError with below_min_basket', async () => {
    fetchMock.mockResolvedValueOnce(
      makeResponse({
        ok: false,
        status: 422,
        json: { reason: 'below_min_basket' },
      })
    );

    const result = await applyReferralCredit('order-101');

    expect(result).toEqual({ type: 'below_min_basket' });
  });

  it('normalizes unknown reason to disabled', async () => {
    // isReferralError true with an unrecognized reason -> normalizeError maps to 'disabled'
    fetchMock.mockResolvedValueOnce(
      makeResponse({
        ok: false,
        status: 400,
        json: { reason: 'totally_unknown_reason' },
      })
    );

    const result = await applyReferralCredit('order-102');

    expect(result).toEqual({ type: 'disabled' });
  });

  it('rethrows non-Error when response.ok but json parse fails with non-Error', async () => {
    // response.ok = true AND json throws something that is NOT an Error instance
    // This exercises line 110: `throw ... new Error('Unexpected response...')`
    const customJsonMock = jest.fn().mockRejectedValue('string-error');
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: customJsonMock,
    });

    await expect(applyReferralCredit('order-103')).rejects.toThrow(
      'Unexpected response when applying referral credit'
    );
  });

  it('returns disabled error with message from ApiErrorResponse when not a referral error', async () => {
    // response.ok = false, payload is NOT a referral error (no reason field)
    // status is NOT 409 -> reason = 'disabled', message from payload.message
    fetchMock.mockResolvedValueOnce(
      makeResponse({
        ok: false,
        status: 500,
        json: { message: 'Internal server error' },
      })
    );

    const result = await applyReferralCredit('order-104');

    expect(result).toEqual({ type: 'disabled', message: 'Internal server error' });
  });
});
