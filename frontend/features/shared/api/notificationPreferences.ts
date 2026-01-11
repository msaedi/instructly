import { fetchWithAuth } from '@/lib/api';

export type NotificationPreferenceChannels = {
  email: boolean;
  push: boolean;
  sms: boolean;
};

export interface PreferencesByCategory {
  lesson_updates: NotificationPreferenceChannels;
  messages: NotificationPreferenceChannels;
  reviews: NotificationPreferenceChannels;
  learning_tips: NotificationPreferenceChannels;
  system_updates: NotificationPreferenceChannels;
  promotional: NotificationPreferenceChannels;
}

export interface PreferenceResponse {
  id: string;
  category: string;
  channel: string;
  enabled: boolean;
  locked: boolean;
}

export interface PreferenceUpdate {
  category: string;
  channel: string;
  enabled: boolean;
}

const BASE_PATH = '/api/v1/notification-preferences';

async function parseErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string; message?: string };
    return payload.detail ?? payload.message ?? fallback;
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

export const notificationPreferencesApi = {
  getPreferences: async (): Promise<PreferencesByCategory> => {
    return requestJson<PreferencesByCategory>(BASE_PATH, { method: 'GET' }, 'Failed to load preferences');
  },

  updatePreference: async (
    category: string,
    channel: string,
    enabled: boolean
  ): Promise<PreferenceResponse> => {
    return requestJson<PreferenceResponse>(
      `${BASE_PATH}/${category}/${channel}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      },
      'Failed to update preference'
    );
  },

  updatePreferencesBulk: async (updates: PreferenceUpdate[]): Promise<PreferenceResponse[]> => {
    return requestJson<PreferenceResponse[]>(
      BASE_PATH,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates }),
      },
      'Failed to update preferences'
    );
  },
};
