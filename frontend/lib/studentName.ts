export function formatStudentDisplayName(firstName: string, lastInitial: string): string {
  const normalizedFirstName = firstName.trim();
  const normalizedLastInitial = lastInitial.trim().replace(/\.+$/, '');

  if (!normalizedFirstName) {
    return 'Student';
  }

  if (!normalizedLastInitial) {
    return normalizedFirstName;
  }

  return `${normalizedFirstName} ${normalizedLastInitial}.`;
}
