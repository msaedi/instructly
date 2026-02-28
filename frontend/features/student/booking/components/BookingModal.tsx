// frontend/features/student/booking/components/BookingModal.tsx
'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { X, MapPin, Clock, DollarSign, User, Mail, Phone, MessageSquare } from 'lucide-react';
import { BookingModalProps, Service } from '../types';
import { logger } from '@/lib/logger';
import { formatFullName } from '@/utils/nameDisplay';
import { useAuth } from '../hooks/useAuth';
import { storeBookingIntent, calculateEndTime } from '@/features/shared/utils/booking';
import { at } from '@/lib/ts/safe';
import { getServiceAreaBoroughs, getServiceAreaDisplay } from '@/lib/profileServiceAreas';
import { BookingPayment, PAYMENT_STATUS } from '@/features/student/payment/types';
import { BookingType } from '@/features/shared/types/booking';
import { determineBookingType } from '@/features/shared/utils/paymentCalculations';
import { useFocusTrap } from '@/hooks/useFocusTrap';
import { useScrollLock } from '@/hooks/useScrollLock';

type BookingFormErrors = Partial<{
  name: string;
  email: string;
  phone: string;
  agreedToTerms: string;
  service: string;
}>;

export default function BookingModal({
  isOpen,
  onClose,
  instructor,
  selectedDate,
  selectedTime,
}: BookingModalProps) {
  const router = useRouter();
  const { user, isAuthenticated, redirectToLogin } = useAuth();
  const defaultService = at(instructor.services, 0) ?? null;
  const defaultDuration = defaultService?.duration ?? 60;
  const [selectedService, setSelectedService] = useState<Service | null>(() => defaultService);
  const [duration, setDuration] = useState(() => defaultDuration); // Default to 60 minutes
  const totalPrice = useMemo(() => {
    if (!selectedService) return 0;
    const rateRaw = selectedService.hourly_rate as unknown;
    const rateNum = typeof rateRaw === 'number' ? rateRaw : parseFloat(String(rateRaw ?? '0'));
    const safeRate = Number.isNaN(rateNum) ? 0 : rateNum;
    const hours = duration / 60;
    return safeRate * hours;
  }, [selectedService, duration]);
  const [showBookingForm, setShowBookingForm] = useState(() => isAuthenticated);
  const [bookingFormData, setBookingFormData] = useState(() => ({
    name: user?.full_name || '',
    email: user?.email || '',
    phone: '',
    notes: '',
    agreedToTerms: false,
  }));
  const [errors, setErrors] = useState<BookingFormErrors>({});
  const modalRef = useRef<HTMLDivElement | null>(null);
  const serviceAreaBoroughs = getServiceAreaBoroughs(instructor);
  const serviceAreaDisplay = getServiceAreaDisplay(instructor) || 'NYC';
  const primaryServiceArea = serviceAreaBoroughs[0] ?? serviceAreaDisplay;

  const resetState = useCallback(() => {
    setSelectedService(defaultService);
    setDuration(defaultDuration);
    setShowBookingForm(isAuthenticated);
    setBookingFormData({
      name: user?.full_name || '',
      email: user?.email || '',
      phone: '',
      notes: '',
      agreedToTerms: false,
    });
    setErrors({});
  }, [defaultDuration, defaultService, isAuthenticated, user?.email, user?.full_name]);

  const handleClose = useCallback(() => {
    resetState();
    onClose();
  }, [onClose, resetState]);

  useFocusTrap({
    isOpen,
    containerRef: modalRef,
    onEscape: handleClose,
  });
  useScrollLock(isOpen);

  const clearFieldError = useCallback((field: keyof BookingFormErrors) => {
    setErrors((prev) => {
      if (!prev[field]) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  }, []);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  const formatTime = (timeString: string) => {
    const parts = timeString.split(':');
    const hours = at(parts, 0);
    const minutes = at(parts, 1);
    if (!hours || !minutes) return 'Invalid time';
    const time = new Date();
    time.setHours(parseInt(hours), parseInt(minutes));
    return time.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
  };

  const handleServiceChange = (service: Service) => {
    setSelectedService(service);
    setDuration(service.duration);
    clearFieldError('service');
    logger.info('Service selected', {
      serviceId: service.id,
      skill: service.skill,
      rate: service.hourly_rate,
      duration: service.duration,
    });
  };

  const handleDurationChange = (newDuration: number) => {
    setDuration(newDuration);
    logger.info('Duration changed', { duration: newDuration });
  };

  const handleContinue = () => {
    if (!selectedService) return;

    // Check authentication
    if (!isAuthenticated) {
      // Prepare booking data for after login
      const bookingDate = new Date(selectedDate + 'T' + selectedTime);
      const basePrice = totalPrice;
      const totalAmount = basePrice;
      const bookingType = determineBookingType(bookingDate);

      const paymentBookingData: BookingPayment = {
        bookingId: '', // Will be set after creation
        instructorId: String(instructor.user_id),
        instructorName: `${instructor.user.first_name} ${instructor.user.last_initial}.`,
        lessonType: selectedService.skill,
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

      // Store booking data and slot info for after login
      sessionStorage.setItem('bookingData', JSON.stringify(paymentBookingData));
      sessionStorage.setItem('serviceId', String(selectedService.id));
      sessionStorage.setItem('selectedSlot', JSON.stringify({
        date: selectedDate,
        time: selectedTime,
        duration,
        instructorId: instructor.user_id
      }));

      // Store booking intent for after login (to go directly to payment page)
      storeBookingIntent({
        instructorId: instructor.user_id,
        serviceId: selectedService.id,
        date: selectedDate,
        time: selectedTime,
        duration,
        skipModal: true, // Flag to skip modal and go directly to payment
      });

      // Redirect to login with payment page as return URL
      const returnUrl = `/student/booking/confirm`;
      logger.info('User not authenticated, redirecting to login', {
        returnUrl,
        bookingIntent: {
          instructorId: instructor.user_id,
          date: selectedDate,
          time: selectedTime,
        },
      });

      redirectToLogin(returnUrl);
      return;
    }

    // If authenticated, show booking form
    setErrors({});
    setShowBookingForm(true);
    if (user) {
      setBookingFormData((prev) => ({
        ...prev,
        name: formatFullName(user) || '',
        email: user.email || '',
      }));
    }
    logger.info('User authenticated, showing booking form', {
      userId: user?.id,
      userEmail: user?.email,
    });
  };

  const handleBookingSubmit = async () => {
    const service = selectedService;
    const nextErrors: BookingFormErrors = {};

    if (!bookingFormData.name.trim()) {
      nextErrors.name = 'Full name is required';
    }

    if (!bookingFormData.email.trim()) {
      nextErrors.email = 'Email is required';
    }

    if (!bookingFormData.phone.trim()) {
      nextErrors.phone = 'Phone number is required';
    }

    if (!bookingFormData.agreedToTerms) {
      nextErrors.agreedToTerms = 'Please agree to the terms and cancellation policy';
    }

    if (!service) {
      nextErrors.service = 'Please select a service';
    }

    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }

    if (!service) {
      return;
    }

    setErrors({});

    // Prepare booking data for confirmation page
    const bookingDate = new Date(selectedDate + 'T' + selectedTime);
    const basePrice = totalPrice;
    const totalAmount = basePrice;
    const bookingType = determineBookingType(bookingDate);

    const paymentBookingData: BookingPayment = {
      bookingId: '', // Will be set after creation
      instructorId: String(instructor.user_id),
      instructorName: `${instructor.user.first_name} ${instructor.user.last_initial}.`,
      lessonType: service.skill,
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

    // Store booking data in session storage for the confirmation page
    sessionStorage.setItem('bookingData', JSON.stringify(paymentBookingData));
    sessionStorage.setItem('serviceId', String(service.id));

    // Store the selected slot info so it can be restored when going back
    sessionStorage.setItem('selectedSlot', JSON.stringify({
      date: selectedDate,
      time: selectedTime,
      duration,
      instructorId: instructor.user_id
    }));

    // Navigate to confirmation page
    router.push('/student/booking/confirm');
  };

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      handleClose();
    }
  };

  const handleFormChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value, type } = e.target;
    const checked = (e.target as HTMLInputElement).checked;

    setBookingFormData((prev) => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }));

    if (name === 'agreedToTerms' && type === 'checkbox' && checked) {
      clearFieldError('agreedToTerms');
      return;
    }

    if ((name === 'name' || name === 'email' || name === 'phone') && value.trim()) {
      clearFieldError(name);
    }
  };

  if (!isOpen) return null;

  const isBookingFormInvalid =
    !bookingFormData.name.trim() ||
    !bookingFormData.email.trim() ||
    !bookingFormData.phone.trim() ||
    !bookingFormData.agreedToTerms;
  const submitDescribedBy = [
    isBookingFormInvalid ? 'booking-submit-hint' : undefined,
    errors.service ? 'booking-service-error' : undefined,
  ].filter(Boolean).join(' ') || undefined;

  return (
    <div
      className="insta-dialog-backdrop flex items-center justify-center z-50 p-4"
      onClick={handleOverlayClick}
    >
      <div
        ref={modalRef}
        className="insta-dialog-panel bg-white dark:bg-gray-800 max-w-md w-full max-h-[90vh] overflow-y-auto"
        role="dialog"
        aria-modal="true"
        aria-labelledby="booking-modal-title"
        tabIndex={-1}
      >
        {/* Header */}
        <div className="flex justify-between items-center p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 id="booking-modal-title" className="text-xl font-semibold text-gray-900 dark:text-white">
            Confirm Your Lesson
          </h2>
          <button
            onClick={handleClose}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            aria-label="Close modal"
          >
            <X className="h-5 w-5 text-gray-500 dark:text-gray-400" aria-hidden="true" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {showBookingForm ? (
            // Booking Form for authenticated users
            <>
              <div className="space-y-4">
                <h3 className="text-lg font-medium text-gray-900 dark:text-white">
                  Your Information
                </h3>

                {/* Name Field */}
                <div>
                  <label htmlFor="booking-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    <User className="inline h-4 w-4 mr-1" />
                    Full Name *
                  </label>
                  <input
                    id="booking-name"
                    type="text"
                    name="name"
                    value={bookingFormData.name}
                    onChange={handleFormChange}
                    required
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
                    placeholder="John Doe"
                    aria-invalid={!!errors.name}
                    aria-describedby={errors.name ? 'booking-name-error' : undefined}
                  />
                  {errors.name && (
                    <p id="booking-name-error" role="alert" aria-live="assertive" className="mt-1 text-sm text-red-600 dark:text-red-400">
                      {errors.name}
                    </p>
                  )}
                </div>

                {/* Email Field */}
                <div>
                  <label htmlFor="booking-email" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    <Mail className="inline h-4 w-4 mr-1" />
                    Email *
                  </label>
                  <input
                    id="booking-email"
                    type="email"
                    name="email"
                    value={bookingFormData.email}
                    onChange={handleFormChange}
                    required
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
                    placeholder="john@example.com"
                    aria-invalid={!!errors.email}
                    aria-describedby={errors.email ? 'booking-email-error' : undefined}
                  />
                  {errors.email && (
                    <p id="booking-email-error" role="alert" aria-live="assertive" className="mt-1 text-sm text-red-600 dark:text-red-400">
                      {errors.email}
                    </p>
                  )}
                </div>

                {/* Phone Field */}
                <div>
                  <label htmlFor="booking-phone" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    <Phone className="inline h-4 w-4 mr-1" />
                    Phone Number *
                  </label>
                  <input
                    id="booking-phone"
                    type="tel"
                    name="phone"
                    value={bookingFormData.phone}
                    onChange={handleFormChange}
                    required
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
                    placeholder="(555) 123-4567"
                    aria-invalid={!!errors.phone}
                    aria-describedby={errors.phone ? 'booking-phone-error' : undefined}
                  />
                  {errors.phone && (
                    <p id="booking-phone-error" role="alert" aria-live="assertive" className="mt-1 text-sm text-red-600 dark:text-red-400">
                      {errors.phone}
                    </p>
                  )}
                </div>

                {/* Notes Field */}
                <div>
                  <label htmlFor="booking-notes" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    <MessageSquare className="inline h-4 w-4 mr-1" />
                    Special Requests or Notes
                  </label>
                  <textarea
                    id="booking-notes"
                    name="notes"
                    value={bookingFormData.notes}
                    onChange={handleFormChange}
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
                    placeholder="Any specific topics, learning goals, or requirements..."
                  />
                </div>

                {/* Booking Summary */}
                <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 space-y-2">
                  <h4 className="font-medium text-gray-900 dark:text-white">Booking Summary</h4>
                  <div className="text-sm space-y-1 text-gray-600 dark:text-gray-400">
                    <div>Instructor: {instructor.user.first_name} {instructor.user.last_initial}.</div>
                    <div>Service: {selectedService?.skill}</div>
                    <div>Date: {formatDate(selectedDate)}</div>
                    <div>Time: {formatTime(selectedTime)}</div>
                    <div>Duration: {duration} minutes</div>
                    <div className="font-medium text-gray-900 dark:text-white">
                      Total: ${Math.round(totalPrice)}
                    </div>
                  </div>
                </div>

                {/* Terms Agreement */}
                <div className="flex items-start">
                  <input
                    id="booking-terms"
                    type="checkbox"
                    name="agreedToTerms"
                    checked={bookingFormData.agreedToTerms}
                    onChange={handleFormChange}
                    className="mt-1 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                    aria-invalid={!!errors.agreedToTerms}
                    aria-describedby={errors.agreedToTerms ? 'booking-terms-error' : undefined}
                  />
                  <label htmlFor="booking-terms" className="ml-2 text-sm text-gray-600 dark:text-gray-400">
                    I agree to the cancellation policy and terms of service. Free cancellation until
                    2 hours before the lesson.
                  </label>
                </div>
                {errors.agreedToTerms && (
                  <p id="booking-terms-error" role="alert" aria-live="assertive" className="mt-1 text-sm text-red-600 dark:text-red-400">
                    {errors.agreedToTerms}
                  </p>
                )}
              </div>

              {/* Form Button - Only Continue to Payment */}
              <p id="booking-submit-hint" className="sr-only">
                Complete all required fields and agree to the terms to continue to payment.
              </p>
              <button
                onClick={handleBookingSubmit}
                disabled={isBookingFormInvalid}
                className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-medium py-3 px-4 rounded-lg transition-colors"
                aria-describedby={submitDescribedBy}
              >
                Continue to Payment
              </button>
              {errors.service && (
                <p id="booking-service-error" role="alert" aria-live="assertive" className="mt-1 text-sm text-red-600 dark:text-red-400">
                  {errors.service}
                </p>
              )}
            </>
          ) : (
            <>
              {/* Instructor and Time Info */}
              <div className="space-y-4">
                <div className="flex items-center space-x-3">
                  {/* Instructor Photo Placeholder */}
                  <div className="w-12 h-12 bg-gray-200 dark:bg-gray-700 rounded-full flex items-center justify-center">
                    <span className="text-gray-500 dark:text-gray-400 font-medium">
                      {instructor.user.first_name.charAt(0)}
                    </span>
                  </div>
                  <div>
                    <h3 className="font-medium text-gray-900 dark:text-white">
                      {selectedService?.skill || 'Lesson'} with {instructor.user.first_name} {instructor.user.last_initial}.
                    </h3>
                    <div className="flex items-center text-sm text-gray-600 dark:text-gray-400">
                      <Clock className="h-4 w-4 mr-1" />
                      {formatDate(selectedDate)} at {formatTime(selectedTime)}
                    </div>
                  </div>
                </div>
              </div>

              {/* Service Selection (if multiple services) */}
              {instructor.services.length > 1 && (
                <div className="space-y-3">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                    Select Service:
                  </label>
                  <div className="space-y-2">
                    {instructor.services.map((service) => (
                      <label
                        key={service.id}
                        className="flex items-center space-x-3 p-3 border border-gray-200 dark:border-gray-600 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                      >
                        <input
                          type="radio"
                          name="service"
                          value={service.id}
                          checked={selectedService?.id === service.id}
                          onChange={() => handleServiceChange(service)}
                          className="text-blue-600 focus:ring-blue-500"
                        />
                        <div className="flex-1">
                          <div className="font-medium text-gray-900 dark:text-white">
                            {service.skill}
                          </div>
                          <div className="text-sm text-gray-600 dark:text-gray-400">
                            ${service.hourly_rate}/hour
                          </div>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {/* Duration Selection */}
              <div className="space-y-3">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Duration:
                </label>
                <div className="space-y-2">
                  {[30, 60, 90].map((minutes) => {
                    const rateRaw = selectedService ? (selectedService.hourly_rate as unknown) : 0;
                    const rateNum = typeof rateRaw === 'number' ? rateRaw : parseFloat(String(rateRaw ?? '0'));
                    const safeRate = Number.isNaN(rateNum) ? 0 : rateNum;
                    const price = selectedService ? (safeRate * minutes) / 60 : 0;
                    return (
                      <label
                        key={minutes}
                        className="flex items-center justify-between p-3 border border-gray-200 dark:border-gray-600 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                      >
                        <div className="flex items-center space-x-3">
                          <input
                            type="radio"
                            name="duration"
                            value={minutes}
                            checked={duration === minutes}
                            onChange={() => handleDurationChange(minutes)}
                            className="text-blue-600 focus:ring-blue-500"
                          />
                          <span className="text-gray-900 dark:text-white">{minutes} minutes</span>
                        </div>
                        <span className="font-medium text-gray-900 dark:text-white">
                          ${Math.round(price)}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>

              {/* Location Info */}
              <div className="flex items-start space-x-3 p-3 bg-gray-50 dark:bg-gray-700 rounded-lg">
                <MapPin className="h-5 w-5 text-gray-500 dark:text-gray-400 mt-0.5" />
                <div>
                  <div className="font-medium text-gray-900 dark:text-white">
                    {instructor.user.first_name}&apos;s Studio
                  </div>
                  <div className="text-sm text-gray-600 dark:text-gray-400">
                    {primaryServiceArea} • Location details will be provided after
                    booking
                  </div>
                </div>
              </div>

              {/* Price Summary */}
              <div className="flex items-center justify-between p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                <div className="flex items-center space-x-2">
                  <DollarSign className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                  <span className="font-medium text-gray-900 dark:text-white">Total</span>
                </div>
                <span className="text-xl font-bold text-blue-600 dark:text-blue-400">
                  ${Math.round(totalPrice)}
                </span>
              </div>

              {/* Continue Button */}
              <button
                onClick={handleContinue}
                disabled={!selectedService}
                className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-medium py-3 px-4 rounded-lg transition-colors"
              >
                Continue to Booking
              </button>

              {/* Trust & Policy Info */}
              <div className="text-xs text-gray-500 dark:text-gray-400 text-center space-y-1">
                <div>Free cancellation until 2 hours before</div>
                <div>100% satisfaction guarantee</div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
