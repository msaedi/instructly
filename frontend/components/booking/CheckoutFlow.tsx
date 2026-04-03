'use client';

import React, { useState, useEffect, useMemo } from 'react';
import {
  Elements,
  PaymentElement,
  useStripe,
  useElements,
} from '@stripe/react-stripe-js';
import { getStripe, getPaymentElementAppearance } from '@/features/shared/payment/utils/stripe';
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
import { fetchWithSessionRefresh } from '@/lib/auth/sessionRefresh';
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
import { extractApiErrorMessage } from '@/lib/apiErrors';

type CheckoutResponse = components['schemas']['CheckoutResponse'];


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

// Inner form component for new-card PaymentElement (must be inside <Elements>)
const NewCardPaymentForm: React.FC<{
  paymentIntentId: string;
  onSuccess: (paymentIntentId: string) => void;
  onError: (error: string) => void;
  payAmount: number;
  processing: boolean;
  setProcessing: (v: boolean) => void;
}> = ({ paymentIntentId, onSuccess, onError, payAmount, processing, setProcessing }) => {
  const stripe = useStripe();
  const elements = useElements();

  const handleSubmit = async () => {
    if (!stripe || !elements) return void onError('Stripe not initialized');

    setProcessing(true);

    try {
      const { error: confirmError } = await stripe.confirmPayment({
        elements,
        confirmParams: {
          return_url: `${window.location.origin}/student/booking/complete`,
        },
        redirect: 'if_required',
      });

      if (confirmError) {
        throw new Error(confirmError.message || 'Payment failed');
      }

      // PaymentIntent is now in requires_capture state (capture_method: manual)
      logger.info('Payment processed successfully');
      onSuccess(paymentIntentId);
    } catch (error: unknown) {
      logger.error('Payment processing error:', error);
      const message = error instanceof Error ? error.message : 'Payment failed. Please try again.';
      onError(message);
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="p-4 border rounded-lg">
        <PaymentElement />
      </div>

      {/* Security Badge */}
      <div className="flex items-center space-x-2 text-sm text-gray-500 dark:text-gray-400">
        <Shield className="h-4 w-4" />
        <span>Your payment information is encrypted and secure</span>
      </div>

      {/* Pay Button */}
      <Button
        onClick={handleSubmit}
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

// Payment Form Component (handles saved cards + new card via PaymentElement)
const PaymentForm: React.FC<{
  booking: Booking;
  savedMethods: PaymentMethod[];
  onSuccess: (paymentIntentId: string) => void;
  onError: (error: string) => void;
  studentPayAmount?: number;
}> = ({ booking, savedMethods, onSuccess, onError, studentPayAmount }) => {
  const [selectedMethod, setSelectedMethod] = useState<string | 'new'>('new');
  const [processing, setProcessing] = useState(false);
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [intentPaymentIntentId, setIntentPaymentIntentId] = useState<string | null>(null);
  const [intentLoading, setIntentLoading] = useState(false);

  // Stable ref for onError to avoid re-triggering the intent fetch effect
  const onErrorRef = React.useRef(onError);
  onErrorRef.current = onError;

  const payAmount = typeof studentPayAmount === 'number'
    ? Number(studentPayAmount.toFixed(2))
    : 0;

  useEffect(() => {
    // Select default method if available
    const defaultMethod = savedMethods.find(m => m.is_default);
    if (defaultMethod) {
      setSelectedMethod(defaultMethod.id);
    }
  }, [savedMethods]);

  // Track whether we've already fetched a PI for this booking
  const hasFetchedIntentRef = React.useRef(false);

  // Fetch PaymentIntent clientSecret when "new card" is selected.
  // Reuse existing PI if user toggles away and back — avoids orphaned intents.
  useEffect(() => {
    if (selectedMethod !== 'new') {
      return;
    }

    // Already have a PI for this booking — reuse it
    if (hasFetchedIntentRef.current) {
      return;
    }

    let cancelled = false;
    const fetchIntent = async () => {
      setIntentLoading(true);
      try {
        const response = await fetchWithSessionRefresh('/api/v1/payments/checkout', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            booking_id: booking.id,
          }),
        });

        if (!response.ok) {
          const errorData = (await response.json()) as ApiErrorResponse;
          throw new Error(extractApiErrorMessage(errorData, 'Failed to initialize payment'));
        }

        const result = (await response.json()) as CheckoutResponse;
        if (!cancelled && result.client_secret) {
          setClientSecret(result.client_secret);
          setIntentPaymentIntentId(result.payment_intent_id);
          hasFetchedIntentRef.current = true;
        }
      } catch (error: unknown) {
        if (!cancelled) {
          hasFetchedIntentRef.current = false; // Allow retry on error
          const message = error instanceof Error ? error.message : 'Failed to initialize payment';
          onErrorRef.current(message);
        }
      } finally {
        if (!cancelled) {
          setIntentLoading(false);
        }
      }
    };

    void fetchIntent();
    return () => { cancelled = true; };
  }, [selectedMethod, booking.id]);

  // Process payment for saved card (existing flow — no PaymentElement needed)
  const processSavedCardPayment = async () => {
    setProcessing(true);

    try {
      const response = await fetchWithSessionRefresh('/api/v1/payments/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          booking_id: booking.id,
          payment_method_id: selectedMethod,
          save_payment_method: false,
        }),
      });

      if (!response.ok) {
        const errorData = (await response.json()) as ApiErrorResponse;
        throw new Error(extractApiErrorMessage(errorData, 'Payment failed'));
      }

      const result = (await response.json()) as CheckoutResponse;

      // Handle 3D Secure if required (for saved cards)
      if (result.requires_action && result.client_secret) {
        const stripeInstance = await getStripe();
        if (!stripeInstance) {
          throw new Error('Stripe not initialized');
        }
        const { error: confirmError } = await stripeInstance.confirmPayment({
          clientSecret: result.client_secret,
          confirmParams: {
            return_url: `${window.location.origin}/student/booking/complete`,
          },
          redirect: 'if_required',
        });
        if (confirmError) {
          throw new Error(confirmError.message || 'Payment confirmation failed');
        }
      }

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
        <h3 className="font-medium text-gray-900 dark:text-gray-100">Payment Method</h3>

        {savedMethods.map((method) => (
          <label
            key={method.id}
            className={`flex items-center p-4 border rounded-lg cursor-pointer transition-colors ${
              selectedMethod === method.id
                ? 'border-blue-500 bg-blue-50 dark:bg-blue-900 dark:text-indigo-200'
                : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
            }`}
          >
            <input
              type="radio"
              name="payment-method"
              value={method.id}
              checked={selectedMethod === method.id}
              onChange={(e) => {
                setSelectedMethod(e.target.value);
              }}
              className="mr-3"
            />
            <CreditCard className="h-5 w-5 mr-3 text-gray-400 dark:text-gray-300" />
            <div className="flex-1">
              <span className="font-medium">{method.brand}</span>
              <span className="ml-2 text-gray-500 dark:text-gray-400">•••• {method.last4}</span>
              {method.is_default && (
                <span className="ml-2 text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 px-2 py-0.5 rounded">
                  Default
                </span>
              )}
            </div>
          </label>
        ))}

        <label
          className={`flex items-center p-4 border rounded-lg cursor-pointer transition-colors ${
            selectedMethod === 'new'
              ? 'border-blue-500 bg-blue-50 dark:bg-blue-900 dark:text-indigo-200'
              : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
          }`}
        >
          <input
            type="radio"
            name="payment-method"
            value="new"
            checked={selectedMethod === 'new'}
            onChange={() => {
              setSelectedMethod('new');
            }}
            className="mr-3"
          />
          <div className="flex-1">
            <span className="font-medium">Add New Card</span>
          </div>
        </label>
      </div>

      {/* New Card Input via PaymentElement */}
      {selectedMethod === 'new' && (
        <div className="space-y-4">
          {intentLoading && (
            <div className="flex justify-center items-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-gray-400 dark:text-gray-300" />
            </div>
          )}

          {clientSecret && intentPaymentIntentId && (
            <Elements
              stripe={getStripe()}
              options={{ clientSecret, appearance: getPaymentElementAppearance(
                typeof document !== 'undefined' && document.documentElement.classList.contains('dark')
              ) }}
            >
              <NewCardPaymentForm
                paymentIntentId={intentPaymentIntentId}
                onSuccess={onSuccess}
                onError={onError}
                payAmount={payAmount}
                processing={processing}
                setProcessing={setProcessing}
              />
            </Elements>
          )}
        </div>
      )}

      {/* Saved Card Payment */}
      {selectedMethod !== 'new' && (
        <>
          {/* Security Badge */}
          <div className="flex items-center space-x-2 text-sm text-gray-500 dark:text-gray-400">
            <Shield className="h-4 w-4" />
            <span>Your payment information is encrypted and secure</span>
          </div>

          {/* Pay Button for saved cards */}
          <Button
            onClick={processSavedCardPayment}
            disabled={processing}
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
        </>
      )}
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
        <Loader2 className="h-8 w-8 animate-spin text-gray-400 dark:text-gray-300" />
      </div>
    );
  }

  if (paymentStatus === 'success') {
    return (
      <div className="text-center py-12">
        <CheckCircle className="h-16 w-16 text-green-500 mx-auto mb-4" />
        <h2 className="text-2xl font-semibold mb-2">Payment Successful!</h2>
        <p className="text-gray-600 dark:text-gray-400">Your booking has been confirmed.</p>
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
            <User className="h-5 w-5 text-gray-400 dark:text-gray-300 mt-0.5" />
            <div>
              <p className="font-medium">Service</p>
              <p className="text-gray-600 dark:text-gray-400">{booking.service_name}</p>
              <p className="text-sm text-gray-500 dark:text-gray-400">with {booking.instructor_name}</p>
            </div>
          </div>

          <div className="flex items-start space-x-3">
            <Calendar className="h-5 w-5 text-gray-400 dark:text-gray-300 mt-0.5" />
            <div>
              <p className="font-medium">Date</p>
              <p className="text-gray-600 dark:text-gray-400">{formatBookingDate(booking)}</p>
            </div>
          </div>

          <div className="flex items-start space-x-3">
            <Clock className="h-5 w-5 text-gray-400 dark:text-gray-300 mt-0.5" />
            <div>
              <p className="font-medium">Time</p>
              <p className="text-gray-600 dark:text-gray-400">
                {formatBookingTimeRange(booking)}
              </p>
              <p className="text-sm text-gray-500 dark:text-gray-400">{booking.duration_minutes} minutes</p>
            </div>
          </div>

          <div className="pt-3 border-t">
            <div className="space-y-2">
              <div className="flex justify-between text-gray-600 dark:text-gray-400">
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
                        isCredit ? 'text-green-600 dark:text-green-400' : 'text-gray-600 dark:text-gray-400'
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
                                  className="inline-flex h-4 w-4 items-center justify-center rounded-full text-gray-400 dark:text-gray-300 transition-colors hover:text-gray-600 dark:hover:text-gray-200 focus-visible:outline-none "
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
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  <span className="inline-flex items-center gap-1" aria-label={serviceSupportFeeLabel}>
                    <span>{serviceSupportAnnotationLabel}</span>
                    <Tooltip.Provider delayDuration={150} skipDelayDuration={75}>
                      <Tooltip.Root>
                        <Tooltip.Trigger asChild>
                          <button
                            type="button"
                            className="inline-flex h-4 w-4 items-center justify-center rounded-full text-gray-400 dark:text-gray-300 transition-colors hover:text-gray-600 dark:hover:text-gray-200 focus-visible:outline-none "
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
              <div className="flex justify-between text-sm font-semibold text-gray-800 dark:text-gray-200">
                <span>Total</span>
                <span>{formatCentsToDisplay(previewStudentPayCents)}</span>
              </div>
            </div>
            {isPricingPreviewLoading && (
              <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">Updating pricing…</p>
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

        <PaymentForm
          booking={booking}
          savedMethods={savedMethods}
          onSuccess={handlePaymentSuccess}
          onError={handlePaymentError}
          studentPayAmount={previewStudentPayCents / 100}
        />
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
