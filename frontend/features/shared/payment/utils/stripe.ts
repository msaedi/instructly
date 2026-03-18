import { loadStripe, type Appearance, type Stripe } from '@stripe/stripe-js';
import { STRIPE_PUBLISHABLE_KEY } from '@/lib/publicEnv';

// Initialize Stripe lazily to avoid throwing at module load time in tests
let stripePromise: Promise<Stripe | null> | null = null;

export const getStripe = (): Promise<Stripe | null> => {
  if (!stripePromise) {
    if (!STRIPE_PUBLISHABLE_KEY) {
      throw new Error('NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY is not configured');
    }
    stripePromise = loadStripe(STRIPE_PUBLISHABLE_KEY);
  }
  return stripePromise;
};

// Payment intent request types removed - use generated types from @/features/shared/api/types
// or @/src/api/generated/instructly.schemas if needed

// Stripe Elements configuration
export const stripeElementsOptions = {
  fonts: [
    {
      cssSrc: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap',
    },
  ],
};

// PaymentElement appearance configuration
export function getPaymentElementAppearance(isDark = false): Appearance {
  return {
    theme: isDark ? 'night' : 'stripe',
    variables: {
      fontFamily: 'Inter, system-ui, sans-serif',
      colorPrimary: '#7E22CE',
      colorDanger: '#EF4444',
      ...(isDark && {
        colorBackground: '#1f2937',
      }),
    },
  };
}

// Static export for backward compatibility in tests
export const paymentElementAppearance: Appearance = getPaymentElementAppearance(false);

// Helper to format amount for Stripe (convert dollars to cents)
export const formatAmountForStripe = (amount: number): number => {
  return Math.round(amount * 100);
};

// Helper to format amount from Stripe (convert cents to dollars)
export const formatAmountFromStripe = (amount: number): number => {
  return amount / 100;
};

// Error handling
export const getStripeErrorMessage = (error: unknown): string => {
  if (error && typeof error === 'object' && 'type' in error && 'message' in error) {
    const stripeError = error as { type: string; message: string };
    if (stripeError.type === 'card_error' || stripeError.type === 'validation_error') {
      return stripeError.message;
    }
  }

  // Handle other error types with code property
  if (error && typeof error === 'object' && 'code' in error) {
    const errorWithCode = error as { code: string };
    switch (errorWithCode.code) {
      case 'payment_intent_authentication_failure':
        return 'Authentication failed. Please try a different payment method.';
      case 'payment_intent_payment_attempt_failed':
        return 'Payment failed. Please check your card details and try again.';
      case 'amount_too_large':
        return 'Amount exceeds the maximum transaction limit of $1,000.';
      case 'insufficient_funds':
        return 'Insufficient funds. Please try a different payment method.';
      default:
        return 'An unexpected error occurred. Please try again.';
    }
  }

  return 'An unexpected error occurred. Please try again.';
};
