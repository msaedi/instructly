import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { withApiBase } from '@/lib/apiBase';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';
import type { components } from '@/features/shared/api/types';

type CoverageFeatureCollectionResponse = components['schemas']['CoverageFeatureCollectionResponse'];

export function useInstructorCoverage(instructorIds: string[]) {
  const ids = useMemo(
    () =>
      Array.from(new Set(instructorIds.filter((id) => typeof id === 'string' && id.length > 0))).sort(),
    [instructorIds]
  );

  return useQuery<CoverageFeatureCollectionResponse>({
    queryKey: ['instructors', 'coverage', 'bulk', ids.join(',')],
    enabled: ids.length > 0,
    staleTime: CACHE_TIMES.SLOW,
    queryFn: async ({ signal }) => {
      const params = new URLSearchParams({ ids: ids.join(',') });
      const coverageUrl = withApiBase(`/api/v1/addresses/coverage/bulk?${params.toString()}`);
      const response = await fetch(coverageUrl, { credentials: 'include', signal });
      if (!response.ok) {
        throw new Error('Failed to load coverage areas');
      }
      return (await response.json()) as CoverageFeatureCollectionResponse;
    },
  });
}
