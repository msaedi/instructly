import { useQuery } from '@tanstack/react-query';

import { fetchWithAuth } from '@/lib/api';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';
import type { ServiceAreasResponse } from '@/features/shared/api/types';

export function useInstructorServiceAreas(enabled: boolean) {
  return useQuery<ServiceAreasResponse>({
    queryKey: ['instructor', 'service-areas'],
    queryFn: async () => {
      const response = await fetchWithAuth('/api/v1/addresses/service-areas/me');
      if (!response.ok) {
        throw new Error('Failed to load service areas');
      }
      return (await response.json()) as ServiceAreasResponse;
    },
    enabled,
    staleTime: CACHE_TIMES.FREQUENT,
    refetchOnWindowFocus: false,
  });
}
