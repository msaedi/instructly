import { logger } from '@/lib/logger';
import type { ServiceLocationType } from '@/types/instructor';
import type { FormatPriceState, ServiceFormat } from './formatPricing';
import { FORMAT_CARD_CONFIGS } from './formatPricing';

export type PriceFloorConfig = {
  private_in_person: number;
  private_remote: number;
};

export type NormalizedModality = ServiceLocationType;

export type FloorViolation = {
  modalityLabel: 'in-person' | 'online';
  duration: number;
  floorCents: number;
  baseCents: number;
};

export function normalizeModality(label: string | undefined | null): NormalizedModality {
  const value = String(label ?? '').toLowerCase();
  if (/online|remote|virtual/.test(value)) return 'online';
  return 'in_person';
}

export function computePriceFloorCents(
  floors: PriceFloorConfig,
  modality: NormalizedModality,
  durationMinutes: number,
): number {
  const base = modality === 'in_person' ? floors.private_in_person : floors.private_remote;
  if (!Number.isFinite(base) || durationMinutes <= 0) return 0;
  return Math.round((base * durationMinutes) / 60);
}

export function computeBasePriceCents(hourlyRate: number, durationMinutes: number): number {
  if (!Number.isFinite(hourlyRate) || durationMinutes <= 0) return 0;
  return Math.round((hourlyRate * durationMinutes * 100) / 60);
}

export function formatCents(cents: number): string {
  return (cents / 100).toFixed(2);
}

export function hasFloorViolation(
  hourlyRate: number,
  durationMinutes: number,
  modality: NormalizedModality,
  floors: PriceFloorConfig,
): { floorCents: number; baseCents: number } | null {
  try {
    const floorCents = computePriceFloorCents(floors, modality, durationMinutes);
    const baseCents = computeBasePriceCents(hourlyRate, durationMinutes);
    if (baseCents < floorCents) {
      return { floorCents, baseCents };
    }
    return null;
  } catch (error) {
    logger.error('price floor calculation failed', error as Error, {
      hourlyRate,
      durationMinutes,
      modality,
    });
    return null;
  }
}

export function evaluatePriceFloorViolations(options: {
  hourlyRate: number;
  durationOptions: number[];
  locationTypes: ReadonlyArray<ServiceLocationType>;
  floors: PriceFloorConfig;
}): FloorViolation[] {
  const { hourlyRate, durationOptions, locationTypes, floors } = options;
  if (!Number.isFinite(hourlyRate) || hourlyRate <= 0) return [];
  const durations = (durationOptions.length ? durationOptions : [60])
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value) && value > 0);
  if (!durations.length) return [];

  const modalities = Array.from(
    new Set((locationTypes.length ? locationTypes : ['in_person']).map((label) => normalizeModality(label)))
  );

  const violations: FloorViolation[] = [];
  modalities.forEach((modality) => {
    durations.forEach((duration) => {
      const floorCents = computePriceFloorCents(floors, modality, duration);
      const baseCents = computeBasePriceCents(hourlyRate, duration);
      if (baseCents < floorCents) {
        violations.push({
          modalityLabel: modality === 'in_person' ? 'in-person' : 'online',
          duration,
          floorCents,
          baseCents,
        });
      }
    });
  });
  return violations;
}

export type FormatFloorViolation = {
  format: ServiceFormat;
  duration: number;
  floorCents: number;
  baseCents: number;
};

/**
 * Evaluate price floor violations per-format.
 * Returns a Map keyed by format — only formats with violations are present.
 */
export function evaluateFormatPriceFloorViolations(options: {
  formatPrices: FormatPriceState;
  durationOptions: number[];
  floors: PriceFloorConfig;
}): Map<ServiceFormat, FormatFloorViolation[]> {
  const { formatPrices, durationOptions, floors } = options;
  const result = new Map<ServiceFormat, FormatFloorViolation[]>();

  const durations = (durationOptions.length > 0 ? durationOptions : [60])
    .map((v) => Number(v))
    .filter((v) => Number.isFinite(v) && v > 0);
  if (durations.length === 0) return result;

  for (const config of FORMAT_CARD_CONFIGS) {
    const rateStr = formatPrices[config.format];
    if (rateStr === undefined || rateStr === '') continue;

    const hourlyRate = Number(rateStr);
    if (!Number.isFinite(hourlyRate) || hourlyRate <= 0) continue;

    const modality: NormalizedModality = config.floorModality === 'in_person' ? 'in_person' : 'online';
    const violations: FormatFloorViolation[] = [];

    for (const duration of durations) {
      const floorCents = computePriceFloorCents(floors, modality, duration);
      const baseCents = computeBasePriceCents(hourlyRate, duration);
      if (baseCents < floorCents) {
        violations.push({
          format: config.format,
          duration,
          floorCents,
          baseCents,
        });
      }
    }

    if (violations.length > 0) {
      result.set(config.format, violations);
    }
  }

  return result;
}
