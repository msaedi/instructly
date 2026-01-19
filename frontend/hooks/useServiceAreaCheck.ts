import { useQuery } from '@tanstack/react-query';

import { instructorService } from '@/services/instructorService';

interface ServiceAreaCheckParams {
  instructorId: string;
  lat: number | undefined;
  lng: number | undefined;
}

export function useServiceAreaCheck({ instructorId, lat, lng }: ServiceAreaCheckParams) {
  const hasCoords = typeof lat === 'number' && typeof lng === 'number';
  return useQuery({
    queryKey: ['service-area-check', instructorId, lat, lng],
    queryFn: () => instructorService.checkServiceArea(instructorId, lat!, lng!),
    enabled: Boolean(instructorId) && hasCoords,
    staleTime: 1000 * 60 * 5,
  });
}
