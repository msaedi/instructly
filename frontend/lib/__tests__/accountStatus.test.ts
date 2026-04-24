import { isPaused } from '../accountStatus';

describe('accountStatus helpers', () => {
  it.each<[string | null | undefined, boolean]>([
    ['suspended', true],
    ['active', false],
    ['deactivated', false],
    [undefined, false],
    [null, false],
  ])('returns %s for paused state %#', (status, expected) => {
    expect(isPaused(status)).toBe(expected);
  });
});
