import { pushNotificationApi } from '@/features/shared/api/pushNotifications';

// Mock fetchWithSessionRefresh to delegate to global.fetch so the
// existing fetchMock works unchanged (no refresh-interceptor side effects).
jest.mock('@/lib/auth/sessionRefresh', () => ({
  fetchWithSessionRefresh: (...args: Parameters<typeof fetch>) => fetch(...args),
}));

describe('pushNotificationApi', () => {
  const originalFetch = global.fetch;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    });
    global.fetch = fetchMock as unknown as typeof global.fetch;
  });

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // @ts-expect-error - cleanup when fetch was initially undefined
      delete global.fetch;
    }
  });

  it('fetches the VAPID public key', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ public_key: 'test-key' }),
    });

    const key = await pushNotificationApi.getVapidPublicKey();

    expect(key).toBe('test-key');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toEqual(expect.stringContaining('/api/v1/push/vapid-public-key'));
    expect(options).toMatchObject({ method: 'GET', credentials: 'include' });
  });

  it('subscribes with endpoint payload', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ success: true }),
    });

    await pushNotificationApi.subscribe({
      endpoint: 'https://example.com',
      p256dh: 'key',
      auth: 'auth',
    });

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toEqual(expect.stringContaining('/api/v1/push/subscribe'));
    expect(options).toMatchObject({
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    });
    expect(options.body).toBe(JSON.stringify({ endpoint: 'https://example.com', p256dh: 'key', auth: 'auth' }));
  });

  it('unsubscribes with endpoint payload', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ success: true }),
    });

    await pushNotificationApi.unsubscribe('https://example.com');

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toEqual(expect.stringContaining('/api/v1/push/unsubscribe'));
    expect(options).toMatchObject({
      method: 'DELETE',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
    });
    expect(options.body).toBe(JSON.stringify({ endpoint: 'https://example.com' }));
  });

  describe('getSubscriptions', () => {
    it('fetches all push subscriptions for current user', async () => {
      const subscriptions = [
        { id: 'sub-1', endpoint: 'https://push.example.com/1', created_at: '2024-01-01' },
        { id: 'sub-2', endpoint: 'https://push.example.com/2', created_at: '2024-01-02' },
      ];

      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => subscriptions,
      });

      const result = await pushNotificationApi.getSubscriptions();

      expect(result).toEqual(subscriptions);
      const [url, options] = fetchMock.mock.calls[0];
      expect(url).toEqual(expect.stringContaining('/api/v1/push/subscriptions'));
      expect(options).toMatchObject({ method: 'GET', credentials: 'include' });
    });

    it('returns empty array when no subscriptions exist', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      });

      const result = await pushNotificationApi.getSubscriptions();

      expect(result).toEqual([]);
    });
  });

  describe('error handling', () => {
    it('extracts error detail from JSON response', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Authentication required' }),
      });

      await expect(pushNotificationApi.getVapidPublicKey()).rejects.toThrow(
        'Authentication required'
      );
    });

    it('extracts error message from JSON response', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => ({ message: 'Invalid request parameters' }),
      });

      await expect(pushNotificationApi.subscribe({
        endpoint: 'https://example.com',
        p256dh: 'key',
        auth: 'auth',
      })).rejects.toThrow('Invalid request parameters');
    });

    it('uses fallback message when JSON parse fails', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error('Invalid JSON');
        },
      });

      await expect(pushNotificationApi.getVapidPublicKey()).rejects.toThrow(
        'Failed to load VAPID public key'
      );
    });

    it('uses fallback message when error response has no detail or message', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: async () => ({ error: 'forbidden' }),
      });

      await expect(pushNotificationApi.unsubscribe('https://example.com')).rejects.toThrow(
        'Failed to unsubscribe from push notifications'
      );
    });

    it('handles network failure during subscribe', async () => {
      fetchMock.mockRejectedValueOnce(new Error('Network error'));

      await expect(pushNotificationApi.subscribe({
        endpoint: 'https://example.com',
        p256dh: 'key',
        auth: 'auth',
      })).rejects.toThrow('Network error');
    });

    it('handles 429 rate limit response', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 429,
        json: async () => ({ detail: 'Too many requests' }),
      });

      await expect(pushNotificationApi.getSubscriptions()).rejects.toThrow(
        'Too many requests'
      );
    });
  });
});
