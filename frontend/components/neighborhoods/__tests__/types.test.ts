import {
  LONG_NAME_THRESHOLD,
  getMatchPriority,
  isLongDisplayName,
  matchSelectorItem,
  normalizeSearchText,
} from '../types';
import type { SelectorDisplayItem } from '@/features/shared/api/types';

function makeItem(
  overrides: Partial<SelectorDisplayItem> & Pick<SelectorDisplayItem, 'display_key' | 'display_name' | 'borough'>,
): SelectorDisplayItem {
  return {
    additional_boroughs: overrides.additional_boroughs ?? [],
    borough: overrides.borough,
    display_key: overrides.display_key,
    display_name: overrides.display_name,
    display_order: overrides.display_order ?? 0,
    nta_ids: overrides.nta_ids ?? [overrides.display_key],
    search_terms: overrides.search_terms ?? [],
  };
}

describe('neighborhood selector types utilities', () => {
  it('normalizes punctuation, apostrophes, and repeated whitespace', () => {
    expect(normalizeSearchText("  Prince's...   Bay  ")).toBe('princes bay');
  });

  it('marks long display names when they exceed the threshold', () => {
    expect(isLongDisplayName('x'.repeat(LONG_NAME_THRESHOLD))).toBe(false);
    expect(isLongDisplayName('x'.repeat(LONG_NAME_THRESHOLD + 1))).toBe(true);
  });

  it('marks multi-segment compound names as full-width even below the character threshold', () => {
    expect(isLongDisplayName('Eastchester / Edenwald / Baychester')).toBe(true);
    expect(isLongDisplayName('Chelsea / Hudson Yards')).toBe(true);
  });

  it('marks the current nine long-form neighborhood labels as full-width candidates', () => {
    const longNeighborhoodNames = [
      "Annadale / Huguenot / Prince's Bay / Woodrow",
      'Carroll Gardens / Cobble Hill / Gowanus / Red Hook',
      'Grasmere / Arrochar / South Beach / Dongan Hills',
      'Mariners Harbor / Arlington / Graniteville',
      'New Springville / Willowbrook / Bulls Head / Travis',
      'Rockaway Park / Belle Harbor / Broad Channel / Breezy Point',
      'Sheepshead Bay / Manhattan Beach / Gerritsen Beach',
      'Todt Hill / Emerson Hill / Lighthouse Hill / Manor Heights',
      'West New Brighton / Silver Lake / Grymes Hill',
    ];

    expect(longNeighborhoodNames).toHaveLength(9);
    expect(longNeighborhoodNames.every((name) => isLongDisplayName(name))).toBe(true);
  });

  it('marks long compound names over the threshold as full-width candidates', () => {
    expect(isLongDisplayName('Financial District / Battery Park City')).toBe(true);
  });

  it('returns Infinity for null match priority and ranks other types deterministically', () => {
    expect(getMatchPriority(null)).toBe(Number.POSITIVE_INFINITY);
    expect(getMatchPriority('display_part')).toBeLessThan(getMatchPriority('raw_nta'));
  });

  it('returns no match for empty queries', () => {
    const item = makeItem({
      borough: 'Queens',
      display_key: 'south-jamaica',
      display_name: 'South Jamaica',
    });

    expect(matchSelectorItem(item, '')).toEqual({ rank: null, matchedTerm: null });
  });

  it('matches additional boroughs when the display name and aliases do not match', () => {
    const item = makeItem({
      borough: 'Bronx',
      display_key: 'kingsbridge-marble-hill',
      display_name: 'Kingsbridge / Marble Hill',
      additional_boroughs: ['Manhattan'],
      search_terms: [{ term: 'Kingsbridge', type: 'display_part' }],
    });

    expect(matchSelectorItem(item, normalizeSearchText('manhattan'))).toEqual({
      rank: 'display_name',
      matchedTerm: null,
    });
  });

  it('returns no match when nothing matches the query', () => {
    const item = makeItem({
      borough: 'Manhattan',
      display_key: 'chelsea',
      display_name: 'Chelsea',
      search_terms: [{ term: 'Chelsea', type: 'display_part' }],
    });

    expect(matchSelectorItem(item, normalizeSearchText('astoria'))).toEqual({
      rank: null,
      matchedTerm: null,
    });
  });
});
