import type { PricingPreviewQuotePayloadBase } from '@/lib/api/pricing';
import {
  computeCreditStorageKey,
  readStoredCreditDecision,
  removeStoredCreditDecision,
  writeStoredCreditDecision,
} from '../creditStorage';

describe('creditStorage helpers', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it('builds a key from bookingId when available', () => {
    const key = computeCreditStorageKey({ bookingId: '  booking-123  ' });
    expect(key).toBe('insta:credits:last:booking-123');
  });

  it('builds a stable key from quote payload data', () => {
    const payloadA = {
      instructor_id: 'inst-1',
      instructor_service_id: 'svc-1',
      booking_date: '2025-06-01',
      start_time: '10:00',
      selected_duration: 60,
      location_type: 'online',
      meeting_location: 'Online',
      metadata: { list: [null, { b: 2, a: 1 }] },
    } as PricingPreviewQuotePayloadBase;

    const payloadB = {
      meeting_location: 'Online',
      selected_duration: 60,
      start_time: '10:00',
      booking_date: '2025-06-01',
      instructor_service_id: 'svc-1',
      instructor_id: 'inst-1',
      location_type: 'online',
      metadata: { list: [null, { a: 1, b: 2 }] },
    } as PricingPreviewQuotePayloadBase;

    const keyA = computeCreditStorageKey({ quotePayloadBase: payloadA });
    const keyB = computeCreditStorageKey({ quotePayloadBase: payloadB });

    expect(keyA).toBe(keyB);
    expect(keyA).toContain('insta:credits:last:');
  });

  it('returns null when no bookingId or payload is provided', () => {
    expect(computeCreditStorageKey({})).toBeNull();
  });

  it('reads and normalizes stored credit decisions', () => {
    window.sessionStorage.setItem(
      'insta:credits:last:test',
      JSON.stringify({ lastCreditCents: -12.4, explicitlyRemoved: 'yes' }),
    );

    const result = readStoredCreditDecision('insta:credits:last:test');

    expect(result).toEqual({ lastCreditCents: 0, explicitlyRemoved: true });
  });

  it('returns null when stored data is missing or invalid', () => {
    expect(readStoredCreditDecision('missing')).toBeNull();

    window.sessionStorage.setItem('insta:credits:last:bad', '{not-json');
    expect(readStoredCreditDecision('insta:credits:last:bad')).toBeNull();
  });

  it('writes sanitized credit decisions to storage', () => {
    const setItemSpy = jest.spyOn(Storage.prototype, 'setItem');

    writeStoredCreditDecision('insta:credits:last:write', {
      lastCreditCents: 12.7,
      explicitlyRemoved: true,
    });

    expect(setItemSpy).toHaveBeenCalledWith(
      'insta:credits:last:write',
      JSON.stringify({ lastCreditCents: 13, explicitlyRemoved: true }),
    );
    setItemSpy.mockRestore();
  });

  it('removes stored credit decision entries', () => {
    const removeItemSpy = jest.spyOn(Storage.prototype, 'removeItem');

    removeStoredCreditDecision('insta:credits:last:remove');

    expect(removeItemSpy).toHaveBeenCalledWith('insta:credits:last:remove');
    removeItemSpy.mockRestore();
  });

  it('no-ops when window is undefined', () => {
    const originalWindow = globalThis.window;

    (globalThis as { window?: Window }).window = undefined;

    expect(readStoredCreditDecision('insta:credits:last:none')).toBeNull();
    expect(() =>
      writeStoredCreditDecision('insta:credits:last:none', {
        lastCreditCents: 1,
        explicitlyRemoved: false,
      }),
    ).not.toThrow();
    expect(() => removeStoredCreditDecision('insta:credits:last:none')).not.toThrow();

    (globalThis as { window?: Window }).window = originalWindow;
  });

});
