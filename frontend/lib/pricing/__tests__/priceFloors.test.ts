import {
  computeBasePriceCents,
  computePriceFloorCents,
  evaluatePriceFloorViolations,
  evaluateFormatPriceFloorViolations,
  type PriceFloorConfig,
} from '../priceFloors';
import type { FormatPriceState } from '../formatPricing';

const mockFloors: PriceFloorConfig = {
  private_in_person: 9000,
  private_remote: 7000,
};

describe('priceFloors helpers', () => {
  it('computes prorated in-person floors for 60/45/30 minutes', () => {
    expect(computePriceFloorCents(mockFloors, 'in_person', 60)).toBe(9000);
    expect(computePriceFloorCents(mockFloors, 'in_person', 45)).toBe(6750);
    expect(computePriceFloorCents(mockFloors, 'in_person', 30)).toBe(4500);
  });

  it('computes prorated online floors for 60/45/30 minutes', () => {
    expect(computePriceFloorCents(mockFloors, 'online', 60)).toBe(7000);
    expect(computePriceFloorCents(mockFloors, 'online', 45)).toBe(5250);
    expect(computePriceFloorCents(mockFloors, 'online', 30)).toBe(3500);
  });

  it('rounds base cents to the nearest integer for fractional hourly rates', () => {
    expect(computeBasePriceCents(120.01, 45)).toBe(9001);
    expect(computeBasePriceCents(50.005, 60)).toBe(5001);
    expect(computeBasePriceCents(89.99, 30)).toBe(4500);
  });

  it('detects violations when base price is below required floor', () => {
    const violations = evaluatePriceFloorViolations({
      hourlyRate: 60,
      durationOptions: [60, 45],
      locationTypes: ['in_person'],
      floors: mockFloors,
    });

    expect(violations).toHaveLength(2);
    expect(violations[0]).toMatchObject({
      modalityLabel: 'in-person',
      duration: 60,
      floorCents: 9000,
    });
  });
});

describe('evaluateFormatPriceFloorViolations', () => {
  it('returns empty map when no formats are enabled', () => {
    const result = evaluateFormatPriceFloorViolations({
      formatPrices: {},
      durationOptions: [60],
      floors: mockFloors,
    });
    expect(result.size).toBe(0);
  });

  it('skips formats with empty rate strings', () => {
    const formatPrices: FormatPriceState = { student_location: '' };
    const result = evaluateFormatPriceFloorViolations({
      formatPrices,
      durationOptions: [60],
      floors: mockFloors,
    });
    expect(result.size).toBe(0);
  });

  it('detects violation for student_location using in_person floor', () => {
    const formatPrices: FormatPriceState = { student_location: '60' };
    const result = evaluateFormatPriceFloorViolations({
      formatPrices,
      durationOptions: [60],
      floors: mockFloors,
    });
    expect(result.has('student_location')).toBe(true);
    const violations = result.get('student_location')!;
    expect(violations).toHaveLength(1);
    expect(violations[0]).toMatchObject({
      format: 'student_location',
      duration: 60,
      floorCents: 9000,
    });
  });

  it('detects violation for instructor_location using in_person floor', () => {
    const formatPrices: FormatPriceState = { instructor_location: '60' };
    const result = evaluateFormatPriceFloorViolations({
      formatPrices,
      durationOptions: [60],
      floors: mockFloors,
    });
    expect(result.has('instructor_location')).toBe(true);
    expect(result.get('instructor_location')).toHaveLength(1);
  });

  it('detects violation for online using remote floor', () => {
    const formatPrices: FormatPriceState = { online: '50' };
    const result = evaluateFormatPriceFloorViolations({
      formatPrices,
      durationOptions: [60],
      floors: mockFloors,
    });
    expect(result.has('online')).toBe(true);
    const violations = result.get('online')!;
    expect(violations[0]).toMatchObject({
      format: 'online',
      floorCents: 7000,
    });
  });

  it('returns no violations when rates meet floors', () => {
    const formatPrices: FormatPriceState = {
      student_location: '100',
      online: '80',
    };
    const result = evaluateFormatPriceFloorViolations({
      formatPrices,
      durationOptions: [60],
      floors: mockFloors,
    });
    expect(result.size).toBe(0);
  });

  it('evaluates each format independently across multiple durations', () => {
    const formatPrices: FormatPriceState = {
      student_location: '60',
      online: '80',
    };
    const result = evaluateFormatPriceFloorViolations({
      formatPrices,
      durationOptions: [60, 45],
      floors: mockFloors,
    });
    // student_location at $60 violates $90 floor for both durations
    expect(result.get('student_location')).toHaveLength(2);
    // online at $80 is above $70 floor — no violation
    expect(result.has('online')).toBe(false);
  });
});
