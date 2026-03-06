import {
  buildDisplayDate,
  getClientFloorViolation,
  hasRelevantConflict,
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
