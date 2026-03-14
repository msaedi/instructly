export function encodeUint8ArrayToBase64(value: Uint8Array): string {
  if (typeof Buffer !== 'undefined') {
    return Buffer.from(value).toString('base64');
  }

  let binary = '';
  value.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return globalThis.btoa(binary);
}

export function decodeBase64ToUint8Array(value: string, expectedLength?: number): Uint8Array {
  const decoded =
    typeof Buffer !== 'undefined'
      ? Uint8Array.from(Buffer.from(value, 'base64'))
      : Uint8Array.from(globalThis.atob(value), (char) => char.charCodeAt(0));

  if (expectedLength !== undefined && decoded.length !== expectedLength) {
    throw new Error(`decoded bitmap length must be ${expectedLength}`);
  }

  return decoded;
}
