export type AddressPlace = {
  address: string;
  label?: string;
};

export const addPreferredPlace = <T extends AddressPlace>(
  prev: T[],
  rawValue: string,
  buildEntry: (trimmed: string) => T,
  maxPlaces = 2,
): { didAdd: boolean; next: T[] } => {
  const trimmed = rawValue.trim();
  if (!trimmed) {
    return { didAdd: false, next: prev };
  }
  if (prev.length >= maxPlaces) {
    return { didAdd: false, next: prev };
  }
  const exists = prev.some((place) => place.address.toLowerCase() === trimmed.toLowerCase());
  if (exists) {
    return { didAdd: false, next: prev };
  }
  return { didAdd: true, next: [...prev, buildEntry(trimmed)] };
};

export const updateOptionalPlaceLabel = <T extends AddressPlace>(
  prev: T[],
  index: number,
  label: string,
): T[] =>
  prev.map((place, idx) => {
    if (idx !== index) {
      return place;
    }
    const nextLabel = label.trim();
    if (!nextLabel) {
      const { label: _omit, ...rest } = place;
      return rest as T;
    }
    return { ...place, label: nextLabel };
  });

export const getNeighborhoodMatchId = (match: {
  neighborhood_id?: string | null;
  id?: string | null;
}): string | null => match.neighborhood_id || match.id || null;

export const getGlobalNeighborhoodMatchesWithIds = <T extends {
  neighborhood_id?: string | null;
  id?: string | null;
}>(
  matches: T[],
): Array<{ id: string; match: T }> =>
  matches.flatMap((match) => {
    const id = getNeighborhoodMatchId(match);
    return id ? [{ id, match }] : [];
  });
