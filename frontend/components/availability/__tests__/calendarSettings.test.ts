import {
  CALENDAR_BUFFER_OPTIONS,
  CALENDAR_SETTINGS_DEFAULTS,
  TRAVEL_BUFFER_OPTIONS,
  areCalendarSettingsEqual,
  deriveCalendarAcknowledgementVariant,
  getCalendarSettingsDraft,
} from '../calendarSettings';

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
      deriveCalendarAcknowledgementVariant([
        {
          id: 'service-1',
          service_catalog_id: 'catalog-1',
          service_catalog_name: 'Piano',
          min_hourly_rate: 90,
          description: null,
          format_prices: [
            { format: 'student_location', hourly_rate: 120 },
            { format: 'online', hourly_rate: 90 },
          ],
        },
      ])
    ).toBe('mixed_formats');
  });

  it('derives the travel-only acknowledgement variant', () => {
    expect(
      deriveCalendarAcknowledgementVariant([
        {
          id: 'service-1',
          service_catalog_id: 'catalog-1',
          service_catalog_name: 'Piano',
          min_hourly_rate: 120,
          description: null,
          format_prices: [{ format: 'student_location', hourly_rate: 120 }],
        },
      ])
    ).toBe('travel_only');
  });

  it('derives the non-travel acknowledgement variant and exposes valid options', () => {
    expect(
      deriveCalendarAcknowledgementVariant([
        {
          id: 'service-1',
          service_catalog_id: 'catalog-1',
          service_catalog_name: 'Piano',
          min_hourly_rate: 100,
          description: null,
          format_prices: [{ format: 'instructor_location', hourly_rate: 100 }],
        },
      ])
    ).toBe('non_travel_only');
    expect(CALENDAR_BUFFER_OPTIONS).toContain(0);
    expect(TRAVEL_BUFFER_OPTIONS).toEqual([15, 20, 25, 30, 45, 60, 75, 90, 120]);
  });
});
