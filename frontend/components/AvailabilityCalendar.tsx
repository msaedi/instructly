// frontend/components/AvailabilityCalendar.tsx
'use client';

import { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

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
}

export default function AvailabilityCalendar({ instructorId }: AvailabilityCalendarProps) {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [availability, setAvailability] = useState<AvailabilityDay[]>([]);
  const [loading, setLoading] = useState(true);

  // Generate next 14 days starting from today
  const generateNext14Days = () => {
    const days = [];
    const today = new Date();

    for (let i = 0; i < 14; i++) {
      const date = new Date(today);
      date.setDate(today.getDate() + i);
      days.push({
        date: date.toISOString().split('T')[0],
        dayName: date.toLocaleDateString('en-US', { weekday: 'short' }),
        dayNumber: date.getDate(),
        isToday: i === 0,
      });
    }
    return days;
  };

  const next14Days = generateNext14Days();

  // Fetch availability data
  useEffect(() => {
    const fetchAvailability = async () => {
      setLoading(true);
      try {
        const startDate = next14Days[0].date;
        const endDate = next14Days[next14Days.length - 1].date;

        // Mock data for now - replace with actual API call
        const mockAvailability: AvailabilityDay[] = next14Days.map((day) => ({
          date: day.date,
          slots:
            Math.random() > 0.3
              ? [
                  { start_time: '09:00', end_time: '10:00', is_available: true },
                  { start_time: '10:00', end_time: '11:00', is_available: true },
                  { start_time: '14:00', end_time: '15:00', is_available: true },
                  { start_time: '15:00', end_time: '16:00', is_available: true },
                  { start_time: '17:00', end_time: '18:00', is_available: true },
                ]
              : [],
        }));

        setAvailability(mockAvailability);
      } catch (error) {
        console.error('Failed to fetch availability:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchAvailability();
  }, [instructorId]);

  const getAvailableSlots = (date: string) => {
    const dayAvailability = availability.find((day) => day.date === date);
    return dayAvailability?.slots.filter((slot) => slot.is_available) || [];
  };

  const hasAvailability = (date: string) => {
    return getAvailableSlots(date).length > 0;
  };

  const groupSlotsByTimeOfDay = (slots: TimeSlot[]) => {
    const morning = slots.filter((slot) => {
      const hour = parseInt(slot.start_time.split(':')[0]);
      return hour < 12;
    });

    const afternoon = slots.filter((slot) => {
      const hour = parseInt(slot.start_time.split(':')[0]);
      return hour >= 12 && hour < 17;
    });

    const evening = slots.filter((slot) => {
      const hour = parseInt(slot.start_time.split(':')[0]);
      return hour >= 17;
    });

    return { morning, afternoon, evening };
  };

  const formatTime = (time: string) => {
    const [hours, minutes] = time.split(':');
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour % 12 || 12;
    return `${displayHour}:${minutes}${ampm}`;
  };

  const handleTimeSlotSelect = (date: string, startTime: string, endTime: string) => {
    // TODO: Navigate to booking page or open booking modal
    console.log('Selected time slot:', { date, startTime, endTime });
    alert(`Selected: ${new Date(date).toLocaleDateString()} at ${formatTime(startTime)}`);
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
    </div>
  );
}
