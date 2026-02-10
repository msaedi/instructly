import { phoneApi } from '../phone';
import { fetchWithAuth } from '@/lib/api';

jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(),
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

const fetchWithAuthMock = fetchWithAuth as jest.Mock;

describe('phoneApi.getPhoneStatus', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('fetches phone status', async () => {
    const payload = { phone_number: '+15555555555', verified: false };
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: true, json: payload }));

    const result = await phoneApi.getPhoneStatus();

    expect(result).toEqual(payload);
    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/account/phone', { method: 'GET' });
  });

  it('uses detail message when provided', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, json: { detail: 'Failed status' } }));

    await expect(phoneApi.getPhoneStatus()).rejects.toThrow('Failed status');
  });

  it('falls back when error payload cannot be parsed', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, jsonThrows: true }));

    await expect(phoneApi.getPhoneStatus()).rejects.toThrow('Failed to load phone status');
  });
});

describe('parseErrorMessage fallback chain', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('uses message field when detail is absent', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(
      makeResponse({ ok: false, json: { message: 'Custom error' } })
    );

    await expect(phoneApi.getPhoneStatus()).rejects.toThrow('Custom error');
  });

  it('uses fallback when error body has no detail or message', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, json: {} }));

    await expect(phoneApi.getPhoneStatus()).rejects.toThrow('Failed to load phone status');
  });

  it('uses fallback when detail is null', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(
      makeResponse({ ok: false, json: { detail: null } })
    );

    await expect(phoneApi.getPhoneStatus()).rejects.toThrow('Failed to load phone status');
  });
});

describe('phoneApi.updatePhoneNumber', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('updates the phone number', async () => {
    const payload = { phone_number: '+15555555555', verified: false };
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: true, json: payload }));

    const result = await phoneApi.updatePhoneNumber('+15555555555');

    expect(result).toEqual(payload);
    expect(fetchWithAuthMock).toHaveBeenCalledWith(
      '/api/v1/account/phone',
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_number: '+15555555555' }),
      }
    );
  });

  it('uses detail message when provided', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, json: { detail: 'Update failed' } }));

    await expect(phoneApi.updatePhoneNumber('+15555555555')).rejects.toThrow('Update failed');
  });

  it('falls back when error payload cannot be parsed', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, jsonThrows: true }));

    await expect(phoneApi.updatePhoneNumber('+15555555555')).rejects.toThrow('Failed to update phone number');
  });
});

describe('phoneApi.sendVerification', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('sends a verification code', async () => {
    const payload = { sent: true };
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: true, json: payload }));

    const result = await phoneApi.sendVerification();

    expect(result).toEqual(payload);
    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/account/phone/verify', { method: 'POST' });
  });

  it('uses detail message when provided', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, json: { detail: 'Failed send' } }));

    await expect(phoneApi.sendVerification()).rejects.toThrow('Failed send');
  });

  it('falls back when error payload cannot be parsed', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, jsonThrows: true }));

    await expect(phoneApi.sendVerification()).rejects.toThrow('Failed to send verification code');
  });
});

describe('phoneApi.confirmVerification', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('confirms a verification code', async () => {
    const payload = { verified: true };
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: true, json: payload }));

    const result = await phoneApi.confirmVerification('123456');

    expect(result).toEqual(payload);
    expect(fetchWithAuthMock).toHaveBeenCalledWith(
      '/api/v1/account/phone/verify/confirm',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: '123456' }),
      }
    );
  });

  it('uses detail message when provided', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, json: { detail: 'Confirm failed' } }));

    await expect(phoneApi.confirmVerification('123456')).rejects.toThrow('Confirm failed');
  });

  it('falls back when error payload cannot be parsed', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, jsonThrows: true }));

    await expect(phoneApi.confirmVerification('123456')).rejects.toThrow('Failed to verify phone number');
  });
});
