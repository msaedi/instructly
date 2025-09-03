// frontend/components/AvailabilityCalendar.tsx
'use client';

import { useState, useEffect } from 'react';
import { publicApi } from '@/features/shared/api/client';
import { logger } from '@/lib/logger';
import TimeSelectionModal from '@/features/student/booking/components/TimeSelectionModal';
import { Instructor } from '@/features/student/booking/types';
import { getBookingIntent, clearBookingIntent } from '@/features/student/booking';
import { at } from '@/lib/ts/safe';

interface TimeSlot {
  start_time: string;
  end_time: string;
  is_available: boolean;
}

interface AvailabilityDay {
  date: string;
  slots: TimeSlot[];
}

interface AvailabilityCalendarProps {
  instructorId: string;
  instructor: Instructor;
}

export default function AvailabilityCalendar({
  instructorId,
  instructor,
}: AvailabilityCalendarProps) {

  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [availability, setAvailability] = useState<AvailabilityDay[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal State
  const [isTimeSelectionModalOpen, setIsTimeSelectionModalOpen] = useState(false);
  const [selectedTime, setSelectedTime] = useState<string>('');
  const [preSelectedDate, setPreSelectedDate] = useState<string | undefined>();
  const [preSelectedTime, setPreSelectedTime] = useState<string | undefined>();
  const [preSelectedServiceId, setPreSelectedServiceId] = useState<string | undefined>();
  const [shouldOpenModalFromIntent, setShouldOpenModalFromIntent] = useState(false);

  // Handle time slot selection - opens TimeSelectionModal with pre-selected values
  const handleTimeSlotSelect = (date: string, startTime: string, endTime: string) => {
    setPreSelectedDate(date);
    setPreSelectedTime(startTime);
    setSelectedDate(date);
    setSelectedTime(startTime);
    setIsTimeSelectionModalOpen(true);
    logger.info('Time slot selected - opening TimeSelectionModal', {
      date,
      startTime,
      endTime,
      instructorId,
    });
  };

  // (Time selection is handled internally by TimeSelectionModal)

  // Handle modal closures
  const handleCloseTimeSelectionModal = () => {
    setIsTimeSelectionModalOpen(false);
    setPreSelectedDate(undefined);
    setPreSelectedTime(undefined);
    setPreSelectedServiceId(undefined);
  };

  // Generate next 14 days starting from today - memoize to avoid regeneration
  const [next14Days] = useState(() => {
    const days = [];
    const today = new Date();

    for (let i = 0; i < 14; i++) {
      const date = new Date(today);
      date.setDate(today.getDate() + i);
      days.push({
        date: at(date.toISOString().split('T'), 0) || '',
        dayName: date.toLocaleDateString('en-US', { weekday: 'short' }),
        dayNumber: date.getDate(),
        isToday: i === 0,
      });
    }
    return days;
  });

  // Check for stored booking intent on mount
  useEffect(() => {
    const intent = getBookingIntent();
    logger.info('Checking for booking intent', {
      hasIntent: !!intent,
      instructorId: instructor.user_id,
      intentInstructorId: intent?.instructorId,
    });

    if (intent && intent.instructorId === instructor.user_id) {
      logger.info('Found matching booking intent, restoring state', intent);
      setSelectedDate(intent.date);
      setSelectedTime(intent.time);
      setPreSelectedDate(intent.date);
      setPreSelectedTime(intent.time);
      if (intent.serviceId) {
        setPreSelectedServiceId(intent.serviceId);
      }
      setShouldOpenModalFromIntent(true);
      clearBookingIntent();
    }
  }, [instructor.user_id]);

  // Open modal when booking intent is restored
  useEffect(() => {
    if (shouldOpenModalFromIntent && selectedDate && selectedTime && !loading) {
      setIsTimeSelectionModalOpen(true);
      setPreSelectedDate(selectedDate);
      setPreSelectedTime(selectedTime);
      setShouldOpenModalFromIntent(false);
    }
  }, [shouldOpenModalFromIntent, selectedDate, selectedTime, loading]);

  // Fetch availability data
  useEffect(() => {
    const fetchAvailability = async () => {
      setLoading(true);
      setError(null);
      try {
        const firstDay = at(next14Days, 0);
        const lastDay = at(next14Days, next14Days.length - 1);
        if (!firstDay || !lastDay) {
          throw new Error('Invalid date range');
        }
        const startDate = firstDay.date;
        const endDate = lastDay.date;

        logger.info('Fetching availability for instructor', { instructorId, startDate, endDate });

        // Call the real availability API
        const response = await publicApi.getInstructorAvailability(instructorId, {
          start_date: startDate,
          end_date: endDate,
        });

        logger.debug('Availability API response received', {
          hasData: !!response.data,
          hasError: !!response.error,
          status: response.status,
          dataKeys: response.data ? Object.keys(response.data) : [],
        });

        if (response.data) {
          // Transform API response to our expected format
          const availabilityMap = new Map<string, TimeSlot[]>();

          if (response.data.availability_by_date) {
            Object.entries(response.data.availability_by_date).forEach(
              ([date, dayData]: [string, { available_slots?: { start_time: string; end_time: string }[] }]) => {
                const slots = dayData.available_slots
                  ? dayData.available_slots.map((slot: { start_time: string; end_time: string }) => ({
                      start_time: slot.start_time,
                      end_time: slot.end_time,
                      is_available: true, // All slots from available_slots are available
                    }))
                  : [];
                availabilityMap.set(date, slots);
              }
            );
          }

          // Create availability data for all 14 days
          const availabilityData: AvailabilityDay[] = next14Days.map((day) => {
            const date = day?.date;
            if (!date) return { date: '', slots: [] };
            return {
              date,
              slots: availabilityMap.get(date) || [],
            };
          }).filter(day => day.date !== '') as AvailabilityDay[];

          setAvailability(availabilityData);
          logger.info('Availability data processed successfully', {
            totalDays: availabilityData.length,
            daysWithSlots: availabilityData.filter((day) => day.slots.length > 0).length,
          });
        } else {
          setError(response.error || 'Failed to load availability');
          // Fall back to empty availability
          setAvailability(next14Days.map((day) => ({ date: day?.date || '', slots: [] })).filter(day => day.date !== ''));
        }
      } catch (error) {
        logger.error('Failed to fetch availability', error, { instructorId });
        setError('Unable to load availability. Please try again.');
        // Fall back to empty availability on error
        setAvailability(next14Days.map((day) => ({ date: day.date, slots: [] })));
      } finally {
        setLoading(false);
      }
    };

    fetchAvailability();
  }, [instructorId, next14Days]);

  const getAvailableSlots = (date: string) => {
    const dayAvailability = availability.find((day) => day.date === date);
    const allSlots = dayAvailability?.slots.filter((slot) => slot.is_available) || [];

    // Filter out past time slots
    const now = new Date();
    return allSlots.filter((slot) => {
      const slotDateTime = new Date(`${date}T${slot.start_time}`);
      return slotDateTime > now;
    });
  };

  const hasAvailability = (date: string) => {
    return getAvailableSlots(date).length > 0;
  };

  const groupSlotsByTimeOfDay = (slots: TimeSlot[]) => {
    const morning = slots.filter((slot) => {
      const timeParts = slot.start_time.split(':');
      const hourStr = at(timeParts, 0);
      if (!hourStr) return false;
      const hour = parseInt(hourStr);
      return hour < 12;
    });

    const afternoon = slots.filter((slot) => {
      const timeParts = slot.start_time.split(':');
      const hourStr = at(timeParts, 0);
      if (!hourStr) return false;
      const hour = parseInt(hourStr);
      return hour >= 12 && hour < 17;
    });

    const evening = slots.filter((slot) => {
      const timeParts = slot.start_time.split(':');
      const hourStr = at(timeParts, 0);
      if (!hourStr) return false;
      const hour = parseInt(hourStr);
      return hour >= 17;
    });

    return { morning, afternoon, evening };
  };

  const formatTime = (time: string) => {
    const timeParts = time.split(':');
    const hours = at(timeParts, 0);
    const minutes = at(timeParts, 1);
    if (!hours || !minutes) return '';
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour % 12 || 12;
    return `${displayHour}:${minutes}${ampm}`;
  };

  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
        <div className="animate-pulse">
          <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-1/3 mb-4"></div>
          <div className="grid grid-cols-7 gap-2">
            {Array.from({ length: 14 }).map((_, i) => (
              <div key={i} className="h-12 bg-gray-200 dark:bg-gray-700 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  const selectedDaySlots = selectedDate ? getAvailableSlots(selectedDate) : [];
  const groupedSlots = groupSlotsByTimeOfDay(selectedDaySlots);

  // Check if instructor has any availability at all
  const hasAnyAvailability = availability.some((day) => day.slots.length > 0);

  if (error) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
        <div className="text-center py-8">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
            Unable to Load Availability
          </h3>
          <p className="text-gray-600 dark:text-gray-400 mb-4">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-2">Availability</h3>
        <p className="text-sm text-gray-600">Select a day to see available times</p>
      </div>

      {/* 14-day calendar grid */}
      <div className="mb-6">
        <div className="grid grid-cols-7 gap-2 mb-4">
          {next14Days.map((day) => (
            <button
              key={day.date}
              onClick={() => setSelectedDate(day.date)}
              disabled={!hasAvailability(day.date)}
              className={`
                p-3 text-center rounded-lg border-2 transition-all
                ${
                  day.isToday
                    ? 'border-blue-500 dark:border-blue-400'
                    : 'border-gray-200 dark:border-gray-600'
                }
                ${selectedDate === day.date ? 'bg-blue-600 text-white border-blue-600' : ''}
                ${
                  hasAvailability(day.date)
                    ? 'hover:border-blue-300 dark:hover:border-blue-400 cursor-pointer'
                    : 'opacity-50 cursor-not-allowed bg-gray-50 dark:bg-gray-700'
                }
                ${
                  !selectedDate && hasAvailability(day.date) && !day.isToday
                    ? 'hover:bg-gray-50 dark:hover:bg-gray-700'
                    : ''
                }
              `}
            >
              <div className="text-xs font-medium">{day.dayName}</div>
              <div className="text-sm font-semibold">{day.dayNumber}</div>
              {hasAvailability(day.date) && (
                <div className="w-2 h-2 bg-green-500 rounded-full mx-auto mt-1"></div>
              )}
            </button>
          ))}
        </div>

        <div className="flex items-center text-xs text-gray-600 space-x-4">
          <div className="flex items-center">
            <div className="w-2 h-2 bg-green-500 rounded-full mr-1"></div>
            <span>Has availability</span>
          </div>
          <div className="flex items-center">
            <div className="w-2 h-2 bg-gray-300 rounded-full mr-1"></div>
            <span>Fully booked</span>
          </div>
        </div>

        {/* No availability message */}
        {!hasAnyAvailability && (
          <div className="mt-4 p-4 bg-gray-50 dark:bg-gray-700 rounded-lg text-center">
            <p className="text-gray-600 dark:text-gray-400 text-sm">
              This instructor has no available times in the next 14 days.
            </p>
            <p className="text-gray-500 dark:text-gray-500 text-xs mt-1">
              Try contacting them directly or check back later.
            </p>
          </div>
        )}
      </div>

      {/* Time slots for selected day */}
      {selectedDate && (
        <div className="border-t pt-6">
          <h4 className="font-medium text-gray-900 mb-4">
            {new Date(selectedDate).toLocaleDateString('en-US', {
              weekday: 'long',
              month: 'long',
              day: 'numeric',
            })}
          </h4>

          {selectedDaySlots.length === 0 ? (
            <p className="text-gray-500 text-center py-4">No available times for this day</p>
          ) : (
            <div className="space-y-6">
              {groupedSlots.morning.length > 0 && (
                <div>
                  <h5 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-3">
                    Morning
                  </h5>
                  <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                    {groupedSlots.morning.map((slot, index) => (
                      <button
                        key={index}
                        onClick={() =>
                          handleTimeSlotSelect(selectedDate, slot.start_time, slot.end_time)
                        }
                        className="min-h-[44px] px-3 py-2 text-sm border-2 border-gray-200 dark:border-gray-600 rounded-lg hover:border-blue-600 hover:bg-blue-50 dark:hover:bg-gray-700 dark:hover:border-blue-400 transition-colors dark:text-white cursor-pointer"
                      >
                        {formatTime(slot.start_time)}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {groupedSlots.afternoon.length > 0 && (
                <div>
                  <h5 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-3">
                    Afternoon
                  </h5>
                  <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                    {groupedSlots.afternoon.map((slot, index) => (
                      <button
                        key={index}
                        onClick={() =>
                          handleTimeSlotSelect(selectedDate, slot.start_time, slot.end_time)
                        }
                        className="min-h-[44px] px-3 py-2 text-sm border-2 border-gray-200 dark:border-gray-600 rounded-lg hover:border-blue-600 hover:bg-blue-50 dark:hover:bg-gray-700 dark:hover:border-blue-400 transition-colors dark:text-white cursor-pointer"
                      >
                        {formatTime(slot.start_time)}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {groupedSlots.evening.length > 0 && (
                <div>
                  <h5 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-3">
                    Evening
                  </h5>
                  <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                    {groupedSlots.evening.map((slot, index) => (
                      <button
                        key={index}
                        onClick={() =>
                          handleTimeSlotSelect(selectedDate, slot.start_time, slot.end_time)
                        }
                        className="min-h-[44px] px-3 py-2 text-sm border-2 border-gray-200 dark:border-gray-600 rounded-lg hover:border-blue-600 hover:bg-blue-50 dark:hover:bg-gray-700 dark:hover:border-blue-400 transition-colors dark:text-white cursor-pointer"
                      >
                        {formatTime(slot.start_time)}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Time Selection Modal */}
      <TimeSelectionModal
        isOpen={isTimeSelectionModalOpen}
        onClose={handleCloseTimeSelectionModal}
        instructor={instructor}
        preSelectedDate={preSelectedDate}
        preSelectedTime={preSelectedTime}
        serviceId={preSelectedServiceId}
        // Don't pass onTimeSelected - let TimeSelectionModal handle navigation
      />
    </div>
  );
}
