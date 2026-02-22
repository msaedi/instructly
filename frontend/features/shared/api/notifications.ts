import { fetchWithAuth } from '@/lib/api';
import type { ApiErrorResponse, components } from '@/features/shared/api/types';
import { extractApiErrorMessage } from '@/lib/apiErrors';

export type NotificationItem = components['schemas']['NotificationResponse'];
export type NotificationListResponse = components['schemas']['NotificationListResponse'];
export type NotificationUnreadCountResponse = components['schemas']['NotificationUnreadCountResponse'];

export interface NotificationQueryParams {
  limit?: number;
  offset?: number;
  unreadOnly?: boolean;
}

const NOTIFICATIONS_PATH = '/api/v1/notifications';
const UNREAD_COUNT_PATH = '/api/v1/notifications/unread-count';

async function parseErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as ApiErrorResponse;
    return extractApiErrorMessage(payload, fallback);
  } catch {
    return fallback;
  }
}

async function requestJson<T>(path: string, init: RequestInit, fallbackError: string): Promise<T> {
  const response = await fetchWithAuth(path, init);
  if (!response.ok) {
    const message = await parseErrorMessage(response, fallbackError);
    throw new Error(message);
  }
  return (await response.json()) as T;
}

function buildQuery(params?: NotificationQueryParams): string {
  if (!params) return '';
  const search = new URLSearchParams();
  if (typeof params.limit === 'number') search.set('limit', String(params.limit));
  if (typeof params.offset === 'number') search.set('offset', String(params.offset));
  if (typeof params.unreadOnly === 'boolean') {
    search.set('unread_only', params.unreadOnly ? 'true' : 'false');
  }
  const query = search.toString();
  return query ? `?${query}` : '';
}

export const notificationApi = {
  getNotifications: async (
    params?: NotificationQueryParams
  ): Promise<NotificationListResponse> => {
    const query = buildQuery(params);
    return requestJson<NotificationListResponse>(
      `${NOTIFICATIONS_PATH}${query}`,
      { method: 'GET' },
      'Failed to load notifications'
    );
  },

  getUnreadCount: async (): Promise<NotificationUnreadCountResponse> => {
    return requestJson<NotificationUnreadCountResponse>(
      UNREAD_COUNT_PATH,
      { method: 'GET' },
      'Failed to load unread count'
    );
  },

  markAsRead: async (id: string): Promise<void> => {
    await requestJson<{ success: boolean }>(
      `${NOTIFICATIONS_PATH}/${id}/read`,
      { method: 'POST' },
      'Failed to mark notification as read'
    );
  },

  markAllAsRead: async (): Promise<void> => {
    await requestJson<{ success: boolean }>(
      `${NOTIFICATIONS_PATH}/read-all`,
      { method: 'POST' },
      'Failed to mark notifications as read'
    );
  },

  deleteNotification: async (id: string): Promise<void> => {
    await requestJson<{ success: boolean }>(
      `${NOTIFICATIONS_PATH}/${id}`,
      { method: 'DELETE' },
      'Failed to delete notification'
    );
  },

  deleteAll: async (): Promise<void> => {
    await requestJson<{ success: boolean }>(
      NOTIFICATIONS_PATH,
      { method: 'DELETE' },
      'Failed to clear notifications'
    );
  },
};
