const AM_PM_REGEX = /^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*$/i;
const BASIC_TIME_REGEX = /^\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*$/;

function padTimePart(value: number): string {
  return value.toString().padStart(2, '0');
}

/**
 * Convert a human-readable time label (e.g. "2:30pm" or "14:30") into 24-hour HH:MM format.
 */
export function to24HourTime(label: string): string {
  const trimmed = String(label ?? '').trim();
  if (!trimmed) {
    throw new Error('Time value is required');
  }

  const ampmMatch = trimmed.match(AM_PM_REGEX);
  if (ampmMatch) {
    const [, hours = '0', minutes = '0', suffix = ''] = ampmMatch;
    let hourValue = parseInt(hours, 10);
    const minuteValue = parseInt(minutes, 10) || 0;
    const lowerSuffix = suffix.toLowerCase();

    if (Number.isNaN(hourValue) || hourValue < 1 || hourValue > 12) {
      throw new Error(`Invalid hour in time string: ${label}`);
    }

    if (lowerSuffix === 'pm' && hourValue !== 12) {
      hourValue += 12;
    }
    if (lowerSuffix === 'am' && hourValue === 12) {
      hourValue = 0;
    }

    return `${padTimePart(hourValue)}:${padTimePart(minuteValue)}`;
  }

  const basicMatch = trimmed.match(BASIC_TIME_REGEX);
  if (basicMatch) {
    const [, hours = '0', minutes = '0'] = basicMatch;
    const hourValue = parseInt(hours, 10);
    const minuteValue = parseInt(minutes, 10) || 0;
    if (Number.isNaN(hourValue) || hourValue < 0 || hourValue > 23) {
      throw new Error(`Invalid hour in time string: ${label}`);
    }
    if (minuteValue < 0 || minuteValue > 59) {
      throw new Error(`Invalid minutes in time string: ${label}`);
    }
    return `${padTimePart(hourValue)}:${padTimePart(minuteValue)}`;
  }

  const parsed = new Date(`1970-01-01T${trimmed}`);
  if (!Number.isNaN(parsed.getTime())) {
    return `${padTimePart(parsed.getHours())}:${padTimePart(parsed.getMinutes())}`;
  }

  throw new Error(`Unsupported time format: ${label}`);
}

/**
 * Convert a HH:MM (or HH:MM:SS) time string into minutes since midnight.
 * Treat "00:00" as 24:00 when used as an end time.
 */
export function timeToMinutes(
  value: string,
  options: { isEndTime?: boolean } = {}
): number {
  const trimmed = String(value ?? '').trim();
  if (!trimmed) {
    return 0;
  }
  const [hoursRaw = '0', minutesRaw = '0'] = trimmed.split(':');
  const hours = Number.parseInt(hoursRaw, 10);
  const minutes = Number.parseInt(minutesRaw, 10);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    return 0;
  }
  if (hours === 24 && minutes === 0) {
    return 24 * 60;
  }
  const total = hours * 60 + minutes;
  if (options.isEndTime && total === 0) {
    return 24 * 60;
  }
  return total;
}

/**
 * Add minutes to a HH:MM time string (24-hour) and return the resulting HH:MM (wrapping at 24 hours).
 */
export function addMinutesHHMM(start: string, minutesToAdd: number): string {
  if (!Number.isFinite(minutesToAdd)) {
    throw new Error('Minutes to add must be a finite number');
  }
  const normalizedStart = to24HourTime(start);
  const [hourPart = '0', minutePart = '0'] = normalizedStart.split(':');
  const startMinutes = parseInt(hourPart, 10) * 60 + parseInt(minutePart, 10);
  const totalMinutes = (startMinutes + Math.round(minutesToAdd)) % (24 * 60);
  const wrappedMinutes = totalMinutes < 0 ? totalMinutes + 24 * 60 : totalMinutes;
  const hours = Math.floor(wrappedMinutes / 60);
  const minutes = wrappedMinutes % 60;
  return `${padTimePart(hours)}:${padTimePart(minutes)}`;
}
