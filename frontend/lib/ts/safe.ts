// frontend/lib/ts/safe.ts
export const isPresent = <T>(v: T | null | undefined): v is T => v != null;

export function invariant(cond: unknown, msg = 'Invariant failed'): asserts cond {
  if (!cond) throw new Error(msg);
}

export function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export function requireString(value: unknown, name = 'value'): asserts value is string {
  if (typeof value !== 'string') throw new Error(`${name} must be a string`);
}

export function at<T>(arr: readonly T[] | undefined, i: number): T | undefined {
  return arr?.[i];
}

export function get<K extends string, V>(obj: Partial<Record<K, V>> | undefined, key: K): V | undefined {
  return obj?.[key];
}

export function toDate(input: Date | string | number | undefined): Date | undefined {
  if (input == null) return undefined;
  const d = input instanceof Date ? input : new Date(input);
  return isNaN(d.getTime()) ? undefined : d;
}

// Common guard for array items
export function hasIndex<T>(arr: readonly T[] | undefined, i: number): arr is readonly T[] {
  return !!arr && i >= 0 && i < arr.length;
}
