import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { components } from '@/features/shared/api/types';
import { fetchWithAuth } from '@/lib/api';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';

type TrustedDeviceListResponse = components['schemas']['TrustedDeviceListResponse'];
type TrustedDeviceRevokeResponse = components['schemas']['TrustedDeviceRevokeResponse'];

const QUERY_KEY = ['user', '2fa', 'trusted-devices'] as const;

export function useTrustedDevices(enabled: boolean = true) {
  return useQuery<TrustedDeviceListResponse>({
    queryKey: QUERY_KEY,
    queryFn: async () => {
      const response = await fetchWithAuth('/api/v1/2fa/trusted-devices');
      if (!response.ok) {
        throw new Error('Failed to fetch trusted devices');
      }
      return (await response.json()) as TrustedDeviceListResponse;
    },
    enabled,
    staleTime: CACHE_TIMES.FREQUENT,
    refetchOnWindowFocus: false,
  });
}

export const trustedDevicesQueryKey = QUERY_KEY;

export function useInvalidateTrustedDevices() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: QUERY_KEY });
}

export function useRevokeTrustedDevice() {
  const queryClient = useQueryClient();
  return useMutation<TrustedDeviceRevokeResponse, Error, string>({
    mutationFn: async (deviceId: string) => {
      const response = await fetchWithAuth(`/api/v1/2fa/trusted-devices/${deviceId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw new Error('Failed to revoke trusted device');
      }
      return (await response.json()) as TrustedDeviceRevokeResponse;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });
}

export function useRevokeAllTrustedDevices() {
  const queryClient = useQueryClient();
  return useMutation<TrustedDeviceRevokeResponse, Error, void>({
    mutationFn: async () => {
      const response = await fetchWithAuth('/api/v1/2fa/trusted-devices', {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw new Error('Failed to revoke trusted devices');
      }
      return (await response.json()) as TrustedDeviceRevokeResponse;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });
}
