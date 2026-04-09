import type { Feature, FeatureCollection, Geometry } from 'geojson';

import type { SelectorDisplayItem } from '@/features/shared/api/types';

export type SelectionMode = 'single' | 'multi';

export const LONG_NAME_THRESHOLD = 14;
export const VERY_LONG_NAME_THRESHOLD = 37;

export type MatchRank =
  | 'display_name'
  | 'display_part'
  | 'hidden_subarea'
  | 'raw_nta'
  | 'abbreviation'
  | null;

export type SearchMatch = {
  rank: MatchRank;
  matchedTerm: string | null;
};

export type NeighborhoodPolygonProperties = {
  id?: string;
  display_key?: string;
  display_name?: string;
  borough?: string;
  region_name?: string;
  [key: string]: unknown;
};

export type NeighborhoodPolygonFeature = Feature<Geometry, NeighborhoodPolygonProperties>;
export type NeighborhoodPolygonFeatureCollection = FeatureCollection<
  Geometry,
  NeighborhoodPolygonProperties
>;

const MATCH_PRIORITY: Exclude<MatchRank, null>[] = [
  'display_name',
  'display_part',
  'hidden_subarea',
  'raw_nta',
  'abbreviation',
];

export function normalizeSearchText(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/['’]/g, '')
    .replace(/[^\w\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function isLongDisplayName(displayName: string): boolean {
  const segments = displayName.split(' / ').filter(Boolean).length;
  return displayName.length > LONG_NAME_THRESHOLD || segments >= 2;
}

export function isVeryLongDisplayName(displayName: string): boolean {
  const segments = displayName.split(' / ').filter(Boolean).length;
  return displayName.length > VERY_LONG_NAME_THRESHOLD || segments >= 3;
}

export function getMatchPriority(rank: MatchRank): number {
  if (rank === null) {
    return Number.POSITIVE_INFINITY;
  }
  return MATCH_PRIORITY.indexOf(rank);
}

export function matchSelectorItem(
  item: SelectorDisplayItem,
  normalizedQuery: string,
): SearchMatch {
  if (!normalizedQuery) {
    return { rank: null, matchedTerm: null };
  }

  if (normalizeSearchText(item.display_name).includes(normalizedQuery)) {
    return { rank: 'display_name', matchedTerm: null };
  }

  for (const type of MATCH_PRIORITY.slice(1)) {
    const match = item.search_terms.find((term) => {
      if (term.type !== type) {
        return false;
      }
      return normalizeSearchText(term.term).includes(normalizedQuery);
    });
    if (match) {
      return { rank: type, matchedTerm: match.term };
    }
  }

  if (
    item.additional_boroughs?.some((borough) =>
      normalizeSearchText(borough).includes(normalizedQuery),
    )
  ) {
    // Intentionally ranked as display_name: borough context matches should surface prominently.
    return { rank: 'display_name', matchedTerm: null };
  }

  return { rank: null, matchedTerm: null };
}
