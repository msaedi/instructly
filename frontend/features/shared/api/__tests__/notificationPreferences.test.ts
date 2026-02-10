import { notificationPreferencesApi } from '../notificationPreferences';
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

describe('notificationPreferencesApi.getPreferences', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('fetches preferences', async () => {
    const payload = { booking: { email: true } };
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: true, json: payload }));

    const result = await notificationPreferencesApi.getPreferences();

    expect(result).toEqual(payload);
    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/notification-preferences', { method: 'GET' });
  });

  it('uses detail message when provided', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, json: { detail: 'Failed' } }));

    await expect(notificationPreferencesApi.getPreferences()).rejects.toThrow('Failed');
  });

  it('falls back when error payload cannot be parsed', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, jsonThrows: true }));

    await expect(notificationPreferencesApi.getPreferences()).rejects.toThrow('Failed to load preferences');
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

    await expect(notificationPreferencesApi.getPreferences()).rejects.toThrow('Custom error');
  });

  it('uses fallback when error body has no detail or message', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, json: {} }));

    await expect(notificationPreferencesApi.getPreferences()).rejects.toThrow('Failed to load preferences');
  });

  it('uses fallback when detail is null', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(
      makeResponse({ ok: false, json: { detail: null } })
    );

    await expect(notificationPreferencesApi.getPreferences()).rejects.toThrow('Failed to load preferences');
  });
});

describe('notificationPreferencesApi.updatePreference', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('updates a single preference', async () => {
    const payload = { category: 'booking', channel: 'email', enabled: true };
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: true, json: payload }));

    const result = await notificationPreferencesApi.updatePreference('booking', 'email', true);

    expect(result).toEqual(payload);
    expect(fetchWithAuthMock).toHaveBeenCalledWith(
      '/api/v1/notification-preferences/booking/email',
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: true }),
      }
    );
  });

  it('uses detail message when provided', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, json: { detail: 'Update failed' } }));

    await expect(notificationPreferencesApi.updatePreference('booking', 'email', false)).rejects.toThrow('Update failed');
  });

  it('falls back when error payload cannot be parsed', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, jsonThrows: true }));

    await expect(notificationPreferencesApi.updatePreference('booking', 'email', false)).rejects.toThrow('Failed to update preference');
  });
});

describe('notificationPreferencesApi.updatePreferencesBulk', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('updates preferences in bulk', async () => {
    const payload = [{ category: 'booking', channel: 'email', enabled: true }];
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: true, json: payload }));

    const updates = [{ category: 'booking', channel: 'email', enabled: true }];
    const result = await notificationPreferencesApi.updatePreferencesBulk(updates);

    expect(result).toEqual(payload);
    expect(fetchWithAuthMock).toHaveBeenCalledWith(
      '/api/v1/notification-preferences',
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates }),
      }
    );
  });

  it('uses detail message when provided', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, json: { detail: 'Bulk failed' } }));

    await expect(notificationPreferencesApi.updatePreferencesBulk([])).rejects.toThrow('Bulk failed');
  });

  it('falls back when error payload cannot be parsed', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, jsonThrows: true }));

    await expect(notificationPreferencesApi.updatePreferencesBulk([])).rejects.toThrow('Failed to update preferences');
  });
});
