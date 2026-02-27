/**
 * Barrel export test for features/shared/api/schemas/index.ts (lines 1-4).
 *
 * Verifies that all sub-modules are re-exported from the barrel index.
 * If a module is renamed or removed without updating the barrel, this test fails.
 */

import * as barrel from '../index';

describe('schemas barrel export (index.ts)', () => {
  it('re-exports loadMeSchema from ./me', () => {
    expect(typeof barrel.loadMeSchema).toBe('function');
  });

  it('re-exports loadCreateBookingSchema from ./booking', () => {
    expect(typeof barrel.loadCreateBookingSchema).toBe('function');
  });

  it('re-exports from ./bookingList', () => {
    // bookingList exports loadBookingListSchema
    expect(typeof barrel.loadBookingListSchema).toBe('function');
  });

  it('re-exports from ./instructorProfile', () => {
    // instructorProfile exports loadInstructorProfileSchema
    expect(typeof barrel.loadInstructorProfileSchema).toBe('function');
  });
});
