import { fetchWithAuth } from '@/lib/api';
import type { ApiErrorResponse, components } from '@/features/shared/api/types';
import { extractApiErrorMessage } from '@/lib/apiErrors';

export type PreferencesByCategory = components['schemas']['PreferencesByCategory'];
export type PreferenceResponse = components['schemas']['PreferenceResponse'];
export type PreferenceUpdate = components['schemas']['PreferenceUpdate'];
export type NotificationPreferenceChannels = Record<string, boolean>;

const BASE_PATH = '/api/v1/notification-preferences';

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
