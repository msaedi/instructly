'use client';

import { useState, useEffect, useRef, useCallback, useMemo, useReducer } from 'react';
import { flushSync } from 'react-dom';
import { X, ArrowLeft } from 'lucide-react';
import { format } from 'date-fns';
import { logger } from '@/lib/logger';
import { at } from '@/lib/ts/safe';
import { publicApi } from '@/features/shared/api/client';
import { useAuth } from '@/features/shared/hooks/useAuth';
import Calendar from '@/features/student/booking/components/TimeSelectionModal/Calendar';
import TimeDropdown from '@/features/student/booking/components/TimeSelectionModal/TimeDropdown';
import DurationButtons from '@/features/student/booking/components/TimeSelectionModal/DurationButtons';
import SummarySection from '@/features/student/booking/components/TimeSelectionModal/SummarySection';

// Type for availability slots
interface AvailabilitySlot {
  start_time: string;
  end_time: string;
}

type AvailabilityByDate = Record<string, { date: string; available_slots: AvailabilitySlot[]; is_blackout: boolean }>;

type State = {
  loadingAvailability: boolean;
  loadingTimeSlots: boolean;
  selectedDate: string | null;
  selectedTime: string | null;
  showTimeDropdown: boolean;
  timeSlots: string[];
  availableDates: string[];
  availabilityData: AvailabilityByDate | null;
};

type Action =
  | { type: 'AVAILABILITY_LOAD_START' }
  | { type: 'AVAILABILITY_LOAD_SUCCESS'; payload: { availabilityData: AvailabilityByDate; availableDates: string[]; selectedDate: string | null; timeSlots: string[]; selectedTime: string | null; showTimeDropdown: boolean } }
  | { type: 'AVAILABILITY_LOAD_FAIL' }
  | { type: 'DATE_SELECT_START'; payload: { selectedDate: string } }
  | { type: 'DATE_SELECT_SUCCESS'; payload: { timeSlots: string[]; selectedTime: string | null } }
  | { type: 'DATE_SELECT_FAIL' }
  | { type: 'SET_SELECTED_TIME'; payload: { selectedTime: string } };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'AVAILABILITY_LOAD_START':
      return { ...state, loadingAvailability: true };
    case 'AVAILABILITY_LOAD_SUCCESS':
      return {
        ...state,
        loadingAvailability: false,
        availabilityData: action.payload.availabilityData,
        availableDates: action.payload.availableDates,
        selectedDate: action.payload.selectedDate,
        timeSlots: action.payload.timeSlots,
        selectedTime: action.payload.selectedTime,
        showTimeDropdown: action.payload.showTimeDropdown,
      };
    case 'AVAILABILITY_LOAD_FAIL':
      return { ...state, loadingAvailability: false };
    case 'DATE_SELECT_START':
      return {
        ...state,
        loadingTimeSlots: true,
        selectedDate: action.payload.selectedDate,
        showTimeDropdown: true,
        selectedTime: null,
      };
    case 'DATE_SELECT_SUCCESS':
      return {
        ...state,
        loadingTimeSlots: false,
        timeSlots: action.payload.timeSlots,
        selectedTime: action.payload.selectedTime,
      };
    case 'DATE_SELECT_FAIL':
      return { ...state, loadingTimeSlots: false };
    case 'SET_SELECTED_TIME':
      return { ...state, selectedTime: action.payload.selectedTime };
    default:
      return state;
  }
}

interface RescheduleTimeSelectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  instructor: {
    user_id: string;
    user: {
      first_name: string;
      last_initial: string;
    };
    services: Array<{
      id?: string;
      duration_options: number[];
      hourly_rate: number;
      skill: string;
    }>;
  };
  onTimeSelected?: (selection: { date: string; time: string; duration: number }) => void;
  onOpenChat?: () => void;
  currentLesson?: {
    date: string;
    time: string;
    service: string;
  };
}

export default function RescheduleTimeSelectionModal({
  isOpen,
  onClose,
  instructor,
  onTimeSelected,
  onOpenChat,
  currentLesson,
}: RescheduleTimeSelectionModalProps) {
  const { user } = useAuth();

  // Check if lesson is within 12 hours - should not be reschedulable
  const checkCanReschedule = () => {
    if (!currentLesson) return true;
    const lessonDateTime = new Date(`${currentLesson.date}T${currentLesson.time}`);
    const hoursUntilLesson = (lessonDateTime.getTime() - Date.now()) / (1000 * 60 * 60);
    return hoursUntilLesson >= 12;
  };

  const canReschedule = checkCanReschedule();
  const studentTimezone = (user as unknown as Record<string, unknown>)?.timezone as string || Intl.DateTimeFormat().resolvedOptions().timeZone;

  const formatDateInTz = (d: Date, tz: string) => {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: tz,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    } as const).format(d);
  };


  // Get duration options from the service
  const getDurationOptions = useCallback(() => {
    const selectedService = at(instructor.services, 0);
    const durations = selectedService?.duration_options || [30, 60, 90, 120];
    const hourlyRate = selectedService?.hourly_rate || 100;

    return durations.map((duration) => ({
      duration,
      price: Math.round((hourlyRate * duration) / 60),
    }));
  }, [instructor.services]);

  const durationOptions = useMemo(() => getDurationOptions(), [getDurationOptions]);

  // Component state
  const [selectedDuration, setSelectedDuration] = useState<number>(
    durationOptions.length > 0
      ? Math.min(...durationOptions.map((o) => o.duration))
      : 60
  );
  const [currentMonth, setCurrentMonth] = useState<Date>(new Date());
  const [disabledDurations] = useState<number[]>([]);
  const [state, dispatch] = useReducer(reducer, {
    loadingAvailability: false,
    loadingTimeSlots: false,
    selectedDate: null,
    selectedTime: null,
    showTimeDropdown: false,
    timeSlots: [],
    availableDates: [],
    availabilityData: null,
  });
  const { selectedDate, selectedTime, showTimeDropdown, timeSlots, availableDates, loadingAvailability, loadingTimeSlots, availabilityData } = state;

  const modalRef = useRef<HTMLDivElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);

  // Get instructor display name
  const getInstructorDisplayName = () => {
    const firstName = instructor.user.first_name;
    const lastInitial = instructor.user.last_initial;
    return `${firstName} ${lastInitial}.`;
  };

  const isMountedRef = useRef(true);
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const fetchAvailability = useCallback(async () => {
    dispatch({ type: 'AVAILABILITY_LOAD_START' });
    try {
      const today = new Date();
      const endDate = new Date();
      endDate.setDate(today.getDate() + 30);

      const localDateStr = formatDateInTz(today, studentTimezone);
      const localEndStr = formatDateInTz(endDate, studentTimezone);

      const response = await publicApi.getInstructorAvailability(instructor.user_id.toString(), {
        start_date: localDateStr,
        end_date: localEndStr,
      });

      if (response.data?.availability_by_date) {
        const availabilityByDate = response.data.availability_by_date as AvailabilityByDate;
        const datesWithSlots: string[] = [];
        Object.keys(availabilityByDate).forEach((date) => {
          const dateData = availabilityByDate[date];
          if (!dateData) return;
          const slots = dateData.available_slots || [];
          const now = new Date();
          const nowLocalStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
          const isToday = date === nowLocalStr;

          const validSlots = slots.filter((slot: AvailabilitySlot) => {
            if (!isToday) return true;
            const parts = slot.start_time.split(':');
            const hours = at(parts, 0);
            const minutes = at(parts, 1);
            if (!hours || !minutes) return false;
            const slotTime = new Date();
            slotTime.setHours(parseInt(hours), parseInt(minutes), 0, 0);
            return slotTime > now;
          });

          if (validSlots.length > 0) {
            datesWithSlots.push(date);
          }
        });

        let nextSelectedDate: string | null = null;
        let nextTimeSlots: string[] = [];
        let nextSelectedTime: string | null = null;
        let nextShowDropdown = false;

        if (datesWithSlots.length > 0) {
          const firstDate = at(datesWithSlots, 0);
          if (!firstDate) {
            if (!isMountedRef.current) return;
            dispatch({
              type: 'AVAILABILITY_LOAD_SUCCESS',
              payload: {
                availabilityData: availabilityByDate,
                availableDates: datesWithSlots,
                selectedDate: null,
                timeSlots: [],
                selectedTime: null,
                showTimeDropdown: false,
              },
            });
            return;
          }
          const firstDateData = availabilityByDate[firstDate];
          if (!firstDateData) {
            if (!isMountedRef.current) return;
            dispatch({
              type: 'AVAILABILITY_LOAD_SUCCESS',
              payload: {
                availabilityData: availabilityByDate,
                availableDates: datesWithSlots,
                selectedDate: null,
                timeSlots: [],
                selectedTime: null,
                showTimeDropdown: false,
              },
            });
            return;
          }
          const slots = firstDateData.available_slots || [];
          const expandDiscreteStarts = (
            start: string,
            end: string,
            stepMinutes: number,
            requiredMinutes: number
          ): string[] => {
            const startParts = start.split(':');
            const endParts = end.split(':');
            const sh = parseInt(at(startParts, 0) || '0', 10);
            const sm = parseInt(at(startParts, 1) || '0', 10);
            const eh = parseInt(at(endParts, 0) || '0', 10);
            const em = parseInt(at(endParts, 1) || '0', 10);
            const startTotal = sh * 60 + sm;
            const endTotal = eh * 60 + em;

            const times: string[] = [];
            for (let t = startTotal; t + requiredMinutes <= endTotal; t += stepMinutes) {
              const h = Math.floor(t / 60);
              const m = t % 60;
              const ampm = h >= 12 ? 'pm' : 'am';
              const displayHour = (h % 12) || 12;
              times.push(`${displayHour}:${String(m).padStart(2, '0')}${ampm}`);
            }
            return times;
          };

          const formattedSlots = slots.flatMap((slot: AvailabilitySlot) =>
            expandDiscreteStarts(slot.start_time, slot.end_time, 60, selectedDuration)
          );

          nextSelectedDate = firstDate;
          nextShowDropdown = true;
          nextTimeSlots = formattedSlots;
          if (formattedSlots.length > 0) {
            const firstSlot = at(formattedSlots, 0);
            if (firstSlot) nextSelectedTime = firstSlot;
          }
        }

        if (!isMountedRef.current) return;
        flushSync(() => {
          dispatch({
            type: 'AVAILABILITY_LOAD_SUCCESS',
            payload: {
              availabilityData: availabilityByDate,
              availableDates: datesWithSlots,
              selectedDate: nextSelectedDate,
              timeSlots: nextTimeSlots,
              selectedTime: nextSelectedTime,
              showTimeDropdown: nextShowDropdown,
            },
          });
        });
      }
    } catch (error) {
      logger.error('Failed to fetch availability', error);
      if (!isMountedRef.current) return;
      dispatch({ type: 'AVAILABILITY_LOAD_FAIL' });
    }
  }, [instructor.user_id, studentTimezone, selectedDuration]);

  // Fetch availability data when modal opens
  useEffect(() => {
    if (isOpen && instructor.user_id) {
      fetchAvailability();
    }
  }, [isOpen, instructor.user_id, fetchAvailability]);

  // Handle date selection
  const handleDateSelect = useCallback(
    (date: string) => {
      dispatch({ type: 'DATE_SELECT_START', payload: { selectedDate: date } });

      const dateData = availabilityData?.[date];
      if (availabilityData && dateData) {
        const slots = dateData.available_slots || [];

        const expandDiscreteStarts = (
          start: string,
          end: string,
          stepMinutes: number,
          requiredMinutes: number
        ): string[] => {
          const startParts = start.split(':');
          const endParts = end.split(':');
          const sh = parseInt(at(startParts, 0) || '0', 10);
          const sm = parseInt(at(startParts, 1) || '0', 10);
          const eh = parseInt(at(endParts, 0) || '0', 10);
          const em = parseInt(at(endParts, 1) || '0', 10);
          const startTotal = sh * 60 + sm;
          const endTotal = eh * 60 + em;

          const times: string[] = [];
          for (let t = startTotal; t + requiredMinutes <= endTotal; t += stepMinutes) {
            const h = Math.floor(t / 60);
            const m = t % 60;
            const ampm = h >= 12 ? 'pm' : 'am';
            const displayHour = (h % 12) || 12;
            times.push(`${displayHour}:${String(m).padStart(2, '0')}${ampm}`);
          }
          return times;
        };

        const formattedSlots = slots.flatMap((slot: AvailabilitySlot) =>
          expandDiscreteStarts(slot.start_time, slot.end_time, 60, selectedDuration)
        );

        if (!isMountedRef.current) return;
        dispatch({
          type: 'DATE_SELECT_SUCCESS',
          payload: { timeSlots: formattedSlots, selectedTime: at(formattedSlots, 0) || null },
        });
      }
      // If there was no availability data for the selected date, just stop loading
      if (!isMountedRef.current) return;
      dispatch({ type: 'DATE_SELECT_FAIL' });
    },
    [availabilityData, selectedDuration]
  );

  // Handle time selection
  const handleTimeSelect = (time: string) => {
    dispatch({ type: 'SET_SELECTED_TIME', payload: { selectedTime: time } });
  };

  // Handle escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      previousActiveElement.current = document.activeElement as HTMLElement;
      modalRef.current?.focus();
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      if (!isOpen && previousActiveElement.current) {
        previousActiveElement.current.focus();
      }
    };
  }, [isOpen, onClose]);

  // Body scroll lock
  useEffect(() => {
    if (isOpen) {
      const originalStyle = window.getComputedStyle(document.body).overflow;
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = originalStyle;
      };
    }
  }, [isOpen]);

  // Handle backdrop click
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  // Handle continue button
  const handleContinue = () => {
    if (selectedDate && selectedTime && onTimeSelected) {
      onTimeSelected({
        date: selectedDate,
        time: selectedTime,
        duration: selectedDuration,
      });
    }
  };

  // Calculate price
  const getCurrentPrice = () => {
    const service = at(instructor.services, 0);
    const hourlyRate = service?.hourly_rate || 100;
    return Math.round((hourlyRate * selectedDuration) / 60);
  };

  if (!isOpen) return null;

  // If cannot reschedule, show error message
  if (!canReschedule) {
    return (
      <div className="fixed inset-0 z-50 overflow-y-auto" style={{ backgroundColor: 'rgba(0, 0, 0, 0.5)' }}>
        <div className="flex min-h-full items-center justify-center p-4">
          <div className="bg-white rounded-xl p-6 max-w-md w-full">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Cannot Reschedule</h3>
            <p className="text-gray-600 mb-4">
              Lessons cannot be rescheduled within 12 hours of the start time.
            </p>
            <p className="text-sm text-gray-500 mb-6">
              If you need to make changes, please contact your instructor directly through chat.
            </p>
            <div className="flex gap-3">
              <button
                onClick={onClose}
                className="flex-1 py-2 px-4 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
              >
                Close
              </button>
              {onOpenChat && (
                <button
                  onClick={() => {
                    onClose();
                    onOpenChat();
                  }}
                  className="flex-1 py-2 px-4 bg-[#6A0DAD] text-white rounded-lg hover:bg-[#6A0DAD] transition-colors"
                >
                  Chat with Instructor
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Copy the exact structure from TimeSelectionModal
  return (
    <>
      {/* Mobile Full Screen View */}
      <div className="md:hidden fixed inset-0 z-50 bg-white dark:bg-gray-900">
        <div className="h-full flex flex-col">
          {/* Mobile Header */}
          <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
            <button
              onClick={onClose}
              className="p-2 -ml-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
              aria-label="Go back"
            >
              <ArrowLeft className="h-6 w-6 text-gray-600 dark:text-gray-400" />
            </button>
            <h2 className="text-2xl font-medium text-gray-900 dark:text-white">
              Need to reschedule?
            </h2>
            <div className="w-10" />
          </div>

          {/* Subtext */}
          <div className="px-4 pt-4 pb-2">
            <p className="text-gray-600">
              Choose a new lesson date & time below.
            </p>
          </div>

          {/* Instructor Name */}
          <div className="px-4 pb-2">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-8 h-8 rounded-full overflow-hidden">
                {/* Use avatar component if available in this module scope */}
                {/* We avoid importing heavy components into this modal; placeholder kept minimal */}
                <div className="w-8 h-8 bg-gray-200" />
              </div>
              <p className="text-base font-bold text-black">
                {getInstructorDisplayName()}&apos;s availability
              </p>
            </div>
            {currentLesson && (
              <div className="p-2 bg-yellow-50 rounded-lg">
                <p className="text-sm text-gray-600">
                  <span className="font-medium">Current lesson:</span>{' '}
                  {format(new Date(`${currentLesson.date}T${currentLesson.time}`), 'EEE MMM d')} at{' '}
                  {format(new Date(`${currentLesson.date}T${currentLesson.time}`), 'h:mm a')}
                </p>
              </div>
            )}
          </div>

          {/* Mobile Content */}
          <div className="flex-1 overflow-y-auto px-4 pb-20">
            {loadingAvailability ? (
              <div className="text-center py-8">
                <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[#6A0DAD]"></div>
                <p className="mt-2 text-gray-600">Loading availability...</p>
              </div>
            ) : (
              <div className="space-y-6">
                <Calendar
                  currentMonth={currentMonth}
                  selectedDate={selectedDate}
                  availableDates={availableDates}
                  onDateSelect={handleDateSelect}
                  onMonthChange={setCurrentMonth}
                />

                {showTimeDropdown && selectedDate && (
                  <TimeDropdown
                    selectedTime={selectedTime}
                    timeSlots={timeSlots}
                    isVisible={showTimeDropdown}
                    onTimeSelect={handleTimeSelect}
                    disabled={false}
                    isLoading={loadingTimeSlots}
                  />
                )}

                {durationOptions.length > 1 && (
                  <DurationButtons
                    durationOptions={durationOptions}
                    selectedDuration={selectedDuration}
                    onDurationSelect={setSelectedDuration}
                    disabledDurations={disabledDurations}
                  />
                )}
              </div>
            )}
          </div>

          {/* Mobile Footer */}
          <div className="fixed bottom-0 left-0 right-0 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 p-4">
            <div className="space-y-3">
              <p className="text-sm text-gray-600 text-center">
                Prefer to discuss?{' '}
                <button
                  onClick={() => {
                    if (onOpenChat) {
                      onOpenChat();
                    }
                  }}
                  className="text-[#6A0DAD] hover:underline"
                >
                  Chat to reschedule
                </button>
              </p>
              <button
                onClick={handleContinue}
                disabled={!selectedDate || !selectedTime}
                className={`w-full py-3 rounded-lg font-medium transition-colors ${
                  selectedDate && selectedTime
                    ? 'bg-[#6A0DAD] text-white hover:bg-[#6A0DAD]'
                    : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                }`}
              >
                Select and continue
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Desktop Modal View */}
      <div
        className="hidden md:block fixed inset-0 z-50 overflow-y-auto"
        style={{ backgroundColor: 'rgba(0, 0, 0, 0.5)' }}
        onClick={handleBackdropClick}
        aria-modal="true"
        role="dialog"
      >
        <div className="flex min-h-screen items-center justify-center p-4">
          {/* Backdrop */}
          <div
            className="fixed inset-0 transition-opacity"
            style={{ backgroundColor: 'var(--modal-backdrop, rgba(0, 0, 0, 0.5))' }}
          />

          {/* Modal */}
          <div
            ref={modalRef}
            tabIndex={-1}
            className="relative bg-white dark:bg-gray-900 rounded-lg shadow-xl w-full max-w-[720px] max-h-[90vh] flex flex-col animate-slideUp"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Desktop Header */}
            <div className="flex items-center justify-between p-8 pb-0">
              <h2
                className="text-2xl font-medium text-gray-900 dark:text-white"
                style={{ color: '#333333' }}
              >
                Need to reschedule?
              </h2>
              <button
                onClick={onClose}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                aria-label="Close modal"
              >
                <X className="h-6 w-6" />
              </button>
            </div>

            {/* Subtext */}
            <div className="px-8 pt-2 pb-2">
              <p className="text-gray-600">
                Choose a new lesson date & time below.
              </p>
            </div>

            {/* Instructor Name */}
            <div className="px-8 pb-6 flex items-center gap-2">
              <div className="w-8 h-8 rounded-full overflow-hidden">
                <div className="w-8 h-8 bg-gray-200" />
              </div>
              <p className="text-base font-bold text-black">
                {getInstructorDisplayName()}&apos;s availability
              </p>
            </div>

            {/* Current lesson info bar */}
            {currentLesson && (
              <div className="mx-8 mb-4 p-3 bg-yellow-50 rounded-lg">
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  <span className="font-medium">Current lesson:</span>{' '}
                  {format(new Date(`${currentLesson.date}T${currentLesson.time}`), 'EEE MMM d')} at{' '}
                  {format(new Date(`${currentLesson.date}T${currentLesson.time}`), 'h:mm a')}
                  {' • '}{currentLesson.service}
                </p>
              </div>
            )}

            {/* Desktop Content - Split Layout */}
            <div className="flex-1 overflow-y-auto px-8 pb-8">
              {loadingAvailability ? (
                <div className="text-center py-8">
                  <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[#6A0DAD]"></div>
                  <p className="mt-2 text-gray-600">Loading availability...</p>
                </div>
              ) : (
                <div className="flex gap-8">
                  {/* Left Section - Calendar and Controls */}
                  <div className="flex-1">
                    {/* Calendar Component */}
                    <Calendar
                        currentMonth={currentMonth}
                        selectedDate={selectedDate}
                        availableDates={availableDates}
                        onDateSelect={handleDateSelect}
                        onMonthChange={setCurrentMonth}
                    />

                    {showTimeDropdown && selectedDate && (
                      <div className="mb-4">
                        <TimeDropdown
                          selectedTime={selectedTime}
                          timeSlots={timeSlots}
                          isVisible={showTimeDropdown}
                          onTimeSelect={handleTimeSelect}
                          disabled={false}
                          isLoading={loadingTimeSlots}
                        />
                      </div>
                    )}

                    {durationOptions.length > 1 && (
                      <div className="mb-4">
                        <DurationButtons
                          durationOptions={durationOptions}
                          selectedDuration={selectedDuration}
                          onDurationSelect={setSelectedDuration}
                          disabledDurations={disabledDurations}
                        />
                      </div>
                    )}
                  </div>

                  {/* Right Section - Summary and CTA */}
                  <div className="w-[200px] flex-shrink-0 pt-12">
                    <SummarySection
                      selectedDate={selectedDate}
                      selectedTime={selectedTime}
                      selectedDuration={selectedDuration}
                      price={getCurrentPrice()}
                      onContinue={handleContinue}
                      isComplete={!!selectedDate && !!selectedTime}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Chat to reschedule link */}
            <div className="px-8 pb-4 text-center">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Prefer to discuss?{' '}
                <button
                  onClick={() => {
                    if (onOpenChat) {
                      onOpenChat();
                    }
                  }}
                  className="text-[#6A0DAD] hover:underline"
                >
                  Chat to reschedule
                </button>
              </p>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
