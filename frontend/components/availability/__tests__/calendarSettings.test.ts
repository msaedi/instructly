import {
  CALENDAR_BUFFER_OPTIONS,
  CALENDAR_SETTINGS_DEFAULTS,
  TRAVEL_BUFFER_OPTIONS,
  areCalendarSettingsEqual,
  deriveCalendarAcknowledgementVariant,
  formatTagLabel,
  getCalendarSettingsDraft,
  getAvailableTagOptions,
  isTaggingEnabled,
} from '../calendarSettings';
import { TAG_NO_TRAVEL, TAG_NONE, TAG_ONLINE_ONLY } from '@/lib/calendar/bitset';

const serviceWithFormats = (...formats: Array<'student_location' | 'instructor_location' | 'online'>) => ({
  id: `service-${formats.join('-')}`,
  service_catalog_id: 'catalog-1',
  service_catalog_name: 'Piano',
  min_hourly_rate: 90,
  description: null,
  format_prices: formats.map((format, index) => ({
    format,
    hourly_rate: 90 + index * 10,
  })),
});

describe('calendarSettings helpers', () => {
  it('builds defaults when profile settings are missing', () => {
    expect(getCalendarSettingsDraft()).toEqual(CALENDAR_SETTINGS_DEFAULTS);
  });

  it('builds a draft from instructor profile values', () => {
    expect(
      getCalendarSettingsDraft({
        non_travel_buffer_minutes: 30,
        travel_buffer_minutes: 90,
        overnight_protection_enabled: false,
        services: [],
      })
    ).toEqual({
      nonTravelBufferMinutes: 30,
      travelBufferMinutes: 90,
      overnightProtectionEnabled: false,
    });
  });

  it('compares null drafts safely', () => {
    const draft = {
      nonTravelBufferMinutes: 15,
      travelBufferMinutes: 60,
      overnightProtectionEnabled: true,
    };

    expect(areCalendarSettingsEqual(null, null)).toBe(true);
    expect(areCalendarSettingsEqual(draft, null)).toBe(false);
    expect(areCalendarSettingsEqual(null, draft)).toBe(false);
    expect(areCalendarSettingsEqual(draft, { ...draft })).toBe(true);
    expect(
      areCalendarSettingsEqual(draft, {
        ...draft,
        overnightProtectionEnabled: false,
      })
    ).toBe(false);
  });

  it('derives the mixed-format acknowledgement variant', () => {
    expect(
      deriveCalendarAcknowledgementVariant([serviceWithFormats('student_location', 'online')])
    ).toBe('mixed_formats');
  });

  it('defaults the acknowledgement variant to non-travel when no services are present', () => {
    expect(deriveCalendarAcknowledgementVariant()).toBe('non_travel_only');
    expect(getAvailableTagOptions()).toEqual([]);
    expect(isTaggingEnabled()).toBe(false);
  });

  it('derives the travel-only acknowledgement variant', () => {
    expect(deriveCalendarAcknowledgementVariant([serviceWithFormats('student_location')])).toBe(
      'travel_only'
    );
  });

  it('derives the non-travel acknowledgement variant and exposes valid options', () => {
    expect(deriveCalendarAcknowledgementVariant([serviceWithFormats('instructor_location')])).toBe(
      'non_travel_only'
    );
    expect(CALENDAR_BUFFER_OPTIONS).toContain(10);
    expect(CALENDAR_BUFFER_OPTIONS).not.toContain(0);
    expect(TRAVEL_BUFFER_OPTIONS).toEqual([30, 45, 60, 75, 90, 120]);
  });

  it('returns no tag options for single-format instructors', () => {
    expect(getAvailableTagOptions([serviceWithFormats('online')])).toEqual([]);
    expect(getAvailableTagOptions([serviceWithFormats('instructor_location')])).toEqual([]);
    expect(getAvailableTagOptions([serviceWithFormats('student_location')])).toEqual([]);
    expect(isTaggingEnabled([serviceWithFormats('online')])).toBe(false);
  });

  it('ignores services without format_prices data', () => {
    const onlineServiceWithoutFormats = {
      ...serviceWithFormats('online'),
      format_prices: undefined,
    } as unknown as ReturnType<typeof serviceWithFormats>;

    const travelServiceWithoutFormats = {
      ...serviceWithFormats('student_location'),
      format_prices: undefined,
    } as unknown as ReturnType<typeof serviceWithFormats>;

    expect(
      deriveCalendarAcknowledgementVariant([onlineServiceWithoutFormats])
    ).toBe('non_travel_only');
    expect(getAvailableTagOptions([travelServiceWithoutFormats])).toEqual([]);
  });

  it('returns online-only for online and studio instructors', () => {
    expect(
      getAvailableTagOptions([serviceWithFormats('online', 'instructor_location')])
    ).toEqual([TAG_ONLINE_ONLY]);
  });

  it('returns online-only for online and travel instructors', () => {
    expect(getAvailableTagOptions([serviceWithFormats('online', 'student_location')])).toEqual([
      TAG_ONLINE_ONLY,
    ]);
  });

  it('returns no-travel for studio and travel instructors', () => {
    expect(
      getAvailableTagOptions([serviceWithFormats('instructor_location', 'student_location')])
    ).toEqual([TAG_NO_TRAVEL]);
  });

  it('returns both tags for instructors offering all three formats', () => {
    expect(
      getAvailableTagOptions([
        serviceWithFormats('online'),
        serviceWithFormats('student_location'),
        serviceWithFormats('instructor_location'),
      ])
    ).toEqual([TAG_ONLINE_ONLY, TAG_NO_TRAVEL]);
    expect(
      isTaggingEnabled([
        serviceWithFormats('online'),
        serviceWithFormats('student_location'),
        serviceWithFormats('instructor_location'),
      ])
    ).toBe(true);
  });

  it('maps format tags to readable labels', () => {
    expect(formatTagLabel(TAG_NONE)).toBe('All formats');
    expect(formatTagLabel(TAG_ONLINE_ONLY)).toBe('Online Only');
    expect(formatTagLabel(TAG_NO_TRAVEL)).toBe('No Travel');
  });
});
