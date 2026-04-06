import { useQuery } from '@tanstack/react-query';

import type { NeighborhoodPolygonFeatureCollection } from '@/components/neighborhoods/types';
import { queryFn } from '@/lib/react-query/api';
import { queryKeys } from '@/lib/react-query/queryClient';

const ONE_DAY_MS = 24 * 60 * 60 * 1000;

export function useNeighborhoodPolygons(
  market: string = 'nyc',
  enabled: boolean = true,
) {
  return useQuery<NeighborhoodPolygonFeatureCollection>({
    queryKey: queryKeys.neighborhoods.polygons(market),
    queryFn: queryFn<NeighborhoodPolygonFeatureCollection>(
      '/api/v1/addresses/neighborhoods/polygons',
      { params: { market } },
    ),
    enabled,
    staleTime: ONE_DAY_MS,
    gcTime: ONE_DAY_MS,
  });
}
