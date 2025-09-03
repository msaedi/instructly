'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { PaymentSection } from '@/features/student/payment';
import { BookingPayment, PaymentStatus, BookingType } from '@/features/student/payment/types';
import { navigationStateManager } from '@/lib/navigation/navigationStateManager';
import { logger } from '@/lib/logger';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { at } from '@/lib/ts/safe';

export default function BookingConfirmationPage() {
  const [bookingData, setBookingData] = useState<BookingPayment | null>(null);
  const [serviceId, setServiceId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [paymentComplete, setPaymentComplete] = useState(false);
  const [confirmationNumber, setConfirmationNumber] = useState<string>('');
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  // Check authentication and redirect if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      // Store the current URL to return after login
      const returnUrl = '/student/booking/confirm';
      logger.info('User not authenticated, redirecting to login', { returnUrl });
      router.push(`/login?redirect=${encodeURIComponent(returnUrl)}`);
    }
  }, [authLoading, isAuthenticated, router]);

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
        setTimeout(() => router.push('/student/lessons'), 100);
      }
    } else {
      // Attempt to recover from reschedule flow
      const storedReschedule = sessionStorage.getItem('rescheduleData');
      if (storedReschedule) {
        try {
          const rd = JSON.parse(storedReschedule);

          // Parse display time like "8:00am" to 24h HH:MM:SS
          const toStartTime = (display: string): string => {
            const lower = String(display).toLowerCase();
            const core = lower.replace(/am|pm/g, '').trim();
            const [hh, mm] = core.split(':');
            let hour = parseInt(hh || '0', 10);
            const minute = parseInt(mm || '0', 10);
            const isPM = lower.includes('pm');
            const isAM = lower.includes('am');
            if (isPM && hour !== 12) hour += 12;
            if (isAM && hour === 12) hour = 0;
            return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:00`;
          };

          const startTime = toStartTime(rd.time);
          const parts = startTime.split(':');
          const sh = parseInt(at(parts, 0) || '0', 10);
          const sm = parseInt(at(parts, 1) || '0', 10);
          const duration = parseInt(String(rd.duration || 0), 10) || 0;
          const endTotal = sh * 60 + (sm || 0) + duration;
          const endHour = Math.floor(endTotal / 60);
          const endMinute = endTotal % 60;
          const endTime = `${String(endHour).padStart(2, '0')}:${String(endMinute).padStart(2, '0')}:00`;

          const basePrice = Math.round(((rd.hourlyRate || 0) * duration) / 60);
          const serviceFee = Math.round(basePrice * 0.1);
          const totalAmount = basePrice + serviceFee;

          const freeCancel = new Date(`${rd.date}T${startTime}`);
          if (!isNaN(freeCancel.getTime())) {
            freeCancel.setHours(freeCancel.getHours() - 24);
          }

          const paymentBooking: BookingPayment = {
            bookingId: '',
            instructorId: rd.instructorId,
            instructorName: rd.instructorName || 'Instructor',
            // Preserve service ULID for downstream API call
            // Also carry it on the top-level object for convenience
            // eslint-disable-next-line @typescript-eslint/ban-ts-comment
            // @ts-ignore
            serviceId: rd.serviceId,
            lessonType: rd.serviceName || 'Lesson',
            date: new Date(rd.date),
            startTime,
            endTime,
            duration,
            location: 'Online',
            basePrice,
            serviceFee,
            totalAmount,
            bookingType: BookingType.STANDARD,
            paymentStatus: PaymentStatus.PENDING,
            freeCancellationUntil: isNaN(freeCancel.getTime()) ? undefined : freeCancel,
          } as BookingPayment;

          setBookingData(paymentBooking);
          setServiceId(rd.serviceId || null);
          setIsLoading(false);
          return;
        } catch (e) {
          logger.error('[BOOKING CONFIRM] Failed to parse reschedule data', e as Error);
          setIsLoading(false);
          setTimeout(() => router.push('/student/lessons'), 100);
          return;
        }
      }

      // Redirect back if no booking data and no reschedule data
      setIsLoading(false);
      // Delay redirect to avoid React strict mode issues
      setTimeout(() => router.push('/student/lessons'), 100);
    }
  }, [bookingData, router]);

  const handlePaymentSuccess = (confirmationNum: string) => {
    // Set payment complete state
    setPaymentComplete(true);
    setConfirmationNumber(confirmationNum);

    // Clear all session storage after successful payment
    sessionStorage.removeItem('bookingData');
    sessionStorage.removeItem('serviceId');

    // Clear navigation state since booking is complete
    navigationStateManager.clearBookingFlow();

    // Redirect to dashboard after a delay
    setTimeout(() => {
      router.push('/student/lessons');
    }, 5000); // 5 seconds to show success message
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
        date: dateString || '',
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


  // Show loading while checking authentication
  if (authLoading) {
    return (
      <div className="min-h-screen">
        <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <Link className="inline-block" href="/">
              <h1 className="text-3xl font-bold text-[#6A0DAD] hover:text-[#6A0DAD] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
            </Link>
            <div className="pr-4">
              <div className="w-9 h-9 bg-gray-200 rounded-full animate-pulse"></div>
            </div>
          </div>
        </header>
        <div className="flex items-center justify-center pt-32">
          <div className="animate-pulse">
            <div className="h-8 bg-gray-200 rounded w-48 mb-4"></div>
            <div className="h-4 bg-gray-200 rounded w-32"></div>
          </div>
        </div>
      </div>
    );
  }

  // If not authenticated, don't render anything (redirect will happen)
  if (!isAuthenticated) {
    return null;
  }

  if (isLoading) {
    return (
      <div className="min-h-screen">
        {/* Header - matching search results page */}
        <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <Link className="inline-block" href="/">
              <h1 className="text-3xl font-bold text-[#6A0DAD] hover:text-[#6A0DAD] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
            </Link>
            <div className="pr-4">
              <UserProfileDropdown />
            </div>
          </div>
        </header>
        <div className="flex items-center justify-center pt-32">
          <div className="animate-pulse">
            <div className="h-8 bg-gray-200 rounded w-48 mb-4"></div>
            <div className="h-4 bg-gray-200 rounded w-32"></div>
          </div>
        </div>
      </div>
    );
  }

  if (!bookingData) {
    return (
      <div className="min-h-screen">
        {/* Header - matching search results page */}
        <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <Link href="/" className="inline-block">
              <h1 className="text-3xl font-bold text-[#6A0DAD] hover:text-[#6A0DAD] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
            </Link>
            <div className="pr-4">
              <UserProfileDropdown />
            </div>
          </div>
        </header>
        <div className="flex items-center justify-center pt-32">
          <div className="text-center">
            <h2 className="text-2xl font-bold text-gray-900 mb-4">
              No booking data found
            </h2>
            <button
              onClick={() => router.push('/student/lessons')}
              className="text-[#6A0DAD] hover:text-[#6A0DAD] hover:underline"
            >
              Back to My Lessons
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Show success view if payment is complete
  if (paymentComplete) {
    return (
      <div className="min-h-screen">
        {/* Header - matching search results page */}
        <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <Link href="/" className="inline-block">
              <h1 className="text-3xl font-bold text-[#6A0DAD] hover:text-[#6A0DAD] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
            </Link>
            <div className="pr-4">
              <UserProfileDropdown />
            </div>
          </div>
        </header>

        <div className="px-6 py-6">
          <div className="max-w-md mx-auto">
            <div className="bg-white/95 backdrop-blur-sm rounded-xl border border-gray-200 p-8 text-center">
              {/* Success Icon */}
              <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-6">
                <svg className="w-12 h-12 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>

              <h2 className="text-3xl font-bold text-gray-900 mb-4">Booking Confirmed!</h2>

              <p className="text-lg text-gray-600 mb-2">
                Your lesson with <span className="font-semibold">{bookingData?.instructorName}</span> is confirmed.
              </p>

              <p className="text-sm text-gray-500 mb-8">
                Confirmation #{confirmationNumber}
              </p>

              <div className="rounded-lg p-4 mb-8" style={{ backgroundColor: 'rgb(249, 247, 255)' }}>
                <p className="text-sm text-purple-800">
                  Check your email for booking details and instructor contact information.
                </p>
              </div>

              <div className="space-y-3">
                <button
                  onClick={() => router.push('/student/lessons')}
                  className="w-full bg-[#6A0DAD] text-white py-3 px-6 rounded-lg font-medium hover:bg-[#6A0DAD] transition-colors"
                >
                  View My Lessons
                </button>

                <button
                  onClick={() => router.push(bookingData?.instructorId ? `/instructors/${bookingData.instructorId}` : '/student/lessons')}
                  className="w-full bg-white text-[#6A0DAD] py-3 px-6 rounded-lg font-medium border-2 border-[#6A0DAD] hover:bg-purple-50 transition-colors"
                >
                  Book Another Lesson
                </button>
              </div>

              <p className="text-xs text-gray-500 mt-6">
                Redirecting to your lessons in 5 seconds...
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Header - matching search results page */}
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full">
          <Link className="inline-block" href="/">
            <h1 className="text-3xl font-bold text-[#6A0DAD] hover:text-[#6A0DAD] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
          </Link>
          <div className="pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      <div className="px-6 py-6">
        <div className="max-w-4xl mx-auto">
          {/* Payment Section - Full Width */}
          <PaymentSection
            bookingData={{
              ...bookingData,
              // Pass the service ID if needed
              metadata: { serviceId },
            }}
            onSuccess={handlePaymentSuccess}
            onError={handlePaymentError}
            onBack={handleBack}
            showPaymentMethodInline={true}
          />
        </div>
      </div>
    </div>
  );
}
