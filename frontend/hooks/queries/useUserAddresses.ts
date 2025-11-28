/**
 * React Query hook for user addresses
 *
 * Provides cached access to the current user's saved addresses.
 * This replaces direct fetchWithAuth calls to /api/v1/addresses/me.
 *
 * @example
 * ```tsx
 * function AddressList() {
 *   const { data, isLoading } = useUserAddresses();
 *
 *   if (isLoading) return <div>Loading...</div>;
 *   return (
 *     <ul>
 *       {data?.items.map(addr => <li key={addr.id}>{addr.street_line1}</li>)}
 *     </ul>
 *   );
 * }
 * ```
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { fetchWithAuth } from '@/lib/api';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';
import type { AddressListResponse } from '@/src/api/generated/instructly.schemas';

const QUERY_KEY = ['user', 'addresses'] as const;

/**
 * Hook to fetch user's saved addresses
 *
 * @param enabled - Whether the query should be enabled (default: true)
 * @returns React Query result with AddressListResponse (has .items array)
 */
export function useUserAddresses(enabled: boolean = true) {
  return useQuery<AddressListResponse>({
    queryKey: QUERY_KEY,
    queryFn: async () => {
      const response = await fetchWithAuth('/api/v1/addresses/me');
      if (!response.ok) {
        throw new Error('Failed to fetch user addresses');
      }
      return response.json() as Promise<AddressListResponse>;
    },
    enabled,
    staleTime: CACHE_TIMES.SLOW, // 15 minutes - addresses rarely change
    refetchOnWindowFocus: false,
  });
}

/**
 * Query key for use with invalidation
 */
export const userAddressesQueryKey = QUERY_KEY;

/**
 * Hook to invalidate user addresses cache
 * Use this after creating, updating, or deleting an address
 */
export function useInvalidateUserAddresses() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: QUERY_KEY });
}

// Re-export the generated type for convenience
export type { AddressListResponse, AddressResponse } from '@/src/api/generated/instructly.schemas';
