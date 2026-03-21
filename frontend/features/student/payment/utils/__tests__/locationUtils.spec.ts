import {
  ADDRESS_PLACEHOLDER,
  AGREED_PUBLIC_LOCATION_PLACEHOLDER,
  INSTRUCTOR_LOCATION_PLACEHOLDER,
  getGenericMeetingLocationLabel,
  getTimeSelectionModalLocationType,
  isOnlineLocationLabel,
  isPlaceholderMeetingLocation,
  normalizeLocationTypeHint,
  resolveLocationType,
  sanitizeMeetingLocation,
} from '../locationUtils';

describe('locationUtils', () => {
  it('recognizes online labels and ignores non-string values', () => {
    expect(ADDRESS_PLACEHOLDER).toBe('Student provided address');
    expect(INSTRUCTOR_LOCATION_PLACEHOLDER).toBe('Instructor location');
    expect(AGREED_PUBLIC_LOCATION_PLACEHOLDER).toBe('Agreed public location');
    expect(isOnlineLocationLabel('Virtual lesson')).toBe(true);
    expect(isOnlineLocationLabel(42)).toBe(false);
  });

  it('normalizes location hints from strings and blanks', () => {
    expect(normalizeLocationTypeHint('remote')).toBe('online');
    expect(normalizeLocationTypeHint('studio')).toBe('instructor_location');
    expect(normalizeLocationTypeHint('public meetup')).toBe('neutral_location');
    expect(normalizeLocationTypeHint('in-person')).toBe('student_location');
    expect(normalizeLocationTypeHint('   ')).toBeNull();
    expect(normalizeLocationTypeHint(undefined)).toBeNull();
  });

  it('resolves location type from explicit hints, modality, fallback text, and defaults', () => {
    expect(
      resolveLocationType({
        locationTypeHint: 'neutral_location',
        modalityHint: 'remote',
        fallbackLocation: 'Online lesson',
      }),
    ).toBe('neutral_location');

    expect(
      resolveLocationType({
        modalityHint: 'studio',
        fallbackLocation: '123 Main St',
      }),
    ).toBe('instructor_location');

    expect(
      resolveLocationType({
        fallbackLocation: 'Online only',
      }),
    ).toBe('online');

    expect(
      resolveLocationType({
        defaultLocationType: 'student_location',
      }),
    ).toBe('student_location');
  });

  it('filters placeholder meeting labels and preserves real locations', () => {
    expect(isPlaceholderMeetingLocation(123)).toBe(false);
    expect(isPlaceholderMeetingLocation('   ')).toBe(false);
    expect(isPlaceholderMeetingLocation(INSTRUCTOR_LOCATION_PLACEHOLDER)).toBe(true);
    expect(isPlaceholderMeetingLocation('At a meeting point')).toBe(true);
    expect(isPlaceholderMeetingLocation('123 Main St')).toBe(false);

    expect(sanitizeMeetingLocation('At instructor\'s location')).toBe('');
    expect(sanitizeMeetingLocation('  123 Main St  ')).toBe('123 Main St');
  });

  it('returns generic labels for checkout summaries and modal mapping', () => {
    expect(getGenericMeetingLocationLabel('online')).toBe('Online');
    expect(getGenericMeetingLocationLabel('instructor_location')).toBe("At instructor's location");
    expect(getGenericMeetingLocationLabel('neutral_location')).toBe('At a meeting point');
    expect(getGenericMeetingLocationLabel('student_location')).toBe('At your location');

    expect(getTimeSelectionModalLocationType('neutral_location')).toBe('student_location');
    expect(getTimeSelectionModalLocationType('online')).toBe('online');
  });
});
