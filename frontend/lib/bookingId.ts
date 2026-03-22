export function shortenBookingId(ulid: string): string {
  const normalized = ulid.trim().toUpperCase();

  if (normalized.length < 9) {
    return normalized;
  }

  const prefix = normalized.slice(5, 8);
  const suffix = normalized.slice(-4);

  return `${prefix}-${suffix}`;
}
