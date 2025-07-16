import { loadStripe, Stripe } from '@stripe/stripe-js';

// Initialize Stripe - use test key for now
const stripePromise = loadStripe(
  process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY || 'pk_test_placeholder'
);

export const getStripe = (): Promise<Stripe | null> => stripePromise;

export interface CreatePaymentIntentRequest {
  amount: number;
  currency: string;
  captureMethod: 'manual' | 'automatic';
  metadata: {
    bookingId: string;
    instructorId: string;
    studentId: string;
    lessonDate: string;
    bookingType: string;
  };
}

export interface ConfirmPaymentRequest {
  paymentIntentId: string;
  paymentMethodId: string;
}

// Stripe Elements configuration
export const stripeElementsOptions = {
  fonts: [
    {
      cssSrc: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap',
    },
  ],
};

export const cardElementOptions = {
  style: {
    base: {
      fontSize: '16px',
      color: '#374151',
      fontFamily: 'Inter, system-ui, sans-serif',
      '::placeholder': {
        color: '#9CA3AF',
      },
    },
    invalid: {
      color: '#EF4444',
      iconColor: '#EF4444',
    },
  },
};

// Helper to format amount for Stripe (convert dollars to cents)
export const formatAmountForStripe = (amount: number): number => {
  return Math.round(amount * 100);
};

// Helper to format amount from Stripe (convert cents to dollars)
export const formatAmountFromStripe = (amount: number): number => {
  return amount / 100;
};

// Error handling
export const getStripeErrorMessage = (error: any): string => {
  if (error.type === 'card_error' || error.type === 'validation_error') {
    return error.message;
  }

  switch (error.code) {
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
};
