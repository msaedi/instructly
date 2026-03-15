export function formatDisplayName(
  firstName?: string | null,
  lastInitial?: string | null,
  fallback: string = 'Student',
): string {
  const first = firstName?.trim() ?? '';
  const initial = lastInitial?.trim() ?? '';

  if (!first) {
    return fallback;
  }
  if (!initial) {
    return first;
  }
  return `${first} ${initial}`;
}
