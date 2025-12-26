import { describe, it, expect } from '@jest/globals';
import { fromWindows, toWindows, SLOTS_PER_DAY, newEmptyBits, idx, toggle } from '../bitset';

describe('bitset', () => {
  describe('fromWindows', () => {
    it('should handle midnight end time (00:00:00) as end-of-day', () => {
      // This is the critical test case for the bug fix
      // API returns "00:00:00" for midnight, which should be treated as slot 48 (end of day)
      const windows = [{ start_time: '20:00:00', end_time: '00:00:00' }];
      const bits = fromWindows(windows);

      // Slots 40-47 (20:00-23:30) should be set
      for (let slot = 40; slot < 48; slot++) {
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        const isSet = ((bits[byteIdx] ?? 0) >> bitIdx) & 1;
        expect(isSet).toBe(1);
      }

      // Slot 39 (19:30) should NOT be set
      const slot39Byte = Math.floor(39 / 8);
      const slot39Bit = 39 % 8;
      expect(((bits[slot39Byte] ?? 0) >> slot39Bit) & 1).toBe(0);
    });

    it('should handle normal end time (23:30:00)', () => {
      const windows = [{ start_time: '20:00:00', end_time: '23:30:00' }];
      const bits = fromWindows(windows);

      // Slots 40-46 (20:00-23:00) should be set
      for (let slot = 40; slot < 47; slot++) {
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        const isSet = ((bits[byteIdx] ?? 0) >> bitIdx) & 1;
        expect(isSet).toBe(1);
      }

      // Slot 47 (23:30) should NOT be set
      const slot47Byte = Math.floor(47 / 8);
      const slot47Bit = 47 % 8;
      expect(((bits[slot47Byte] ?? 0) >> slot47Bit) & 1).toBe(0);
    });

    it('should handle multiple windows with midnight end time', () => {
      const windows = [
        { start_time: '08:00:00', end_time: '12:00:00' },
        { start_time: '20:00:00', end_time: '00:00:00' },
      ];
      const bits = fromWindows(windows);

      // Morning slots 16-23 (08:00-11:30)
      for (let slot = 16; slot < 24; slot++) {
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        const isSet = ((bits[byteIdx] ?? 0) >> bitIdx) & 1;
        expect(isSet).toBe(1);
      }

      // Evening slots 40-47 (20:00-23:30)
      for (let slot = 40; slot < 48; slot++) {
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        const isSet = ((bits[byteIdx] ?? 0) >> bitIdx) & 1;
        expect(isSet).toBe(1);
      }
    });

    it('should handle midnight start time as start-of-day (slot 0)', () => {
      // Midnight as START time should still be slot 0
      const windows = [{ start_time: '00:00:00', end_time: '02:00:00' }];
      const bits = fromWindows(windows);

      // Slots 0-3 (00:00-01:30) should be set
      for (let slot = 0; slot < 4; slot++) {
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        const isSet = ((bits[byteIdx] ?? 0) >> bitIdx) & 1;
        expect(isSet).toBe(1);
      }
    });

    it('should produce correct bits count for 8pm-midnight (8 slots)', () => {
      const windows = [{ start_time: '20:00:00', end_time: '00:00:00' }];
      const bits = fromWindows(windows);

      let count = 0;
      for (let slot = 0; slot < SLOTS_PER_DAY; slot++) {
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        if (((bits[byteIdx] ?? 0) >> bitIdx) & 1) count++;
      }

      // 8pm to midnight = 4 hours = 8 half-hour slots
      expect(count).toBe(8);
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

      // Set slots 40-47 (8pm to midnight)
      for (let slot = 40; slot < 48; slot++) {
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        bits[byteIdx] = (bits[byteIdx] ?? 0) | (1 << bitIdx);
      }

      const windows = toWindows(bits);
      expect(windows).toHaveLength(1);
      expect(windows[0]).toEqual({
        start_time: '20:00:00',
        end_time: '24:00:00', // toWindows uses 24:00 format
      });
    });

    it('should handle multiple contiguous ranges', () => {
      const bits = newEmptyBits();

      // Set slots 16-23 (8am to noon)
      for (let slot = 16; slot < 24; slot++) {
        const byteIdx = Math.floor(slot / 8);
        const bitIdx = slot % 8;
        bits[byteIdx] = (bits[byteIdx] ?? 0) | (1 << bitIdx);
      }

      // Set slots 28-31 (2pm to 4pm)
      for (let slot = 28; slot < 32; slot++) {
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
      // Backend sends "00:00:00", frontend should handle it
      const original = [{ start_time: '20:00:00', end_time: '00:00:00' }];
      const bits = fromWindows(original);
      const result = toWindows(bits);

      expect(result).toHaveLength(1);
      expect(result[0]?.start_time).toBe('20:00:00');
      // toWindows outputs "24:00:00" format (which is correct)
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
      expect(idx(0, 0)).toBe(0);    // midnight
      expect(idx(8, 0)).toBe(16);   // 8am
      expect(idx(8, 30)).toBe(17);  // 8:30am
      expect(idx(12, 0)).toBe(24);  // noon
      expect(idx(20, 0)).toBe(40);  // 8pm
      expect(idx(23, 30)).toBe(47); // 11:30pm
    });
  });

  describe('toggle function', () => {
    it('should set and unset individual slots', () => {
      let bits = newEmptyBits();

      // Turn on slot 40 (8pm)
      bits = toggle(bits, 40, true);
      const byteIdx = Math.floor(40 / 8);
      const bitIdx = 40 % 8;
      expect(((bits[byteIdx] ?? 0) >> bitIdx) & 1).toBe(1);

      // Turn off slot 40
      bits = toggle(bits, 40, false);
      expect(((bits[byteIdx] ?? 0) >> bitIdx) & 1).toBe(0);
    });

    it('should ignore out of range slots', () => {
      let bits = newEmptyBits();
      bits = toggle(bits, 48, true);  // Out of range
      bits = toggle(bits, -1, true);  // Negative

      // All bits should still be 0
      for (let i = 0; i < bits.length; i++) {
        expect(bits[i]).toBe(0);
      }
    });
  });
});
