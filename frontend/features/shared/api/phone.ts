import { fetchWithAuth } from '@/lib/api';
import type { ApiErrorResponse, components } from '@/features/shared/api/types';
import { extractApiErrorMessage } from '@/lib/apiErrors';

type PhoneUpdateResponse = components['schemas']['PhoneUpdateResponse'];
export type PhoneVerifyResponse = components['schemas']['PhoneVerifyResponse'];
export type PhoneStatusResponse = PhoneUpdateResponse;

const BASE_PATH = '/api/v1/account/phone';

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

export const phoneApi = {
  getPhoneStatus: async (): Promise<PhoneStatusResponse> => {
    return requestJson<PhoneStatusResponse>(BASE_PATH, { method: 'GET' }, 'Failed to load phone status');
  },
  updatePhoneNumber: async (phoneNumber: string): Promise<PhoneStatusResponse> => {
    return requestJson<PhoneStatusResponse>(
      BASE_PATH,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_number: phoneNumber }),
      },
      'Failed to update phone number'
    );
  },
  sendVerification: async (): Promise<PhoneVerifyResponse> => {
    return requestJson<PhoneVerifyResponse>(
      `${BASE_PATH}/verify`,
      { method: 'POST' },
      'Failed to send verification code'
    );
  },
  confirmVerification: async (code: string): Promise<PhoneVerifyResponse> => {
    return requestJson<PhoneVerifyResponse>(
      `${BASE_PATH}/verify/confirm`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      },
      'Failed to verify phone number'
    );
  },
};
