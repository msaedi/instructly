import { formatStudentDisplayName } from '../studentName';

describe('formatStudentDisplayName', () => {
  it('formats first name with last initial and a trailing period', () => {
    expect(formatStudentDisplayName('John', 'S')).toBe('John S.');
    expect(formatStudentDisplayName('John', 'S.')).toBe('John S.');
  });

  it('returns only the first name when the last initial is blank', () => {
    expect(formatStudentDisplayName('John', '')).toBe('John');
  });

  it('falls back to Student when the first name is empty', () => {
    expect(formatStudentDisplayName('', 'S')).toBe('Student');
  });
});
