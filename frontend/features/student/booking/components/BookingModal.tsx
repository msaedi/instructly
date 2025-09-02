// frontend/features/student/booking/components/BookingModal.tsx
'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { X, MapPin, Clock, DollarSign, User, Mail, Phone, MessageSquare } from 'lucide-react';
import { BookingModalProps, Service } from '../types';
import { logger } from '@/lib/logger';
import { formatInstructorFromUser, formatFullName, getUserInitials } from '@/utils/nameDisplay';
import { useAuth, storeBookingIntent } from '../hooks/useAuth';
import { calculateEndTime } from '../hooks/useCreateBooking';
import {
  BookingPayment,
  BookingType,
  determineBookingType,
  calculateServiceFee,
  calculateTotalAmount,
} from '@/features/student/payment';

export default function BookingModal({
  isOpen,
  onClose,
  instructor,
  selectedDate,
  selectedTime,
}: BookingModalProps) {
  const router = useRouter();
  const { user, isAuthenticated, redirectToLogin } = useAuth();
  const [selectedService, setSelectedService] = useState<Service | null>(null);
  const [duration, setDuration] = useState(60); // Default to 60 minutes
  const [totalPrice, setTotalPrice] = useState(0);
  const [showBookingForm, setShowBookingForm] = useState(false);
  const [bookingFormData, setBookingFormData] = useState({
    name: '',
    email: '',
    phone: '',
    notes: '',
    agreedToTerms: false,
  });

  // Initialize with first service if multiple, or use the only service
  useEffect(() => {
    if (instructor.services.length > 0 && !selectedService) {
      const firstService = instructor.services[0];
      setSelectedService(firstService);
      setDuration(firstService.duration);
      setTotalPrice(firstService.hourly_rate * (firstService.duration / 60));
    }
  }, [instructor.services.length]);

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
      // Set initial service if not set
      if (!selectedService && instructor.services.length > 0) {
        setSelectedService(instructor.services[0]);
        setDuration(instructor.services[0].duration);
      }

      // For authenticated users, show the booking form directly
      if (isAuthenticated) {
        setShowBookingForm(true);
      } else {
        // For unauthenticated users, we'll redirect when they try to continue
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
  }, [
    isOpen,
    isAuthenticated,
    user?.full_name,
    user?.email,
  ]);

  // Update price when service or duration changes
  useEffect(() => {
    if (selectedService) {
      const hourlyRate = selectedService.hourly_rate;
      const hours = duration / 60;
      setTotalPrice(hourlyRate * hours);
    }
  }, [selectedService, duration]);

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
    const [hours, minutes] = timeString.split(':');
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
      const serviceFee = calculateServiceFee(basePrice);
      const totalAmount = calculateTotalAmount(basePrice);
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
        location: instructor.areas_of_service[0] || 'NYC',
        basePrice,
        serviceFee,
        totalAmount,
        bookingType,
        paymentStatus: 'pending' as any,
        freeCancellationUntil:
          bookingType === BookingType.STANDARD
            ? new Date(bookingDate.getTime() - 24 * 60 * 60 * 1000)
            : undefined,
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
    setShowBookingForm(true);
    logger.info('User authenticated, showing booking form', {
      userId: user?.id,
      userEmail: user?.email,
    });
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

    // Prepare booking data for confirmation page
    const bookingDate = new Date(selectedDate + 'T' + selectedTime);
    const basePrice = totalPrice;
    const serviceFee = calculateServiceFee(basePrice);
    const totalAmount = calculateTotalAmount(basePrice);
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
      location: instructor.areas_of_service[0] || 'NYC',
      basePrice,
      serviceFee,
      totalAmount,
      bookingType,
      paymentStatus: 'pending' as any,
      freeCancellationUntil:
        bookingType === BookingType.STANDARD
          ? new Date(bookingDate.getTime() - 24 * 60 * 60 * 1000)
          : undefined,
    };

    // Store booking data in session storage for the confirmation page
    sessionStorage.setItem('bookingData', JSON.stringify(paymentBookingData));
    sessionStorage.setItem('serviceId', String(selectedService.id));

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
      onClose();
    }
  };

  const handleFormChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value, type } = e.target;
    const checked = (e.target as HTMLInputElement).checked;

    setBookingFormData((prev) => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }));
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 flex items-center justify-center z-50 p-4"
      style={{ backgroundColor: 'var(--modal-backdrop)' }}
      onClick={handleOverlayClick}
    >
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex justify-between items-center p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            Confirm Your Lesson
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            aria-label="Close modal"
          >
            <X className="h-5 w-5 text-gray-500 dark:text-gray-400" />
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
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    <User className="inline h-4 w-4 mr-1" />
                    Full Name *
                  </label>
                  <input
                    type="text"
                    name="name"
                    value={bookingFormData.name}
                    onChange={handleFormChange}
                    required
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
                    placeholder="John Doe"
                  />
                </div>

                {/* Email Field */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    <Mail className="inline h-4 w-4 mr-1" />
                    Email *
                  </label>
                  <input
                    type="email"
                    name="email"
                    value={bookingFormData.email}
                    onChange={handleFormChange}
                    required
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
                    placeholder="john@example.com"
                  />
                </div>

                {/* Phone Field */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    <Phone className="inline h-4 w-4 mr-1" />
                    Phone Number *
                  </label>
                  <input
                    type="tel"
                    name="phone"
                    value={bookingFormData.phone}
                    onChange={handleFormChange}
                    required
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
                    placeholder="(555) 123-4567"
                  />
                </div>

                {/* Notes Field */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    <MessageSquare className="inline h-4 w-4 mr-1" />
                    Special Requests or Notes
                  </label>
                  <textarea
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
                    type="checkbox"
                    name="agreedToTerms"
                    checked={bookingFormData.agreedToTerms}
                    onChange={handleFormChange}
                    className="mt-1 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                  />
                  <label className="ml-2 text-sm text-gray-600 dark:text-gray-400">
                    I agree to the cancellation policy and terms of service. Free cancellation until
                    2 hours before the lesson.
                  </label>
                </div>
              </div>

              {/* Form Button - Only Continue to Payment */}
              <button
                onClick={handleBookingSubmit}
                disabled={
                  !bookingFormData.name ||
                  !bookingFormData.email ||
                  !bookingFormData.phone ||
                  !bookingFormData.agreedToTerms
                }
                className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-medium py-3 px-4 rounded-lg transition-colors"
              >
                Continue to Payment
              </button>
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
                    const price = selectedService
                      ? (selectedService.hourly_rate * minutes) / 60
                      : 0;
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
                    {instructor.areas_of_service[0]} • Location details will be provided after
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
