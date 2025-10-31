// frontend/lib/calendar/normalize.ts
//
// Pure normalization helpers for instructor availability calendar slots.
// Converts raw API slot data into day-scoped segments that respect backend
// guarantees including 24:00 end times, overnight spans, containment
// suppression, adjacency merging, and DST-aware math for America/New_York.

import type { TimeSlot } from '@/types/availability';

const DEFAULT_TIME_ZONE = 'America/New_York';

/** Time slot with the date the backend associates it with. */
export interface DatedTimeSlot extends TimeSlot {
  date: string; // YYYY-MM-DD
}

/** A timezone-aware range representing the full extent of a slot. */
export interface NormalizedRange {
  start: Date;
  end: Date;
  slot: DatedTimeSlot;
}

/** A range constrained to a single display day. */
export interface DailySegment extends NormalizedRange {
  date: string; // YYYY-MM-DD for the day this piece renders on
}

/** Final segment with layout metrics for rendering. */
export interface DayDisplaySegment extends DailySegment {
  startMinutes: number;
  endMinutes: number;
  durationMinutes: number;
}

// Cache expensive Intl.DateTimeFormat instances by time zone.
const formatterCache = new Map<string, Intl.DateTimeFormat>();

function getFormatter(timeZone: string): Intl.DateTimeFormat {
  let formatter = formatterCache.get(timeZone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat('en-US', {
      timeZone,
      hourCycle: 'h23',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
    formatterCache.set(timeZone, formatter);
  }
  return formatter;
}

function parseTime(value: string): { hour: number; minute: number; second: number } {
  const [rawHour, rawMinute = '0', rawSecond = '0'] = value.split(':');
  return {
    hour: Number(rawHour),
    minute: Number(rawMinute),
    second: Number(rawSecond),
  };
}

function formatIsoDate(date: Date, timeZone: string): string {
  const formatter = getFormatter(timeZone);
  const parts = formatter.formatToParts(date);
  const map: Record<string, string> = {};
  for (const part of parts) {
    if (part.type === 'literal') continue;
    map[part.type] = part.value;
  }
  return `${map['year']}-${map['month']}-${map['day']}`;
}

function addDays(date: string, days: number): string {
  const [yearStr, monthStr, dayStr] = date.split('-');
  const year = Number(yearStr ?? '0');
  const month = Number(monthStr ?? '1');
  const day = Number(dayStr ?? '1');
  const utc = Date.UTC(year, month - 1, day);
  const adjusted = new Date(utc + days * 24 * 60 * 60 * 1000);
  const y = adjusted.getUTCFullYear();
  const m = String(adjusted.getUTCMonth() + 1).padStart(2, '0');
  const d = String(adjusted.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function partsToObject(parts: Intl.DateTimeFormatPart[]): {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
} {
  const out = {
    year: 0,
    month: 0,
    day: 0,
    hour: 0,
    minute: 0,
    second: 0,
  };

  for (const part of parts) {
    if (part.type === 'literal') continue;
    switch (part.type) {
      case 'year':
        out.year = Number(part.value);
        break;
      case 'month':
        out.month = Number(part.value);
        break;
      case 'day':
        out.day = Number(part.value);
        break;
      case 'hour':
        out.hour = Number(part.value);
        break;
      case 'minute':
        out.minute = Number(part.value);
        break;
      case 'second':
        out.second = Number(part.value);
        break;
      default:
        break;
    }
  }

  return out;
}

function compareLocal(
  actual: { year: number; month: number; day: number; hour: number; minute: number; second: number },
  desired: { year: number; month: number; day: number; hour: number; minute: number; second: number }
): number {
  const actualMinutes =
    Date.UTC(actual.year, actual.month - 1, actual.day, actual.hour, actual.minute, actual.second) / 60000;
  const desiredMinutes =
    Date.UTC(desired.year, desired.month - 1, desired.day, desired.hour, desired.minute, desired.second) / 60000;
  return desiredMinutes - actualMinutes;
}

/**
 * Create a UTC instant representing the local time in the provided timezone.
 * Uses iterative refinement to respect DST transitions.
 */
function makeZonedDate(date: string, time: string, timeZone: string): Date {
  const [yearStr, monthStr, dayStr] = date.split('-');
  const year = Number(yearStr ?? '0');
  const month = Number(monthStr ?? '1');
  const day = Number(dayStr ?? '1');
  const { hour, minute, second } = parseTime(time);
  const desired = { year, month, day, hour, minute, second };

  let instant = Date.UTC(year, month - 1, day, hour, minute, second);
  let iterations = 0;
  let previousDiff = Number.NaN;

  while (iterations < 8) {
    const formatter = getFormatter(timeZone);
    const parts = formatter.formatToParts(new Date(instant));
    const actual = partsToObject(parts);
    const diffMinutes = compareLocal(actual, desired);

    if (diffMinutes === 0) {
      return new Date(instant);
    }

    if (!Number.isNaN(previousDiff) && Math.abs(diffMinutes) === Math.abs(previousDiff)) {
      // Non-existent local time (e.g., DST skip). Break and return best effort.
      break;
    }

    previousDiff = diffMinutes;
    instant += diffMinutes * 60000;
    iterations += 1;
  }

  return new Date(instant);
}

function minutesSinceDayStart(date: Date, day: string, timeZone: string): number {
  const midnight = makeZonedDate(day, '00:00:00', timeZone);
  return Math.round((date.getTime() - midnight.getTime()) / 60000);
}

function formatTimeOfDay(date: Date, timeZone: string): string {
  const formatter = getFormatter(timeZone);
  const parts = formatter.formatToParts(date);
  const map = partsToObject(parts);
  const hour = String(map['hour']).padStart(2, '0');
  const minute = String(map['minute']).padStart(2, '0');
  const second = String(map['second']).padStart(2, '0');
  return `${hour}:${minute}:${second}`;
}

function getDayLengthMinutes(day: string, timeZone: string): number {
  const midnight = makeZonedDate(day, '00:00:00', timeZone);
  const nextMidnight = makeZonedDate(addDays(day, 1), '00:00:00', timeZone);
  return Math.round((nextMidnight.getTime() - midnight.getTime()) / 60000);
}

function isMidnight(time: string): boolean {
  return time.startsWith('24:') || time === '24';
}

/**
 * Normalize 24:00 end times to the following day's midnight while keeping
 * the original range semantics intact.
 */
export function normalizeMidnight(
  slot: DatedTimeSlot,
  timeZone: string = DEFAULT_TIME_ZONE
): NormalizedRange {
  const { date, start_time, end_time } = slot;
  const start = makeZonedDate(date, start_time, timeZone);

  let endDate = date;
  let normalizedEnd = end_time;

  if (isMidnight(end_time)) {
    endDate = addDays(date, 1);
    normalizedEnd = '00:00:00';
  }

  let end = makeZonedDate(endDate, normalizedEnd, timeZone);

  if (end.getTime() <= start.getTime()) {
    const adjustedDate = addDays(endDate, 1);
    end = makeZonedDate(adjustedDate, normalizedEnd, timeZone);
  }

  return { start, end, slot };
}

/**
 * Split a range that may cross midnights into day-specific segments.
 */
export function splitOvernight(
  range: NormalizedRange,
  timeZone: string = DEFAULT_TIME_ZONE
): DailySegment[] {
  const segments: DailySegment[] = [];
  let cursorStart = range.start;

  while (cursorStart.getTime() < range.end.getTime()) {
    const date = formatIsoDate(cursorStart, timeZone);
    const nextDay = addDays(date, 1);
    const nextMidnight = makeZonedDate(nextDay, '00:00:00', timeZone);
    const segmentEnd = range.end.getTime() <= nextMidnight.getTime() ? range.end : nextMidnight;

    segments.push({
      start: cursorStart,
      end: segmentEnd,
      date,
      slot: range.slot,
    });

    cursorStart = segmentEnd;
  }

  return segments;
}

/**
 * Remove segments that are fully contained within another segment for the same day.
 */
export function suppressContained(segments: DailySegment[]): DailySegment[] {
  if (segments.length <= 1) {
    return segments.slice();
  }

  const sorted = [...segments].sort((a, b) => {
    const startDiff = a.start.getTime() - b.start.getTime();
    if (startDiff !== 0) return startDiff;
    return b.end.getTime() - a.end.getTime();
  });

  const result: DailySegment[] = [];

  for (const segment of sorted) {
    const last = result[result.length - 1];
    if (
      last &&
      segment.start.getTime() >= last.start.getTime() &&
      segment.end.getTime() <= last.end.getTime()
    ) {
      continue;
    }
    result.push(segment);
  }

  return result;
}

/**
 * Merge adjacent segments when the end of one exactly matches the start of the next.
 */
export function mergeAdjacent(segments: DailySegment[]): DailySegment[] {
  if (segments.length === 0) {
    return [];
  }

  const sorted = [...segments].sort((a, b) => a.start.getTime() - b.start.getTime());
  const merged: DailySegment[] = [];
  let current: DailySegment | null = null;

  for (const segment of sorted) {
    if (!current) {
      current = segment;
      continue;
    }

    if (current.end.getTime() === segment.start.getTime()) {
      current = {
        ...current,
        end: segment.end,
      };
      continue;
    }

    merged.push(current);
    current = segment;
  }

  if (current) {
    merged.push(current);
  }

  return merged;
}

/**
 * Assemble fully normalized segments for a single day.
 */
export function buildDaySegments(
  date: string,
  slots: TimeSlot[],
  timeZone: string = DEFAULT_TIME_ZONE
): DayDisplaySegment[] {
  const initial: DailySegment[] = [];

  for (const slot of slots) {
    const dated: DatedTimeSlot = { ...slot, date };
    const normalized = normalizeMidnight(dated, timeZone);
    const pieces = splitOvernight(normalized, timeZone);
    initial.push(...pieces);
  }

  const grouped: Record<string, DailySegment[]> = {};
  for (const segment of initial) {
    const existing = grouped[segment.date];
    if (existing) {
      existing.push(segment);
    } else {
      grouped[segment.date] = [segment];
    }
  }

  const result: DayDisplaySegment[] = [];

  for (const [day, segments] of Object.entries(grouped)) {
    const deduped = suppressContained(segments);
    const merged = mergeAdjacent(deduped);

    for (const segment of merged) {
      const startMinutes = minutesSinceDayStart(segment.start, segment.date, timeZone);
      const endMinutes = minutesSinceDayStart(segment.end, segment.date, timeZone);
      result.push({
        ...segment,
        date: day,
        startMinutes,
        endMinutes,
        durationMinutes: endMinutes - startMinutes,
      });
    }
  }

  return result.sort((a, b) => a.startMinutes - b.startMinutes);
}

/**
 * Normalize an entire week schedule keyed by day.
 */
export function buildWeekSegments(
  schedule: Record<string, TimeSlot[]>,
  timeZone: string = DEFAULT_TIME_ZONE
): Record<string, DayDisplaySegment[]> {
  const output: Record<string, DayDisplaySegment[]> = {};

  for (const [date, slots] of Object.entries(schedule)) {
    const segments = buildDaySegments(date, slots, timeZone);
    for (const segment of segments) {
      if (!output[segment.date]) {
        output[segment.date] = [];
      }
      output[segment.date]!.push(segment);
    }
  }

  for (const day of Object.keys(output)) {
    const segmentsForDay = output[day];
    if (segmentsForDay) {
      segmentsForDay.sort((a, b) => a.startMinutes - b.startMinutes);
    }
  }

  return output;
}

function segmentsToTimeSlots(
  segments: DayDisplaySegment[],
  timeZone: string
): TimeSlot[] {
  const slots: TimeSlot[] = [];
  if (segments.length === 0) return slots;

  const day = segments[0]?.date;
  if (!day) {
    return slots;
  }
  const dayLength = getDayLengthMinutes(day, timeZone);

  for (const segment of segments) {
    const start = formatTimeOfDay(segment.start, timeZone);
    const end =
      segment.endMinutes >= dayLength
        ? '24:00:00'
        : formatTimeOfDay(segment.end, timeZone);

    slots.push({
      start_time: start,
      end_time: end,
    });
  }

  return slots;
}

/**
 * Normalize a week schedule to remove duplicates, split overnights, and merge adjacency.
 */
export function normalizeSchedule(
  schedule: Record<string, TimeSlot[]>,
  timeZone: string = DEFAULT_TIME_ZONE
): Record<string, TimeSlot[]> {
  const segmentsByDay = buildWeekSegments(schedule, timeZone);
  const normalized: Record<string, TimeSlot[]> = {};

  for (const [day, segments] of Object.entries(segmentsByDay)) {
    if (segments.length === 0) continue;
    normalized[day] = segmentsToTimeSlots(segments, timeZone);
  }

  return normalized;
}
