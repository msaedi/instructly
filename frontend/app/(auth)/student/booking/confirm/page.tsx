'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Calendar, Clock, MapPin, DollarSign, User } from 'lucide-react';
import { PaymentSection } from '@/features/student/payment';
import { BookingPayment } from '@/features/student/payment/types';
import { navigationStateManager } from '@/lib/navigation/navigationStateManager';
import { logger } from '@/lib/logger';

export default function BookingConfirmationPage() {
  const [bookingData, setBookingData] = useState<BookingPayment | null>(null);
  const [serviceId, setServiceId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    // Skip if already loaded
    if (bookingData) {
      return;
    }

    // Retrieve booking data from sessionStorage
    const storedData = sessionStorage.getItem('bookingData');
    const storedServiceId = sessionStorage.getItem('serviceId');


    if (storedData) {
      try {
        const parsedData = JSON.parse(storedData);
        setBookingData(parsedData);
        setServiceId(storedServiceId);

        setIsLoading(false);
      } catch (error) {
        logger.error('[BOOKING CONFIRM] Failed to parse booking data', error as Error);
        setIsLoading(false);
        // Delay redirect to avoid React strict mode issues
        setTimeout(() => router.push('/search'), 100);
      }
    } else {
      // Redirect back if no booking data
      setIsLoading(false);
      // Delay redirect to avoid React strict mode issues
      setTimeout(() => router.push('/search'), 100);
    }
  }, [bookingData, router]);

  const handlePaymentSuccess = (confirmationNumber: string) => {
    // Clear all session storage after successful payment
    sessionStorage.removeItem('bookingData');
    sessionStorage.removeItem('serviceId');

    // Clear navigation state since booking is complete
    navigationStateManager.clearBookingFlow();

    // The PaymentSection already handles redirect to dashboard
  };

  const handlePaymentError = (error: Error) => {
    logger.error('[BOOKING CONFIRM] Payment failed', error);
    // The PaymentSection component already shows error UI
    // We could add additional error handling here
  };

  const handleBack = () => {
    // Save the slot data before navigating back
    if (bookingData) {
      // Convert Date to string if needed
      const dateString = bookingData.date instanceof Date
        ? bookingData.date.toISOString().split('T')[0]
        : String(bookingData.date).split('T')[0];

      const bookingFlowData = {
        date: dateString,
        time: bookingData.startTime,
        duration: bookingData.duration,
        instructorId: bookingData.instructorId,
      };

      navigationStateManager.saveBookingFlow(bookingFlowData, 'payment');
    }

    // Only clear the booking data
    sessionStorage.removeItem('bookingData');
    sessionStorage.removeItem('serviceId');

    // Get instructor ID from booking data to navigate back
    if (bookingData?.instructorId) {
      // Navigate directly to instructor profile - state manager will restore slot
      const url = `/instructors/${bookingData.instructorId}`;
      router.push(url);
      return;
    }

    // Fallback: go back but skip auth pages
    const previousUrl = document.referrer;

    // If the referrer is a login page, go to home instead
    if (previousUrl && (previousUrl.includes('/login') || previousUrl.includes('/signin'))) {
      router.push('/');
    } else {
      router.back();
    }
  };

  const formatDate = (date: Date | string) => {
    const dateObj = typeof date === 'string' ? new Date(date) : date;
    return dateObj.toLocaleDateString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  const formatTime = (time: string) => {
    const [hours, minutes] = time.split(':');
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour % 12 || 12;
    return `${displayHour}:${minutes} ${ampm}`;
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-48 mb-4"></div>
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-32"></div>
        </div>
      </div>
    );
  }

  if (!bookingData) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
            No booking data found
          </h2>
          <button
            onClick={() => router.push('/search')}
            className="text-blue-600 dark:text-blue-400 hover:underline"
          >
            Back to search
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <div className="bg-white dark:bg-gray-800 shadow-sm border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <button
            onClick={handleBack}
            className="inline-flex items-center text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
            data-testid="payment-back-button"
          >
            <ArrowLeft className="h-5 w-5 mr-2" />
            Back
          </button>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-8">
          Complete Your Booking
        </h1>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Booking Details - Left Side */}
          <div className="lg:col-span-1">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 sticky top-8">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
                Booking Summary
              </h2>

              <div className="space-y-4">
                {/* Instructor */}
                <div className="flex items-start">
                  <User className="h-5 w-5 text-gray-500 dark:text-gray-400 mt-0.5 mr-3" />
                  <div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">Instructor</div>
                    <div className="font-medium text-gray-900 dark:text-white">
                      {bookingData.instructorName}
                    </div>
                  </div>
                </div>

                {/* Service */}
                <div className="flex items-start">
                  <div className="h-5 w-5 text-gray-500 dark:text-gray-400 mt-0.5 mr-3">📚</div>
                  <div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">Service</div>
                    <div className="font-medium text-gray-900 dark:text-white">
                      {bookingData.lessonType}
                    </div>
                  </div>
                </div>

                {/* Date */}
                <div className="flex items-start">
                  <Calendar className="h-5 w-5 text-gray-500 dark:text-gray-400 mt-0.5 mr-3" />
                  <div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">Date</div>
                    <div className="font-medium text-gray-900 dark:text-white">
                      {formatDate(bookingData.date)}
                    </div>
                  </div>
                </div>

                {/* Time */}
                <div className="flex items-start">
                  <Clock className="h-5 w-5 text-gray-500 dark:text-gray-400 mt-0.5 mr-3" />
                  <div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">Time</div>
                    <div className="font-medium text-gray-900 dark:text-white">
                      {formatTime(bookingData.startTime)} - {formatTime(bookingData.endTime)}
                    </div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">
                      {bookingData.duration} minutes
                    </div>
                  </div>
                </div>

                {/* Location */}
                <div className="flex items-start">
                  <MapPin className="h-5 w-5 text-gray-500 dark:text-gray-400 mt-0.5 mr-3" />
                  <div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">Location</div>
                    <div className="font-medium text-gray-900 dark:text-white">
                      {bookingData.location}
                    </div>
                  </div>
                </div>

                {/* Divider */}
                <hr className="border-gray-200 dark:border-gray-700" />

                {/* Pricing */}
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600 dark:text-gray-400">Base price</span>
                    <span className="text-gray-900 dark:text-white">
                      ${bookingData.basePrice.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600 dark:text-gray-400">Service fee</span>
                    <span className="text-gray-900 dark:text-white">
                      ${bookingData.serviceFee.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex justify-between font-semibold text-lg pt-2 border-t border-gray-200 dark:border-gray-700">
                    <span className="text-gray-900 dark:text-white">Total</span>
                    <span className="text-blue-600 dark:text-blue-400">
                      ${bookingData.totalAmount.toFixed(2)}
                    </span>
                  </div>
                </div>

                {/* Cancellation Policy */}
                {bookingData.freeCancellationUntil && (
                  <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 mt-4">
                    <p className="text-sm text-blue-800 dark:text-blue-300">
                      Free cancellation until {formatDate(bookingData.freeCancellationUntil)} at{' '}
                      {formatTime(
                        new Date(bookingData.freeCancellationUntil).toTimeString().slice(0, 5)
                      )}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Payment Section - Right Side */}
          <div className="lg:col-span-2">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
              <PaymentSection
                bookingData={{
                  ...bookingData,
                  // Pass the service ID if needed
                  metadata: { serviceId },
                }}
                onSuccess={handlePaymentSuccess}
                onError={handlePaymentError}
                onBack={handleBack}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
