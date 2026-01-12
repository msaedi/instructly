import { withApiBase } from '@/lib/apiBase';

export interface PushSubscriptionData {
  endpoint: string;
  p256dh: string;
  auth: string;
  user_agent?: string;
}

export interface PushSubscriptionResponse {
  id: string;
  endpoint: string;
  user_agent: string | null;
  created_at: string;
}

interface VapidPublicKeyResponse {
  public_key: string;
}

const VAPID_KEY_PATH = '/api/v1/push/vapid-public-key';
const SUBSCRIBE_PATH = '/api/v1/push/subscribe';
const UNSUBSCRIBE_PATH = '/api/v1/push/unsubscribe';
const SUBSCRIPTIONS_PATH = '/api/v1/push/subscriptions';

async function parseErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string; message?: string };
    return payload.detail ?? payload.message ?? fallback;
  } catch {
    return fallback;
  }
}

async function requestJson<T>(path: string, init: RequestInit, fallbackError: string): Promise<T> {
  const response = await fetch(withApiBase(path), {
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
  subscribe: async (subscription: PushSubscriptionData): Promise<void> => {
    await requestJson<{ success: boolean }>(
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
    await requestJson<{ success: boolean }>(
      UNSUBSCRIBE_PATH,
      {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint }),
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
