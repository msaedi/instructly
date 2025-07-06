// frontend/app/instructors/[id]/page.tsx
'use client';

/**
 * Individual Instructor Profile Page
 *
 * Updated with complete booking flow using new time-based API.
 * No more availability_slot_id - uses instructor_id + date + time range.
 *
 * @module instructors/[id]/page
 */

import { useState, useEffect, use } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, MessageCircle, Calendar, Clock, Check } from 'lucide-react';
import { fetchAPI } from '@/lib/api';
import { bookingsApi } from '@/lib/api/bookings';
import { BRAND } from '@/app/config/brand';
import { logger } from '@/lib/logger';

// Import centralized types
import type { InstructorProfile } from '@/types/instructor';
import type { BookingCreate, AvailabilitySlot } from '@/types/booking';
import { RequestStatus } from '@/types/api';
import { getErrorMessage } from '@/types/common';

/**
 * Time slot selection state
 * Stores complete context for booking creation
 */
interface SelectedTimeSlot {
  instructorId: number;
  date: string; // "2025-07-15"
  startTime: string; // "09:00"
  endTime: string; // "10:00"
}

/**
 * Instructor Profile Page Component with Booking Flow
 */
export default function InstructorProfilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [instructor, setInstructor] = useState<InstructorProfile | null>(null);
  const [requestStatus, setRequestStatus] = useState<RequestStatus>(RequestStatus.IDLE);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  // Booking flow state
  const [showBookingFlow, setShowBookingFlow] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [availableSlots, setAvailableSlots] = useState<AvailabilitySlot[]>([]);
  const [selectedTimeSlot, setSelectedTimeSlot] = useState<SelectedTimeSlot | null>(null);
  const [selectedService, setSelectedService] = useState<number | null>(null);
  const [studentNote, setStudentNote] = useState('');
  const [bookingLoading, setBookingLoading] = useState(false);
  const [bookingError, setBookingError] = useState<string | null>(null);

  useEffect(() => {
    const fetchInstructor = async () => {
      logger.info('Fetching instructor profile', { instructorId: id });
      setRequestStatus(RequestStatus.LOADING);

      try {
        logger.time(`fetchInstructor-${id}`);
        const response = await fetchAPI(`/instructors/${id}`);
        logger.timeEnd(`fetchInstructor-${id}`);

        if (!response.ok) {
          if (response.status === 404) {
            logger.warn('Instructor not found', {
              instructorId: id,
              status: response.status,
            });
            throw new Error('Instructor not found');
          }

          logger.error('Failed to fetch instructor profile', null, {
            instructorId: id,
            status: response.status,
            statusText: response.statusText,
          });
          throw new Error('Failed to fetch instructor profile');
        }

        const data: InstructorProfile = await response.json();
        logger.info('Instructor profile fetched successfully', {
          instructorId: id,
          userId: data.user_id,
          servicesCount: data.services.length,
          areasCount: data.areas_of_service.length,
        });

        setInstructor(data);
        setRequestStatus(RequestStatus.SUCCESS);
      } catch (err) {
        const errorMessage = getErrorMessage(err);
        logger.error('Error fetching instructor profile', err, {
          instructorId: id,
          errorMessage,
        });

        setError(errorMessage);
        setRequestStatus(RequestStatus.ERROR);
      }
    };

    if (id) {
      fetchInstructor();
    } else {
      logger.warn('No instructor ID provided in route params');
      setError('Invalid instructor ID');
      setRequestStatus(RequestStatus.ERROR);
    }
  }, [id]);

  /**
   * Fetch available slots for selected date
   */
  const fetchAvailableSlots = async (date: string) => {
    if (!instructor) return;

    logger.info('Fetching available slots', {
      instructorId: instructor.user_id,
      date,
    });

    try {
      // Using availability API to get slots for the date
      const response = await fetchAPI(
        `/instructors/availability-windows/week?start_date=${date}&instructor_id=${instructor.user_id}`
      );

      if (!response.ok) {
        throw new Error('Failed to fetch availability');
      }

      const data = await response.json();
      // Extract slots for the specific date
      const slotsForDate = data[date] || [];

      logger.info('Available slots fetched', {
        date,
        slotsCount: slotsForDate.length,
      });

      setAvailableSlots(slotsForDate);
    } catch (err) {
      logger.error('Failed to fetch available slots', err, { date });
      setBookingError('Failed to load available times');
      setAvailableSlots([]);
    }
  };

  /**
   * Handle date selection
   */
  const handleDateChange = (date: string) => {
    setSelectedDate(date);
    setSelectedTimeSlot(null); // Reset time selection
    fetchAvailableSlots(date);
  };

  /**
   * Handle time slot selection
   */
  const handleTimeSlotSelect = (slot: AvailabilitySlot) => {
    if (!instructor) return;

    const timeSlot: SelectedTimeSlot = {
      instructorId: instructor.user_id,
      date: selectedDate,
      startTime: slot.start_time.substring(0, 5), // Convert "HH:MM:SS" to "HH:MM"
      endTime: slot.end_time.substring(0, 5),
    };

    logger.info('Time slot selected', timeSlot);
    setSelectedTimeSlot(timeSlot);
  };

  /**
   * Create booking with new API format
   */
  const handleCreateBooking = async () => {
    if (!selectedTimeSlot || !selectedService || !instructor) {
      logger.warn('Cannot create booking - missing data', {
        hasTimeSlot: !!selectedTimeSlot,
        hasService: !!selectedService,
      });
      return;
    }

    setBookingLoading(true);
    setBookingError(null);

    try {
      // First check availability
      const availabilityCheck = await bookingsApi.checkAvailability({
        instructor_id: selectedTimeSlot.instructorId,
        service_id: selectedService,
        booking_date: selectedTimeSlot.date,
        start_time: selectedTimeSlot.startTime,
        end_time: selectedTimeSlot.endTime,
      });

      if (!availabilityCheck.available) {
        throw new Error(availabilityCheck.reason || 'Time slot not available');
      }

      // Create the booking
      const bookingData: BookingCreate = {
        instructor_id: selectedTimeSlot.instructorId,
        service_id: selectedService,
        booking_date: selectedTimeSlot.date,
        start_time: selectedTimeSlot.startTime,
        end_time: selectedTimeSlot.endTime,
        student_note: studentNote || undefined,
      };

      const booking = await bookingsApi.createBooking(bookingData);

      logger.info('Booking created successfully', {
        bookingId: booking.id,
        status: booking.status,
      });

      // Navigate to booking confirmation or dashboard
      router.push(`/dashboard/student/bookings?highlight=${booking.id}`);
    } catch (err) {
      const errorMessage = getErrorMessage(err);
      logger.error('Failed to create booking', err, { errorMessage });
      setBookingError(errorMessage);
    } finally {
      setBookingLoading(false);
    }
  };

  /**
   * Handle back navigation
   */
  const handleBackClick = () => {
    logger.info('Navigating back to instructors list from profile', {
      instructorId: id,
    });
    router.push('/instructors');
  };

  /**
   * Handle book session button click
   */
  const handleBookSession = () => {
    logger.info('Book session clicked', {
      instructorId: id,
      instructorName: instructor?.user.full_name,
    });
    setShowBookingFlow(true);
  };

  /**
   * Handle message instructor button click
   */
  const handleMessageInstructor = () => {
    logger.info('Message instructor clicked', {
      instructorId: id,
      instructorName: instructor?.user.full_name,
    });
    // TODO: Implement messaging feature
    logger.warn('Messaging feature not yet implemented', { instructorId: id });
  };

  /**
   * Generate next 30 days for date selection
   */
  const generateDateOptions = () => {
    const dates = [];
    const today = new Date();
    for (let i = 1; i <= 30; i++) {
      const date = new Date(today);
      date.setDate(today.getDate() + i);
      dates.push(date.toISOString().split('T')[0]);
    }
    return dates;
  };

  // Loading state
  if (requestStatus === RequestStatus.LOADING) {
    logger.debug('Rendering loading state for instructor profile', { instructorId: id });
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div
          className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"
          role="status"
          aria-label="Loading instructor profile"
        ></div>
      </div>
    );
  }

  // Error state
  if (requestStatus === RequestStatus.ERROR) {
    logger.debug('Rendering error state for instructor profile', {
      instructorId: id,
      error,
    });
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-red-500 mb-2">Error</h2>
          <p className="text-gray-600 dark:text-gray-400 mb-4">{error}</p>
          <button
            onClick={handleBackClick}
            className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
            aria-label="Go back to instructors list"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Browse
          </button>
        </div>
      </div>
    );
  }

  // Instructor not found
  if (!instructor) {
    logger.error('Instructor data is null after successful fetch', null, {
      instructorId: id,
    });
    return null;
  }

  logger.debug('Rendering instructor profile', {
    instructorId: id,
    instructorName: instructor.user.full_name,
    showBookingFlow,
  });

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="container mx-auto px-4 py-8">
        {/* Back Button */}
        <button
          onClick={handleBackClick}
          className="flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 mb-8 transition-colors"
          aria-label="Go back to instructors list"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Browse
        </button>

        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg overflow-hidden">
          {/* Header Section */}
          <div className="p-8 border-b dark:border-gray-700">
            <h1 className="text-3xl font-bold mb-4 dark:text-white">{instructor.user.full_name}</h1>
            <div className="flex flex-wrap gap-4 text-gray-600 dark:text-gray-400">
              <div className="flex items-center gap-2">
                <svg
                  className="h-5 w-5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
                  />
                </svg>
                <span>Areas: {instructor.areas_of_service.join(', ')}</span>
              </div>
              <div className="flex items-center gap-2">
                <svg
                  className="h-5 w-5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <span>{instructor.years_experience} years experience</span>
              </div>
            </div>
          </div>

          {/* Main Content */}
          <div className="p-8">
            {showBookingFlow ? (
              // Booking Flow
              <div className="space-y-6">
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-2xl font-semibold dark:text-white">Book a Session</h2>
                  <button
                    onClick={() => setShowBookingFlow(false)}
                    className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                  >
                    ✕
                  </button>
                </div>

                {/* Error message */}
                {bookingError && (
                  <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 text-red-700 dark:text-red-400">
                    {bookingError}
                  </div>
                )}

                {/* Step 1: Select Service */}
                <div>
                  <h3 className="text-lg font-medium mb-3 dark:text-white">1. Select Service</h3>
                  <div className="space-y-2">
                    {instructor.services.map((service) => (
                      <label
                        key={service.id}
                        className={`flex items-start p-4 border rounded-lg cursor-pointer transition-colors ${
                          selectedService === service.id
                            ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-500'
                            : 'bg-white dark:bg-gray-700 border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600'
                        }`}
                      >
                        <input
                          type="radio"
                          name="service"
                          value={service.id}
                          checked={selectedService === service.id}
                          onChange={() => setSelectedService(service.id)}
                          className="mt-1 mr-3"
                        />
                        <div className="flex-1">
                          <div className="flex justify-between items-start">
                            <div>
                              <h4 className="font-medium dark:text-white">{service.skill}</h4>
                              {service.description && (
                                <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                                  {service.description}
                                </p>
                              )}
                            </div>
                            <span className="text-lg font-semibold text-blue-600 dark:text-blue-400">
                              ${service.hourly_rate}/hr
                            </span>
                          </div>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Step 2: Select Date */}
                <div>
                  <h3 className="text-lg font-medium mb-3 dark:text-white">2. Select Date</h3>
                  <select
                    value={selectedDate}
                    onChange={(e) => handleDateChange(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Choose a date</option>
                    {generateDateOptions().map((date) => (
                      <option key={date} value={date}>
                        {new Date(date + 'T00:00:00').toLocaleDateString('en-US', {
                          weekday: 'long',
                          month: 'long',
                          day: 'numeric',
                        })}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Step 3: Select Time */}
                {selectedDate && (
                  <div>
                    <h3 className="text-lg font-medium mb-3 dark:text-white">3. Select Time</h3>
                    {availableSlots.length === 0 ? (
                      <p className="text-gray-500 dark:text-gray-400">
                        No available times for this date. Please select another date.
                      </p>
                    ) : (
                      <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                        {availableSlots.map((slot, index) => {
                          const isSelected =
                            selectedTimeSlot?.startTime === slot.start_time.substring(0, 5);
                          return (
                            <button
                              key={index}
                              onClick={() => handleTimeSlotSelect(slot)}
                              className={`p-3 rounded-lg border transition-colors ${
                                isSelected
                                  ? 'bg-blue-500 text-white border-blue-500'
                                  : 'bg-white dark:bg-gray-700 border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 text-gray-900 dark:text-white'
                              }`}
                            >
                              <Clock className="h-4 w-4 mx-auto mb-1" />
                              <div className="text-sm">{slot.start_time.substring(0, 5)}</div>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}

                {/* Step 4: Add Note (Optional) */}
                <div>
                  <h3 className="text-lg font-medium mb-3 dark:text-white">
                    4. Add a Note (Optional)
                  </h3>
                  <textarea
                    value={studentNote}
                    onChange={(e) => setStudentNote(e.target.value)}
                    placeholder="Any topics you'd like to focus on or questions you have..."
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    rows={3}
                  />
                </div>

                {/* Summary and Book Button */}
                {selectedService && selectedTimeSlot && (
                  <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
                    <h4 className="font-medium mb-2 dark:text-white">Booking Summary</h4>
                    <div className="space-y-1 text-sm text-gray-600 dark:text-gray-400">
                      <p>
                        Service: {instructor.services.find((s) => s.id === selectedService)?.skill}
                      </p>
                      <p>
                        Date:{' '}
                        {new Date(selectedDate + 'T00:00:00').toLocaleDateString('en-US', {
                          weekday: 'long',
                          month: 'long',
                          day: 'numeric',
                        })}
                      </p>
                      <p>
                        Time: {selectedTimeSlot.startTime} - {selectedTimeSlot.endTime}
                      </p>
                      <p className="font-medium text-gray-900 dark:text-white">
                        Total: $
                        {instructor.services.find((s) => s.id === selectedService)?.hourly_rate ||
                          0}
                      </p>
                    </div>
                  </div>
                )}

                {/* Book Button */}
                <button
                  onClick={handleCreateBooking}
                  disabled={!selectedService || !selectedTimeSlot || bookingLoading}
                  className={`w-full py-3 rounded-lg font-medium transition-colors ${
                    selectedService && selectedTimeSlot && !bookingLoading
                      ? 'bg-blue-500 text-white hover:bg-blue-600'
                      : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                  }`}
                >
                  {bookingLoading ? (
                    <span className="flex items-center justify-center gap-2">
                      <div className="animate-spin rounded-full h-5 w-5 border-2 border-white border-t-transparent" />
                      Creating Booking...
                    </span>
                  ) : (
                    'Confirm Booking'
                  )}
                </button>
              </div>
            ) : (
              // Profile View
              <>
                {/* Services & Pricing Section */}
                <section className="mb-8" aria-labelledby="services-heading">
                  <h2 id="services-heading" className="text-xl font-semibold mb-4 dark:text-white">
                    Services & Pricing
                  </h2>
                  <div className="space-y-3">
                    {instructor.services.map((service) => (
                      <div
                        key={service.id}
                        className="flex justify-between items-start p-4 bg-gray-50 dark:bg-gray-700 rounded-lg"
                      >
                        <div>
                          <h3 className="font-medium text-gray-900 dark:text-white">
                            {service.skill}
                          </h3>
                          {service.description && (
                            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                              {service.description}
                            </p>
                          )}
                        </div>
                        <div className="text-lg font-semibold text-blue-600 dark:text-blue-400">
                          ${service.hourly_rate}/hr
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                {/* Bio Section */}
                <section className="mb-8" aria-labelledby="about-heading">
                  <h2 id="about-heading" className="text-xl font-semibold mb-4 dark:text-white">
                    About
                  </h2>
                  <p className="text-gray-700 dark:text-gray-300 leading-relaxed">
                    {instructor.bio}
                  </p>
                </section>

                {/* Action Buttons */}
                <div className="flex flex-col sm:flex-row gap-4">
                  <button
                    onClick={handleBookSession}
                    className="flex-1 flex items-center justify-center gap-2 bg-blue-500 text-white px-6 py-3 rounded-lg hover:bg-blue-600 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                    aria-label={`Book a session with ${instructor.user.full_name}`}
                  >
                    <Calendar className="h-5 w-5" />
                    Book a Session
                  </button>
                  <button
                    onClick={handleMessageInstructor}
                    className="flex-1 flex items-center justify-center gap-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 px-6 py-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500"
                    aria-label={`Send a message to ${instructor.user.full_name}`}
                  >
                    <MessageCircle className="h-5 w-5" />
                    Message Instructor
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
