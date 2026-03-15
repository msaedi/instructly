export const SLOTS_PER_DAY = 288;
export const MINUTES_PER_SLOT = 5;
export const BYTES_PER_DAY = 36;
export const BOOKING_START_STEP_MINUTES = 15;
export const AVAILABILITY_CELL_MINUTES = 30;
export const BITS_PER_CELL = 6; // AVAILABILITY_CELL_MINUTES / MINUTES_PER_SLOT
export const BITS_PER_TAG = 2;
export const TAG_BYTES_PER_DAY = Math.ceil((SLOTS_PER_DAY * BITS_PER_TAG) / 8);
export const TAG_NONE = 0;
export const TAG_ONLINE_ONLY = 1;
export const TAG_NO_TRAVEL = 2;
export const TAG_RESERVED = 3;
export type DayBits = Uint8Array;
export type DayTags = Uint8Array;
export type FormatTag =
  | typeof TAG_NONE
  | typeof TAG_ONLINE_ONLY
  | typeof TAG_NO_TRAVEL
  | typeof TAG_RESERVED;

export function newEmptyBits(): DayBits {
  return new Uint8Array(BYTES_PER_DAY);
}

export function newEmptyTags(): DayTags {
  return new Uint8Array(TAG_BYTES_PER_DAY);
}

export function idx(hh: number, mm: number): number {
  return Math.floor((hh * 60 + mm) / MINUTES_PER_SLOT);
}

export function toWindows(
  bits: DayBits,
): { start_time: string; end_time: string }[] {
  const on: number[] = [];
  for (let b = 0; b < BYTES_PER_DAY; b += 1) {
    const byteValue = bits[b] ?? 0;
    for (let bit = 0; bit < 8; bit += 1) {
      const i = b * 8 + bit;
      if (i >= SLOTS_PER_DAY) break;
      if ((byteValue >> bit) & 1) on.push(i);
    }
  }
  if (on.length === 0) return [];

  const toTime = (slotIdx: number) => {
    const totalMinutes = slotIdx * MINUTES_PER_SLOT;
    const H = Math.floor(totalMinutes / 60);
    const M = totalMinutes % 60;
    return `${String(H).padStart(2, "0")}:${String(M).padStart(
      2,
      "0",
    )}:00`;
  };

  const out: { start_time: string; end_time: string }[] = [];
  const firstSlot = on[0]!;
  let start = firstSlot;
  let prev = firstSlot;
  for (let k = 1; k < on.length; k += 1) {
    const current = on[k]!;
    if (current === prev + 1) {
      prev = current;
      continue;
    }
    out.push({ start_time: toTime(start), end_time: toTime(prev + 1) });
    start = current;
    prev = current;
  }
  out.push({ start_time: toTime(start), end_time: toTime(prev + 1) });
  return out;
}

export function fromWindows(
  windows: { start_time: string; end_time: string }[],
): DayBits {
  const bits = newEmptyBits();
  const toIdx = (timeStr: string, isEndTime: boolean = false): number => {
    const [H, M] = timeStr.split(":").map(Number);
    // Midnight (00:00) as end time means end-of-day (slot 288)
    if (isEndTime && H === 0 && M === 0) {
      return SLOTS_PER_DAY;
    }
    return idx(Number(H), Number(M));
  };

  for (const { start_time, end_time } of windows) {
    const start = Math.max(0, Math.min(SLOTS_PER_DAY, toIdx(start_time, false)));
    const end = Math.max(0, Math.min(SLOTS_PER_DAY, toIdx(end_time, true)));
    for (let i = start; i < end; i += 1) {
      const byte = Math.floor(i / 8);
      if (byte >= bits.length) break;
      const bit = i % 8;
      const current: number = bits[byte] ?? 0;
      bits[byte] = current | (1 << bit);
    }
  }
  return bits;
}

export function toggle(bits: DayBits, slotIndex: number, on: boolean): DayBits {
  const next = bits.slice();
  const byte = Math.floor(slotIndex / 8);
  if (byte >= next.length || slotIndex < 0 || slotIndex >= SLOTS_PER_DAY) {
    return next;
  }
  const bit = slotIndex % 8;
  const current: number = next[byte] ?? 0;
  next[byte] = on ? current | (1 << bit) : current & ~(1 << bit);
  return next;
}

export function getSlotTag(tags: DayTags, slot: number): FormatTag {
  if (tags.length !== TAG_BYTES_PER_DAY) {
    throw new Error(`tags length must be ${TAG_BYTES_PER_DAY}`);
  }
  if (slot < 0 || slot >= SLOTS_PER_DAY) {
    throw new Error('slot out of range');
  }
  const bitOffset = slot * BITS_PER_TAG;
  const byteIdx = Math.floor(bitOffset / 8);
  const bitPos = bitOffset % 8;
  return (((tags[byteIdx] ?? 0) >> bitPos) & 0b11) as FormatTag;
}

export function setSlotTag(tags: DayTags, slot: number, tag: FormatTag): DayTags {
  if (tags.length !== TAG_BYTES_PER_DAY) {
    throw new Error(`tags length must be ${TAG_BYTES_PER_DAY}`);
  }
  if (slot < 0 || slot >= SLOTS_PER_DAY) {
    throw new Error('slot out of range');
  }
  if (tag < TAG_NONE || tag > TAG_RESERVED) {
    throw new Error('tag must be 0-3');
  }
  const next = tags.slice();
  const bitOffset = slot * BITS_PER_TAG;
  const byteIdx = Math.floor(bitOffset / 8);
  const bitPos = bitOffset % 8;
  next[byteIdx] = (next[byteIdx] ?? 0) & ~(0b11 << bitPos);
  next[byteIdx] = (next[byteIdx] ?? 0) | ((tag & 0b11) << bitPos);
  return next;
}

export function setRangeTag(tags: DayTags, startSlot: number, count: number, tag: FormatTag): DayTags {
  if (tags.length !== TAG_BYTES_PER_DAY) {
    throw new Error(`tags length must be ${TAG_BYTES_PER_DAY}`);
  }
  if (count <= 0) {
    throw new Error('count must be greater than 0');
  }
  if (startSlot < 0 || startSlot + count > SLOTS_PER_DAY) {
    throw new Error('range out of bounds');
  }
  if (tag < TAG_NONE || tag > TAG_RESERVED) {
    throw new Error('tag must be 0-3');
  }
  const next = tags.slice();
  for (let i = 0; i < count; i += 1) {
    const slot = startSlot + i;
    const bitOffset = slot * BITS_PER_TAG;
    const byteIdx = Math.floor(bitOffset / 8);
    const bitPos = bitOffset % 8;
    next[byteIdx] = (next[byteIdx] ?? 0) & ~(0b11 << bitPos);
    next[byteIdx] = (next[byteIdx] ?? 0) | ((tag & 0b11) << bitPos);
  }
  return next;
}

export function getRangeTag(tags: DayTags, startSlot: number, count: number): FormatTag | null {
  if (count <= 0) {
    throw new Error('count must be greater than 0');
  }
  const first = getSlotTag(tags, startSlot);
  for (let i = 1; i < count; i += 1) {
    if (getSlotTag(tags, startSlot + i) !== first) {
      return null;
    }
  }
  return first;
}

/** Toggle a range of consecutive slots (used by 30-min grid cells -> 6 bits). */
export function toggleRange(bits: DayBits, startSlot: number, count: number, on: boolean): DayBits {
  const next = bits.slice();
  for (let i = 0; i < count; i += 1) {
    const slot = startSlot + i;
    const byte = Math.floor(slot / 8);
    if (byte >= next.length || slot < 0 || slot >= SLOTS_PER_DAY) continue;
    const bit = slot % 8;
    const current: number = next[byte] ?? 0;
    next[byte] = on ? current | (1 << bit) : current & ~(1 << bit);
  }
  return next;
}

/** Check if ALL bits in a range are set (for 30-min cell display). */
export function isRangeSet(bits: DayBits | undefined, startSlot: number, count: number): boolean {
  if (!bits) return false;
  for (let i = 0; i < count; i += 1) {
    const slotIndex = startSlot + i;
    const byte = Math.floor(slotIndex / 8);
    const bit = slotIndex % 8;
    if ((((bits[byte] ?? 0) >> bit) & 1) === 0) return false;
  }
  return true;
}
