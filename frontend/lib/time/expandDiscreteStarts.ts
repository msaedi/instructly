import { timeToMinutes } from '@/lib/time';

/** Generate all valid booking start times within a time window at a given step. */
export function expandDiscreteStarts(
  start: string,
  end: string,
  stepMinutes: number,
  requiredMinutes: number,
): string[] {
  const startTotal = timeToMinutes(start);
  const endTotal = timeToMinutes(end, { isEndTime: true });

  // Snap up to the next step boundary so all starts align to the booking grid
  const snapped = Math.ceil(startTotal / stepMinutes) * stepMinutes;

  const times: string[] = [];
  for (let t = snapped; t + requiredMinutes <= endTotal; t += stepMinutes) {
    const h = Math.floor(t / 60);
    const m = t % 60;
    const ampm = h >= 12 ? 'pm' : 'am';
    const displayHour = (h % 12) || 12;
    times.push(`${displayHour}:${String(m).padStart(2, '0')}${ampm}`);
  }
  return times;
}
