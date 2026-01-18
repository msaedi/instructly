import {
  formatRelativeTimestamp,
  formatTimeLabel,
  formatShortDate,
  getInitials,
  formatStudentName,
} from '../formatters';

describe('formatters', () => {
  describe('formatRelativeTimestamp', () => {
    beforeEach(() => {
      jest.useFakeTimers().setSystemTime(new Date('2024-01-15T12:00:00Z'));
    });

    afterEach(() => {
      jest.useRealTimers();
    });

    it('returns empty string for null input', () => {
      expect(formatRelativeTimestamp(null)).toBe('');
    });

    it('returns empty string for undefined input', () => {
      expect(formatRelativeTimestamp(undefined)).toBe('');
    });

    it('returns empty string for empty string input', () => {
      expect(formatRelativeTimestamp('')).toBe('');
    });

    it('returns empty string for invalid date string', () => {
      expect(formatRelativeTimestamp('invalid-date')).toBe('');
    });

    it('formats recent date as "less than a minute ago"', () => {
      const now = new Date('2024-01-15T11:59:30Z');
      const result = formatRelativeTimestamp(now);
      expect(result).toContain('ago');
    });

    it('formats date from a few minutes ago', () => {
      const fiveMinutesAgo = new Date('2024-01-15T11:55:00Z');
      const result = formatRelativeTimestamp(fiveMinutesAgo);
      expect(result).toContain('5 minutes ago');
    });

    it('formats date from hours ago', () => {
      const twoHoursAgo = new Date('2024-01-15T10:00:00Z');
      const result = formatRelativeTimestamp(twoHoursAgo);
      expect(result).toContain('2 hours ago');
    });

    it('formats date from a day ago', () => {
      const oneDayAgo = new Date('2024-01-14T12:00:00Z');
      const result = formatRelativeTimestamp(oneDayAgo);
      expect(result).toContain('1 day ago');
    });

    it('handles string input', () => {
      const result = formatRelativeTimestamp('2024-01-15T11:55:00Z');
      expect(result).toContain('5 minutes ago');
    });

    it('handles Date object input', () => {
      const date = new Date('2024-01-15T11:55:00Z');
      const result = formatRelativeTimestamp(date);
      expect(result).toContain('5 minutes ago');
    });
  });

  describe('formatTimeLabel', () => {
    it('returns empty string for null input', () => {
      expect(formatTimeLabel(null)).toBe('');
    });

    it('returns empty string for undefined input', () => {
      expect(formatTimeLabel(undefined)).toBe('');
    });

    it('returns empty string for empty string input', () => {
      expect(formatTimeLabel('')).toBe('');
    });

    it('returns empty string for invalid date string', () => {
      expect(formatTimeLabel('invalid-date')).toBe('');
    });

    it('formats time correctly from string', () => {
      const result = formatTimeLabel('2024-01-15T14:30:00Z');
      // Format depends on locale, but should contain time components
      expect(result).toBeTruthy();
      expect(result.length).toBeGreaterThan(0);
    });

    it('formats time correctly from Date object', () => {
      const date = new Date('2024-01-15T14:30:00Z');
      const result = formatTimeLabel(date);
      expect(result).toBeTruthy();
      expect(result.length).toBeGreaterThan(0);
    });
  });

  describe('formatShortDate', () => {
    it('returns empty string for null input', () => {
      expect(formatShortDate(null)).toBe('');
    });

    it('returns empty string for undefined input', () => {
      expect(formatShortDate(undefined)).toBe('');
    });

    it('returns empty string for empty string input', () => {
      expect(formatShortDate('')).toBe('');
    });

    it('returns empty string for invalid date string', () => {
      expect(formatShortDate('invalid-date')).toBe('');
    });

    it('formats date in MM/dd/yy format from string', () => {
      const result = formatShortDate('2024-11-28T12:00:00Z');
      expect(result).toBe('11/28/24');
    });

    it('formats date in MM/dd/yy format from Date object', () => {
      const date = new Date('2024-11-28T12:00:00Z');
      const result = formatShortDate(date);
      expect(result).toBe('11/28/24');
    });

    it('pads single digit months', () => {
      const result = formatShortDate('2024-01-05T12:00:00Z');
      expect(result).toBe('01/05/24');
    });
  });

  describe('getInitials', () => {
    it('returns initials from first and last name', () => {
      expect(getInitials('John', 'Doe')).toBe('JD');
    });

    it('returns only first initial when last name is null', () => {
      expect(getInitials('John', null)).toBe('J');
    });

    it('returns only last initial when first name is null', () => {
      expect(getInitials(null, 'Doe')).toBe('D');
    });

    it('returns ?? when both names are null', () => {
      expect(getInitials(null, null)).toBe('??');
    });

    it('returns ?? when both names are undefined', () => {
      expect(getInitials(undefined, undefined)).toBe('??');
    });

    it('returns ?? when both names are empty strings', () => {
      expect(getInitials('', '')).toBe('??');
    });

    it('converts initials to uppercase', () => {
      expect(getInitials('john', 'doe')).toBe('JD');
    });

    it('handles single character names', () => {
      expect(getInitials('J', 'D')).toBe('JD');
    });

    it('handles first name only with empty last', () => {
      expect(getInitials('John', '')).toBe('J');
    });

    it('handles last name only with empty first', () => {
      expect(getInitials('', 'Doe')).toBe('D');
    });
  });

  describe('formatStudentName', () => {
    it('formats full name with last initial', () => {
      expect(formatStudentName('John', 'Doe')).toBe('John D.');
    });

    it('returns first name only when last name is null', () => {
      expect(formatStudentName('John', null)).toBe('John');
    });

    it('returns last name only when first name is null', () => {
      expect(formatStudentName(null, 'Doe')).toBe('Doe');
    });

    it('returns "Student" when both names are null', () => {
      expect(formatStudentName(null, null)).toBe('Student');
    });

    it('returns "Student" when both names are undefined', () => {
      expect(formatStudentName(undefined, undefined)).toBe('Student');
    });

    it('returns "Student" when both names are empty strings', () => {
      expect(formatStudentName('', '')).toBe('Student');
    });

    it('trims whitespace from names', () => {
      expect(formatStudentName('  John  ', '  Doe  ')).toBe('John D.');
    });

    it('handles single character last name', () => {
      expect(formatStudentName('John', 'D')).toBe('John D.');
    });

    it('returns first name when last name is empty after trimming', () => {
      expect(formatStudentName('John', '   ')).toBe('John');
    });
  });
});
