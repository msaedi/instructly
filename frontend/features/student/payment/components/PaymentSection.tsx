'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { AlertCircle } from 'lucide-react';
import { BookingPayment, PaymentCard, CreditBalance, PaymentMethod } from '../types';
import { usePaymentFlow, PaymentStep } from '../hooks/usePaymentFlow';
import PaymentMethodSelection from './PaymentMethodSelection';
import PaymentConfirmation from './PaymentConfirmation';
import PaymentProcessing from './PaymentProcessing';
import PaymentSuccess from './PaymentSuccess';
import { logger } from '@/lib/logger';
import { requireString } from '@/lib/ts/safe';
import { toDateOnlyString } from '@/lib/availability/dateHelpers';
import { useCreateBooking } from '@/features/student/booking/hooks/useCreateBooking';
import { paymentService } from '@/services/api/payments';
import { protectedApi, type Booking } from '@/features/shared/api/client';
import { ApiProblemError } from '@/lib/api/fetch';
import {
  fetchPricingPreview,
  type PricingPreviewResponse,
} from '@/lib/api/pricing';
import CheckoutApplyReferral from '@/components/referrals/CheckoutApplyReferral';

// Custom error for payment actions that require user interaction
class PaymentActionError extends Error {
  constructor(
    message: string,
    public client_secret: string,
    public payment_intent_id: string
  ) {
    super(message);
    this.name = 'PaymentActionError';
  }
}

const normalizeCurrency = (value: unknown, fallback: number): number => {
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

const mergeBookingIntoPayment = (booking: Booking, fallback: BookingPayment): BookingPayment => {
  const durationMinutes = booking.duration_minutes ?? fallback.duration;
  const hourlyRate = normalizeCurrency(booking.hourly_rate, fallback.basePrice);
  const computedBase = durationMinutes
    ? Number(((hourlyRate * durationMinutes) / 60).toFixed(2))
    : fallback.basePrice;
  const totalAmount = normalizeCurrency(booking.total_price, fallback.totalAmount);

  const rawServiceFee = (booking as unknown as { service_fee?: unknown; booking_protection_fee?: unknown; platform_fee?: unknown })?.service_fee
    ?? (booking as unknown as { booking_protection_fee?: unknown }).booking_protection_fee
    ?? (booking as unknown as { platform_fee?: unknown }).platform_fee
    ?? fallback.serviceFee;
  const serviceFee = normalizeCurrency(rawServiceFee, fallback.serviceFee);

  const bookingDate = booking.booking_date
    ? new Date(`${booking.booking_date}T00:00:00`)
    : fallback.date;

  const instructorName = booking.instructor
    ? `${booking.instructor.first_name} ${booking.instructor.last_initial ?? ''}`.trim()
    : fallback.instructorName;

  return {
    ...fallback,
    bookingId: booking.id || fallback.bookingId,
    instructorId: booking.instructor_id || fallback.instructorId,
    instructorName: instructorName || fallback.instructorName,
    lessonType: booking.service_name || fallback.lessonType,
    date: bookingDate,
    startTime: booking.start_time || fallback.startTime,
    endTime: booking.end_time || fallback.endTime,
    duration: durationMinutes ?? fallback.duration,
    location: booking.meeting_location || fallback.location,
    basePrice: computedBase,
    serviceFee,
    totalAmount,
  };
};

interface PaymentSectionProps {
  bookingData: BookingPayment & {
    metadata?: Record<string, unknown>;
    serviceId?: string; // Optional fallback property
  };
  onSuccess: (confirmationNumber: string) => void;
  onError: (error: Error) => void;
  onBack?: () => void;
  showPaymentMethodInline?: boolean;
}

export function PaymentSection({ bookingData, onSuccess, onError, onBack, showPaymentMethodInline = false }: PaymentSectionProps) {
  const {
    createBooking,
    error: bookingError,
    reset: resetBookingError,
  } = useCreateBooking();

  const [confirmationNumber, setConfirmationNumber] = useState<string>('');
  const [updatedBookingData, setUpdatedBookingData] = useState<BookingPayment>(bookingData);
  const [localErrorMessage, setLocalErrorMessage] = useState<string>('');
  const [floorViolationMessage, setFloorViolationMessage] = useState<string | null>(null);
  const [referralAppliedCents, setReferralAppliedCents] = useState(0);
  const [promoApplied, setPromoApplied] = useState(false);
  const [pricingPreview, setPricingPreview] = useState<PricingPreviewResponse | null>(null);
  const [isPricingPreviewLoading, setIsPricingPreviewLoading] = useState(false);
  const [creditSliderCents, setCreditSliderCents] = useState(0);
  const [lastSuccessfulCreditCents, setLastSuccessfulCreditCents] = useState(0);
  const previewRequestIdRef = useRef(0);
  const pendingPreviewCreditsRef = useRef<number | null>(null);
  const lastPreviewCreditsRef = useRef<number | null>(null);

  // Real payment data from backend
  const [userCards, setUserCards] = useState<PaymentCard[]>([]);
  const [userCredits, setUserCredits] = useState<CreditBalance>({
    totalAmount: 0,
    credits: [],
  });
  const [autoAppliedCredits, setAutoAppliedCredits] = useState(false);
  const [isLoadingPaymentMethods, setIsLoadingPaymentMethods] = useState(true);

  // Track selected card ID separately for payment processing
  const [selectedCardId, setSelectedCardId] = useState<string | undefined>();

  // Initialize payment flow
  const {
    currentStep,
    paymentMethod,
    creditsToUse,
    error: paymentError,
    goToStep,
    selectPaymentMethod: selectPaymentMethodOriginal,
    reset: resetPayment,
  } = usePaymentFlow({
    booking: updatedBookingData,
    onSuccess: (bookingId) => {
      logger.info('Payment successful', { bookingId });
    },
    onError: (error) => {
      logger.error('Payment failed', error);
    },
  });

  // Get the actual selected card from userCards instead of using the mock from hook
  const selectedCard = selectedCardId ? userCards.find(card => card.id === selectedCardId) : null;

  // Wrap selectPaymentMethod to track card ID
  const selectPaymentMethod = useCallback((method: PaymentMethod, cardId?: string, credits?: number) => {
    setSelectedCardId(cardId);
    setUserChangingPayment(false); // Reset flag when a new method is selected
    selectPaymentMethodOriginal(method, cardId, credits);
  }, [selectPaymentMethodOriginal]);

  const updateCreditSelection = useCallback((creditCents: number, totalDueCents: number) => {
    const normalizedCreditCents = Math.max(0, Math.round(creditCents));
    const creditDollars = Number((normalizedCreditCents / 100).toFixed(2));
    const currentCreditCents = Math.max(0, Math.round(creditsToUse * 100));
    const coversFullAmount = normalizedCreditCents >= totalDueCents;

    if (normalizedCreditCents === 0) {
      if (paymentMethod !== PaymentMethod.CREDIT_CARD || currentCreditCents !== 0) {
        const effectiveCardId = selectedCardId
          ?? userCards.find((card) => card.isDefault)?.id
          ?? userCards[0]?.id;
        selectPaymentMethod(PaymentMethod.CREDIT_CARD, effectiveCardId, 0);
      }
      return;
    }

    if (coversFullAmount) {
      if (paymentMethod !== PaymentMethod.CREDITS || currentCreditCents !== normalizedCreditCents) {
        selectPaymentMethod(PaymentMethod.CREDITS, undefined, creditDollars);
      }
      return;
    }

    const effectiveCardId = selectedCardId
      ?? userCards.find((card) => card.isDefault)?.id
      ?? userCards[0]?.id;
    if (paymentMethod !== PaymentMethod.MIXED || currentCreditCents !== normalizedCreditCents) {
      selectPaymentMethod(PaymentMethod.MIXED, effectiveCardId, creditDollars);
    }
  }, [creditsToUse, paymentMethod, selectPaymentMethod, selectedCardId, userCards]);

  const subtotalCents = useMemo(() => Math.max(0, Math.round((updatedBookingData.totalAmount ?? 0) * 100)), [updatedBookingData.totalAmount]);
  const effectiveOrderId = updatedBookingData.bookingId || bookingData.bookingId;

  useEffect(() => {
    setReferralAppliedCents(0);
  }, [effectiveOrderId]);

  useEffect(() => {
    setFloorViolationMessage(null);
  }, [updatedBookingData.duration, updatedBookingData.basePrice, updatedBookingData.totalAmount]);

  useEffect(() => {
    const nextCreditCents = Math.max(0, Math.round(creditsToUse * 100));
    setCreditSliderCents(nextCreditCents);
  }, [creditsToUse]);

  const refreshOrderSummary = useCallback(async (orderIdentifier: string) => {
    try {
      const response = await protectedApi.getBooking(orderIdentifier);
      if (response.data) {
        setUpdatedBookingData(prev => mergeBookingIntoPayment(response.data as Booking, prev));
      } else if (response.error) {
        logger.warn('Failed to refresh order summary after referral application', {
          orderId: orderIdentifier,
          error: response.error,
        });
      }
    } catch (error) {
      logger.error('Unexpected error refreshing order summary', error as Error, {
        orderId: orderIdentifier,
      });
    }
  }, [setUpdatedBookingData]);

  const refreshCurrentOrderSummary = useCallback(async () => {
    if (!effectiveOrderId) return;
    await refreshOrderSummary(effectiveOrderId);
  }, [effectiveOrderId, refreshOrderSummary]);

  const handleReferralApplied = useCallback((cents: number) => {
    setReferralAppliedCents(cents);
    setPromoApplied(false);
  }, []);

  const referralApplyPanel = (
    <CheckoutApplyReferral
      orderId={effectiveOrderId ?? ''}
      subtotalCents={subtotalCents}
      promoApplied={promoApplied}
      onApplied={handleReferralApplied}
      onRefreshOrderSummary={refreshCurrentOrderSummary}
    />
  );

  const getTotalDueCents = useCallback(() => {
    if (pricingPreview) {
      return pricingPreview.student_pay_cents + Math.max(0, pricingPreview.credit_applied_cents);
    }
    return Math.max(0, Math.round((updatedBookingData.totalAmount ?? 0) * 100));
  }, [pricingPreview, updatedBookingData.totalAmount]);

  const handleCreditToggle = useCallback(() => {
    const totalDueCents = getTotalDueCents();
    if (creditSliderCents > 0) {
      setCreditSliderCents(0);
      updateCreditSelection(0, totalDueCents);
      if (floorViolationMessage) {
        setFloorViolationMessage(null);
      }
      return;
    }

    const availableCreditCents = Math.max(0, Math.round((userCredits.totalAmount || 0) * 100));
    if (availableCreditCents === 0) return;

    const targetCents = Math.min(availableCreditCents, totalDueCents);
    setCreditSliderCents(targetCents);
    updateCreditSelection(targetCents, totalDueCents);
  }, [creditSliderCents, getTotalDueCents, updateCreditSelection, userCredits.totalAmount, floorViolationMessage]);

  const handleCreditAmountChange = useCallback((amountDollars: number) => {
    const totalDueCents = getTotalDueCents();
    const requestedCents = Math.max(0, Math.round(amountDollars * 100));
    const clampedCents = Math.min(requestedCents, totalDueCents);
    if (floorViolationMessage && clampedCents <= lastSuccessfulCreditCents) {
      setFloorViolationMessage(null);
    }
    setCreditSliderCents(clampedCents);
    updateCreditSelection(clampedCents, totalDueCents);
  }, [getTotalDueCents, updateCreditSelection, floorViolationMessage, lastSuccessfulCreditCents]);

  const abortControllerRef = useRef<AbortController | null>(null);
  const loadPricingPreview = useCallback(async (creditCents: number) => {
    const bookingDraftId = updatedBookingData.bookingId || bookingData.bookingId;
    if (!bookingDraftId) {
      logger.warn('Skipping pricing preview fetch: missing booking id');
      return;
    }

    const normalizedCreditCents = Math.max(0, Math.round(creditCents));
    pendingPreviewCreditsRef.current = normalizedCreditCents;
    const requestId = (previewRequestIdRef.current += 1);
    setIsPricingPreviewLoading(true);
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const preview = await fetchPricingPreview(bookingDraftId, normalizedCreditCents, { signal: controller.signal });
      if (previewRequestIdRef.current !== requestId) {
        return;
      }

      pendingPreviewCreditsRef.current = null;
      lastPreviewCreditsRef.current = preview.credit_applied_cents;
      setPricingPreview(preview);
      setCreditSliderCents(preview.credit_applied_cents);
      setLastSuccessfulCreditCents(preview.credit_applied_cents);

      setUpdatedBookingData((prev) => ({
        ...prev,
        basePrice: preview.base_price_cents / 100,
        serviceFee: preview.student_fee_cents / 100,
        totalAmount: (preview.student_pay_cents + Math.max(0, preview.credit_applied_cents)) / 100,
      }));

      const totalDueCents = preview.student_pay_cents + Math.max(0, preview.credit_applied_cents);
      updateCreditSelection(preview.credit_applied_cents, totalDueCents);
    } catch (error) {
      if (previewRequestIdRef.current !== requestId) {
        return;
      }
      pendingPreviewCreditsRef.current = null;

      if (controller.signal.aborted) {
        logger.debug('pricing-preview-aborted', {
          bookingId: bookingDraftId,
          requestedCreditCents: normalizedCreditCents,
        });
        return;
      }

      const maybeProblemError = error as ApiProblemError;
      const status = maybeProblemError?.response?.status;
      if (status === 422) {
        const detail = maybeProblemError?.problem?.detail ?? 'Price must meet minimum requirements.';
        setFloorViolationMessage(detail);
        logger.info('pricing-floor-violation', {
          bookingId: bookingDraftId,
          requestedCreditCents: normalizedCreditCents,
        });
        setCreditSliderCents(lastSuccessfulCreditCents);
        const totalDueCents = getTotalDueCents();
        updateCreditSelection(lastSuccessfulCreditCents, totalDueCents);
        lastPreviewCreditsRef.current = lastSuccessfulCreditCents;
        return;
      }

      if (status !== undefined) {
        logger.warn('Pricing preview error with unexpected status', {
          bookingId: bookingDraftId,
          requestedCreditCents: normalizedCreditCents,
          status,
        });
      }

      logger.error('Failed to fetch pricing preview', error as Error, {
        bookingId: bookingDraftId,
        requestedCreditCents: normalizedCreditCents,
      });
      setLocalErrorMessage('Unable to refresh pricing preview. Please try again.');
      setCreditSliderCents(lastSuccessfulCreditCents);
      updateCreditSelection(lastSuccessfulCreditCents, getTotalDueCents());
    } finally {
      if (previewRequestIdRef.current === requestId) {
        setIsPricingPreviewLoading(false);
      }
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
    }
  }, [updatedBookingData.bookingId, bookingData.bookingId, updateCreditSelection, lastSuccessfulCreditCents, getTotalDueCents]);

  useEffect(() => {
    const bookingDraftId = updatedBookingData.bookingId || bookingData.bookingId;
    if (!bookingDraftId) return;
    const desiredCreditCents = Math.max(0, Math.round(creditsToUse * 100));
    if (
      pendingPreviewCreditsRef.current === desiredCreditCents ||
      (pricingPreview && lastPreviewCreditsRef.current === desiredCreditCents)
    ) {
      return;
    }

    const timeoutId = setTimeout(() => {
      void loadPricingPreview(desiredCreditCents);
    }, 200);

    return () => {
      clearTimeout(timeoutId);
      abortControllerRef.current?.abort();
    };
  }, [updatedBookingData.bookingId, bookingData.bookingId, creditsToUse, pricingPreview, loadPricingPreview]);

  // Fetch real payment methods and credits from backend
  useEffect(() => {
    const fetchPaymentData = async () => {
      try {
        setIsLoadingPaymentMethods(true);

        logger.info('Fetching payment data');

        // Fetch payment methods
        const methods = await paymentService.listPaymentMethods();
        logger.info('Payment methods response', { methods });

        const mappedCards: PaymentCard[] = methods.map(method => ({
          id: method.id,
          last4: method.last4,
          brand: method.brand.charAt(0).toUpperCase() + method.brand.slice(1), // Capitalize brand
          expiryMonth: 12, // These fields aren't returned by backend yet
          expiryYear: 2025,
          isDefault: method.is_default,
        }));
        setUserCards(mappedCards);

        // Fetch credit balance
        const balance = await paymentService.getCreditBalance();
        logger.info('Credit balance response', { balance });

        setUserCredits({
          totalAmount: balance.available || 0,
          credits: [], // Credits detail not implemented yet
          earliestExpiry: balance.expires_at || null,
        });

        logger.info('Successfully loaded payment data', {
          cardCount: mappedCards.length,
          creditBalance: balance.available,
          cards: mappedCards
        });
      } catch (error) {
        logger.error('Failed to load payment methods', {
          error: error as Error,
          message: (error as Error).message,
          stack: (error as Error).stack
        });
        // Fall back to mock data for testing
        logger.warn('Using mock payment data as fallback');
        setUserCards([
          {
            id: '1',
            last4: '4242',
            brand: 'Visa',
            expiryMonth: 12,
            expiryYear: 2025,
            isDefault: true,
          },
        ]);
      } finally {
        setIsLoadingPaymentMethods(false);
      }
    };

    void fetchPaymentData();
  }, []);

  // Auto-apply available credits by default on confirmation step
  useEffect(() => {
    const hasCredits = (userCredits?.totalAmount || 0) > 0;
    if (!hasCredits || autoAppliedCredits) return;

    // Determine a card to use if needed
    const defaultCard = userCards.find(c => c.isDefault) || userCards[0];
    const effectiveCardId = selectedCardId || defaultCard?.id;

    if (!effectiveCardId) return; // No card yet

    const totalDueDollars = getTotalDueCents() / 100;
    const amountToApply = Math.min(userCredits.totalAmount || 0, totalDueDollars);
    if (amountToApply <= 0) return;

    selectPaymentMethod(PaymentMethod.MIXED, effectiveCardId, amountToApply);
    setAutoAppliedCredits(true);
  }, [userCredits, userCards, selectedCardId, autoAppliedCredits, selectPaymentMethod, getTotalDueCents]);

  // Track if user manually went back to change payment method
  const [userChangingPayment, setUserChangingPayment] = useState(false);

  // If inline mode, skip directly to confirmation (but not if user is changing payment)
  useEffect(() => {
    if (showPaymentMethodInline && currentStep === PaymentStep.METHOD_SELECTION && userCards.length > 0 && !userChangingPayment) {
      // Auto-select credit card payment with default card
      const defaultCard = userCards.find(card => card.isDefault) || userCards[0];
      selectPaymentMethod(PaymentMethod.CREDIT_CARD, defaultCard?.id);
    }
  }, [showPaymentMethodInline, currentStep, selectPaymentMethod, userCards, userChangingPayment]);

  // Override processPayment to create booking and process payment
  const processPayment = async () => {
    setFloorViolationMessage(null);
    // Set to processing state
    goToStep(PaymentStep.PROCESSING);

    try {
      // Helper: convert display times like "6:00am" or "12:30pm" to 24h "HH:MM"
      const toHHMM = (display: string): string => {
        const lower = String(display ?? '').trim().toLowerCase();
        if (!lower) throw new Error('Invalid time format: empty');
        // If already in HH:MM or HH:MM:SS (24h), normalize to HH:MM
        const basicMatch = lower.match(/^\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*$/) as RegExpMatchArray | null;
        const ampmMatch = lower.match(/^\s*(\d{1,2}):(\d{2})\s*(am|pm)\s*$/) as RegExpMatchArray | null;
        if (ampmMatch) {
          const [, hStr = '', mStr = '', ampm = ''] = ampmMatch as RegExpMatchArray;
          let hour = parseInt(hStr, 10);
          const minute = parseInt(mStr, 10);
          if (ampm === 'pm' && hour !== 12) hour += 12;
          if (ampm === 'am' && hour === 12) hour = 0;
          return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
        }
        if (basicMatch) {
          const [, hStr = '', mStr = ''] = basicMatch as RegExpMatchArray;
          const hour = parseInt(hStr, 10);
          const minute = parseInt(mStr, 10);
          return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
        }
        // Fallback: attempt Date parse
        const parsed = new Date(`1970-01-01T${display}`);
        if (!Number.isNaN(parsed.getTime())) {
          return `${String(parsed.getHours()).padStart(2, '0')}:${String(parsed.getMinutes()).padStart(2, '0')}`;
        }
        throw new Error(`Invalid time format: ${display}`);
      };

      // Get instructor ID and service ID from booking data (now strings/ULIDs)
      const instructorId = String(bookingData.instructorId || '');
      // Prefer explicit serviceId (ULID) from metadata; as a fallback, try bookingData.serviceId
      const serviceId = String((bookingData.metadata?.['serviceId'] || bookingData.serviceId) ?? '');

      // Normalize times and date
      const formattedStartTime = toHHMM(String(bookingData.startTime ?? ''));
      const endTime = toHHMM(String(bookingData.endTime ?? ''));

      // If date is missing (null/undefined), try to recover from selectedSlot in sessionStorage
      let bookingDate: string;
      if (!bookingData.date) {
        try {
          const slotRaw = sessionStorage.getItem('selectedSlot');
          if (slotRaw) {
            const slot = JSON.parse(slotRaw) as { date?: string };
            if (slot?.date) {
              bookingDate = toDateOnlyString(slot.date, 'selectedSlot.booking_date');
              // One-time recovery: patch bookingData in memory to avoid repeated missing-date errors
              setUpdatedBookingData((prev) => ({ ...prev, date: new Date(bookingDate) }));
            } else {
              throw new Error('missing');
            }
          } else {
            throw new Error('missing');
          }
        } catch {
          // As a last resort, error out clearly
          throw new Error('Missing booking date. Please re-select date and time.');
        }
      } else {
        bookingDate = toDateOnlyString(bookingData.date as Date | string, 'booking_date');
      }

      // Debug logging to identify missing data
      logger.info('Preparing booking request', {
        instructorId,
        serviceId,
        bookingDate,
        startTime: formattedStartTime,
        endTime,
        duration: bookingData.duration,
        metadata: bookingData.metadata,
        lessonType: bookingData.lessonType,
        fullBookingData: bookingData,
      });

      // Step 1: Create booking via API
      requireString(bookingDate, 'bookingDate');
      requireString(instructorId, 'instructorId');
      requireString(serviceId, 'serviceId');
      // Build a payload compatible with CreateBookingRequest used by protectedApi
      const selectedDuration = (() => {
        try {
          const startParts = formattedStartTime.split(':');
          const endParts = endTime.split(':');
          const sh = parseInt(startParts[0] ?? '0', 10);
          const sm = parseInt(startParts[1] ?? '0', 10);
          const eh = parseInt(endParts[0] ?? '0', 10);
          const em = parseInt(endParts[1] ?? '0', 10);
          const mins = (eh * 60 + em) - (sh * 60 + sm);
          return Number.isFinite(mins) && mins > 0 ? mins : undefined;
        } catch {
          return undefined;
        }
      })();

      const booking = await createBooking({
        instructor_id: instructorId,
        instructor_service_id: serviceId,
        booking_date: bookingDate,
        start_time: formattedStartTime,
        end_time: endTime,
        selected_duration: selectedDuration,
      } as unknown as import('@/features/shared/api/client').CreateBookingRequest);

      if (!booking) {
        const errorMsg = (bookingError as string) || 'Failed to create booking';
        const context = { bookingError, bookingData };
        if (/minimum price/i.test(errorMsg)) {
          logger.warn('Booking creation blocked by price floor validation', context);
          setFloorViolationMessage(errorMsg);
          resetBookingError();
          goToStep(PaymentStep.CONFIRMATION);
          return;
        }
        logger.error('Booking creation prevented', new Error(errorMsg), context);
        throw new Error(errorMsg);
      }

      logger.info('Booking created successfully', {
        bookingId: booking.id,
        status: booking.status,
      });

      // Step 2: Process payment if there's an amount due
      const amountDue = Math.max(0, bookingData.totalAmount - creditsToUse - referralAppliedCents / 100);

      try {
        if (amountDue > 0 && selectedCardId) {
          // Process payment through Stripe
          const checkoutResult = await paymentService.createCheckout({
            booking_id: String(booking.id),
            payment_method_id: selectedCardId,
            save_payment_method: false, // Can be configured based on user preference
          });

          logger.info('Payment processed', {
            paymentIntentId: checkoutResult.payment_intent_id,
            status: checkoutResult.status,
            amount: checkoutResult.amount,
          });

          // Check if payment requires additional action (3D Secure, etc.)
          if (checkoutResult.requires_action && checkoutResult.client_secret) {
            // Surface requires_action to the caller/UI; a Stripe Elements flow should confirm this PI.
            // Here we return a specific error to trigger the 3DS UI upstream.
            throw new PaymentActionError(
              'requires_action',
              checkoutResult.client_secret,
              checkoutResult.payment_intent_id
            );
          }

          if (checkoutResult.status !== 'succeeded' && checkoutResult.status !== 'processing') {
            throw new Error(`Payment failed with status: ${checkoutResult.status}`);
          }
        } else if (amountDue > 0) {
          // No payment method selected but payment is required
          throw new Error('Payment method required');
        }
      } catch (paymentError: unknown) {
        // Payment failed - cancel the booking to free up the slot
        logger.warn('Payment failed, cancelling booking', {
          bookingId: booking.id,
          error: paymentError,
        });

        try {
          await protectedApi.cancelBooking(String(booking.id), 'Payment failed');
          logger.info('Booking cancelled after payment failure', { bookingId: booking.id });
        } catch (cancelError) {
          logger.error('Failed to cancel booking after payment failure', cancelError as Error);
        }

        // Provide better error messages for specific failures
        const errorMessage = (paymentError as Record<string, unknown>)?.['message'] || 'Payment failed';
        // If requires_action, instruct UI to perform 3DS confirmation
        if (errorMessage === 'requires_action' && (paymentError as Record<string, unknown>)?.['client_secret']) {
          setLocalErrorMessage('Additional authentication required to complete your payment.');
          goToStep(PaymentStep.ERROR);
          // The page embedding PaymentSection can detect this message and call stripe.confirmCardPayment
          throw new Error('3ds_required');
        }
        if (typeof errorMessage === 'string' && errorMessage.includes('Instructor payment account not set up')) {
          throw new Error('This instructor is not yet set up to receive payments. Please try booking with another instructor or contact support.');
        }

        // Re-throw the payment error
        throw paymentError;
      }

      // Update booking data with actual booking ID
      const updatedData = { ...updatedBookingData, bookingId: String(booking.id) };
      setUpdatedBookingData(updatedData);
      const confirmationNum = `B${booking.id}`;
      setConfirmationNumber(confirmationNum);

      // Move to success state
      goToStep(PaymentStep.SUCCESS);

      // Call success callback
      onSuccess(confirmationNum);

    } catch (error) {
      logger.error('Payment processing failed', error as Error);

      // Extract the error message
      const defaultMsg = 'An error occurred while processing your payment.';
      let errorMessage = defaultMsg;
      if (error instanceof Error) {
        errorMessage = error.message;
        // Clean up specific Stripe error messages
        if (errorMessage.includes('insufficient funds')) {
          errorMessage = 'Your card has insufficient funds. Please try a different payment method.';
        } else if (errorMessage.includes('card was declined')) {
          errorMessage = 'Your card was declined. Please try a different payment method.';
        } else if (errorMessage.includes('expired')) {
          errorMessage = 'Your card has expired. Please use a different payment method.';
        } else if (errorMessage.includes('PaymentMethod was previously used')) {
          errorMessage = 'This payment method cannot be reused. Please add a new card or select a different payment method.';
        } else if (errorMessage.includes('Payment failed with status')) {
          errorMessage = 'Payment could not be processed. Please try again or use a different card.';
        }
      }

      setLocalErrorMessage(errorMessage);
      goToStep(PaymentStep.ERROR);
      onError(error as Error);
    }
  };

  // Handle error retry
  const handleRetry = () => {
    resetPayment();
    resetBookingError();
    setLocalErrorMessage('');
    setFloorViolationMessage(null);
    goToStep(PaymentStep.METHOD_SELECTION);
  };

  // Show loading state while fetching payment methods
  if (isLoadingPaymentMethods) {
    return (
      <div className="w-full p-8 text-center">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 rounded w-48 mx-auto mb-4"></div>
          <div className="h-4 bg-gray-200 rounded w-32 mx-auto"></div>
        </div>
        <p className="text-gray-500 mt-4">Loading payment methods...</p>
      </div>
    );
  }

  return (
    <div className="w-full">
      {/* Show both payment selection and confirmation on same page when inline mode */}
      {showPaymentMethodInline && (currentStep === PaymentStep.METHOD_SELECTION || currentStep === PaymentStep.CONFIRMATION) ? (
        <div className="space-y-6">
          {/* Payment Method Selection at the top */}
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Select Payment Method</h2>
            <PaymentMethodSelection
              booking={updatedBookingData}
              cards={userCards}
              credits={userCredits}
              onSelectPayment={(method, cardId, credits) => {
                selectPaymentMethod(method, cardId, credits);
                // Automatically move to confirmation view when a payment method is selected
                if (currentStep === PaymentStep.METHOD_SELECTION) {
                  goToStep(PaymentStep.CONFIRMATION);
                }
              }}
              {...(onBack && { onBack })}
              onCardAdded={(newCard) => {
                // Add the new card to the list
                setUserCards([...userCards, newCard]);
              logger.info('New card added to list', { cardId: newCard.id });
              }}
            />
          </div>

          <div>
            {referralApplyPanel}
          </div>

          {/* Show confirmation details below if payment method is selected */}
          {currentStep === PaymentStep.CONFIRMATION && (
            <PaymentConfirmation
              booking={updatedBookingData}
              paymentMethod={paymentMethod!}
              {...(selectedCard?.last4 && { cardLast4: selectedCard.last4 })}
              {...(selectedCard?.brand && { cardBrand: selectedCard.brand })}
              {...(selectedCard?.isDefault !== undefined && { isDefaultCard: selectedCard.isDefault })}
              creditsUsed={creditSliderCents / 100}
              availableCredits={userCredits.totalAmount}
              {...(userCredits.earliestExpiry && { creditEarliestExpiry: userCredits.earliestExpiry })}
              promoApplied={promoApplied}
              onPromoStatusChange={setPromoApplied}
              referralAppliedCents={referralAppliedCents}
              referralActive={referralAppliedCents > 0}
              floorViolationMessage={floorViolationMessage}
              onClearFloorViolation={() => setFloorViolationMessage(null)}
              onConfirm={processPayment}
              onBack={() => goToStep(PaymentStep.METHOD_SELECTION)}
              onChangePaymentMethod={() => {
                setUserChangingPayment(true);
                // Don't change step, just let user select a different method above
              }}
              pricingPreview={pricingPreview}
              isPricingPreviewLoading={isPricingPreviewLoading}
              onCreditToggle={handleCreditToggle}
              onCreditAmountChange={handleCreditAmountChange}
            />
          )}
        </div>
      ) : (
        <>
          {/* Original step-by-step flow for non-inline mode */}
          {currentStep === PaymentStep.METHOD_SELECTION && (
            <PaymentMethodSelection
              booking={updatedBookingData}
              cards={userCards}
              credits={userCredits}
              onSelectPayment={selectPaymentMethod}
              {...(onBack && { onBack })}
              onCardAdded={(newCard) => {
                // Add the new card to the list
                setUserCards([...userCards, newCard]);
                logger.info('New card added to list', { cardId: newCard.id });
              }}
            />
          )}

          {(currentStep === PaymentStep.METHOD_SELECTION || currentStep === PaymentStep.CONFIRMATION) && (
            <div className="mt-6">
              {referralApplyPanel}
            </div>
          )}
          {currentStep === PaymentStep.CONFIRMATION && (
            <PaymentConfirmation
              booking={updatedBookingData}
              paymentMethod={paymentMethod!}
              {...(selectedCard?.last4 && { cardLast4: selectedCard.last4 })}
              {...(selectedCard?.brand && { cardBrand: selectedCard.brand })}
              {...(selectedCard?.isDefault !== undefined && { isDefaultCard: selectedCard.isDefault })}
              creditsUsed={creditSliderCents / 100}
              availableCredits={userCredits.totalAmount}
              {...(userCredits.earliestExpiry && { creditEarliestExpiry: userCredits.earliestExpiry })}
              promoApplied={promoApplied}
              onPromoStatusChange={setPromoApplied}
              referralAppliedCents={referralAppliedCents}
              referralActive={referralAppliedCents > 0}
              floorViolationMessage={floorViolationMessage}
              onClearFloorViolation={() => setFloorViolationMessage(null)}
              onConfirm={processPayment}
              onBack={() => goToStep(PaymentStep.METHOD_SELECTION)}
              onChangePaymentMethod={() => {
                setUserChangingPayment(true);
                goToStep(PaymentStep.METHOD_SELECTION);
              }}
              pricingPreview={pricingPreview}
              isPricingPreviewLoading={isPricingPreviewLoading}
              onCreditToggle={handleCreditToggle}
              onCreditAmountChange={handleCreditAmountChange}
            />
          )}
        </>
      )}
      {currentStep === PaymentStep.PROCESSING && (
        <PaymentProcessing
          amount={updatedBookingData.totalAmount - creditsToUse}
          bookingType={updatedBookingData.bookingType}
        />
      )}
      {currentStep === PaymentStep.SUCCESS && (
        <PaymentSuccess
          booking={updatedBookingData}
          confirmationNumber={confirmationNumber}
          {...(selectedCard?.last4 && { cardLast4: selectedCard.last4 })}
        />
      )}
      {currentStep === PaymentStep.ERROR && (
        <div className="p-8 text-center">
          <AlertCircle className="h-16 w-16 text-red-500 mx-auto mb-4" />
          <h2 className="text-2xl font-bold mb-2">
            {localErrorMessage?.includes('booking') || bookingError?.includes('booking')
              ? 'Booking Failed'
              : 'Payment Failed'}
          </h2>
          <p className="text-gray-600 dark:text-gray-400 mb-6">
            {localErrorMessage || paymentError || bookingError || 'An error occurred while processing your payment.'}
          </p>
          <button
            onClick={handleRetry}
            className="bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 mr-4"
          >
            Try Again
          </button>
          {onBack && (
            <button
              onClick={() => {
                resetPayment();
                onBack();
              }}
              className="text-gray-600 hover:text-gray-800"
            >
              Cancel
            </button>
          )}
        </div>
      )}
    </div>
  );
}
