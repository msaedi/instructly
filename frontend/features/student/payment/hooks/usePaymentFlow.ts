'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { BookingPayment, PaymentMethod, PaymentCard, PAYMENT_STATUS } from '../types';
import type { PaymentProcessResponse } from '@/features/shared/api/types';

interface UsePaymentFlowProps {
  booking: BookingPayment;
  onSuccess?: (bookingId: string) => void;
  onError?: (error: Error) => void;
}

interface UsePaymentFlowReturn {
  currentStep: PaymentStep;
  paymentMethod: PaymentMethod | null;
  selectedCard: PaymentCard | null;
  creditsToUse: number;
  isProcessing: boolean;
  error: string | null;

  goToStep: (step: PaymentStep) => void;
  selectPaymentMethod: (method: PaymentMethod, cardId?: string, credits?: number) => void;
  processPayment: () => Promise<void>;
  reset: () => void;
}

export enum PaymentStep {
  METHOD_SELECTION = 'method_selection',
  CONFIRMATION = 'confirmation',
  PROCESSING = 'processing',
  SUCCESS = 'success',
  ERROR = 'error',
}

export function usePaymentFlow({
  booking,
  onSuccess,
  onError,
}: UsePaymentFlowProps): UsePaymentFlowReturn {
  const router = useRouter();
  const [currentStep, setCurrentStep] = useState<PaymentStep>(PaymentStep.METHOD_SELECTION);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod | null>(null);
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  const [creditsToUse, setCreditsToUse] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const goToStep = useCallback((step: PaymentStep) => {
    setCurrentStep(step);
    setError(null);
  }, []);

  const selectPaymentMethod = useCallback(
    (method: PaymentMethod, cardId?: string, credits: number = 0) => {
      setPaymentMethod(method);
      if (cardId) {
        setSelectedCardId(cardId);
      }
      setCreditsToUse(credits);
      goToStep(PaymentStep.CONFIRMATION);
    },
    [goToStep]
  );

  const processPayment = useCallback(async () => {
    if (!paymentMethod) {
      setError('No payment method selected');
      return;
    }

    setIsProcessing(true);
    goToStep(PaymentStep.PROCESSING);

    try {
      // Simulate API call - replace with actual Stripe integration
      const response = await fetch('/api/v1/payments/process', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          bookingId: booking.bookingId,
          paymentMethod,
          cardId: selectedCardId,
          creditsToUse,
          amount: booking.totalAmount - creditsToUse,
          captureMethod: booking.bookingType === 'last_minute' ? 'automatic' : 'manual',
        }),
      });

      if (!response.ok) {
        throw new Error('Payment processing failed');
      }

      const result = (await response.json()) as PaymentProcessResponse;

      // Update booking with payment info
      booking.paymentStatus = PAYMENT_STATUS.AUTHORIZED;
      booking.stripeIntentId = result.paymentIntentId;

      goToStep(PaymentStep.SUCCESS);

      if (onSuccess) {
        onSuccess(booking.bookingId);
      }

      // Redirect to dashboard after 3 seconds
      setTimeout(() => {
        router.push('/student/lessons');
      }, 3000);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Payment failed';
      setError(errorMessage);
      goToStep(PaymentStep.ERROR);

      if (onError) {
        onError(err instanceof Error ? err : new Error(errorMessage));
      }
    } finally {
      setIsProcessing(false);
    }
  }, [booking, paymentMethod, selectedCardId, creditsToUse, goToStep, onSuccess, onError, router]);

  const reset = useCallback(() => {
    setCurrentStep(PaymentStep.METHOD_SELECTION);
    setPaymentMethod(null);
    setSelectedCardId(null);
    setCreditsToUse(0);
    setError(null);
    setIsProcessing(false);
  }, []);

  // Mock data - replace with actual data fetching
  const selectedCard = selectedCardId
    ? {
        id: selectedCardId,
        last4: '4242',
        brand: 'Visa',
        expiryMonth: 12,
        expiryYear: 2025,
        isDefault: true,
      }
    : null;

  return {
    currentStep,
    paymentMethod,
    selectedCard,
    creditsToUse,
    isProcessing,
    error,
    goToStep,
    selectPaymentMethod,
    processPayment,
    reset,
  };
}
