'use client';

import { useState, useEffect } from 'react';
import { AlertCircle } from 'lucide-react';
import { BookingPayment, PaymentCard, CreditBalance, PaymentMethod } from '../types';
import { usePaymentFlow, PaymentStep } from '../hooks/usePaymentFlow';
import PaymentMethodSelection from './PaymentMethodSelection';
import PaymentConfirmation from './PaymentConfirmation';
import PaymentProcessing from './PaymentProcessing';
import PaymentSuccess from './PaymentSuccess';
import { logger } from '@/lib/logger';
import { useCreateBooking, calculateEndTime } from '@/features/student/booking';
import { paymentService } from '@/services/api/payments';
import { protectedApi } from '@/features/shared/api/client';

interface PaymentSectionProps {
  bookingData: BookingPayment & { metadata?: any };
  onSuccess: (confirmationNumber: string) => void;
  onError: (error: Error) => void;
  onBack?: () => void;
  showPaymentMethodInline?: boolean;
}

export function PaymentSection({ bookingData, onSuccess, onError, onBack, showPaymentMethodInline = false }: PaymentSectionProps) {
  const {
    createBooking,
    isLoading: isCreatingBooking,
    error: bookingError,
    reset: resetBookingError,
  } = useCreateBooking();

  const [confirmationNumber, setConfirmationNumber] = useState<string>('');
  const [updatedBookingData, setUpdatedBookingData] = useState<BookingPayment>(bookingData);
  const [localErrorMessage, setLocalErrorMessage] = useState<string>('');

  // Real payment data from backend
  const [userCards, setUserCards] = useState<PaymentCard[]>([]);
  const [userCredits, setUserCredits] = useState<CreditBalance>({
    totalAmount: 0,
    credits: [],
  });
  const [isLoadingPaymentMethods, setIsLoadingPaymentMethods] = useState(true);

  // Track selected card ID separately for payment processing
  const [selectedCardId, setSelectedCardId] = useState<string | undefined>();

  // Initialize payment flow
  const {
    currentStep,
    paymentMethod,
    selectedCard: selectedCardFromHook,
    creditsToUse,
    isProcessing,
    error: paymentError,
    goToStep,
    selectPaymentMethod: selectPaymentMethodOriginal,
    processPayment: processPaymentOriginal,
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
  const selectPaymentMethod = (method: PaymentMethod, cardId?: string, credits?: number) => {
    setSelectedCardId(cardId);
    setUserChangingPayment(false); // Reset flag when a new method is selected
    selectPaymentMethodOriginal(method, cardId, credits);
  };

  // Fetch real payment methods and credits from backend
  useEffect(() => {
    const fetchPaymentData = async () => {
      try {
        setIsLoadingPaymentMethods(true);

        // Check if we have an access token
        const token = localStorage.getItem('access_token');
        logger.info('Fetching payment data', {
          hasToken: !!token,
          tokenPreview: token ? token.substring(0, 20) + '...' : null
        });

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

    fetchPaymentData();
  }, []);

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
    // Set to processing state
    goToStep(PaymentStep.PROCESSING);

    try {
      // Get instructor ID and service ID from booking data (now strings/ULIDs)
      const instructorId = bookingData.instructorId;
      // Try to get serviceId from metadata first, otherwise use lessonType
      const serviceId = bookingData.metadata?.serviceId || bookingData.lessonType;

      // Format time to remove seconds if present
      const formattedStartTime = bookingData.startTime.split(':').slice(0, 2).join(':');
      const endTime = bookingData.endTime.split(':').slice(0, 2).join(':');
      const bookingDate =
        bookingData.date instanceof Date
          ? bookingData.date.toISOString().split('T')[0]
          : bookingData.date;

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
      const booking = await createBooking({
        instructor_id: instructorId,
        instructor_service_id: serviceId, // Changed to match backend schema
        booking_date: bookingDate,
        start_time: formattedStartTime,
        end_time: endTime,
        selected_duration: bookingData.duration,
      });

      if (!booking) {
        // Use the specific error message from the booking hook
        const errorMsg = bookingError || 'Failed to create booking';
        logger.error('Booking creation prevented', new Error(errorMsg), {
          bookingError,
          bookingData
        });
        throw new Error(errorMsg);
      }

      logger.info('Booking created successfully', {
        bookingId: booking.id,
        status: booking.status,
      });

      // Step 2: Process payment if there's an amount due
      const amountDue = bookingData.totalAmount - creditsToUse;

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
            // TODO: Handle 3D Secure authentication with Stripe Elements
            logger.warn('Payment requires additional authentication', {
              paymentIntentId: checkoutResult.payment_intent_id,
            });
            // For now, we'll treat this as an error
            throw new Error('Payment requires additional authentication. Please try a different card.');
          }

          if (checkoutResult.status !== 'succeeded' && checkoutResult.status !== 'processing') {
            throw new Error(`Payment failed with status: ${checkoutResult.status}`);
          }
        } else if (amountDue > 0) {
          // No payment method selected but payment is required
          throw new Error('Payment method required');
        }
      } catch (paymentError: any) {
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
        const errorMessage = paymentError?.message || 'Payment failed';
        if (errorMessage.includes('Instructor payment account not set up')) {
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
      let errorMessage = 'An error occurred while processing your payment.';
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
      {currentStep === PaymentStep.METHOD_SELECTION && (
        <PaymentMethodSelection
          booking={updatedBookingData}
          cards={userCards}
          credits={userCredits}
          onSelectPayment={selectPaymentMethod}
          onBack={onBack}
          onCardAdded={(newCard) => {
            // Add the new card to the list
            setUserCards([...userCards, newCard]);
            logger.info('New card added to list', { cardId: newCard.id });
          }}
        />
      )}
      {currentStep === PaymentStep.CONFIRMATION && (
        <PaymentConfirmation
          booking={updatedBookingData}
          paymentMethod={paymentMethod!}
          cardLast4={selectedCard?.last4}
          cardBrand={selectedCard?.brand}
          isDefaultCard={selectedCard?.isDefault}
          creditsUsed={creditsToUse}
          onConfirm={processPayment}
          onBack={() => goToStep(PaymentStep.METHOD_SELECTION)}
          onChangePaymentMethod={() => {
            setUserChangingPayment(true);
            goToStep(PaymentStep.METHOD_SELECTION);
          }}
        />
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
          cardLast4={selectedCard?.last4}
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
