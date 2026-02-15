import { withApiBase } from '@/lib/apiBase';
import { fetchWithSessionRefresh } from '@/lib/auth/sessionRefresh';
import type { ApiErrorResponse, components } from '@/features/shared/api/types';

type PushSubscribeRequest = components['schemas']['PushSubscribeRequest'];
type PushUnsubscribeRequest = components['schemas']['PushUnsubscribeRequest'];
type PushSubscriptionResponse = components['schemas']['PushSubscriptionResponse'];
type PushStatusResponse = components['schemas']['PushStatusResponse'];
type VapidPublicKeyResponse = components['schemas']['VapidPublicKeyResponse'];

const VAPID_KEY_PATH = '/api/v1/push/vapid-public-key';
const SUBSCRIBE_PATH = '/api/v1/push/subscribe';
const UNSUBSCRIBE_PATH = '/api/v1/push/unsubscribe';
const SUBSCRIPTIONS_PATH = '/api/v1/push/subscriptions';

async function parseErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as ApiErrorResponse;
    return payload.detail ?? payload.message ?? fallback;
  } catch {
    return fallback;
  }
}

async function requestJson<T>(path: string, init: RequestInit, fallbackError: string): Promise<T> {
  const response = await fetchWithSessionRefresh(withApiBase(path), {
    ...init,
    credentials: 'include',
  });

  if (!response.ok) {
    const message = await parseErrorMessage(response, fallbackError);
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export const pushNotificationApi = {
  /**
   * Get VAPID public key for subscription
   */
  getVapidPublicKey: async (): Promise<string> => {
    const data = await requestJson<VapidPublicKeyResponse>(
      VAPID_KEY_PATH,
      { method: 'GET' },
      'Failed to load VAPID public key'
    );
    return data.public_key;
  },

  /**
   * Subscribe to push notifications
   */
  subscribe: async (subscription: PushSubscribeRequest): Promise<void> => {
    await requestJson<PushStatusResponse>(
      SUBSCRIBE_PATH,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(subscription),
      },
      'Failed to subscribe to push notifications'
    );
  },

  /**
   * Unsubscribe from push notifications
   */
  unsubscribe: async (endpoint: string): Promise<void> => {
    const payload: PushUnsubscribeRequest = { endpoint };
    await requestJson<PushStatusResponse>(
      UNSUBSCRIBE_PATH,
      {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
      'Failed to unsubscribe from push notifications'
    );
  },

  /**
   * List all push subscriptions for current user
   */
  getSubscriptions: async (): Promise<PushSubscriptionResponse[]> => {
    return requestJson<PushSubscriptionResponse[]>(
      SUBSCRIPTIONS_PATH,
      { method: 'GET' },
      'Failed to load push subscriptions'
    );
  },
};
