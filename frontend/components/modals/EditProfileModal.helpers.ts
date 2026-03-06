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

export const removeIndexedItem = <T>(items: T[], index: number): T[] => {
  if (!items[index]) {
    return items;
  }
  return items.filter((_, currentIndex) => currentIndex !== index);
};

type ServiceLike = {
  hourly_rate?: number;
};

export const updateIndexedServiceField = <T extends ServiceLike>(
  services: T[],
  index: number,
  field: keyof T,
  value: string | number,
): T[] => {
  const service = services[index];
  if (!service) {
    return services;
  }

  const nextValue =
    field === 'hourly_rate' && typeof value === 'number' && Number.isNaN(value)
      ? 0
      : value;

  const next = [...services];
  next[index] = { ...service, [field]: nextValue as T[keyof T] };
  return next;
};

export const getNeighborhoodMatchId = (match: {
  neighborhood_id?: string | null;
  id?: string | null;
}): string | null => match.neighborhood_id || match.id || null;

export const removeServiceFromProfile = <
  TProfile extends { services: TService[] },
  TService extends { skill?: string },
>(
  profileData: TProfile,
  index: number,
): { nextProfileData: TProfile; removedService: TService | null } => {
  const nextServices = removeIndexedItem(profileData.services, index);
  if (nextServices === profileData.services) {
    return { nextProfileData: profileData, removedService: null };
  }
  return {
    nextProfileData: { ...profileData, services: nextServices },
    removedService: profileData.services[index] ?? null,
  };
};

export const updateServiceInProfile = <
  TProfile extends { services: TService[] },
  TService extends ServiceLike,
>(
  profileData: TProfile,
  index: number,
  field: keyof TService,
  value: string | number,
): TProfile => {
  const nextServices = updateIndexedServiceField(profileData.services, index, field, value);
  if (nextServices === profileData.services) {
    return profileData;
  }
  return { ...profileData, services: nextServices };
};

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
