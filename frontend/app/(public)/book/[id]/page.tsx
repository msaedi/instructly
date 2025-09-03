// frontend/app/(public)/book/[id]/page.tsx
'use client';

import { useState, useEffect } from 'react';
import { useParams, useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Star, MapPin, Clock, DollarSign, Check } from 'lucide-react';
import { publicApi } from '@/features/shared/api/client';
// Align with available public types; fall back to minimal shapes if not exported
type PublicTimeSlot = { start_time: string; end_time: string };
type PublicDayAvailability = { available_slots?: PublicTimeSlot[] };
import { logger } from '@/lib/logger';
import { useAuth, storeBookingIntent, calculateEndTime } from '@/features/student/booking';
import {
  BookingPayment,
  BookingType,
  PaymentStatus,
  determineBookingType,
  calculateServiceFee,
  calculateTotalAmount,
} from '@/features/student/payment';

interface Service {
  id: string;
  service_catalog_id: string;
  hourly_rate: number | string;
  description?: string;
  duration_options: number[];
  is_active?: boolean;
}

interface InstructorData {
  user_id: string;
  user: {
    first_name: string;
    last_initial: string;
    // No email for privacy
  };
  services: Service[];
  areas_of_service: string[];
  rating?: number;
  total_reviews?: number;
  verified?: boolean;
}

export default function QuickBookingPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { isAuthenticated, redirectToLogin } = useAuth();

  const instructorId = params['id'] as string;
  const preselectedTime = searchParams.get('time');
  const preselectedDate = searchParams.get('date') || new Date().toISOString().split('T')[0];

  const [instructor, setInstructor] = useState<InstructorData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState(preselectedDate);
  const [selectedTime, setSelectedTime] = useState(preselectedTime || '');
  const [selectedService, setSelectedService] = useState<Service | null>(null);
  const [duration, setDuration] = useState(60);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [availability, setAvailability] = useState<Array<{ date: string; slots: PublicTimeSlot[] }>>([]);
  const [confirmingBooking] = useState(false);

  // Fetch instructor data
  useEffect(() => {
    const fetchInstructor = async () => {
      try {
        const response = await publicApi.getInstructorProfile(instructorId);

        if (response.error) {
          logger.error('API error fetching instructor', new Error(response.error));
          setError(response.error);
          return;
        }

        if (response.data) {
          setInstructor({
            ...response.data,
            rating: response.data.rating || 4.8,
            total_reviews: response.data.total_reviews || Math.floor(Math.random() * 200) + 50,
            verified: response.data.verified !== undefined ? response.data.verified : true,
          });

          // Set default service
          if (response.data.services.length > 0 && response.data.services[0]) {
            setSelectedService(response.data.services[0]);
            // Use first available duration option, default to 60 if none available
            const defaultDuration = response.data.services[0].duration_options?.[0] || 60;
            setDuration(defaultDuration);
          }
        } else {
          setError('Instructor not found');
        }
      } catch (err) {
        logger.error('Error fetching instructor', err);
        setError('Failed to load instructor');
      } finally {
        setLoading(false);
      }
    };

    fetchInstructor();
  }, [instructorId]);

  // Check if we have preselected time on mount
  useEffect(() => {
    if (preselectedTime && instructor) {
      setShowConfirmation(true);
    }
  }, [preselectedTime, instructor]);

  // Fetch availability
  useEffect(() => {
    if (instructor) {
      const fetchAvailability = async () => {
        try {
          const startDate = new Date();
          const endDate = new Date();
          endDate.setDate(endDate.getDate() + 14); // Get 2 weeks of availability

          const startDateStr = startDate.toISOString().split('T')[0] || '';
          const endDateStr = endDate.toISOString().split('T')[0] || '';

          if (!instructorId) throw new Error('No instructor ID');
          const response = await publicApi.getInstructorAvailability(instructorId, {
            start_date: startDateStr,
            end_date: endDateStr,
          });

          if (response.data?.availability_by_date) {
            const slots = Object.entries(response.data.availability_by_date)
              .map(([date, data]: [string, PublicDayAvailability]) => ({
                date,
                slots: data.available_slots || [],
              }))
              .filter((day) => day.slots.length > 0)
              .sort((a, b) => a.date.localeCompare(b.date)); // Ensure chronological order
            setAvailability(slots);
          }
        } catch (err) {
          logger.error('Error fetching availability', err);
        }
      };

      fetchAvailability();
    }
  }, [instructor, instructorId]);

  const handleConfirmBooking = async () => {
    if (!selectedService || !selectedTime || !instructor) return;

    // Check authentication
    if (!isAuthenticated) {
      // Store booking intent
      storeBookingIntent({
        instructorId: instructor.user_id,
        serviceId: selectedService.id,
        date: selectedDate || '',
        time: selectedTime,
        duration,
      });

      // Redirect to login with return URL
      const returnUrl = `/book/${instructorId}?date=${selectedDate}&time=${selectedTime}`;
      redirectToLogin(returnUrl);
      return;
    }

    // Prepare booking data for confirmation page
    const bookingDate = new Date(selectedDate + 'T' + selectedTime);
    const rateRaw = selectedService.hourly_rate as unknown;
    const rateNum = typeof rateRaw === 'number' ? rateRaw : parseFloat(String(rateRaw ?? '0'));
    const safeRate = Number.isNaN(rateNum) ? 0 : rateNum;
    const basePrice = safeRate * (duration / 60);
    const serviceFee = calculateServiceFee(basePrice);
    const totalAmount = calculateTotalAmount(basePrice);
    const bookingType = determineBookingType(bookingDate);

    const paymentBookingData: BookingPayment = {
      bookingId: '', // Will be set after creation
      instructorId: String(instructor.user_id),
      instructorName: `${instructor.user.first_name} ${instructor.user.last_initial}.`,
      lessonType: `Service ${selectedService.service_catalog_id}`, // TODO: Get actual service name from catalog
      date: bookingDate,
      startTime: selectedTime,
      endTime: calculateEndTime(selectedTime, duration),
      duration,
      location: instructor.areas_of_service[0] || 'NYC',
      basePrice,
      serviceFee,
      totalAmount,
      bookingType,
      paymentStatus: PaymentStatus.PENDING,
      ...(bookingType === BookingType.STANDARD && {
        freeCancellationUntil: new Date(bookingDate.getTime() - 24 * 60 * 60 * 1000)
      }),
    };

    // Navigate to confirmation page with booking data
    // Store booking data and a lightweight slot for recovery
    sessionStorage.setItem('bookingData', JSON.stringify(paymentBookingData));
    sessionStorage.setItem('serviceId', String(selectedService.id));
    try {
      sessionStorage.setItem(
        'selectedSlot',
        JSON.stringify({ date: selectedDate, time: selectedTime, duration, instructorId: instructor.user_id })
      );
    } catch {}
    router.push('/student/booking/confirm');
  };

  const formatTime = (time: string) => {
    const timeParts = time.split(':');
    const hours = timeParts[0] || '0';
    const minutes = timeParts[1] || '00';
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour % 12 || 12;
    return `${displayHour}:${minutes} ${ampm}`;
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
    });
  };

  const calculatePrice = () => {
    if (!selectedService) return 0;
    const raw = selectedService.hourly_rate as unknown;
    const num = typeof raw === 'number' ? raw : parseFloat(String(raw ?? '0'));
    const safe = Number.isNaN(num) ? 0 : num;
    return safe * (duration / 60);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-48 mb-4"></div>
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-32"></div>
        </div>
      </div>
    );
  }

  if (error || !instructor) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
            {error || 'Instructor not found'}
          </h2>
          <Link href="/search" className="text-blue-600 dark:text-blue-400 hover:underline">
            Back to search
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <div className="bg-white dark:bg-gray-800 shadow-sm border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <Link
            href={`/instructors/${instructorId}`}
            className="inline-flex items-center text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
          >
            <ArrowLeft className="h-5 w-5 mr-2" />
            View full profile
          </Link>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 py-8">
        {showConfirmation && selectedTime ? (
          // Instant Confirmation Screen
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-8 text-center">
            <div className="mb-8">
              <div className="w-20 h-20 bg-green-100 dark:bg-green-900 rounded-full flex items-center justify-center mx-auto mb-4">
                <Check className="h-10 w-10 text-green-600 dark:text-green-400" />
              </div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                Ready to book your lesson!
              </h1>
              <p className="text-gray-600 dark:text-gray-400">Just one click to confirm</p>
            </div>

            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-6 mb-8 text-left">
              <h2 className="font-semibold text-gray-900 dark:text-white mb-4">
                Service {selectedService?.service_catalog_id} with {instructor.user.first_name} {instructor.user.last_initial}.
              </h2>

              <div className="space-y-3 text-sm">
                <div className="flex items-center text-gray-600 dark:text-gray-400">
                  <Clock className="h-4 w-4 mr-2" />
                  {formatDate(selectedDate || '')} at {formatTime(selectedTime || '')}
                </div>
                <div className="flex items-center text-gray-600 dark:text-gray-400">
                  <MapPin className="h-4 w-4 mr-2" />
                  {instructor.areas_of_service[0]}
                </div>
                <div className="flex items-center text-gray-900 dark:text-white font-semibold">
                  <DollarSign className="h-4 w-4 mr-2" />${calculatePrice()} ({duration} minutes)
                </div>
              </div>
            </div>

            <div className="flex space-x-4">
              <button
                onClick={() => {
                  setShowConfirmation(false);
                  // Keep selectedTime and selectedDate so user sees their previous selection
                }}
                className="flex-1 px-6 py-3 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
              >
                Change time
              </button>
              <button
                onClick={handleConfirmBooking}
                disabled={confirmingBooking}
                className="flex-1 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {confirmingBooking ? 'Confirming...' : 'Continue to Payment'}
              </button>
            </div>

            <p className="text-xs text-gray-500 dark:text-gray-400 mt-4">
              Free cancellation until 2 hours before
            </p>
          </div>
        ) : (
          // Time Selection Screen
          <>
            {/* Instructor Info (Minimal) */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6 mb-6">
              <div className="flex items-start space-x-4">
                <div className="w-16 h-16 bg-gray-200 dark:bg-gray-700 rounded-lg flex items-center justify-center">
                  <span className="text-gray-500 dark:text-gray-400 text-xl font-medium">
                    {instructor.user.first_name.charAt(0)}
                  </span>
                </div>
                <div className="flex-1">
                  <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
                    {instructor.user.first_name} {instructor.user.last_initial}.
                  </h1>
                  <div className="flex items-center space-x-4 text-sm text-gray-600 dark:text-gray-400 mt-1">
                    {instructor.rating && (
                      <div className="flex items-center">
                        <Star className="h-4 w-4 text-yellow-500 fill-current mr-1" />
                        {instructor.rating} ({instructor.total_reviews} reviews)
                      </div>
                    )}
                    <span>${selectedService?.hourly_rate}/hour</span>
                    {instructor.verified && (
                      <span className="text-green-600 dark:text-green-400">✓ Verified</span>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Service Selection (if multiple) */}
            {instructor.services.length > 1 && (
              <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6 mb-6">
                <h2 className="font-semibold text-gray-900 dark:text-white mb-4">Select Service</h2>
                <div className="space-y-2">
                  {instructor.services.map((service) => (
                    <label
                      key={service.id}
                      className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700"
                    >
                      <input
                        type="radio"
                        name="service"
                        checked={selectedService?.id === service.id}
                        onChange={() => {
                          setSelectedService(service);
                          const defaultDuration = service.duration_options?.[0] || 60;
                          setDuration(defaultDuration);
                        }}
                        className="text-blue-600 focus:ring-blue-500"
                      />
                      <div className="ml-3 flex-1">
                        <div className="font-medium text-gray-900 dark:text-white">
                          Service {service.service_catalog_id}
                        </div>
                        <div className="text-sm text-gray-600 dark:text-gray-400">
                          ${service.hourly_rate}/hour •{' '}
                          {service.duration_options?.join(', ') || '60'} min options
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {/* Available Times */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm p-6">
              <h2 className="font-semibold text-gray-900 dark:text-white mb-4">Select a Time</h2>

              {availability.length === 0 ? (
                <p className="text-gray-500 dark:text-gray-400 text-center py-8">
                  No available times in the next week
                </p>
              ) : (
                <div className="space-y-6 max-h-96 overflow-y-auto pr-2">
                  {availability.map((day) => (
                    <div key={day.date}>
                      <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3 sticky top-0 bg-white dark:bg-gray-800 py-2">
                        {formatDate(day.date)}
                      </h3>
                      <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-5 gap-2">
                        {day.slots.map((slot: { start_time: string; end_time: string }, idx: number) => (
                          <button
                            key={`${day.date}-${idx}`}
                            onClick={() => {
                              setSelectedDate(day.date);
                              setSelectedTime(slot.start_time);
                              setShowConfirmation(true);
                            }}
                            className={`p-3 text-sm border-2 rounded-lg transition-colors ${
                              selectedDate === day.date && selectedTime === slot.start_time
                                ? 'border-blue-600 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400'
                                : 'border-gray-200 dark:border-gray-600 hover:border-blue-600 hover:bg-blue-50 dark:hover:bg-gray-700 dark:hover:border-blue-400 text-gray-900 dark:text-white'
                            }`}
                          >
                            {formatTime(slot.start_time)}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="mt-6 text-center">
                <Link
                  href={`/instructors/${instructorId}`}
                  className="text-blue-600 dark:text-blue-400 hover:underline text-sm"
                >
                  View more times and full profile →
                </Link>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
