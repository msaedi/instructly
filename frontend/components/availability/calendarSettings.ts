import { availableFormatsFromPrices } from '@/lib/pricing/formatPricing';
import type { InstructorProfile, InstructorService } from '@/types/instructor';

export const CALENDAR_SETTINGS_DEFAULTS = {
  nonTravelBufferMinutes: 15,
  travelBufferMinutes: 60,
  overnightProtectionEnabled: true,
} as const;

export const CALENDAR_BUFFER_OPTIONS = [0, 5, 10, 15, 20, 25, 30, 45, 60, 75, 90, 120] as const;
export const TRAVEL_BUFFER_OPTIONS = CALENDAR_BUFFER_OPTIONS.filter((value) => value >= 15);

export type CalendarSettingsDraft = {
  nonTravelBufferMinutes: number;
  travelBufferMinutes: number;
  overnightProtectionEnabled: boolean;
};

export type CalendarSettingsAcknowledgementVariant =
  | 'mixed_formats'
  | 'non_travel_only'
  | 'travel_only';

export function getCalendarSettingsDraft(
  profile?: Pick<
    InstructorProfile,
    | 'non_travel_buffer_minutes'
    | 'travel_buffer_minutes'
    | 'overnight_protection_enabled'
    | 'services'
  > | null
): CalendarSettingsDraft {
  return {
    nonTravelBufferMinutes:
      profile?.non_travel_buffer_minutes ?? CALENDAR_SETTINGS_DEFAULTS.nonTravelBufferMinutes,
    travelBufferMinutes: profile?.travel_buffer_minutes ?? CALENDAR_SETTINGS_DEFAULTS.travelBufferMinutes,
    overnightProtectionEnabled:
      profile?.overnight_protection_enabled ?? CALENDAR_SETTINGS_DEFAULTS.overnightProtectionEnabled,
  };
}

export function areCalendarSettingsEqual(
  left: CalendarSettingsDraft | null,
  right: CalendarSettingsDraft | null
): boolean {
  if (!left || !right) {
    return left === right;
  }

  return (
    left.nonTravelBufferMinutes === right.nonTravelBufferMinutes &&
    left.travelBufferMinutes === right.travelBufferMinutes &&
    left.overnightProtectionEnabled === right.overnightProtectionEnabled
  );
}

export function deriveCalendarAcknowledgementVariant(
  services: InstructorService[] = []
): CalendarSettingsAcknowledgementVariant {
  const allFormats = new Set(
    services.flatMap((service) => availableFormatsFromPrices(service.format_prices ?? []))
  );

  const hasTravel = allFormats.has('student_location');
  const hasNonTravel = allFormats.has('online') || allFormats.has('instructor_location');

  if (hasTravel && hasNonTravel) {
    return 'mixed_formats';
  }

  if (hasTravel) {
    return 'travel_only';
  }

  return 'non_travel_only';
}
