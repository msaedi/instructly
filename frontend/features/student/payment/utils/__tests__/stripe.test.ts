const setupModule = (publishableKey?: string) => {
  jest.resetModules();
  const loadStripe = jest.fn().mockResolvedValue({});
  jest.doMock('@stripe/stripe-js', () => ({ loadStripe }));
  jest.doMock('@/lib/publicEnv', () => ({ STRIPE_PUBLISHABLE_KEY: publishableKey }));
  const stripeModule = require('../stripe') as typeof import('../stripe');
  return { stripeModule, loadStripe };
};

describe('getStripe', () => {
  it('initializes Stripe with the publishable key', async () => {
    const { stripeModule, loadStripe } = setupModule('pk_live_123');
    await stripeModule.getStripe();
    expect(loadStripe).toHaveBeenCalledWith('pk_live_123');
  });

  it('falls back to the placeholder key when missing', async () => {
    const { stripeModule, loadStripe } = setupModule(undefined);
    await stripeModule.getStripe();
    expect(loadStripe).toHaveBeenCalledWith('pk_test_placeholder');
  });

  it('returns the same promise on repeated calls', () => {
    const { stripeModule } = setupModule('pk_live_123');
    const first = stripeModule.getStripe();
    const second = stripeModule.getStripe();
    expect(first).toBe(second);
  });
});

describe('formatAmountForStripe', () => {
  it('converts dollars to cents', () => {
    const { stripeModule } = setupModule('pk_live_123');
    expect(stripeModule.formatAmountForStripe(10)).toBe(1000);
  });

  it('rounds to the nearest cent', () => {
    const { stripeModule } = setupModule('pk_live_123');
    expect(stripeModule.formatAmountForStripe(10.005)).toBe(1001);
  });

  it('handles zero values', () => {
    const { stripeModule } = setupModule('pk_live_123');
    expect(stripeModule.formatAmountForStripe(0)).toBe(0);
  });
});

describe('formatAmountFromStripe', () => {
  it('converts cents to dollars', () => {
    const { stripeModule } = setupModule('pk_live_123');
    expect(stripeModule.formatAmountFromStripe(1250)).toBe(12.5);
  });

  it('handles zero values', () => {
    const { stripeModule } = setupModule('pk_live_123');
    expect(stripeModule.formatAmountFromStripe(0)).toBe(0);
  });

  it('preserves fractional dollar values', () => {
    const { stripeModule } = setupModule('pk_live_123');
    expect(stripeModule.formatAmountFromStripe(105)).toBe(1.05);
  });
});

describe('getStripeErrorMessage', () => {
  it('returns the message for card errors', () => {
    const { stripeModule } = setupModule('pk_live_123');
    expect(stripeModule.getStripeErrorMessage({ type: 'card_error', message: 'Card declined' })).toBe(
      'Card declined'
    );
  });

  it('maps known error codes to friendly messages', () => {
    const { stripeModule } = setupModule('pk_live_123');
    expect(stripeModule.getStripeErrorMessage({ code: 'payment_intent_payment_attempt_failed' })).toBe(
      'Payment failed. Please check your card details and try again.'
    );
  });

  it('returns a default message for unknown errors', () => {
    const { stripeModule } = setupModule('pk_live_123');
    expect(stripeModule.getStripeErrorMessage({ code: 'unknown_code' })).toBe(
      'An unexpected error occurred. Please try again.'
    );
  });
});
