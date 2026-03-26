import {
  TEACHING_ADDRESS_REQUIRED_MESSAGE,
  hasNonEmptyTeachingLocation,
  hasPreferredTeachingLocations,
  servicesUseInstructorLocation,
} from '@/lib/teachingLocations';

describe('teachingLocations helpers', () => {
  it('exports the teaching address validation copy', () => {
    expect(TEACHING_ADDRESS_REQUIRED_MESSAGE).toBe(
      'A teaching address is required when offering lessons at your location.'
    );
  });

  it('detects whether any teaching location is non-empty', () => {
    expect(hasNonEmptyTeachingLocation(['', '  ', 'Studio A'])).toBe(true);
    expect(hasNonEmptyTeachingLocation(['', '   '])).toBe(false);
  });

  it('detects preferred teaching locations from API payloads', () => {
    expect(
      hasPreferredTeachingLocations([
        null,
        'not-an-object',
        { address: '   ' },
        { address: '123 Main St' },
      ])
    ).toBe(true);
    expect(hasPreferredTeachingLocations([{ address: '   ' }, { label: 'Studio' }])).toBe(
      false
    );
    expect(hasPreferredTeachingLocations('invalid')).toBe(false);
  });

  it('detects whether any service uses instructor_location', () => {
    expect(
      servicesUseInstructorLocation([
        null,
        { format_prices: 'invalid' },
        { format_prices: [{ format: 'online' }] },
        { format_prices: [{ format: 'instructor_location' }] },
      ])
    ).toBe(true);
    expect(servicesUseInstructorLocation([{ format_prices: [{ format: 'student_location' }] }])).toBe(
      false
    );
    expect(servicesUseInstructorLocation('invalid')).toBe(false);
  });
});
