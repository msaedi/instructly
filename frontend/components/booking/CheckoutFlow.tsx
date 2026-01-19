'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { loadStripe } from '@stripe/stripe-js';
import {
  Elements,
  CardElement,
  useStripe,
  useElements,
} from '@stripe/react-stripe-js';
import {
  Calendar,
  Clock,
  User,
  CreditCard,
  Loader2,
  CheckCircle,
  XCircle,
  Shield,
  Info,
} from 'lucide-react';
import * as Tooltip from '@radix-ui/react-tooltip';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { logger } from '@/lib/logger';
import { ApiProblemError } from '@/lib/api/fetch';
import { usePaymentMethods } from '@/hooks/queries/usePaymentMethods';
import {
  fetchPricingPreview,
  type PricingPreviewResponse,
  formatCentsToDisplay,
} from '@/lib/api/pricing';
import { usePricingConfig } from '@/lib/pricing/usePricingFloors';
import {
  computeStudentFeePercent,
  formatServiceSupportLabel,
  formatServiceSupportTooltip,
} from '@/lib/pricing/studentFee';
import { formatBookingDate, formatBookingTimeRange } from '@/lib/timezone/formatBookingTime';
import type { ApiErrorResponse, components } from '@/features/shared/api/types';

type CheckoutResponse = components['schemas']['CheckoutResponse'];

const stripePromise = loadStripe(
  process.env['NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY'] || ''
);

interface Booking {
  id: string;
  service_name: string;
  instructor_name: string;
  instructor_id: string;
  booking_date: string;
  start_time: string;
  end_time: string;
  booking_start_utc?: string | null;
  booking_end_utc?: string | null;
  lesson_timezone?: string | null;
  duration_minutes: number;
  hourly_rate: number;
  total_price: number;
}

interface PaymentMethod {
  id: string;
  last4: string;
  brand: string;
  is_default: boolean;
}

interface CheckoutFlowProps {
  booking: Booking;
  onSuccess: (paymentIntentId: string) => void;
  onCancel: () => void;
}

// Payment Form Component (handles Stripe Elements)
const PaymentForm: React.FC<{
  booking: Booking;
  savedMethods: PaymentMethod[];
  onSuccess: (paymentIntentId: string) => void;
  onError: (error: string) => void;
  studentPayAmount?: number;
}> = ({ booking, savedMethods, onSuccess, onError, studentPayAmount }) => {
  const stripe = useStripe();
  const elements = useElements();
  const [selectedMethod, setSelectedMethod] = useState<string | 'new'>('new');
  const [processing, setProcessing] = useState(false);
  const [saveCard, setSaveCard] = useState(false);
  const [cvv, setCvv] = useState('');
  const [requiresCvv, setRequiresCvv] = useState(false);

  const deriveBookingAmount = () => {
    const raw = (booking as unknown as { total_price?: unknown }).total_price;
    if (typeof raw === 'number' && Number.isFinite(raw)) {
      return Number(raw.toFixed(2));
    }
    if (typeof raw === 'string') {
      const parsed = Number(raw);
      if (Number.isFinite(parsed)) {
        return Number(parsed.toFixed(2));
      }
    }
    return 0;
  };

  const payAmount = typeof studentPayAmount === 'number'
    ? Number(studentPayAmount.toFixed(2))
    : deriveBookingAmount();

  useEffect(() => {
    // Select default method if available
    const defaultMethod = savedMethods.find(m => m.is_default);
    if (defaultMethod) {
      setSelectedMethod(defaultMethod.id);
      setRequiresCvv(true);
    }
  }, [savedMethods]);

  const processPayment = async () => {
    if (!stripe) {
      onError('Stripe not initialized');
      return;
    }

    setProcessing(true);

    try {
      let paymentMethodId: string | undefined;

      if (selectedMethod === 'new') {
        // Create new payment method from card element
        if (!elements) {
          throw new Error('Card elements not initialized');
        }

        const cardElement = elements.getElement(CardElement);
        if (!cardElement) {
          throw new Error('Card element not found');
        }

        const { error, paymentMethod } = await stripe.createPaymentMethod({
          type: 'card',
          card: cardElement,
        });

        if (error || !paymentMethod) {
          throw new Error(error?.message || 'Failed to create payment method');
        }

        paymentMethodId = paymentMethod.id;
      } else {
        // Use existing payment method
        paymentMethodId = selectedMethod;
      }

      // Create checkout session with backend
      const response = await fetch('/api/v1/payments/checkout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          // Cookies-only auth; do not attach bearer token
        },
        body: JSON.stringify({
          booking_id: booking.id,
          payment_method_id: paymentMethodId,
          save_payment_method: saveCard && selectedMethod === 'new',
        }),
      });

      if (!response.ok) {
        const errorData = (await response.json()) as ApiErrorResponse;
        throw new Error(errorData.detail || errorData.message || 'Payment failed');
      }

      const result = (await response.json()) as CheckoutResponse;

      // Handle 3D Secure if required
      if (result.requires_action && result.client_secret) {
        const { error: confirmError } = await stripe.confirmCardPayment(
          result.client_secret
        );

        if (confirmError) {
          throw new Error(confirmError.message || 'Payment confirmation failed');
        }
      }

      // Payment successful
      logger.info('Payment processed successfully');
      onSuccess(result.payment_intent_id);
    } catch (error: unknown) {
      logger.error('Payment processing error:', error);
      const message = error instanceof Error ? error.message : 'Payment failed. Please try again.';
      onError(message);
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Payment Method Selection */}
      <div className="space-y-3">
        <h3 className="font-medium text-gray-900">Payment Method</h3>

        {savedMethods.map((method) => (
          <label
            key={method.id}
            className={`flex items-center p-4 border rounded-lg cursor-pointer transition-colors ${
              selectedMethod === method.id
                ? 'border-blue-500 bg-blue-50'
                : 'border-gray-200 hover:border-gray-300'
            }`}
          >
            <input
              type="radio"
              name="payment-method"
              value={method.id}
              checked={selectedMethod === method.id}
              onChange={(e) => {
                setSelectedMethod(e.target.value);
                setRequiresCvv(true);
              }}
              className="mr-3"
            />
            <CreditCard className="h-5 w-5 mr-3 text-gray-400" />
            <div className="flex-1">
              <span className="font-medium">{method.brand}</span>
              <span className="ml-2 text-gray-500">•••• {method.last4}</span>
              {method.is_default && (
                <span className="ml-2 text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                  Default
                </span>
              )}
            </div>
          </label>
        ))}

        <label
          className={`flex items-center p-4 border rounded-lg cursor-pointer transition-colors ${
            selectedMethod === 'new'
              ? 'border-blue-500 bg-blue-50'
              : 'border-gray-200 hover:border-gray-300'
          }`}
        >
          <input
            type="radio"
            name="payment-method"
            value="new"
            checked={selectedMethod === 'new'}
            onChange={() => {
              setSelectedMethod('new');
              setRequiresCvv(false);
            }}
            className="mr-3"
          />
          <div className="flex-1">
            <span className="font-medium">Add New Card</span>
          </div>
        </label>
      </div>

      {/* New Card Input */}
      {selectedMethod === 'new' && (
        <div className="space-y-4">
          <div className="p-4 border rounded-lg">
            <CardElement
              options={{
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
              }}
            />
          </div>

          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={saveCard}
              onChange={(e) => setSaveCard(e.target.checked)}
              className="rounded border-gray-300"
            />
            <span className="text-sm text-gray-700">Save card for future use</span>
          </label>
        </div>
      )}

      {/* CVV for saved cards */}
      {requiresCvv && selectedMethod !== 'new' && (
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700">
            Security Code (CVV)
          </label>
          <input
            type="text"
            maxLength={4}
            placeholder="123"
            value={cvv}
            onChange={(e) => setCvv(e.target.value.replace(/\D/g, ''))}
            className="w-32 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      )}

      {/* Security Badge */}
      <div className="flex items-center space-x-2 text-sm text-gray-500">
        <Shield className="h-4 w-4" />
        <span>Your payment information is encrypted and secure</span>
      </div>

      {/* Pay Button */}
      <Button
        onClick={processPayment}
        disabled={processing || !stripe}
        className="w-full py-3 text-lg"
        size="lg"
      >
        {processing ? (
          <>
            <Loader2 className="h-5 w-5 mr-2 animate-spin" />
            Processing...
          </>
        ) : (
          `Pay $${payAmount.toFixed(2)}`
        )}
      </Button>
    </div>
  );
};

// Main CheckoutFlow Component
const CheckoutFlow: React.FC<CheckoutFlowProps> = ({ booking, onSuccess, onCancel }) => {
  // Use React Query hook for payment methods (deduplicates API calls)
  const { data: savedMethods = [], isLoading: loading } = usePaymentMethods();
  const [error, setError] = useState<string | null>(null);
  const [paymentStatus, setPaymentStatus] = useState<'idle' | 'processing' | 'success' | 'error'>('idle');
  const [pricingPreview, setPricingPreview] = useState<PricingPreviewResponse | null>(null);
  const [isPricingPreviewLoading, setIsPricingPreviewLoading] = useState(false);
  const [pricingPreviewError, setPricingPreviewError] = useState<string | null>(null);
  const { config: pricingConfig } = usePricingConfig();
  const serviceSupportFeePercent = useMemo(
    () => computeStudentFeePercent({ preview: pricingPreview, config: pricingConfig }),
    [pricingConfig, pricingPreview],
  );
  const serviceSupportFeeLabel = useMemo(
    () => formatServiceSupportLabel(serviceSupportFeePercent),
    [serviceSupportFeePercent],
  );
  const serviceSupportAnnotationLabel = useMemo(
    () => formatServiceSupportLabel(serviceSupportFeePercent, { includeFeeWord: false }),
    [serviceSupportFeePercent],
  );
  const serviceSupportTooltip = useMemo(
    () => formatServiceSupportTooltip(serviceSupportFeePercent),
    [serviceSupportFeePercent],
  );

  const normalizeAmount = (value: unknown, fallback = 0): number => {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return Number(value.toFixed(2));
    }
    if (typeof value === 'string') {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {
        return Number(parsed.toFixed(2));
      }
    }
    return Number(fallback.toFixed(2));
  };

  const durationMinutes = booking.duration_minutes ?? 60;
  const hourlyRate = normalizeAmount((booking as unknown as { hourly_rate?: unknown }).hourly_rate, 0);
  const baseLessonAmount = durationMinutes
    ? Number(((hourlyRate * durationMinutes) / 60).toFixed(2))
    : normalizeAmount(booking.total_price, 0);
  const totalAmount = normalizeAmount(booking.total_price, baseLessonAmount);
  const fallbackBaseCents = Math.round(baseLessonAmount * 100);
  const fallbackTotalCents = Math.round(totalAmount * 100);
  const previewBaseCents = pricingPreview ? pricingPreview.base_price_cents : fallbackBaseCents;
  const previewStudentPayCents = pricingPreview ? pricingPreview.student_pay_cents : fallbackTotalCents;
  const previewLineItems = pricingPreview?.line_items ?? [];

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setIsPricingPreviewLoading(true);
      setPricingPreviewError(null);
      try {
        const preview = await fetchPricingPreview(booking.id, 0);
        if (!cancelled) {
          setPricingPreview(preview);
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiProblemError && err.response.status === 422) {
          setPricingPreviewError(err.problem.detail ?? 'Price is below the minimum.');
        } else {
          setPricingPreviewError('Unable to load pricing preview.');
        }
        setPricingPreview(null);
      } finally {
        if (!cancelled) {
          setIsPricingPreviewLoading(false);
        }
      }
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, [booking.id]);

  // Payment methods now loaded via usePaymentMethods hook above

  const handlePaymentSuccess = (paymentIntentId: string) => {
    setPaymentStatus('success');
    setTimeout(() => {
      onSuccess(paymentIntentId);
    }, 2000);
  };

  const handlePaymentError = (errorMessage: string) => {
    setError(errorMessage);
    setPaymentStatus('error');
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (paymentStatus === 'success') {
    return (
      <div className="text-center py-12">
        <CheckCircle className="h-16 w-16 text-green-500 mx-auto mb-4" />
        <h2 className="text-2xl font-semibold mb-2">Payment Successful!</h2>
        <p className="text-gray-600">Your booking has been confirmed.</p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Booking Summary */}
      <Card className="p-6">
        <h2 className="text-xl font-semibold mb-4">Booking Summary</h2>

        <div className="space-y-3">
          <div className="flex items-start space-x-3">
            <User className="h-5 w-5 text-gray-400 mt-0.5" />
            <div>
              <p className="font-medium">Service</p>
              <p className="text-gray-600">{booking.service_name}</p>
              <p className="text-sm text-gray-500">with {booking.instructor_name}</p>
            </div>
          </div>

          <div className="flex items-start space-x-3">
            <Calendar className="h-5 w-5 text-gray-400 mt-0.5" />
            <div>
              <p className="font-medium">Date</p>
              <p className="text-gray-600">{formatBookingDate(booking)}</p>
            </div>
          </div>

          <div className="flex items-start space-x-3">
            <Clock className="h-5 w-5 text-gray-400 mt-0.5" />
            <div>
              <p className="font-medium">Time</p>
              <p className="text-gray-600">
                {formatBookingTimeRange(booking)}
              </p>
              <p className="text-sm text-gray-500">{booking.duration_minutes} minutes</p>
            </div>
          </div>

          <div className="pt-3 border-t">
            <div className="space-y-2">
              <div className="flex justify-between text-gray-600">
                <span>Lesson ({durationMinutes} min)</span>
                <span>{formatCentsToDisplay(previewBaseCents)}</span>
              </div>
              {previewLineItems.length > 0 ? (
                previewLineItems.map((item) => {
                  const isCredit = item.amount_cents < 0;
                  const normalizedLabel = (() => {
                    const label = item.label.toLowerCase();
                    if (label.startsWith('booking protection') || label.startsWith('service & support')) {
                      return serviceSupportFeeLabel;
                    }
                    return item.label;
                  })();
                  const isServiceSupportLineItem = normalizedLabel === serviceSupportFeeLabel;
                  return (
                    <div
                      key={`${item.label}-${item.amount_cents}`}
                      className={`flex justify-between text-sm ${
                        isCredit ? 'text-green-600 dark:text-green-400' : 'text-gray-600'
                      }`}
                    >
                      {isServiceSupportLineItem ? (
                        <span className="inline-flex items-center gap-1" aria-label={serviceSupportFeeLabel}>
                          <span>{serviceSupportFeeLabel}</span>
                          <Tooltip.Provider delayDuration={150} skipDelayDuration={75}>
                            <Tooltip.Root>
                              <Tooltip.Trigger asChild>
                                <button
                                  type="button"
                                  className="inline-flex h-4 w-4 items-center justify-center rounded-full text-gray-400 transition-colors hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 focus-visible:ring-offset-2"
                                  aria-label="Learn about the Service & Support fee"
                                >
                                  <Info className="h-3.5 w-3.5" aria-hidden="true" />
                                </button>
                              </Tooltip.Trigger>
                              <Tooltip.Content
                                side="top"
                                sideOffset={6}
                                className="max-w-xs whitespace-pre-line rounded-md bg-gray-900 px-2 py-1 text-xs text-white shadow text-left"
                              >
                                {serviceSupportTooltip}
                                <Tooltip.Arrow className="fill-gray-900" />
                              </Tooltip.Content>
                            </Tooltip.Root>
                          </Tooltip.Provider>
                        </span>
                      ) : (
                        <span>{normalizedLabel}</span>
                      )}
                      <span>{formatCentsToDisplay(item.amount_cents)}</span>
                    </div>
                  );
                })
              ) : (
                <p className="text-xs text-gray-500">
                  <span className="inline-flex items-center gap-1" aria-label={serviceSupportFeeLabel}>
                    <span>{serviceSupportAnnotationLabel}</span>
                    <Tooltip.Provider delayDuration={150} skipDelayDuration={75}>
                      <Tooltip.Root>
                        <Tooltip.Trigger asChild>
                          <button
                            type="button"
                            className="inline-flex h-4 w-4 items-center justify-center rounded-full text-gray-400 transition-colors hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 focus-visible:ring-offset-2"
                            aria-label="Learn about the Service & Support fee"
                          >
                            <Info className="h-3.5 w-3.5" aria-hidden="true" />
                          </button>
                        </Tooltip.Trigger>
                    <Tooltip.Content
                      side="top"
                      sideOffset={6}
                      className="max-w-xs whitespace-pre-line rounded-md bg-gray-900 px-2 py-1 text-xs text-white shadow text-left"
                    >
                      {serviceSupportTooltip}
                      <Tooltip.Arrow className="fill-gray-900" />
                    </Tooltip.Content>
                      </Tooltip.Root>
                    </Tooltip.Provider>
                  </span>{' '}
                  and credits apply at checkout.
                </p>
              )}
              <div className="flex justify-between text-sm font-semibold text-gray-800">
                <span>Total</span>
                <span>{formatCentsToDisplay(previewStudentPayCents)}</span>
              </div>
            </div>
            {isPricingPreviewLoading && (
              <p className="mt-2 text-xs text-gray-500">Updating pricing…</p>
            )}
            {pricingPreviewError && (
              <p className="mt-2 text-xs text-red-600">{pricingPreviewError}</p>
            )}
          </div>
        </div>
      </Card>

      {/* Payment Section */}
      <Card className="p-6">
        <h2 className="text-xl font-semibold mb-4">Payment</h2>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-start space-x-2">
            <XCircle className="h-5 w-5 text-red-500 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm text-red-700">{error}</p>
              <button
                onClick={() => {
                  setError(null);
                  setPaymentStatus('idle');
                }}
                className="text-sm text-red-600 underline mt-1"
              >
                Try again
              </button>
            </div>
          </div>
        )}

        <Elements stripe={stripePromise}>
          <PaymentForm
            booking={booking}
            savedMethods={savedMethods}
            onSuccess={handlePaymentSuccess}
            onError={handlePaymentError}
            studentPayAmount={previewStudentPayCents / 100}
          />
        </Elements>
      </Card>

      {/* Cancel Button */}
      <div className="flex justify-center">
        <Button
          variant="ghost"
          onClick={onCancel}
          disabled={paymentStatus === 'processing'}
        >
          Cancel and go back
        </Button>
      </div>
    </div>
  );
};

export default CheckoutFlow;
