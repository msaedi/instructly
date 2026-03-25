import type { BookingResponse, InstructorBookingResponse } from '@/features/shared/api/types';

type BookingLocationType = BookingResponse['location_type'] | InstructorBookingResponse['location_type'];

export function formatBookingLocationLabel(locationType: BookingLocationType): string {
  switch (locationType) {
    case 'online':
      return 'Online';
    case 'student_location':
      return "At student's location";
    case 'instructor_location':
      return "At instructor's location";
    case 'neutral_location':
      return 'At a meeting point';
    default:
      return 'Location to be confirmed';
  }
}

export function formatBookingLocationDetail(
  locationType: BookingLocationType,
  locationAddress?: string | null,
  meetingLocation?: string | null,
  serviceArea?: string | null
): string {
  const label = formatBookingLocationLabel(locationType);
  if (locationType === 'online') {
    return label;
  }

  const explicitAddress = locationAddress?.trim();
  if (explicitAddress) {
    return explicitAddress;
  }

  const suffix = [meetingLocation?.trim(), serviceArea?.trim()].find(
    (value) => typeof value === 'string' && value.length > 0
  );

  return suffix ? `${label} · ${suffix}` : label;
}
