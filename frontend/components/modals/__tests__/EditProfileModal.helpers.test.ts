import {
  addPreferredPlace,
  getGlobalNeighborhoodMatchesWithIds,
  getNeighborhoodMatchId,
  removeServiceFromProfile,
  removeIndexedItem,
  updateServiceInProfile,
  updateIndexedServiceField,
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
        label: trimmed.split(' ')[0],
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

  it('removes indexed items and leaves missing indexes untouched', () => {
    const items = [{ id: 'one' }, { id: 'two' }];

    expect(removeIndexedItem(items, 4)).toBe(items);
    expect(removeIndexedItem(items, 0)).toEqual([{ id: 'two' }]);
  });

  it('updates indexed service fields and normalizes NaN hourly rates', () => {
    const services = [
      { skill: 'Piano', hourly_rate: 75 },
      { skill: 'Guitar', hourly_rate: 60 },
    ];

    expect(updateIndexedServiceField(services, 9, 'hourly_rate', 90)).toBe(services);

    const updatedRate = updateIndexedServiceField(services, 0, 'hourly_rate', Number.NaN);
    expect(updatedRate[0]).toEqual({ skill: 'Piano', hourly_rate: 0 });

    const updatedSkill = updateIndexedServiceField(services, 1, 'skill', 'Bass');
    expect(updatedSkill[1]).toEqual({ skill: 'Bass', hourly_rate: 60 });
  });

  it('prefers neighborhood_id and falls back to id when matching neighborhoods', () => {
    expect(getNeighborhoodMatchId({ neighborhood_id: 'n-1', id: 'fallback' })).toBe('n-1');
    expect(getNeighborhoodMatchId({ id: 'fallback' })).toBe('fallback');
    expect(getNeighborhoodMatchId({})).toBeNull();
  });

  it('removes and updates services without mutating the original profile on invalid indexes', () => {
    const profileData = {
      services: [
        { skill: 'Piano', hourly_rate: 75 },
        { skill: 'Guitar', hourly_rate: 60 },
      ],
    };

    const missingRemoval = removeServiceFromProfile(profileData, 9);
    expect(missingRemoval.nextProfileData).toBe(profileData);
    expect(missingRemoval.removedService).toBeNull();

    const removed = removeServiceFromProfile(profileData, 1);
    expect(removed.removedService).toEqual({ skill: 'Guitar', hourly_rate: 60 });
    expect(removed.nextProfileData.services).toEqual([{ skill: 'Piano', hourly_rate: 75 }]);

    expect(updateServiceInProfile(profileData, 9, 'hourly_rate', 90)).toBe(profileData);
    expect(updateServiceInProfile(profileData, 0, 'hourly_rate', Number.NaN).services[0]).toEqual({
      skill: 'Piano',
      hourly_rate: 0,
    });
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
