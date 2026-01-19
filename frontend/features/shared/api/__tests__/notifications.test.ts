import { notificationApi } from '../notifications';
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

describe('notificationApi.getNotifications', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('fetches notifications without query params', async () => {
    const payload = { items: [], total: 0 };
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: true, json: payload }));

    const result = await notificationApi.getNotifications();

    expect(result).toEqual(payload);
    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/notifications', { method: 'GET' });
  });

  it('includes query params when provided', async () => {
    const payload = { items: [{ id: '1' }], total: 1 };
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: true, json: payload }));

    const result = await notificationApi.getNotifications({ limit: 10, offset: 5, unreadOnly: true });

    expect(result).toEqual(payload);
    expect(fetchWithAuthMock).toHaveBeenCalledWith(
      '/api/v1/notifications?limit=10&offset=5&unread_only=true',
      { method: 'GET' }
    );
  });

  it('throws the API detail message on error', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, json: { detail: 'No access' } }));

    await expect(notificationApi.getNotifications()).rejects.toThrow('No access');
  });
});

describe('notificationApi.getUnreadCount', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('fetches unread count', async () => {
    const payload = { unread_count: 2 };
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: true, json: payload }));

    const result = await notificationApi.getUnreadCount();

    expect(result).toEqual(payload);
    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/notifications/unread-count', { method: 'GET' });
  });

  it('uses detail message when present', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, json: { detail: 'Failed count' } }));

    await expect(notificationApi.getUnreadCount()).rejects.toThrow('Failed count');
  });

  it('falls back when error payload cannot be parsed', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, jsonThrows: true }));

    await expect(notificationApi.getUnreadCount()).rejects.toThrow('Failed to load unread count');
  });
});

describe('notificationApi.markAsRead', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('marks a notification as read', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: true, json: { success: true } }));

    await notificationApi.markAsRead('notif-1');

    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/notifications/notif-1/read', { method: 'POST' });
  });

  it('uses detail message when provided', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, json: { detail: 'Already read' } }));

    await expect(notificationApi.markAsRead('notif-1')).rejects.toThrow('Already read');
  });

  it('falls back when error payload cannot be parsed', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, jsonThrows: true }));

    await expect(notificationApi.markAsRead('notif-1')).rejects.toThrow('Failed to mark notification as read');
  });
});

describe('notificationApi.markAllAsRead', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('marks all notifications as read', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: true, json: { success: true } }));

    await notificationApi.markAllAsRead();

    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/notifications/read-all', { method: 'POST' });
  });

  it('uses detail message when provided', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, json: { detail: 'Cannot update' } }));

    await expect(notificationApi.markAllAsRead()).rejects.toThrow('Cannot update');
  });

  it('falls back when error payload cannot be parsed', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, jsonThrows: true }));

    await expect(notificationApi.markAllAsRead()).rejects.toThrow('Failed to mark notifications as read');
  });
});

describe('notificationApi.deleteNotification', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('deletes a specific notification', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: true, json: { success: true } }));

    await notificationApi.deleteNotification('notif-2');

    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/notifications/notif-2', { method: 'DELETE' });
  });

  it('uses detail message when provided', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, json: { detail: 'Delete failed' } }));

    await expect(notificationApi.deleteNotification('notif-2')).rejects.toThrow('Delete failed');
  });

  it('falls back when error payload cannot be parsed', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, jsonThrows: true }));

    await expect(notificationApi.deleteNotification('notif-2')).rejects.toThrow('Failed to delete notification');
  });
});

describe('notificationApi.deleteAll', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('deletes all notifications', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: true, json: { success: true } }));

    await notificationApi.deleteAll();

    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/notifications', { method: 'DELETE' });
  });

  it('uses detail message when provided', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, json: { detail: 'Delete all failed' } }));

    await expect(notificationApi.deleteAll()).rejects.toThrow('Delete all failed');
  });

  it('falls back when error payload cannot be parsed', async () => {
    fetchWithAuthMock.mockResolvedValueOnce(makeResponse({ ok: false, jsonThrows: true }));

    await expect(notificationApi.deleteAll()).rejects.toThrow('Failed to clear notifications');
  });
});
