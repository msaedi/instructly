import type { LocationType } from '@/types/booking';

export const ADDRESS_PLACEHOLDER = 'Student provided address';
export const INSTRUCTOR_LOCATION_PLACEHOLDER = 'Instructor location';
export const AGREED_PUBLIC_LOCATION_PLACEHOLDER = 'Agreed public location';

const ONLINE_LOCATION_PATTERN = /online|remote|virtual/i;

const PLACEHOLDER_LOCATIONS = new Set<string>([
  ADDRESS_PLACEHOLDER.toLowerCase(),
  INSTRUCTOR_LOCATION_PLACEHOLDER.toLowerCase(),
  "instructor's location",
  AGREED_PUBLIC_LOCATION_PLACEHOLDER.toLowerCase(),
  'at your location',
  "at instructor's location",
  'at a meeting point',
  'in-person lesson',
]);

export const isOnlineLocationLabel = (value: unknown): boolean =>
  typeof value === 'string' && ONLINE_LOCATION_PATTERN.test(value);

export const normalizeLocationTypeHint = (value: unknown): LocationType | null => {
  if (typeof value !== 'string') {
    return null;
  }

  const raw = value.trim().toLowerCase();
  if (!raw) {
    return null;
  }

  if (raw.includes('remote') || raw.includes('online') || raw.includes('virtual')) {
    return 'online';
  }
  if (raw.includes('instructor') || raw.includes('studio')) {
    return 'instructor_location';
  }
  if (raw.includes('neutral') || raw.includes('public')) {
    return 'neutral_location';
  }
  if (
    raw.includes('student') ||
    raw.includes('home') ||
    raw.includes('in_person') ||
    raw.includes('in-person')
  ) {
    return 'student_location';
  }

  return null;
};

export const resolveLocationType = ({
  locationTypeHint,
  modalityHint,
  fallbackLocation,
  defaultLocationType = 'student_location',
}: {
  locationTypeHint?: unknown;
  modalityHint?: unknown;
  fallbackLocation?: string | undefined;
  defaultLocationType?: LocationType;
}): LocationType => {
  const explicitLocationType = normalizeLocationTypeHint(locationTypeHint);
  if (explicitLocationType) {
    return explicitLocationType;
  }

  const normalizedModality = normalizeLocationTypeHint(modalityHint);
  if (normalizedModality) {
    return normalizedModality;
  }

  const fallbackType = normalizeLocationTypeHint(fallbackLocation);
  if (fallbackType) {
    return fallbackType;
  }

  return defaultLocationType;
};

export const isPlaceholderMeetingLocation = (value: unknown): boolean => {
  if (typeof value !== 'string') {
    return false;
  }

  const normalized = value.trim().toLowerCase();
  if (!normalized) {
    return false;
  }

  return PLACEHOLDER_LOCATIONS.has(normalized);
};

export const sanitizeMeetingLocation = (value: unknown): string => {
  if (typeof value !== 'string') {
    return '';
  }

  const trimmed = value.trim();
  if (!trimmed || isPlaceholderMeetingLocation(trimmed)) {
    return '';
  }

  return trimmed;
};

export const getGenericMeetingLocationLabel = (locationType: LocationType): string => {
  if (locationType === 'online') {
    return 'Online';
  }
  if (locationType === 'instructor_location') {
    return "At instructor's location";
  }
  if (locationType === 'neutral_location') {
    return 'At a meeting point';
  }
  return 'At your location';
};

export const getTimeSelectionModalLocationType = (locationType: LocationType): LocationType =>
  locationType === 'neutral_location' ? 'student_location' : locationType;
