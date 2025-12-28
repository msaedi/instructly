// frontend/features/student/booking/components/BookingModalWithPayment.tsx
// This is an enhanced version of BookingModal that integrates payment flow
'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { X, MapPin, Clock, DollarSign, ChevronLeft } from 'lucide-react';
import { BookingModalProps, Service } from '../types';
import { logger } from '@/lib/logger';
import { at } from '@/lib/ts/safe';
import { formatFullName } from '@/utils/nameDisplay';
import { getServiceAreaBoroughs, getServiceAreaDisplay } from '@/lib/profileServiceAreas';
import { useAuth } from '../hooks/useAuth';
import { storeBookingIntent, calculateEndTime } from '@/features/shared/utils/booking';
import CheckoutFlow from '@/components/booking/CheckoutFlow';
import { BookingPayment, PAYMENT_STATUS } from '@/features/student/payment/types';
import { BookingType } from '@/features/shared/types/booking';
import { determineBookingType } from '@/features/shared/utils/paymentCalculations';

// Define the Booking interface for pending booking
interface PendingBooking {
  id: string;
  service_name: string;
  instructor_name: string;
  instructor_id: string;
  booking_date: string;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  hourly_rate: number;
  total_price: number;
}

type ModalStep = 'select-time' | 'booking-details' | 'payment' | 'success';

export default function BookingModalWithPayment({
  isOpen,
  onClose,
  instructor,
  selectedDate,
  selectedTime,
}: BookingModalProps) {
  const router = useRouter();
  const { user, isAuthenticated, redirectToLogin } = useAuth();
  const [currentStep, setCurrentStep] = useState<ModalStep>('select-time');
  const [selectedService, setSelectedService] = useState<Service | null>(null);
  const [duration, setDuration] = useState(60); // Default to 60 minutes
  const [totalPrice, setTotalPrice] = useState(0);
  const [showBookingForm, setShowBookingForm] = useState(false);
  const [pendingBooking, setPendingBooking] = useState<PendingBooking | null>(null);
  const [bookingFormData, setBookingFormData] = useState({
    name: '',
    email: '',
    phone: '',
    notes: '',
    agreedToTerms: false,
  });
  const serviceAreaBoroughs = getServiceAreaBoroughs(instructor);
  const serviceAreaDisplayFull = getServiceAreaDisplay(instructor) || 'NYC';
  const primaryServiceArea = serviceAreaBoroughs[0] ?? serviceAreaDisplayFull;

  // Initialize with first service if multiple, or use the only service
  useEffect(() => {
    if (instructor.services.length > 0 && !selectedService) {
      const firstService = at(instructor.services, 0);
      if (firstService) {
        setSelectedService(firstService);
        setDuration(firstService.duration);
        setTotalPrice(firstService.hourly_rate * (firstService.duration / 60));
      }
    }
  }, [instructor.services, selectedService]);

  // Pre-fill form with user data if authenticated
  useEffect(() => {
    if (user && showBookingForm) {
      setBookingFormData((prev) => ({
        ...prev,
        name: formatFullName(user) || '',
        email: user.email || '',
      }));
    }
  }, [user, showBookingForm]);

  // Reset modal state when it opens
  useEffect(() => {
    if (isOpen) {
      setCurrentStep('select-time');
      setPendingBooking(null);

      // Set initial service if not set
      if (!selectedService && instructor.services.length > 0) {
        const firstService = at(instructor.services, 0);
        if (firstService) {
          setSelectedService(firstService);
          setDuration(firstService.duration);
        }
      }

      // For authenticated users, show the booking form directly
      if (isAuthenticated) {
        setShowBookingForm(true);
      } else {
        setShowBookingForm(false);
      }

      // Reset form data
      setBookingFormData({
        name: user?.full_name || '',
        email: user?.email || '',
        phone: '',
        notes: '',
        agreedToTerms: false,
      });
    }
  }, [isOpen, isAuthenticated, instructor.services, selectedService, user?.full_name, user?.email]);

  // Update price when service or duration changes
  useEffect(() => {
    if (selectedService) {
      const rateRaw = (selectedService.hourly_rate as unknown);
      const rateNum = typeof rateRaw === 'number' ? rateRaw : parseFloat(String(rateRaw ?? '0'));
      const safeRate = Number.isNaN(rateNum) ? 0 : rateNum;
      const hours = duration / 60;
      setTotalPrice(safeRate * hours);
    }
  }, [selectedService, duration]);

  const handleContinueToBooking = () => {
    if (!isAuthenticated) {
      // Store booking intent and redirect to login
      const bookingDate = new Date(selectedDate + 'T' + selectedTime);
      const basePrice = totalPrice;
      const totalAmount = basePrice;
      const bookingType = determineBookingType(bookingDate);

      const paymentBookingData: BookingPayment = {
        bookingId: '',
        instructorId: String(instructor.user_id),
        instructorName: `${instructor.user.first_name} ${instructor.user.last_initial}.`,
        lessonType: selectedService!.skill,
        date: bookingDate,
        startTime: selectedTime,
        endTime: calculateEndTime(selectedTime, duration),
        duration,
        location: primaryServiceArea,
        basePrice,
        totalAmount,
        bookingType,
        paymentStatus: PAYMENT_STATUS.SCHEDULED,
        ...(bookingType === BookingType.STANDARD && {
          freeCancellationUntil: new Date(bookingDate.getTime() - 24 * 60 * 60 * 1000)
        }),
      };

      // Store booking data for after login
      sessionStorage.setItem('bookingData', JSON.stringify(paymentBookingData));
      sessionStorage.setItem('serviceId', String(selectedService!.id));
      sessionStorage.setItem('selectedSlot', JSON.stringify({
        date: selectedDate,
        time: selectedTime,
        duration,
        instructorId: instructor.user_id
      }));

      // Store booking intent
      storeBookingIntent({
        instructorId: instructor.user_id,
        serviceId: selectedService!.id,
        date: selectedDate,
        time: selectedTime,
        duration,
        skipModal: true,
      });

      // Redirect to login
      const returnUrl = `/student/booking/confirm`;
      logger.info('User not authenticated, redirecting to login', { returnUrl });
      redirectToLogin(returnUrl);
      return;
    }

    // If authenticated, move to booking details step
    setCurrentStep('booking-details');
    setShowBookingForm(true);
  };

  const handleBookingSubmit = async () => {
    // Validate form
    if (!bookingFormData.name || !bookingFormData.email || !bookingFormData.phone) {
      alert('Please fill in all required fields');
      return;
    }

    if (!bookingFormData.agreedToTerms) {
      alert('Please agree to the terms and cancellation policy');
      return;
    }

    if (!selectedService) {
      alert('Please select a service');
      return;
    }

    // Create booking object for payment
    const basePrice = totalPrice;

    const booking = {
      id: `temp_${Date.now()}`, // Temporary ID until backend creates real one
      service_name: selectedService.skill,
      instructor_name: `${instructor.user.first_name} ${instructor.user.last_initial}.`,
      instructor_id: String(instructor.user_id),
      booking_date: selectedDate,
      start_time: selectedTime,
      end_time: calculateEndTime(selectedTime, duration),
      duration_minutes: duration,
      hourly_rate: selectedService.hourly_rate,
      total_price: basePrice,
    };

    setPendingBooking(booking);
    setCurrentStep('payment');
  };

  const handlePaymentSuccess = (paymentIntentId: string) => {
    logger.info('Payment successful', { paymentIntentId });
    setCurrentStep('success');

    // Navigate to success page after a short delay
    setTimeout(() => {
      onClose();
      router.push('/student/dashboard');
    }, 2000);
  };

  const handleBackButton = () => {
    if (currentStep === 'payment') {
      setCurrentStep('booking-details');
    } else if (currentStep === 'booking-details') {
      setCurrentStep('select-time');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b px-6 py-4 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            {currentStep !== 'select-time' && currentStep !== 'success' && (
              <button
                onClick={handleBackButton}
                className="p-1 hover:bg-gray-100 rounded-full transition-colors"
                aria-label="Go back"
              >
                <ChevronLeft className="h-5 w-5" aria-hidden="true" />
              </button>
            )}
            <h2 className="text-xl font-semibold">
              {currentStep === 'select-time' && 'Book Your Session'}
              {currentStep === 'booking-details' && 'Booking Details'}
              {currentStep === 'payment' && 'Payment'}
              {currentStep === 'success' && 'Booking Confirmed!'}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-full transition-colors"
            aria-label="Close booking modal"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {/* Step 1: Time Selection */}
          {currentStep === 'select-time' && (
            <>
              {/* Service Selection */}
              {instructor.services.length > 1 && (
                <div className="mb-6">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Select Service
                  </label>
                  <select
                    value={selectedService?.id || ''}
                    onChange={(e) => {
                      const service = instructor.services.find(s => String(s.id) === e.target.value);
                      if (service) {
                        setSelectedService(service);
                        setDuration(service.duration);
                      }
                    }}
                    className="w-full p-2 border border-gray-300 rounded-md"
                  >
                    {instructor.services.map((service) => (
                      <option key={service.id} value={service.id}>
                        {service.skill} - ${(() => { const r = service.hourly_rate as unknown; const n = typeof r === 'number' ? r : parseFloat(String(r ?? '0')); return Number.isNaN(n) ? 0 : n; })()}/hr
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Session Details */}
              <div className="space-y-4 mb-6">
                <div className="flex items-center space-x-3">
                  <MapPin className="h-5 w-5 text-gray-400" aria-hidden="true" />
                  <span>{serviceAreaDisplayFull}</span>
                </div>
                <div className="flex items-center space-x-3">
                  <Clock className="h-5 w-5 text-gray-400" aria-hidden="true" />
                  <span>{selectedDate} at {selectedTime}</span>
                </div>
                <div className="flex items-center space-x-3">
                  <DollarSign className="h-5 w-5 text-gray-400" aria-hidden="true" />
                  <span className="font-semibold">${totalPrice.toFixed(2)} total</span>
                </div>
              </div>

              {/* Continue Button */}
              <button
                onClick={handleContinueToBooking}
                className="w-full bg-blue-600 text-white py-3 px-4 rounded-md hover:bg-blue-700 transition-colors"
              >
                Continue to Booking
              </button>
            </>
          )}

          {/* Step 2: Booking Details Form */}
          {currentStep === 'booking-details' && showBookingForm && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Name *
                </label>
                <input
                  type="text"
                  value={bookingFormData.name}
                  onChange={(e) => setBookingFormData({ ...bookingFormData, name: e.target.value })}
                  className="w-full p-2 border border-gray-300 rounded-md"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Email *
                </label>
                <input
                  type="email"
                  value={bookingFormData.email}
                  onChange={(e) => setBookingFormData({ ...bookingFormData, email: e.target.value })}
                  className="w-full p-2 border border-gray-300 rounded-md"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Phone *
                </label>
                <input
                  type="tel"
                  value={bookingFormData.phone}
                  onChange={(e) => setBookingFormData({ ...bookingFormData, phone: e.target.value })}
                  className="w-full p-2 border border-gray-300 rounded-md"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Notes (Optional)
                </label>
                <textarea
                  value={bookingFormData.notes}
                  onChange={(e) => setBookingFormData({ ...bookingFormData, notes: e.target.value })}
                  className="w-full p-2 border border-gray-300 rounded-md"
                  rows={3}
                />
              </div>

              <div className="bg-gray-50 p-4 rounded-md">
                <label className="flex items-start space-x-2">
                  <input
                    type="checkbox"
                    checked={bookingFormData.agreedToTerms}
                    onChange={(e) => setBookingFormData({ ...bookingFormData, agreedToTerms: e.target.checked })}
                    className="mt-1"
                  />
                  <span className="text-sm text-gray-600">
                    I agree to the terms of service and understand the cancellation policy.
                    Standard bookings can be cancelled up to 24 hours before the session for a full refund.
                  </span>
                </label>
              </div>

              <button
                onClick={handleBookingSubmit}
                className="w-full bg-blue-600 text-white py-3 px-4 rounded-md hover:bg-blue-700 transition-colors"
              >
                Continue to Payment
              </button>
            </div>
          )}

          {/* Step 3: Payment */}
          {currentStep === 'payment' && pendingBooking && (
            <CheckoutFlow
              booking={pendingBooking}
              onSuccess={handlePaymentSuccess}
              onCancel={() => setCurrentStep('booking-details')}
            />
          )}

          {/* Step 4: Success */}
          {currentStep === 'success' && (
            <div className="text-center py-8">
              <div className="mb-4">
                <div className="mx-auto h-16 w-16 bg-green-100 rounded-full flex items-center justify-center">
                  <svg className="h-8 w-8 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              </div>
              <h3 className="text-2xl font-semibold mb-2">Booking Confirmed!</h3>
              <p className="text-gray-600 mb-4">
                Your session has been booked successfully. You&apos;ll receive a confirmation email shortly.
              </p>
              <p className="text-sm text-gray-500">
                Redirecting to your dashboard...
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
