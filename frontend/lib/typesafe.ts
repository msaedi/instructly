/**
 * Type-safe utilities for handling unknown values from APIs and external sources.
 * These guards help avoid scattered inline type assertions throughout the codebase.
 */

/**
 * Type guard to check if a value is a non-null object (Record<string, unknown>)
 */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Safely get a string value from an object with a fallback
 */
export function getString(
  obj: unknown,
  key: string,
  fallback: string = ''
): string {
  if (!isRecord(obj)) return fallback;
  const value = obj[key];
  return typeof value === 'string' ? value : fallback;
}

/**
 * Safely get a number value from an object with a fallback
 */
export function getNumber(
  obj: unknown,
  key: string,
  fallback: number = 0
): number {
  if (!isRecord(obj)) return fallback;
  const value = obj[key];
  return typeof value === 'number' ? value : fallback;
}

/**
 * Safely get a boolean value from an object with a fallback
 */
export function getBoolean(
  obj: unknown,
  key: string,
  fallback: boolean = false
): boolean {
  if (!isRecord(obj)) return fallback;
  const value = obj[key];
  return typeof value === 'boolean' ? value : fallback;
}

/**
 * Safely get an array from an object (always returns an array, empty if not found)
 */
export function getArray(
  obj: unknown,
  key: string
): readonly unknown[] {
  if (!isRecord(obj)) return [];
  const value = obj[key];
  return Array.isArray(value) ? value : [];
}

/**
 * Check if an object has a specific property
 */
export function has<K extends string>(
  obj: unknown,
  key: K
): obj is Record<K, unknown> {
  return isRecord(obj) && key in obj;
}

/**
 * Type guard for GeoJSON FeatureCollection (minimal shape used in the app)
 */
export function isFeatureCollection(
  value: unknown
): value is {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    geometry?: {
      type: string;
      coordinates: unknown;
    };
    properties?: Record<string, unknown>;
  }>;
} {
  if (!isRecord(value)) return false;
  if (value.type !== 'FeatureCollection') return false;
  if (!Array.isArray(value.features)) return false;

  // Basic validation that features have the right shape
  return value.features.every((f: unknown) =>
    isRecord(f) &&
    f.type === 'Feature' &&
    (!f.geometry || (isRecord(f.geometry) && typeof f.geometry.type === 'string'))
  );
}

/**
 * Safely access nested properties with dot notation
 */
export function getNestedString(
  obj: unknown,
  path: string,
  fallback: string = ''
): string {
  if (!isRecord(obj)) return fallback;

  const keys = path.split('.');
  let current: unknown = obj;

  for (const key of keys) {
    if (!isRecord(current)) return fallback;
    current = current[key];
  }

  return typeof current === 'string' ? current : fallback;
}

/**
 * Safely access nested number properties
 */
export function getNestedNumber(
  obj: unknown,
  path: string,
  fallback: number = 0
): number {
  if (!isRecord(obj)) return fallback;

  const keys = path.split('.');
  let current: unknown = obj;

  for (const key of keys) {
    if (!isRecord(current)) return fallback;
    current = current[key];
  }

  return typeof current === 'number' ? current : fallback;
}

/**
 * Type guard for checking if a value is a string array
 */
export function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string');
}

/**
 * Type guard for checking if a value is a number array
 */
export function isNumberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every(item => typeof item === 'number');
}

/**
 * Safely cast to string array with fallback
 */
export function getStringArray(
  obj: unknown,
  key: string,
  fallback: string[] = []
): string[] {
  if (!isRecord(obj)) return fallback;
  const value = obj[key];
  return isStringArray(value) ? value : fallback;
}

/**
 * Safely cast to number array with fallback
 */
export function getNumberArray(
  obj: unknown,
  key: string,
  fallback: number[] = []
): number[] {
  if (!isRecord(obj)) return fallback;
  const value = obj[key];
  return isNumberArray(value) ? value : fallback;
}
