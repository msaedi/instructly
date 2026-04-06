import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { queryFn } from '@/lib/react-query/api';
import { queryKeys } from '@/lib/react-query/queryClient';
import type {
  NeighborhoodSelectorResponse,
  SelectorDisplayItem,
} from '@/features/shared/api/types';

const ONE_DAY_MS = 24 * 60 * 60 * 1000;

export function useNeighborhoodSelectorData(market: string = 'nyc') {
  const query = useQuery<NeighborhoodSelectorResponse>({
    queryKey: queryKeys.neighborhoods.selector(market),
    queryFn: queryFn<NeighborhoodSelectorResponse>(
      '/api/v1/addresses/neighborhoods/selector',
      { params: { market } },
    ),
    staleTime: ONE_DAY_MS,
    gcTime: ONE_DAY_MS,
  });

  const allItems = useMemo<SelectorDisplayItem[]>(
    () =>
      query.data?.boroughs?.flatMap((boroughGroup) => boroughGroup.items) ?? [],
    [query.data],
  );

  const itemByKey = useMemo(() => {
    const next = new Map<string, SelectorDisplayItem>();
    for (const item of allItems) {
      next.set(item.display_key, item);
    }
    return next;
  }, [allItems]);

  const boroughs = useMemo(
    () => query.data?.boroughs?.map((boroughGroup) => boroughGroup.borough) ?? [],
    [query.data],
  );

  return {
    ...query,
    allItems,
    itemByKey,
    boroughs,
  };
}
