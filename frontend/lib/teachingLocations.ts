export const TEACHING_ADDRESS_REQUIRED_MESSAGE =
  'A teaching address is required when offering lessons at your location.';

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object';
}

export function hasNonEmptyTeachingLocation(locations: readonly string[]): boolean {
  return locations.some((location: string) => location.trim().length > 0);
}

export function hasPreferredTeachingLocations(
  preferredTeachingLocations: unknown
): boolean {
  if (!Array.isArray(preferredTeachingLocations)) {
    return false;
  }

  const locations = preferredTeachingLocations as unknown[];
  return locations.some((location: unknown) => {
    if (!isRecord(location)) {
      return false;
    }

    const address = location['address'];
    return (
      typeof address === 'string' &&
      address.trim().length > 0
    );
  });
}

export function servicesUseInstructorLocation(services: unknown): boolean {
  if (!Array.isArray(services)) {
    return false;
  }

  const serviceList = services as unknown[];
  return serviceList.some((service: unknown) => {
    if (!isRecord(service)) {
      return false;
    }

    const formatPrices = Array.isArray(service['format_prices'])
      ? (service['format_prices'] as Array<Record<string, unknown>>)
      : [];

    return formatPrices.some(
      (formatPrice: Record<string, unknown>) =>
        formatPrice['format'] === 'instructor_location'
    );
  });
}
