import { describe, it, expect } from '@jest/globals';
import {
  fromWindows,
  getRangeTag,
  getSlotTag,
  idx,
  newEmptyBits,
  newEmptyTags,
  setRangeTag,
  setSlotTag,
  SLOTS_PER_DAY,
  TAG_BYTES_PER_DAY,
  TAG_NO_TRAVEL,
  TAG_NONE,
  TAG_ONLINE_ONLY,
  TAG_RESERVED,
  toWindows,
  toggle,
} from '../bitset';

describe('bitset', () => {
  describe('fromWindows', () => {
    it('should handle midnight end time (00:00:00) as end-of-day', () => {
      const windows = [{ start_time: '20:00:00', end_time: '00:00:00' }];
      const bits = fromWindows(windows);

      // Slots 240-287 (20:00-23:55) should be set
      for (let slot = 240; slot < 288; slot++) {
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        const isSet = ((bits[byteIdx] ?? 0) >> bitIdx) & 1;
        expect(isSet).toBe(1);
      }

      // Slot 239 (19:55) should NOT be set
      const byte239 = Math.floor(239 / 8);
      const bit239 = 239 % 8;
      expect(((bits[byte239] ?? 0) >> bit239) & 1).toBe(0);
    });

    it('should handle normal end time (23:30:00)', () => {
      const windows = [{ start_time: '20:00:00', end_time: '23:30:00' }];
      const bits = fromWindows(windows);

      // Slots 240-281 (20:00-23:25) should be set
      for (let slot = 240; slot < 282; slot++) {
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        const isSet = ((bits[byteIdx] ?? 0) >> bitIdx) & 1;
        expect(isSet).toBe(1);
      }

      // Slot 282 (23:30) should NOT be set
      const byte282 = Math.floor(282 / 8);
      const bit282 = 282 % 8;
      expect(((bits[byte282] ?? 0) >> bit282) & 1).toBe(0);
    });

    it('should handle multiple windows with midnight end time', () => {
      const windows = [
        { start_time: '08:00:00', end_time: '12:00:00' },
        { start_time: '20:00:00', end_time: '00:00:00' },
      ];
      const bits = fromWindows(windows);

      // Morning slots 96-143 (08:00-11:55)
      for (let slot = 96; slot < 144; slot++) {
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        const isSet = ((bits[byteIdx] ?? 0) >> bitIdx) & 1;
        expect(isSet).toBe(1);
      }

      // Evening slots 240-287 (20:00-23:55)
      for (let slot = 240; slot < 288; slot++) {
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        const isSet = ((bits[byteIdx] ?? 0) >> bitIdx) & 1;
        expect(isSet).toBe(1);
      }
    });

    it('should handle midnight start time as start-of-day (slot 0)', () => {
      const windows = [{ start_time: '00:00:00', end_time: '02:00:00' }];
      const bits = fromWindows(windows);

      // Slots 0-23 (00:00-01:55) should be set
      for (let slot = 0; slot < 24; slot++) {
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        const isSet = ((bits[byteIdx] ?? 0) >> bitIdx) & 1;
        expect(isSet).toBe(1);
      }
    });

    it('should produce correct bits count for 8pm-midnight (48 five-min slots)', () => {
      const windows = [{ start_time: '20:00:00', end_time: '00:00:00' }];
      const bits = fromWindows(windows);

      let count = 0;
      for (let slot = 0; slot < SLOTS_PER_DAY; slot++) {
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        if (((bits[byteIdx] ?? 0) >> bitIdx) & 1) count++;
      }

      // 8pm to midnight = 4 hours = 48 five-minute slots
      expect(count).toBe(48);
    });

    it('should handle empty windows array', () => {
      const bits = fromWindows([]);
      for (let i = 0; i < bits.length; i++) {
        expect(bits[i]).toBe(0);
      }
    });
  });

  describe('toWindows', () => {
    it('should convert bits to windows with 24:00:00 for end-of-day', () => {
      const bits = newEmptyBits();

      // Set slots 240-287 (8pm to midnight)
      for (let slot = 240; slot < 288; slot++) {
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        bits[byteIdx] = (bits[byteIdx] ?? 0) | (1 << bitIdx);
      }

      const windows = toWindows(bits);
      expect(windows).toHaveLength(1);
      expect(windows[0]).toEqual({
        start_time: '20:00:00',
        end_time: '24:00:00',
      });
    });

    it('should handle multiple contiguous ranges', () => {
      const bits = newEmptyBits();

      // Set slots 96-143 (8am to noon)
      for (let slot = 96; slot < 144; slot++) {
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        bits[byteIdx] = (bits[byteIdx] ?? 0) | (1 << bitIdx);
      }

      // Set slots 168-191 (2pm to 4pm)
      for (let slot = 168; slot < 192; slot++) {
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        bits[byteIdx] = (bits[byteIdx] ?? 0) | (1 << bitIdx);
      }

      const windows = toWindows(bits);
      expect(windows).toHaveLength(2);
      expect(windows[0]).toEqual({
        start_time: '08:00:00',
        end_time: '12:00:00',
      });
      expect(windows[1]).toEqual({
        start_time: '14:00:00',
        end_time: '16:00:00',
      });
    });
  });

  describe('round-trip: fromWindows -> toWindows', () => {
    it('should preserve 8pm-midnight window (with format normalization)', () => {
      const original = [{ start_time: '20:00:00', end_time: '00:00:00' }];
      const bits = fromWindows(original);
      const result = toWindows(bits);

      expect(result).toHaveLength(1);
      expect(result[0]?.start_time).toBe('20:00:00');
      expect(result[0]?.end_time).toBe('24:00:00');
    });

    it('should preserve morning window exactly', () => {
      const original = [{ start_time: '08:00:00', end_time: '12:00:00' }];
      const bits = fromWindows(original);
      const result = toWindows(bits);

      expect(result).toHaveLength(1);
      expect(result[0]).toEqual(original[0]);
    });
  });

  describe('idx function', () => {
    it('should return correct slot index for common times', () => {
      expect(idx(0, 0)).toBe(0);      // midnight
      expect(idx(8, 0)).toBe(96);     // 8am
      expect(idx(8, 30)).toBe(102);   // 8:30am
      expect(idx(9, 15)).toBe(111);   // 9:15am
      expect(idx(9, 45)).toBe(117);   // 9:45am
      expect(idx(12, 0)).toBe(144);   // noon
      expect(idx(20, 0)).toBe(240);   // 8pm
      expect(idx(23, 30)).toBe(282);  // 11:30pm
      expect(idx(23, 55)).toBe(287);  // 11:55pm
    });
  });

  describe('toggle function', () => {
    it('should set and unset individual slots', () => {
      let bits = newEmptyBits();

      // Turn on slot 240 (8pm)
      bits = toggle(bits, 240, true);
      const byteIdx = Math.floor(240 / 8);
      const bitIdx = 240 % 8;
      expect(((bits[byteIdx] ?? 0) >> bitIdx) & 1).toBe(1);

      // Turn off slot 240
      bits = toggle(bits, 240, false);
      expect(((bits[byteIdx] ?? 0) >> bitIdx) & 1).toBe(0);
    });

    it('should ignore out of range slots', () => {
      let bits = newEmptyBits();
      bits = toggle(bits, 288, true);  // Out of range
      bits = toggle(bits, -1, true);   // Negative

      // All bits should still be 0
      for (let i = 0; i < bits.length; i++) {
        expect(bits[i]).toBe(0);
      }
    });
  });

  describe('tag helpers', () => {
    it('uses 72 bytes for tag storage', () => {
      expect(TAG_BYTES_PER_DAY).toBe(72);
      expect(newEmptyTags()).toHaveLength(72);
    });

    it.each([0, 111, 287])('round-trips all tag values for slot %i', (slot) => {
      for (const tag of [TAG_NONE, TAG_ONLINE_ONLY, TAG_NO_TRAVEL, TAG_RESERVED] as const) {
        const updated = setSlotTag(newEmptyTags(), slot, tag);
        expect(getSlotTag(updated, slot)).toBe(tag);
      }
    });

    it('sets and reads a uniform 6-slot range tag', () => {
      const tags = setRangeTag(newEmptyTags(), 60, 6, TAG_NO_TRAVEL);
      expect(getRangeTag(tags, 60, 6)).toBe(TAG_NO_TRAVEL);
    });

    it('returns null for mixed ranges', () => {
      let tags = setRangeTag(newEmptyTags(), 30, 6, TAG_ONLINE_ONLY);
      tags = setSlotTag(tags, 33, TAG_NONE);
      expect(getRangeTag(tags, 30, 6)).toBeNull();
    });

    it('matches the expected packed bytes for a fixed pattern', () => {
      let tags = newEmptyTags();
      tags = setSlotTag(tags, 0, TAG_ONLINE_ONLY);
      tags = setSlotTag(tags, 1, TAG_NO_TRAVEL);
      tags = setSlotTag(tags, 2, TAG_RESERVED);

      expect(Array.from(tags.slice(0, 2))).toEqual([57, 0]);
    });

    it('rejects wrong-length buffers and out-of-range slots', () => {
      expect(() => getSlotTag(new Uint8Array(71), 0)).toThrow('tags length must be 72');
      expect(() => getSlotTag(newEmptyTags(), SLOTS_PER_DAY)).toThrow('slot out of range');
    });
  });
});
