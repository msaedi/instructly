/**
 * @jest-environment node
 *
 * Tests for shareOrCopy SSR code path (line 5).
 * In a node environment, typeof window === 'undefined', so shareOrCopy returns 'skipped'.
 */

import { shareOrCopy } from '../share';

describe('shareOrCopy SSR (node environment)', () => {
  it('returns "skipped" when window is undefined (line 5)', async () => {
    expect(typeof globalThis.window).toBe('undefined');

    const result = await shareOrCopy({ title: 'Test' }, 'copy text');

    expect(result).toBe('skipped');
  });
});
