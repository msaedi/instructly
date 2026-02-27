import { TRANSACTION_LIMITS, DEFAULT_TIP_OPTIONS } from '../index';

describe('payment types re-exports (line 96)', () => {
  it('re-exports TRANSACTION_LIMITS from shared types', () => {
    expect(TRANSACTION_LIMITS).toBeDefined();
    expect(TRANSACTION_LIMITS.MAX_TRANSACTION).toBe(1000);
    expect(TRANSACTION_LIMITS.CREDIT_EXPIRY_MONTHS).toBe(12);
  });

  it('exports DEFAULT_TIP_OPTIONS with correct structure', () => {
    expect(DEFAULT_TIP_OPTIONS).toHaveLength(4);
    expect(DEFAULT_TIP_OPTIONS[0]).toEqual({ percentage: 0, amount: 0 });
    expect(DEFAULT_TIP_OPTIONS[3]).toEqual({ percentage: 25, amount: 0 });
  });
});
