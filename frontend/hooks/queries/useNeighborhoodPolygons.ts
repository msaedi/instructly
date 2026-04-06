import { useQuery } from '@tanstack/react-query';

import { fetchAPI } from '@/lib/api';
import type { NeighborhoodPolygonFeatureCollection } from '@/components/neighborhoods/types';

const ONE_DAY_MS = 24 * 60 * 60 * 1000;

export function useNeighborhoodPolygons(
  market: string = 'nyc',
  enabled: boolean = true,
) {
  return useQuery<NeighborhoodPolygonFeatureCollection>({
    queryKey: ['neighborhoods', 'polygons', market],
    queryFn: async () => {
      const response = await fetchAPI(
        `/api/v1/addresses/neighborhoods/polygons?market=${encodeURIComponent(market)}`,
      );
      if (!response.ok) {
        throw new Error('Failed to load neighborhood polygons');
      }
      return (await response.json()) as NeighborhoodPolygonFeatureCollection;
    },
    enabled,
    staleTime: ONE_DAY_MS,
    gcTime: ONE_DAY_MS,
  });
}
