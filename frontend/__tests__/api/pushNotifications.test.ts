import { pushNotificationApi } from '@/features/shared/api/pushNotifications';

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
});
