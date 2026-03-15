import {
  addPreferredPlace,
  getGlobalNeighborhoodMatchesWithIds,
  getNeighborhoodMatchId,
  updateOptionalPlaceLabel,
} from '../EditProfileModal.helpers';

describe('EditProfileModal helpers', () => {
  it('does not add blank, duplicate, or third preferred places', () => {
    const blankResult = addPreferredPlace([], '   ', (trimmed) => ({ address: trimmed }));
    expect(blankResult).toEqual({ didAdd: false, next: [] });

    const duplicateResult = addPreferredPlace(
      [{ address: '123 Main St' }],
      '123 MAIN ST',
      (trimmed) => ({ address: trimmed }),
    );
    expect(duplicateResult.didAdd).toBe(false);
    expect(duplicateResult.next).toEqual([{ address: '123 Main St' }]);

    const maxedResult = addPreferredPlace(
      [{ address: 'One' }, { address: 'Two' }],
      'Three',
      (trimmed) => ({ address: trimmed }),
    );
    expect(maxedResult.didAdd).toBe(false);
    expect(maxedResult.next).toHaveLength(2);
  });

  it('adds a normalized preferred place when space is available', () => {
    const result = addPreferredPlace<{ address: string; label?: string }>(
      [{ address: 'One' }],
      ' Two ',
      (trimmed) => ({
        address: trimmed,
        label: trimmed.split(' ')[0] ?? trimmed,
      }),
    );

    expect(result.didAdd).toBe(true);
    expect(result.next).toEqual([
      { address: 'One' },
      { address: 'Two', label: 'Two' },
    ]);
  });

  it('trims labels and removes blank optional labels', () => {
    const trimmed = updateOptionalPlaceLabel(
      [
        { address: '123 Main St', label: 'Studio' },
        { address: 'Central Park', label: 'Park' },
      ],
      1,
      '  Meet here  ',
    );
    expect(trimmed[1]).toEqual({ address: 'Central Park', label: 'Meet here' });

    const cleared = updateOptionalPlaceLabel(trimmed, 1, '   ');
    expect(cleared[1]).toEqual({ address: 'Central Park' });
  });

  it('prefers neighborhood_id and falls back to id when matching neighborhoods', () => {
    expect(getNeighborhoodMatchId({ neighborhood_id: 'n-1', id: 'fallback' })).toBe('n-1');
    expect(getNeighborhoodMatchId({ id: 'fallback' })).toBe('fallback');
    expect(getNeighborhoodMatchId({})).toBeNull();
  });

  it('filters global neighborhood matches down to renderable ids', () => {
    expect(
      getGlobalNeighborhoodMatchesWithIds([
        { id: 'fallback', name: 'Fallback' },
        { neighborhood_id: 'primary', name: 'Primary' },
        { name: 'Discard me' },
      ]),
    ).toEqual([
      { id: 'fallback', match: { id: 'fallback', name: 'Fallback' } },
      { id: 'primary', match: { neighborhood_id: 'primary', name: 'Primary' } },
    ]);
  });
});
