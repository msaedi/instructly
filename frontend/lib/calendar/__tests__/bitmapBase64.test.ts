import { describe, expect, it } from '@jest/globals';

import { decodeBase64ToUint8Array, encodeUint8ArrayToBase64 } from '../bitmapBase64';

describe('bitmapBase64', () => {
  it('round-trips Uint8Array values through base64', () => {
    const original = Uint8Array.from([0, 1, 2, 3, 250, 251, 252, 253, 254, 255]);
    const encoded = encodeUint8ArrayToBase64(original);
    const decoded = decodeBase64ToUint8Array(encoded, original.length);

    expect(Array.from(decoded)).toEqual(Array.from(original));
  });

  it('rejects unexpected decoded length', () => {
    const encoded = encodeUint8ArrayToBase64(Uint8Array.from([1, 2, 3]));
    expect(() => decodeBase64ToUint8Array(encoded, 4)).toThrow(
      'decoded bitmap length must be 4',
    );
  });
});
