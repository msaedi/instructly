'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertCircle } from 'lucide-react';
import { BookingPayment, PaymentCard, CreditBalance } from '../types';
import { usePaymentFlow, PaymentStep } from '../hooks/usePaymentFlow';
import { PaymentMethodSelection } from './PaymentMethodSelection';
import { PaymentConfirmation } from './PaymentConfirmation';
import { PaymentProcessing } from './PaymentProcessing';
import { PaymentSuccess } from './PaymentSuccess';
import { logger } from '@/lib/logger';
import { useCreateBooking, calculateEndTime } from '@/features/student/booking';

interface PaymentSectionProps {
  bookingData: BookingPayment;
  onSuccess: (confirmationNumber: string) => void;
  onError: (error: Error) => void;
  onBack?: () => void;
}

export function PaymentSection({ bookingData, onSuccess, onError, onBack }: PaymentSectionProps) {
  const router = useRouter();
  const {
    createBooking,
    isLoading: isCreatingBooking,
    error: bookingError,
    reset: resetBookingError,
  } = useCreateBooking();

  const [confirmationNumber, setConfirmationNumber] = useState<string>('');
  const [updatedBookingData, setUpdatedBookingData] = useState<BookingPayment>(bookingData);

  // Mock payment data - replace with actual API calls
  const [userCards] = useState<PaymentCard[]>([
    {
      id: '1',
      last4: '4242',
      brand: 'Visa',
      expiryMonth: 12,
      expiryYear: 2025,
      isDefault: true,
    },
  ]);
  const [userCredits] = useState<CreditBalance>({
    totalAmount: 0,
    credits: [],
  });

  // Initialize payment flow
  const {
    currentStep,
    paymentMethod,
    selectedCard,
    creditsToUse,
    isProcessing,
    error: paymentError,
    goToStep,
    selectPaymentMethod,
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

  // Override processPayment to create booking during payment
  const processPayment = async () => {
    // Set to processing state
    goToStep(PaymentStep.PROCESSING);

    try {
      // Parse instructor ID and service ID from booking data
      const instructorId = parseInt(bookingData.instructorId);
      const serviceId = parseInt(bookingData.lessonType); // This might need adjustment based on actual data structure

      // Format time to remove seconds if present
      const formattedStartTime = bookingData.startTime.split(':').slice(0, 2).join(':');
      const endTime = bookingData.endTime.split(':').slice(0, 2).join(':');
      const bookingDate =
        bookingData.date instanceof Date
          ? bookingData.date.toISOString().split('T')[0]
          : bookingData.date;

      // Create booking via API
      const booking = await createBooking({
        instructor_id: instructorId,
        service_id: serviceId, // You may need to pass this through bookingData
        booking_date: bookingDate,
        start_time: formattedStartTime,
        end_time: endTime,
      });

      if (booking) {
        logger.info('Booking created successfully', {
          bookingId: booking.id,
          status: booking.status,
        });

        // Update booking data with actual booking ID
        const updatedData = { ...updatedBookingData, bookingId: String(booking.id) };
        setUpdatedBookingData(updatedData);
        const confirmationNum = `B${booking.id}`;
        setConfirmationNumber(confirmationNum);

        // Move to success state
        goToStep(PaymentStep.SUCCESS);

        // Call success callback
        onSuccess(confirmationNum);

        // After a delay, redirect to dashboard
        setTimeout(() => {
          router.push('/dashboard/student/bookings');
        }, 3000);
      } else {
        throw new Error(bookingError || 'Failed to create booking');
      }
    } catch (error) {
      logger.error('Booking creation failed', error as Error);
      goToStep(PaymentStep.ERROR);
      onError(error as Error);
    }
  };

  // Handle error retry
  const handleRetry = () => {
    resetPayment();
    resetBookingError();
    goToStep(PaymentStep.METHOD_SELECTION);
  };

  return (
    <div className="w-full">
      {currentStep === PaymentStep.METHOD_SELECTION && (
        <PaymentMethodSelection
          booking={updatedBookingData}
          cards={userCards}
          credits={userCredits}
          onSelectPayment={selectPaymentMethod}
          onAddCard={() => {
            // TODO: Implement add card flow
            alert('Add card functionality coming soon');
          }}
        />
      )}
      {currentStep === PaymentStep.CONFIRMATION && (
        <PaymentConfirmation
          booking={updatedBookingData}
          paymentMethod={paymentMethod!}
          cardLast4={selectedCard?.last4}
          creditsUsed={creditsToUse}
          onConfirm={processPayment}
          onBack={() => goToStep(PaymentStep.METHOD_SELECTION)}
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
          <h2 className="text-2xl font-bold mb-2">Payment Failed</h2>
          <p className="text-gray-600 dark:text-gray-400 mb-6">
            {paymentError || bookingError || 'An error occurred while processing your payment.'}
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
