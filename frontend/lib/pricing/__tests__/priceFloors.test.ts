import {
  computeBasePriceCents,
  computePriceFloorCents,
  evaluatePriceFloorViolations,
  type PriceFloorConfig,
} from '../priceFloors';

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
