import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { fetchAPI } from '@/lib/api';
import type {
  NeighborhoodSelectorResponse,
  SelectorDisplayItem,
} from '@/features/shared/api/types';

const ONE_DAY_MS = 24 * 60 * 60 * 1000;

export function useNeighborhoodSelectorData(market: string = 'nyc') {
  const query = useQuery<NeighborhoodSelectorResponse>({
    queryKey: ['neighborhoods', 'selector', market],
    queryFn: async () => {
      const response = await fetchAPI(
        `/api/v1/addresses/neighborhoods/selector?market=${encodeURIComponent(market)}`,
      );
      if (!response.ok) {
        throw new Error('Failed to load neighborhood selector');
      }
      return (await response.json()) as NeighborhoodSelectorResponse;
    },
    staleTime: ONE_DAY_MS,
    gcTime: ONE_DAY_MS,
  });

  const allItems = useMemo<SelectorDisplayItem[]>(
    () =>
      query.data?.boroughs.flatMap((boroughGroup) => boroughGroup.items) ?? [],
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
    () => query.data?.boroughs.map((boroughGroup) => boroughGroup.borough) ?? [],
    [query.data],
  );

  return {
    ...query,
    allItems,
    itemByKey,
    boroughs,
  };
}
