import { BYTES_PER_DAY } from '@/lib/calendar/bitset';
import type { WeekBits } from '@/types/availability';

const BYTE_MASK = 0xff;

export function countSetBits(value: number): number {
  let count = 0;
  let cursor = value & BYTE_MASK;
  while (cursor > 0) {
    count += cursor & 1;
    cursor >>= 1;
  }
  return count;
}

export function computeBitsDelta(
  previous: WeekBits,
  next: WeekBits,
): { added: number; removed: number } {
  let added = 0;
  let removed = 0;
  const allDates = new Set([...Object.keys(previous), ...Object.keys(next)]);
  allDates.forEach((date) => {
    const prevBits = previous[date];
    const nextBits = next[date];
    for (let i = 0; i < BYTES_PER_DAY; i += 1) {
      const prevByte = prevBits ? prevBits[i] ?? 0 : 0;
      const nextByte = nextBits ? nextBits[i] ?? 0 : 0;
      const addedMask = nextByte & (~prevByte & BYTE_MASK);
      const removedMask = prevByte & (~nextByte & BYTE_MASK);
      added += countSetBits(addedMask);
      removed += countSetBits(removedMask);
    }
  });
  return { added, removed };
}
