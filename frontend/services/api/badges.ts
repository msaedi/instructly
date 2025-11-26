import { fetchWithAuth } from '@/lib/api';
import type {
  AdminAward,
  AdminAwardListResponse,
  StudentBadgeItem,
} from '@/types/badges';

type BadgeApiError = Error & { status?: number; payload?: unknown };

async function parseError(response: Response): Promise<never> {
  let message = `Request failed (${response.status})`;
  let payload: unknown;
  try {
    payload = await response.clone().json();
    if (payload && typeof payload === 'object') {
      const detail = (payload as { detail?: string }).detail;
      const msg = (payload as { message?: string }).message;
      message = detail || msg || message;
    }
  } catch {
    // Non-JSON body; keep default message
  }

  const error = new Error(message) as BadgeApiError;
  error.status = response.status;
  error.payload = payload;
  throw error;
}

async function requestJson<T>(endpoint: string, init?: RequestInit): Promise<T> {
  const response = await fetchWithAuth(endpoint, init);
  if (!response.ok) {
    await parseError(response);
  }
  return response.json() as Promise<T>;
}

export const badgesApi = {
  getStudentBadges: (): Promise<StudentBadgeItem[]> => requestJson('/api/v1/students/badges'),
  getStudentBadgesEarned: (): Promise<StudentBadgeItem[]> =>
    requestJson('/api/v1/students/badges/earned'),
  getStudentBadgesProgress: (): Promise<StudentBadgeItem[]> =>
    requestJson('/api/v1/students/badges/progress'),

  listPendingAwards: (params: {
    before?: string;
    status?: string;
    limit?: number;
    offset?: number;
  } = {}): Promise<AdminAwardListResponse> => {
    const search = new URLSearchParams();
    if (params.before) search.set('before', params.before);
    if (params.status) search.set('status', params.status);
    if (typeof params.limit === 'number') search.set('limit', String(params.limit));
    if (typeof params.offset === 'number') search.set('offset', String(params.offset));
    const query = search.toString();
    return requestJson(`/api/admin/badges/pending${query ? `?${query}` : ''}`);
  },

  confirmAward: (awardId: string): Promise<AdminAward> =>
    requestJson(`/api/admin/badges/${awardId}/confirm`, { method: 'POST' }),

  revokeAward: (awardId: string): Promise<AdminAward> =>
    requestJson(`/api/admin/badges/${awardId}/revoke`, { method: 'POST' }),
};

export type { BadgeApiError };
