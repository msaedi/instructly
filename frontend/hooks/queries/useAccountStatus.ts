import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { components, ApiErrorResponse } from '@/features/shared/api/types';
import { extractApiErrorMessage } from '@/lib/apiErrors';
import { fetchWithAuth } from '@/lib/api';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';

type AccountStatusResponse = components['schemas']['AccountStatusResponse'];
type AccountStatusChangeResponse = components['schemas']['AccountStatusChangeResponse'];

export const accountStatusQueryKey = ['user', 'account', 'status'] as const;

async function readJson<T>(response: Response, fallbackMessage: string): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorResponse;
    throw new Error(extractApiErrorMessage(body, fallbackMessage));
  }
  return (await response.json()) as T;
}

export function useAccountStatus(enabled: boolean = true) {
  return useQuery<AccountStatusResponse>({
    queryKey: accountStatusQueryKey,
    queryFn: async () => {
      const response = await fetchWithAuth('/api/v1/account/status');
      return readJson<AccountStatusResponse>(response, 'Failed to load account status.');
    },
    enabled,
    staleTime: CACHE_TIMES.FREQUENT,
    refetchOnWindowFocus: false,
  });
}

export function useInvalidateAccountStatus() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: accountStatusQueryKey });
}

// Backend endpoint/status naming is "suspend/suspended"; UX labels this as pause.
export function useSuspendAccount() {
  return useMutation<AccountStatusChangeResponse, Error>({
    mutationFn: async () => {
      const response = await fetchWithAuth('/api/v1/account/suspend', { method: 'POST' });
      return readJson<AccountStatusChangeResponse>(response, 'Failed to pause account.');
    },
  });
}

export function useReactivateAccount() {
  return useMutation<AccountStatusChangeResponse, Error>({
    mutationFn: async () => {
      const response = await fetchWithAuth('/api/v1/account/reactivate', { method: 'POST' });
      return readJson<AccountStatusChangeResponse>(response, 'Failed to resume account.');
    },
  });
}
