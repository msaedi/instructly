import { countSetBits, computeBitsDelta } from '../bitsDelta';
import type { WeekBits } from '@/types/availability';

describe('countSetBits', () => {
  it('returns 0 for 0', () => {
    expect(countSetBits(0)).toBe(0);
  });

  it('counts bits in 0xFF', () => {
    expect(countSetBits(0xff)).toBe(8);
  });

  it('counts bits in 0b10101010', () => {
    expect(countSetBits(0b10101010)).toBe(4);
  });

  it('masks to one byte', () => {
    // 0x1FF = 0b1_1111_1111 — only bottom 8 bits count
    expect(countSetBits(0x1ff)).toBe(8);
  });
});

describe('computeBitsDelta', () => {
  it('returns zeros for identical bitmaps', () => {
    const bits = new Uint8Array(36);
    bits[0] = 0b11110000;
    const week: WeekBits = { '2025-01-13': bits };
    expect(computeBitsDelta(week, week)).toEqual({ added: 0, removed: 0 });
  });

  it('detects added bits', () => {
    const prev = new Uint8Array(36);
    const next = new Uint8Array(36);
    next[0] = 0b00001111; // 4 new bits
    const result = computeBitsDelta(
      { '2025-01-13': prev } as WeekBits,
      { '2025-01-13': next } as WeekBits,
    );
    expect(result.added).toBe(4);
    expect(result.removed).toBe(0);
  });

  it('detects removed bits', () => {
    const prev = new Uint8Array(36);
    prev[0] = 0b11111111; // 8 bits set
    const next = new Uint8Array(36);
    const result = computeBitsDelta(
      { '2025-01-13': prev } as WeekBits,
      { '2025-01-13': next } as WeekBits,
    );
    expect(result.added).toBe(0);
    expect(result.removed).toBe(8);
  });

  it('detects both added and removed bits', () => {
    const prev = new Uint8Array(36);
    prev[0] = 0b00001111; // lower 4 set
    const next = new Uint8Array(36);
    next[0] = 0b11110000; // upper 4 set
    const result = computeBitsDelta(
      { '2025-01-13': prev } as WeekBits,
      { '2025-01-13': next } as WeekBits,
    );
    expect(result.added).toBe(4);
    expect(result.removed).toBe(4);
  });

  it('handles date only in previous (all removed)', () => {
    const prev = new Uint8Array(36);
    prev[0] = 0b11111111;
    const result = computeBitsDelta(
      { '2025-01-13': prev } as WeekBits,
      {},
    );
    expect(result.added).toBe(0);
    expect(result.removed).toBe(8);
  });

  it('handles date only in next (all added)', () => {
    const next = new Uint8Array(36);
    next[0] = 0b00001111;
    const result = computeBitsDelta(
      {},
      { '2025-01-13': next } as WeekBits,
    );
    expect(result.added).toBe(4);
    expect(result.removed).toBe(0);
  });

  it('handles multiple dates', () => {
    const prev1 = new Uint8Array(36);
    prev1[0] = 0b11111111;
    const next2 = new Uint8Array(36);
    next2[0] = 0b00001111;
    const result = computeBitsDelta(
      { '2025-01-13': prev1 } as WeekBits,
      { '2025-01-14': next2 } as WeekBits,
    );
    expect(result.added).toBe(4);
    expect(result.removed).toBe(8);
  });

  it('handles changes in higher bytes', () => {
    const prev = new Uint8Array(36);
    const next = new Uint8Array(36);
    next[35] = 0b00000011; // 2 bits set in last byte
    const result = computeBitsDelta(
      { '2025-01-13': prev } as WeekBits,
      { '2025-01-13': next } as WeekBits,
    );
    expect(result.added).toBe(2);
    expect(result.removed).toBe(0);
  });
});
