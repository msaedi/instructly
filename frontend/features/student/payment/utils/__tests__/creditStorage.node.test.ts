/**
 * @jest-environment node
 */
import {
  readStoredCreditDecision,
  removeStoredCreditDecision,
  writeStoredCreditDecision,
} from '../creditStorage';

describe('creditStorage SSR (node environment)', () => {
  it('readStoredCreditDecision returns null when window is undefined', () => {
    expect(typeof window).toBe('undefined');
    expect(readStoredCreditDecision('insta:credits:last:ssr')).toBeNull();
  });

  it('writeStoredCreditDecision no-ops when window is undefined', () => {
    expect(typeof window).toBe('undefined');
    expect(() =>
      writeStoredCreditDecision('insta:credits:last:ssr', {
        lastCreditCents: 100,
        explicitlyRemoved: false,
      }),
    ).not.toThrow();
  });

  it('removeStoredCreditDecision no-ops when window is undefined', () => {
    expect(typeof window).toBe('undefined');
    expect(() => removeStoredCreditDecision('insta:credits:last:ssr')).not.toThrow();
  });
});
