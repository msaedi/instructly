export const buildDisplayDate = (value: string | Date | null | undefined): Date | null => {
  if (!value) {
    return null;
  }
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }
  const isoCandidate = typeof value === 'string' ? value.trim() : String(value);
  if (!isoCandidate) {
    return null;
  }
  const parsed = new Date(`${isoCandidate}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};
