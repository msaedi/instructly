import {
  applyManualLocationChange,
  buildDisplayDate,
  getLocationTypeForManualChange,
  getClientFloorViolation,
  hasRelevantConflict,
  resolvePromoAction,
  shouldIgnoreAddressSuggestionSelection,
} from '../PaymentConfirmation.helpers';

describe('PaymentConfirmation helpers', () => {
  const relevantStatuses = new Set(['pending', 'confirmed', 'completed']);
  const overlap = jest.fn((startA: string, durationA: number, startB: string, durationB: number) => {
    return startA === '13:00' && durationA === 60 && startB === '13:30' && durationB === 30;
  });
  const parseTime = jest.fn((value: string) => {
    if (value === 'bad-time') {
      throw new Error('bad time');
    }
    return value;
  });
  const toMinutes = jest.fn((value: string) => {
    if (value === 'bad-time') {
      throw new Error('bad time');
    }
    const [hours = 0, minutes = 0] = value.split(':').map(Number);
    return hours * 60 + minutes;
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('builds display dates and rejects empty or invalid inputs', () => {
    expect(buildDisplayDate('2025-03-01')?.toISOString()).toContain('2025-03-01T00:00:00');
    expect(buildDisplayDate(new Date('2025-03-02T00:00:00Z'))).toBeInstanceOf(Date);
    expect(buildDisplayDate('   ')).toBeNull();
    expect(buildDisplayDate(new Date('invalid'))).toBeNull();
  });

  it('ignores address suggestions when the payload is missing or travel mode is off', () => {
    expect(shouldIgnoreAddressSuggestionSelection(null, true)).toBe(true);
    expect(shouldIgnoreAddressSuggestionSelection({ place_id: 'abc' }, false)).toBe(true);
    expect(shouldIgnoreAddressSuggestionSelection({ place_id: 'abc' }, true)).toBe(false);
  });

  it('restores student travel mode when changing location from a non-travel state', () => {
    expect(getLocationTypeForManualChange(false)).toBe('student_location');
    expect(getLocationTypeForManualChange(true)).toBeNull();
  });

  it('applies manual location change side effects only when leaving a non-travel state', () => {
    const setLocationType = jest.fn();
    const setSelectedPublicSpace = jest.fn();
    const setIsEditingLocation = jest.fn();
    const setAddressDetailsError = jest.fn();
    const onClearFloorViolation = jest.fn();

    applyManualLocationChange({
      isTravelLocation: false,
      setLocationType,
      setSelectedPublicSpace,
      setIsEditingLocation,
      setAddressDetailsError,
      onClearFloorViolation,
    });

    expect(setLocationType).toHaveBeenCalledWith('student_location');
    expect(setSelectedPublicSpace).toHaveBeenCalledWith(null);
    expect(setIsEditingLocation).toHaveBeenCalledWith(true);
    expect(setAddressDetailsError).toHaveBeenCalledWith(null);
    expect(onClearFloorViolation).toHaveBeenCalled();

    jest.clearAllMocks();

    applyManualLocationChange({
      isTravelLocation: true,
      setLocationType,
      setSelectedPublicSpace,
      setIsEditingLocation,
      setAddressDetailsError,
      onClearFloorViolation,
    });

    expect(setLocationType).not.toHaveBeenCalled();
    expect(setSelectedPublicSpace).toHaveBeenCalledWith(null);
    expect(setIsEditingLocation).toHaveBeenCalledWith(true);
    expect(setAddressDetailsError).toHaveBeenCalledWith(null);
    expect(onClearFloorViolation).toHaveBeenCalled();
  });

  it('resolves promo actions for referral conflicts, empty codes, removals, and valid applies', () => {
    expect(
      resolvePromoAction({ referralActive: true, promoActive: false, promoCode: 'SAVE20' }),
    ).toEqual({
      kind: 'error',
      message: 'Referral credit can’t be combined with a promo code.',
    });
    expect(
      resolvePromoAction({ referralActive: false, promoActive: true, promoCode: 'SAVE20' }),
    ).toEqual({ kind: 'remove' });
    expect(
      resolvePromoAction({ referralActive: false, promoActive: false, promoCode: '   ' }),
    ).toEqual({
      kind: 'error',
      message: 'Enter a promo code to apply.',
    });
    expect(
      resolvePromoAction({ referralActive: false, promoActive: false, promoCode: 'SAVE20' }),
    ).toEqual({ kind: 'apply' });
  });

  it('filters out irrelevant conflict items before checking overlap', () => {
    const key = { bookingDate: '2025-03-06', startHHMM24: '13:00', durationMinutes: 60 };

    expect(hasRelevantConflict(null, key, relevantStatuses, parseTime, toMinutes, overlap)).toBe(false);
    expect(
      hasRelevantConflict(
        { booking_date: '2025-03-07', start_time: '13:30', duration_minutes: 30 },
        key,
        relevantStatuses,
        parseTime,
        toMinutes,
        overlap,
      ),
    ).toBe(false);
    expect(
      hasRelevantConflict(
        { booking_date: '2025-03-06', start_time: '13:30', status: 'cancelled', duration_minutes: 30 },
        key,
        relevantStatuses,
        parseTime,
        toMinutes,
        overlap,
      ),
    ).toBe(false);
    expect(
      hasRelevantConflict(
        { booking_date: '2025-03-06' },
        key,
        relevantStatuses,
        parseTime,
        toMinutes,
        overlap,
      ),
    ).toBe(false);
    expect(overlap).not.toHaveBeenCalled();
  });

  it('rejects malformed conflict times and missing derived durations', () => {
    const key = { bookingDate: '2025-03-06', startHHMM24: '13:00', durationMinutes: 60 };

    expect(
      hasRelevantConflict(
        { booking_date: '2025-03-06', start_time: 'bad-time', duration_minutes: 30 },
        key,
        relevantStatuses,
        parseTime,
        toMinutes,
        overlap,
      ),
    ).toBe(false);

    expect(
      hasRelevantConflict(
        { booking_date: '2025-03-06', start_time: '13:30', duration_minutes: 0, end_time: 'bad-time' },
        key,
        relevantStatuses,
        parseTime,
        toMinutes,
        overlap,
      ),
    ).toBe(false);

    expect(
      hasRelevantConflict(
        { booking_date: '2025-03-06', start_time: '14:00', duration_minutes: 0, end_time: '13:30' },
        key,
        relevantStatuses,
        parseTime,
        toMinutes,
        overlap,
      ),
    ).toBe(false);
  });

  it('derives duration from end time and reports actual overlaps', () => {
    const key = { bookingDate: '2025-03-06', startHHMM24: '13:00', durationMinutes: 60 };

    expect(
      hasRelevantConflict(
        { booking_date: '2025-03-06', start_time: '13:30', duration_minutes: 0, end_time: '14:00' },
        key,
        relevantStatuses,
        parseTime,
        toMinutes,
        overlap,
      ),
    ).toBe(true);
    expect(overlap).toHaveBeenCalledWith('13:00', 60, '13:30', 30);
  });

  it('computes client floor violations only when the booking inputs are valid', () => {
    const computeFloor = jest.fn(() => 6000);
    const computeBase = jest.fn(() => 5000);

    expect(
      getClientFloorViolation(null, 100, 60, 'in_person', computeFloor, computeBase),
    ).toBeNull();
    expect(
      getClientFloorViolation({}, 0, 60, 'in_person', computeFloor, computeBase),
    ).toBeNull();
    expect(
      getClientFloorViolation({}, 100, 0, 'in_person', computeFloor, computeBase),
    ).toBeNull();
    expect(
      getClientFloorViolation({}, 100, 60, 'in_person', computeFloor, computeBase),
    ).toEqual({ floorCents: 6000, baseCents: 5000 });

    computeBase.mockReturnValueOnce(7000);
    expect(
      getClientFloorViolation({}, 100, 60, 'in_person', computeFloor, computeBase),
    ).toBeNull();
  });
});
