export const SLOTS_PER_DAY = 48;
export type DayBits = Uint8Array;

export function newEmptyBits(): DayBits {
  return new Uint8Array(6);
}

export function idx(hh: number, mm: number): number {
  return hh * 2 + (mm >= 30 ? 1 : 0);
}

export function toWindows(
  bits: DayBits,
): { start_time: string; end_time: string }[] {
  const on: number[] = [];
  for (let b = 0; b < 6; b += 1) {
    const byteValue = bits[b] ?? 0;
    for (let bit = 0; bit < 8; bit += 1) {
      const i = b * 8 + bit;
      if (i >= SLOTS_PER_DAY) break;
      if ((byteValue >> bit) & 1) on.push(i);
    }
  }
  if (on.length === 0) return [];

  const toTime = (slotIdx: number) => {
    const totalMinutes = slotIdx * 30;
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
  const toIdx = (timeStr: string) => {
    const [H, M] = timeStr.split(":").map(Number);
    return idx(Number(H), Number(M));
  };

  for (const { start_time, end_time } of windows) {
    const start = Math.max(0, Math.min(SLOTS_PER_DAY, toIdx(start_time)));
    const end = Math.max(0, Math.min(SLOTS_PER_DAY, toIdx(end_time)));
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
