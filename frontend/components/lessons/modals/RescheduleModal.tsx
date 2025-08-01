import React, { useState } from 'react';
import { Calendar, Clock, X } from 'lucide-react';
import Modal from '@/components/Modal';
import { Booking } from '@/types/booking';
import { useRescheduleLesson } from '@/hooks/useMyLessons';
import { format, addDays, startOfWeek, isSameDay } from 'date-fns';
import { useQuery } from '@tanstack/react-query';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { queryFn } from '@/lib/react-query/api';

interface RescheduleModalProps {
  isOpen: boolean;
  onClose: () => void;
  lesson: Booking;
}

export function RescheduleModal({ isOpen, onClose, lesson }: RescheduleModalProps) {
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [selectedTime, setSelectedTime] = useState<string | null>(null);

  const rescheduleLesson = useRescheduleLesson();

  // Calculate date range for availability (next 2 weeks)
  const startDate = new Date();
  const endDate = addDays(startDate, 14);

  // Fetch instructor availability
  const { data: availability, isLoading } = useQuery({
    queryKey: queryKeys.availability.week(
      String(lesson.instructor_id),
      format(startDate, 'yyyy-MM-dd')
    ),
    queryFn: queryFn(`/public/instructors/${lesson.instructor_id}/availability`, {
      params: {
        start_date: format(startDate, 'yyyy-MM-dd'),
        end_date: format(endDate, 'yyyy-MM-dd'),
      },
    }),
    staleTime: CACHE_TIMES.FREQUENT,
    enabled: isOpen,
  });

  const handleConfirm = async () => {
    if (!selectedDate || !selectedTime) return;

    const [startTime, endTime] = selectedTime.split('-');

    try {
      await rescheduleLesson.mutateAsync({
        lessonId: lesson.id,
        newDate: format(selectedDate, 'yyyy-MM-dd'),
        newStartTime: startTime,
        newEndTime: endTime,
      });
      onClose();
    } catch (error) {
      console.error('Failed to reschedule:', error);
    }
  };

  // Generate calendar days
  const calendarDays = generateCalendarDays(startDate, endDate);

  // Get available times for selected date
  const availableTimesForDate = selectedDate
    ? getAvailableTimesForDate(availability?.available_slots || [], selectedDate)
    : [];

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Need to reschedule?"
      size="lg"
      footer={
        <div className="flex gap-3 justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2.5 text-gray-700 bg-white border border-gray-300 rounded-lg
                     hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2
                     focus:ring-gray-500 transition-all duration-150 font-medium"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={!selectedDate || !selectedTime || rescheduleLesson.isPending}
            className="px-4 py-2.5 bg-primary text-white rounded-lg hover:bg-primary/90
                     focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary
                     transition-all duration-150 font-medium disabled:opacity-50
                     disabled:cursor-not-allowed"
          >
            {rescheduleLesson.isPending ? 'Rescheduling...' : 'Confirm reschedule'}
          </button>
        </div>
      }
    >
      <div className="space-y-6">
        <p className="text-gray-700">Select a new time with {lesson.instructor?.full_name}</p>

        {/* Calendar Grid */}
        <div className="border rounded-lg p-4">
          <h3 className="font-medium mb-3">{format(startDate, 'MMMM yyyy')}</h3>
          <div className="grid grid-cols-7 gap-1 mb-2">
            {['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'].map((day) => (
              <div key={day} className="text-center text-sm font-medium text-gray-500 py-2">
                {day}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {calendarDays.map((day, index) => {
              const isCurrentBooking = isSameDay(
                day,
                new Date(`${lesson.booking_date}T${lesson.start_time}`)
              );
              const hasAvailability = checkDateHasAvailability(
                availability?.available_slots || [],
                day
              );
              const isPast = day < new Date();

              return (
                <button
                  key={index}
                  onClick={() => setSelectedDate(day)}
                  disabled={isPast || (!hasAvailability && !isLoading)}
                  className={`
                    p-2 text-sm rounded-lg transition-colors relative
                    ${
                      selectedDate && isSameDay(selectedDate, day)
                        ? 'bg-primary text-white'
                        : hasAvailability && !isPast
                          ? 'hover:bg-gray-100 text-gray-900'
                          : 'text-gray-300 cursor-not-allowed'
                    }
                    ${isCurrentBooking ? 'ring-2 ring-primary' : ''}
                  `}
                >
                  {format(day, 'd')}
                  {isCurrentBooking && (
                    <span className="absolute top-0.5 right-0.5 text-xs">X</span>
                  )}
                  {hasAvailability && !isPast && (
                    <span className="absolute bottom-0.5 left-1/2 transform -translate-x-1/2 w-1 h-1 bg-green-500 rounded-full" />
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Time Slots */}
        {selectedDate && (
          <div>
            <h3 className="font-medium mb-3">
              Available times on {format(selectedDate, 'EEEE, MMMM d')}:
            </h3>
            {availableTimesForDate.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {availableTimesForDate.map((slot) => (
                  <button
                    key={slot}
                    onClick={() => setSelectedTime(slot)}
                    className={`
                      px-4 py-2 rounded-lg border transition-colors
                      ${
                        selectedTime === slot
                          ? 'bg-primary text-white border-primary'
                          : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                      }
                    `}
                  >
                    {formatTimeSlot(slot)}
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-gray-500">No available times on this date</p>
            )}
          </div>
        )}

        {/* Current Lesson Info */}
        <div className="bg-gray-50 rounded-lg p-4">
          <p className="text-sm text-gray-600">
            Current lesson:{' '}
            {format(new Date(`${lesson.booking_date}T${lesson.start_time}`), 'EEE MMM d')} at{' '}
            {format(new Date(`${lesson.booking_date}T${lesson.start_time}`), 'h:mm a')}
          </p>
        </div>

        {/* Alternative Options */}
        <div className="text-center">
          <p className="text-sm text-gray-600">
            Prefer to discuss?{' '}
            <button
              onClick={() => {
                onClose();
                // Open chat
              }}
              className="text-primary hover:underline"
            >
              Chat to reschedule
            </button>
          </p>
        </div>
      </div>
    </Modal>
  );
}

// Helper functions
function generateCalendarDays(start: Date, end: Date): Date[] {
  const days: Date[] = [];
  const startOfCalendar = startOfWeek(start, { weekStartsOn: 1 });

  for (let i = 0; i < 14; i++) {
    days.push(addDays(startOfCalendar, i));
  }

  return days;
}

function checkDateHasAvailability(slots: any[], date: Date): boolean {
  const dateStr = format(date, 'yyyy-MM-dd');
  return slots.some((slot) => slot.date === dateStr);
}

function getAvailableTimesForDate(slots: any[], date: Date): string[] {
  const dateStr = format(date, 'yyyy-MM-dd');
  return slots
    .filter((slot) => slot.date === dateStr)
    .map((slot) => `${slot.start_time}-${slot.end_time}`);
}

function formatTimeSlot(slot: string): string {
  const [start] = slot.split('-');
  const [hours, minutes] = start.split(':');
  const date = new Date();
  date.setHours(parseInt(hours), parseInt(minutes));
  return format(date, 'h:mm a');
}
