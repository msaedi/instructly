import {
  calculateCreditApplication,
  validateTransactionAmount,
  formatCurrency,
  calculateTipAmount,
  getTimezoneOffset,
  determineBookingType,
} from '../paymentCalculations';
import { TRANSACTION_LIMITS, BookingType } from '@/features/shared/types/booking';

describe('calculateCreditApplication', () => {
  it('uses available credits up to the total amount', () => {
    expect(calculateCreditApplication(100, 50)).toEqual({
      creditsToUse: 50,
      remainingAmount: 50,
    });
  });

  it('respects maxCreditsAllowed when lower than available credits', () => {
    expect(calculateCreditApplication(200, 150, 75)).toEqual({
      creditsToUse: 75,
      remainingAmount: 125,
    });
  });

  it('caps credits at the total amount', () => {
    expect(calculateCreditApplication(80, 200)).toEqual({
      creditsToUse: 80,
      remainingAmount: 0,
    });
  });
});

describe('validateTransactionAmount', () => {
  it('accepts a positive amount within limits', () => {
    expect(validateTransactionAmount(1)).toBe(true);
  });

  it('rejects zero or negative amounts', () => {
    expect(validateTransactionAmount(0)).toBe(false);
    expect(validateTransactionAmount(-5)).toBe(false);
  });

  it('rejects amounts above the max limit', () => {
    expect(validateTransactionAmount(TRANSACTION_LIMITS.MAX_TRANSACTION)).toBe(true);
    expect(validateTransactionAmount(TRANSACTION_LIMITS.MAX_TRANSACTION + 1)).toBe(false);
  });
});

describe('formatCurrency', () => {
  it('formats whole dollar amounts', () => {
    expect(formatCurrency(10)).toBe('$10.00');
  });

  it('formats zero correctly', () => {
    expect(formatCurrency(0)).toBe('$0.00');
  });

  it('formats cents with two decimals', () => {
    expect(formatCurrency(12.5)).toBe('$12.50');
  });
});

describe('calculateTipAmount', () => {
  it('calculates a percentage of the base amount', () => {
    expect(calculateTipAmount(100, 20)).toBe(20);
  });

  it('returns zero for a zero base', () => {
    expect(calculateTipAmount(0, 15)).toBe(0);
  });

  it('handles fractional percentages', () => {
    expect(calculateTipAmount(80, 12.5)).toBe(10);
  });
});

describe('getTimezoneOffset', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('formats positive offsets with leading zeros', () => {
    jest.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-330);
    expect(getTimezoneOffset()).toBe('+05:30');
  });

  it('formats negative offsets', () => {
    jest.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(480);
    expect(getTimezoneOffset()).toBe('-08:00');
  });

  it('formats UTC offset', () => {
    jest.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(0);
    expect(getTimezoneOffset()).toBe('+00:00');
  });
});

describe('determineBookingType', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-01T00:00:00Z'));
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('returns last minute for lessons within 24 hours', () => {
    expect(determineBookingType(new Date('2025-01-01T12:00:00Z'))).toBe(BookingType.LAST_MINUTE);
  });

  it('returns standard for lessons exactly 24 hours away', () => {
    expect(determineBookingType(new Date('2025-01-02T00:00:00Z'))).toBe(BookingType.STANDARD);
  });

  it('returns standard for lessons beyond 24 hours', () => {
    expect(determineBookingType(new Date('2025-01-03T00:00:00Z'))).toBe(BookingType.STANDARD);
  });
});
