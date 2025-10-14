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
import { PricingPreviewContext, usePricingPreviewController } from '../hooks/usePricingPreview';
import CheckoutApplyReferral from '@/components/referrals/CheckoutApplyReferral';
import { buildCreateBookingPayload } from '../utils/buildCreateBookingPayload';
import {
  buildPricingPreviewQuotePayload,
  type PricingPreviewSelection,
} from '../utils/buildPricingPreviewQuotePayload';
import { to24HourTime } from '@/lib/time';
import { minutesSinceHHMM } from '@/lib/time/overlap';

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

const logDevInfo = (...args: Parameters<typeof logger.info>) => {
  if (process.env.NODE_ENV !== 'production') {
    logger.info(...args);
  }
};

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

type BookingWithMetadata = BookingPayment & { metadata?: Record<string, unknown> };

const mergeBookingIntoPayment = (booking: Booking, fallback: BookingWithMetadata): BookingWithMetadata => {
  const durationMinutes = booking.duration_minutes ?? fallback.duration;
  const hourlyRate = normalizeCurrency(booking.hourly_rate, fallback.basePrice);
  const computedBase = durationMinutes
    ? Number(((hourlyRate * durationMinutes) / 60).toFixed(2))
    : fallback.basePrice;
  const totalAmount = normalizeCurrency(booking.total_price, fallback.totalAmount);

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
    totalAmount,
    metadata: {
      ...(fallback.metadata ?? {}),
      ...(booking as unknown as { metadata?: Record<string, unknown> }).metadata,
    },
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
  const [updatedBookingData, setUpdatedBookingData] = useState<BookingWithMetadata>(bookingData);
  const [localErrorMessage, setLocalErrorMessage] = useState<string>('');
  const [floorViolationMessage, setFloorViolationMessage] = useState<string | null>(null);
  const [referralAppliedCents, setReferralAppliedCents] = useState(0);
  const [promoApplied, setPromoApplied] = useState(false);
  const [creditSliderCents, setCreditSliderCents] = useState(0);
  const [lastSuccessfulCreditCents, setLastSuccessfulCreditCents] = useState(0);
  const resolvedInstructorId = useMemo(() => {
    const candidate =
      (updatedBookingData.instructorId ?? bookingData.instructorId ?? null);
    return typeof candidate === 'string' ? candidate : candidate != null ? String(candidate) : null;
  }, [updatedBookingData.instructorId, bookingData.instructorId]);

  const resolvedServiceId = useMemo(() => {
    const metadataService =
      (updatedBookingData.metadata?.['serviceId'] ?? bookingData.metadata?.['serviceId']) ??
      bookingData.serviceId ?? null;
    if (metadataService === null || metadataService === undefined) {
      return null;
    }
    return typeof metadataService === 'string' ? metadataService : String(metadataService);
  }, [updatedBookingData.metadata, bookingData.metadata, bookingData.serviceId]);

  const mergedMetadata = useMemo(
    () => ({
      ...(bookingData.metadata ?? {}),
      ...(updatedBookingData.metadata ?? {}),
    }) as Record<string, unknown>,
    [bookingData.metadata, updatedBookingData.metadata],
  );

  const quoteSelection = useMemo<PricingPreviewSelection | null>(() => {
    if (!resolvedInstructorId) {
      logDevInfo('[pricing-preview] Missing instructor ID', {
        bookingId: bookingData.bookingId,
        updatedBookingId: updatedBookingData.bookingId,
      });
      return null;
    }

    let effectiveServiceId = resolvedServiceId;
    if (!effectiveServiceId && typeof window !== 'undefined') {
      const stored = window.sessionStorage?.getItem('serviceId');
      effectiveServiceId = stored && stored.trim().length > 0 ? stored : null;
    }
    if (!effectiveServiceId) {
      logDevInfo('[pricing-preview] Missing service ID', {
        resolvedServiceId,
        metadata: mergedMetadata,
        sessionStorageServiceId: typeof window !== 'undefined' ? window.sessionStorage?.getItem('serviceId') : null,
      });
      return null;
    }

    let bookingDateValue = updatedBookingData.date ?? bookingData.date;

    // Try to recover date from sessionStorage if missing
    if (!bookingDateValue && typeof window !== 'undefined') {
      try {
        const storedBooking = window.sessionStorage?.getItem('bookingData');
        if (storedBooking) {
          const parsed = JSON.parse(storedBooking);
          bookingDateValue = parsed.date;
        }
      } catch {
        // Ignore parse errors
      }
    }

    if (!bookingDateValue) {
      logDevInfo('[pricing-preview] Missing booking date', {
        bookingId: bookingData.bookingId,
        updatedBookingId: updatedBookingData.bookingId,
        sessionStorage: typeof window !== 'undefined' ? window.sessionStorage?.getItem('bookingData') : 'N/A'
      });
      return null;
    }

    let bookingDateLocal: string;
    try {
      bookingDateLocal = toDateOnlyString(bookingDateValue, 'pricing-preview.booking-date');
    } catch (error) {
      logger.debug('pricing-preview:quote-date-error', error);
      logDevInfo('[pricing-preview] Date conversion error', { bookingDateValue, error });
      return null;
    }

    const startTimeValue = updatedBookingData.startTime ?? bookingData.startTime;
    if (!startTimeValue) {
      logDevInfo('[pricing-preview] Missing start time', {
        bookingId: bookingData.bookingId,
        updatedBookingId: updatedBookingData.bookingId,
      });
      return null;
    }

    let startHHMM24: string;
    try {
      const timeStr = String(startTimeValue);
      // If already in HH:MM:SS format, extract HH:MM
      if (/^\d{2}:\d{2}:\d{2}$/.test(timeStr)) {
        startHHMM24 = timeStr.slice(0, 5);
      } else {
        startHHMM24 = to24HourTime(timeStr);
      }
    } catch (error) {
      logger.debug('pricing-preview:quote-start-time-error', error);
      logDevInfo('[pricing-preview] Time conversion error', {
        startTimeValue,
        error,
        expectedFormat: 'HH:MM (24hr) or H:MMam/pm'
      });
      return null;
    }

    const resolveDuration = (): number => {
      const candidates = [
        updatedBookingData.duration,
        bookingData.duration,
        mergedMetadata['duration'],
        mergedMetadata['duration_minutes'],
      ];

      for (const candidate of candidates) {
        if (typeof candidate === 'number' && candidate > 0) {
          return Math.round(candidate);
        }
        if (typeof candidate === 'string') {
          const parsed = Number(candidate);
          if (Number.isFinite(parsed) && parsed > 0) {
            return Math.round(parsed);
          }
        }
      }

      const endTimeValue = updatedBookingData.endTime ?? bookingData.endTime;
      if (endTimeValue) {
        try {
          const startMinutes = minutesSinceHHMM(to24HourTime(String(startTimeValue)));
          const endMinutes = minutesSinceHHMM(to24HourTime(String(endTimeValue)));
          const diff = endMinutes - startMinutes;
          if (diff > 0) {
            return diff;
          }
        } catch (error) {
          logger.debug('pricing-preview:unable-to-derive-duration', error);
        }
      }

      return 0;
    };

    const durationMinutes = resolveDuration();
    if (durationMinutes <= 0) {
      return null;
    }

    const rawLocation = (updatedBookingData.location ?? bookingData.location ?? '').toString().trim();
    const meetingLocation = rawLocation || 'Student provided address';
    const metadataModality = String(mergedMetadata['modality'] ?? '').trim().toLowerCase();
    const isRemoteMetadata = metadataModality === 'remote' || metadataModality === 'online';
    const isRemoteLocation = /online|remote|virtual/i.test(meetingLocation);
    const isRemote = isRemoteMetadata || isRemoteLocation;

    const allowedModalities: PricingPreviewSelection['modality'][] = [
      'remote',
      'in_person',
      'student_home',
      'instructor_location',
      'neutral',
    ];
    const normalizedModality = (allowedModalities.find((value) => value === metadataModality) ??
      (isRemote ? 'remote' : 'in_person')) as PricingPreviewSelection['modality'];

    const selection = {
      instructorId: resolvedInstructorId,
      instructorServiceId: effectiveServiceId,
      bookingDateLocalYYYYMMDD: bookingDateLocal,
      startHHMM24,
      selectedDurationMinutes: durationMinutes,
      modality: normalizedModality,
      meetingLocation: isRemote ? 'Online' : meetingLocation,
      appliedCreditCents: Math.max(0, Math.round(creditSliderCents)),
    };

    logDevInfo('[pricing-preview] Quote selection built', selection);

    return selection;
  }, [
    resolvedInstructorId,
    resolvedServiceId,
    updatedBookingData.date,
    bookingData.date,
    updatedBookingData.startTime,
    bookingData.startTime,
    updatedBookingData.endTime,
    bookingData.endTime,
    updatedBookingData.duration,
    bookingData.duration,
    updatedBookingData.location,
    bookingData.location,
    mergedMetadata,
    creditSliderCents,
    bookingData.bookingId,
    updatedBookingData.bookingId,
  ]);

  const quotePayload = useMemo(
    () => (quoteSelection ? buildPricingPreviewQuotePayload(quoteSelection) : null),
    [quoteSelection],
  );

  const previewController = usePricingPreviewController({
    bookingId: bookingData.bookingId || updatedBookingData.bookingId || null,
    quotePayload,
  });
  const {
    preview: pricingPreview,
    applyCredit: applyCreditPreview,
    lastAppliedCreditCents,
  } = previewController;
  const bookingDraftId = useMemo(
    () => updatedBookingData.bookingId || bookingData.bookingId || null,
    [updatedBookingData.bookingId, bookingData.bookingId],
  );
  const lastCommittedCreditRef = useRef<number>(lastAppliedCreditCents);

  useEffect(() => {
    lastCommittedCreditRef.current = lastAppliedCreditCents;
  }, [lastAppliedCreditCents]);

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
      logDevInfo('Payment successful', { bookingId });
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

    // Exit early if no change needed
    if (currentCreditCents === normalizedCreditCents) {
      return;
    }

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

  const handleBookingUpdate = useCallback(
    (updater: (prev: BookingWithMetadata) => BookingWithMetadata) => {
      setUpdatedBookingData((prev) => updater({
        ...prev,
        metadata: { ...(prev.metadata ?? {}) },
      }));
    },
    []
  );

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

  const commitCreditPreview = useCallback(async (creditCents: number) => {
    const normalizedCreditCents = Math.max(0, Math.round(creditCents));

    try {
      await applyCreditPreview(normalizedCreditCents);
      if (floorViolationMessage !== null) {
        setFloorViolationMessage(null);
      }
    } catch (error) {
      const maybeProblemError = error as ApiProblemError;
      const status = maybeProblemError?.response?.status;

      if (status === 422) {
        const detail = maybeProblemError?.problem?.detail ?? 'Price must meet minimum requirements.';
        setFloorViolationMessage(detail);
        logDevInfo('pricing-floor-violation', {
          bookingId: bookingDraftId,
          requestedCreditCents: normalizedCreditCents,
        });
      } else {
        logger.error('Failed to fetch pricing preview', error as Error, {
          bookingId: bookingDraftId,
          requestedCreditCents: normalizedCreditCents,
        });
        setLocalErrorMessage('Unable to refresh pricing preview. Please try again.');
      }

      const fallbackCents = lastSuccessfulCreditCents;
      setCreditSliderCents(fallbackCents);
      updateCreditSelection(fallbackCents, getTotalDueCents());
      lastCommittedCreditRef.current = fallbackCents;
    }
  }, [
    applyCreditPreview,
    bookingDraftId,
    floorViolationMessage,
    getTotalDueCents,
    lastSuccessfulCreditCents,
    updateCreditSelection,
  ]);

  const handleCreditCommitCents = useCallback((creditCents: number) => {
    const normalizedCreditCents = Math.max(0, Math.round(creditCents));
    if (normalizedCreditCents === lastCommittedCreditRef.current) {
      return;
    }
    lastCommittedCreditRef.current = normalizedCreditCents;
    void commitCreditPreview(normalizedCreditCents);
  }, [commitCreditPreview]);

  const handleCreditToggle = useCallback(() => {
    const totalDueCents = getTotalDueCents();
    if (creditSliderCents > 0) {
      const nextCents = 0;
      setCreditSliderCents(nextCents);
      updateCreditSelection(nextCents, totalDueCents);
      handleCreditCommitCents(nextCents);
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
    handleCreditCommitCents(targetCents);
  }, [creditSliderCents, getTotalDueCents, updateCreditSelection, userCredits.totalAmount, floorViolationMessage, handleCreditCommitCents]);

  const handleCreditAmountChange = useCallback((amountDollars: number) => {
    const totalDueCents = getTotalDueCents();
    const requestedCents = Math.max(0, Math.round(amountDollars * 100));
    const clampedCents = Math.min(requestedCents, totalDueCents);

    // Skip if no actual change
    if (creditSliderCents === clampedCents) {
      return;
    }

    if (floorViolationMessage && clampedCents < lastSuccessfulCreditCents) {
      setFloorViolationMessage(null);
    }
    setCreditSliderCents(clampedCents);
    updateCreditSelection(clampedCents, totalDueCents);
    handleCreditCommitCents(clampedCents);
  }, [
    getTotalDueCents,
    updateCreditSelection,
    floorViolationMessage,
    lastSuccessfulCreditCents,
    creditSliderCents,
    handleCreditCommitCents,
  ]);

  useEffect(() => {
    if (!pricingPreview) {
      return;
    }

    const previewCredits = Math.max(0, pricingPreview.credit_applied_cents);

    // Only update if actually changed
    if (lastSuccessfulCreditCents !== previewCredits) {
      setLastSuccessfulCreditCents(previewCredits);
    }

    setCreditSliderCents((prev) => (prev === previewCredits ? prev : previewCredits));

    setUpdatedBookingData((prev) => {
      const newBasePrice = pricingPreview.base_price_cents / 100;
      const newTotalAmount = (pricingPreview.student_pay_cents + previewCredits) / 100;

      // Only update if values actually changed
      if (prev.basePrice === newBasePrice && prev.totalAmount === newTotalAmount) {
        return prev;
      }

      return {
        ...prev,
        basePrice: newBasePrice,
        totalAmount: newTotalAmount,
      };
    });

    const totalDueCents = pricingPreview.student_pay_cents + previewCredits;
    const currentCreditCents = Math.max(0, Math.round(creditsToUse * 100));
    // Only update if significantly different (avoid floating point issues)
    if (Math.abs(currentCreditCents - previewCredits) > 0.01) {
      updateCreditSelection(previewCredits, totalDueCents);
    }
  }, [pricingPreview, creditsToUse, updateCreditSelection, lastSuccessfulCreditCents]);

  // Fetch real payment methods and credits from backend
  useEffect(() => {
    const fetchPaymentData = async () => {
      try {
        setIsLoadingPaymentMethods(true);

        logDevInfo('Fetching payment data');

        // Fetch payment methods
        const methods = await paymentService.listPaymentMethods();
        logDevInfo('Payment methods response', { methods });

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
        logDevInfo('Credit balance response', { balance });

        setUserCredits({
          totalAmount: balance.available || 0,
          credits: [], // Credits detail not implemented yet
          earliestExpiry: balance.expires_at || null,
        });

        logDevInfo('Successfully loaded payment data', {
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

    // Disable auto-apply for now to prevent loops
    // const totalDueDollars = getTotalDueCents() / 100;
    // const amountToApply = Math.min(userCredits.totalAmount || 0, totalDueDollars);
    // if (amountToApply <= 0) return;

    // selectPaymentMethod(PaymentMethod.MIXED, effectiveCardId, amountToApply);
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
      // Get instructor ID and service ID from booking data (now strings/ULIDs)
      const instructorId = String(bookingData.instructorId || '');
      // Prefer explicit serviceId (ULID) from metadata; as a fallback, try bookingData.serviceId
      const serviceId = String((bookingData.metadata?.['serviceId'] || bookingData.serviceId) ?? '');

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
      logDevInfo('Preparing booking request', {
        instructorId,
        serviceId,
        bookingDate,
        startTime: bookingData.startTime,
        endTime: bookingData.endTime,
        duration: bookingData.duration,
        metadata: bookingData.metadata,
        lessonType: bookingData.lessonType,
        fullBookingData: bookingData,
      });

      // Step 1: Create booking via API
      requireString(bookingDate, 'bookingDate');
      requireString(instructorId, 'instructorId');
      requireString(serviceId, 'serviceId');
      const bookingPayload = buildCreateBookingPayload({
        instructorId,
        serviceId,
        bookingDate,
        booking: {
          ...bookingData,
          ...updatedBookingData,
          metadata: {
            ...(bookingData.metadata ?? {}),
            ...(updatedBookingData.metadata ?? {}),
          },
        },
      });

      logDevInfo('Submitting booking payload', bookingPayload);

      const booking = await createBooking(bookingPayload);

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

      logDevInfo('Booking created successfully', {
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

          logDevInfo('Payment processed', {
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
          logDevInfo('Booking cancelled after payment failure', { bookingId: booking.id });
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
      <PricingPreviewContext.Provider value={previewController}>
        <div className="w-full p-8 text-center">
          <div className="animate-pulse">
            <div className="h-8 bg-gray-200 rounded w-48 mx-auto mb-4"></div>
            <div className="h-4 bg-gray-200 rounded w-32 mx-auto"></div>
          </div>
          <p className="text-gray-500 mt-4">Loading payment methods...</p>
        </div>
      </PricingPreviewContext.Provider>
    );
  }

  return (
    <PricingPreviewContext.Provider value={previewController}>
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
              logDevInfo('New card added to list', { cardId: newCard.id });
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
              onCreditToggle={handleCreditToggle}
              onCreditAmountChange={handleCreditAmountChange}
              onBookingUpdate={handleBookingUpdate}
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
                logDevInfo('New card added to list', { cardId: newCard.id });
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
              onCreditToggle={handleCreditToggle}
              onCreditAmountChange={handleCreditAmountChange}
              onBookingUpdate={handleBookingUpdate}
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
    </PricingPreviewContext.Provider>
  );
}
