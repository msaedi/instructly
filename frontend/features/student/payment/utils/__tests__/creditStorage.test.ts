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

  it('survives sessionStorage.getItem throwing (quota exceeded / disabled)', () => {
    const spy = jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('Storage disabled', 'SecurityError');
    });

    expect(readStoredCreditDecision('insta:credits:last:err')).toBeNull();

    spy.mockRestore();
  });

  it('survives sessionStorage.setItem throwing (quota exceeded)', () => {
    const spy = jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('QuotaExceededError', 'QuotaExceededError');
    });

    expect(() =>
      writeStoredCreditDecision('insta:credits:last:err', {
        lastCreditCents: 500,
        explicitlyRemoved: false,
      }),
    ).not.toThrow();

    spy.mockRestore();
  });

  it('survives sessionStorage.removeItem throwing', () => {
    const spy = jest.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new DOMException('Storage disabled', 'SecurityError');
    });

    expect(() => removeStoredCreditDecision('insta:credits:last:err')).not.toThrow();

    spy.mockRestore();
  });

  it('reads stored decision with valid positive lastCreditCents', () => {
    window.sessionStorage.setItem(
      'insta:credits:last:valid',
      JSON.stringify({ lastCreditCents: 1500, explicitlyRemoved: false }),
    );

    const result = readStoredCreditDecision('insta:credits:last:valid');
    expect(result).toEqual({ lastCreditCents: 1500, explicitlyRemoved: false });
  });

  it('reads stored decision with non-number lastCreditCents defaults to 0', () => {
    window.sessionStorage.setItem(
      'insta:credits:last:nan',
      JSON.stringify({ lastCreditCents: 'not-a-number', explicitlyRemoved: true }),
    );

    const result = readStoredCreditDecision('insta:credits:last:nan');
    expect(result).toEqual({ lastCreditCents: 0, explicitlyRemoved: true });
  });

  it('reads stored decision with Infinity lastCreditCents defaults to 0', () => {
    // JSON.parse(JSON.stringify(Infinity)) yields null, so we simulate the parse result
    window.sessionStorage.setItem(
      'insta:credits:last:inf',
      JSON.stringify({ lastCreditCents: null, explicitlyRemoved: false }),
    );

    const result = readStoredCreditDecision('insta:credits:last:inf');
    expect(result).toEqual({ lastCreditCents: 0, explicitlyRemoved: false });
  });

  it('rounds fractional lastCreditCents on read', () => {
    window.sessionStorage.setItem(
      'insta:credits:last:frac',
      JSON.stringify({ lastCreditCents: 1234.56, explicitlyRemoved: false }),
    );

    const result = readStoredCreditDecision('insta:credits:last:frac');
    expect(result).toEqual({ lastCreditCents: 1235, explicitlyRemoved: false });
  });

  it('computes null key when bookingId is empty/whitespace', () => {
    expect(computeCreditStorageKey({ bookingId: '   ' })).toBeNull();
    expect(computeCreditStorageKey({ bookingId: '' })).toBeNull();
  });

  it('prefers bookingId over quotePayloadBase when both provided', () => {
    const key = computeCreditStorageKey({
      bookingId: 'booking-abc',
      quotePayloadBase: {
        instructor_id: 'inst-1',
        instructor_service_id: 'svc-1',
        booking_date: '2025-06-01',
        start_time: '10:00',
        selected_duration: 60,
        location_type: 'online',
        meeting_location: 'Online',
      } as PricingPreviewQuotePayloadBase,
    });
    expect(key).toBe('insta:credits:last:booking-abc');
  });

  it('stableSerialize handles primitive values correctly', () => {
    // Test through computeCreditStorageKey which uses stableSerialize
    const keyWithString = computeCreditStorageKey({
      quotePayloadBase: {
        instructor_id: 'test',
        instructor_service_id: 'svc',
        booking_date: '2025-01-01',
        start_time: '09:00',
        selected_duration: 30,
        location_type: 'online',
        meeting_location: 'Online',
      } as PricingPreviewQuotePayloadBase,
    });
    expect(keyWithString).toBeTruthy();
    expect(typeof keyWithString).toBe('string');
  });

  // SSR branches (typeof window === 'undefined') are covered by
  // creditStorage.node.test.ts which uses @jest-environment node.

  it('stableSerialize handles arrays with nested objects', () => {
    // Test array serialization through computeCreditStorageKey
    const keyA = computeCreditStorageKey({
      quotePayloadBase: {
        instructor_id: 'inst-1',
        instructor_service_id: 'svc-1',
        booking_date: '2025-06-01',
        start_time: '10:00',
        selected_duration: 60,
        location_type: 'online',
        meeting_location: 'Online',
        metadata: { tags: ['a', 'b'], nested: { z: 1, a: 2 } },
      } as PricingPreviewQuotePayloadBase,
    });

    // Same data with different key order in nested object
    const keyB = computeCreditStorageKey({
      quotePayloadBase: {
        instructor_id: 'inst-1',
        instructor_service_id: 'svc-1',
        booking_date: '2025-06-01',
        start_time: '10:00',
        selected_duration: 60,
        location_type: 'online',
        meeting_location: 'Online',
        metadata: { tags: ['a', 'b'], nested: { a: 2, z: 1 } },
      } as PricingPreviewQuotePayloadBase,
    });

    expect(keyA).toBe(keyB);
  });

  it('computeCreditStorageKey returns null for null quotePayloadBase', () => {
    const key = computeCreditStorageKey({
      bookingId: null,
      quotePayloadBase: null,
    });
    expect(key).toBeNull();
  });

});
