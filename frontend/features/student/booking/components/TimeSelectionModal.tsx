'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { X, ArrowLeft } from 'lucide-react';
import { logger } from '@/lib/logger';
import { publicApi } from '@/features/shared/api/client';
import Calendar from './TimeSelectionModal/Calendar';
import TimeDropdown from './TimeSelectionModal/TimeDropdown';
import DurationButtons from './TimeSelectionModal/DurationButtons';
import SummarySection from './TimeSelectionModal/SummarySection';

interface TimeSelectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  instructor: {
    user_id: number;
    user: { full_name: string };
    services: Array<{
      duration_options?: number[];
      duration?: number;
      hourly_rate: number;
      skill: string;
    }>;
  };
  preSelectedDate?: string; // From search context (format: "YYYY-MM-DD")
  preSelectedTime?: string; // Pre-selected time slot
  onTimeSelected: (selection: { date: string; time: string; duration: number }) => void;
}

export default function TimeSelectionModal({
  isOpen,
  onClose,
  instructor,
  preSelectedDate,
  preSelectedTime,
  onTimeSelected,
}: TimeSelectionModalProps) {
  // Get duration options from instructor services
  const getDurationOptions = () => {
    // Collect unique durations from all services
    const durations = new Set<number>();
    instructor.services.forEach((service) => {
      if (service.duration_options && service.duration_options.length > 0) {
        service.duration_options.forEach((d) => durations.add(d));
      } else if (service.duration) {
        durations.add(service.duration);
      }
    });

    // Convert to array and sort
    const sortedDurations = Array.from(durations).sort((a, b) => a - b);

    // Calculate prices based on average hourly rate
    const avgHourlyRate =
      instructor.services.reduce((sum, s) => sum + s.hourly_rate, 0) / instructor.services.length;

    return sortedDurations.map((duration) => ({
      duration,
      price: Math.round((avgHourlyRate * duration) / 60),
    }));
  };

  const durationOptions = getDurationOptions();

  // Component state
  const [selectedDate, setSelectedDate] = useState<string | null>(preSelectedDate || null);
  const [selectedTime, setSelectedTime] = useState<string | null>(preSelectedTime || null);
  // Pre-select middle duration option by default
  const [selectedDuration, setSelectedDuration] = useState<number>(
    durationOptions.length > 1
      ? durationOptions[Math.floor(durationOptions.length / 2)].duration
      : durationOptions[0]?.duration || 60
  );
  const [currentMonth, setCurrentMonth] = useState<Date>(new Date());
  const [showTimeDropdown, setShowTimeDropdown] = useState(false);
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [timeSlots, setTimeSlots] = useState<string[]>([]);
  const [availabilityData, setAvailabilityData] = useState<any>(null);
  const [loadingAvailability, setLoadingAvailability] = useState(false);
  const [loadingTimeSlots, setLoadingTimeSlots] = useState(false);

  const modalRef = useRef<HTMLDivElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);

  // Get instructor first name and last initial
  const getInstructorDisplayName = () => {
    const fullName = instructor.user.full_name;
    const parts = fullName.split(' ');
    const firstName = parts[0];
    const lastName = parts[parts.length - 1];
    const lastInitial = lastName ? lastName.charAt(0) : '';
    return `${firstName} ${lastInitial}.`;
  };

  // Fetch availability data when modal opens
  useEffect(() => {
    if (isOpen && instructor.user_id) {
      fetchAvailability();
    }
  }, [isOpen, instructor.user_id]);

  const fetchAvailability = async () => {
    setLoadingAvailability(true);
    try {
      const today = new Date();
      const endDate = new Date();
      endDate.setDate(today.getDate() + 30); // Get 30 days of availability

      const response = await publicApi.getInstructorAvailability(instructor.user_id.toString(), {
        start_date: today.toISOString().split('T')[0],
        end_date: endDate.toISOString().split('T')[0],
      });

      if (response.data?.availability_by_date) {
        const availabilityByDate = response.data.availability_by_date;
        setAvailabilityData(availabilityByDate);

        // Extract available dates - only include dates with actual time slots
        const datesWithSlots: string[] = [];
        Object.keys(availabilityByDate).forEach((date) => {
          const slots = availabilityByDate[date].available_slots || [];
          // Filter out past times if it's today
          const now = new Date();
          const isToday = date === now.toISOString().split('T')[0];

          const validSlots = slots.filter((slot: any) => {
            if (!isToday) return true;
            const [hours, minutes] = slot.start_time.split(':');
            const slotTime = new Date();
            slotTime.setHours(parseInt(hours), parseInt(minutes), 0, 0);
            return slotTime > now;
          });

          if (validSlots.length > 0) {
            datesWithSlots.push(date);
          }
        });
        setAvailableDates(datesWithSlots);

        // If we have a pre-selected date, load its time slots
        if (preSelectedDate && availabilityByDate[preSelectedDate]) {
          const slots = availabilityByDate[preSelectedDate].available_slots || [];
          const formattedSlots = slots.map((slot: any) => {
            const [hours, minutes] = slot.start_time.split(':');
            const hour = parseInt(hours);
            const ampm = hour >= 12 ? 'pm' : 'am';
            const displayHour = hour % 12 || 12;
            return `${displayHour}:${minutes.padStart(2, '0')}${ampm}`;
          });
          setTimeSlots(formattedSlots);

          // If pre-selected time is provided, format it to match
          if (preSelectedTime) {
            const [hours, minutes] = preSelectedTime.split(':');
            const hour = parseInt(hours);
            const ampm = hour >= 12 ? 'pm' : 'am';
            const displayHour = hour % 12 || 12;
            const formattedTime = `${displayHour}:${minutes.padStart(2, '0')}${ampm}`;
            setSelectedTime(formattedTime);
          }
        }
      }
    } catch (error) {
      logger.error('Failed to fetch availability', error);
    } finally {
      setLoadingAvailability(false);
    }
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
      // Store the currently focused element
      previousActiveElement.current = document.activeElement as HTMLElement;
      // Focus the modal
      modalRef.current?.focus();
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      // Restore focus when modal closes
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
    if (selectedDate && selectedTime) {
      logger.info('Time selection completed', {
        date: selectedDate,
        time: selectedTime,
        duration: selectedDuration,
      });
      onTimeSelected({
        date: selectedDate,
        time: selectedTime,
        duration: selectedDuration,
      });
      onClose();
    }
  };

  // Get current price based on selected duration
  const getCurrentPrice = () => {
    const option = durationOptions.find((opt) => opt.duration === selectedDuration);
    return option?.price || 0;
  };

  // Handle date selection
  const handleDateSelect = async (date: string) => {
    setSelectedDate(date);
    setSelectedTime(null); // Clear previous time selection
    setShowTimeDropdown(true);
    setTimeSlots([]); // Clear previous slots
    setLoadingTimeSlots(true); // Show loading state

    // If we don't have availability data yet, fetch it
    if (!availabilityData) {
      await fetchAvailability();
    }

    // Get time slots from availability data
    if (availabilityData && availabilityData[date]) {
      const slots = availabilityData[date].available_slots || [];

      // Filter out past times if selecting today
      const now = new Date();
      const isToday = date === now.toISOString().split('T')[0];

      const validSlots = slots.filter((slot: any) => {
        if (!isToday) return true;

        const [hours, minutes] = slot.start_time.split(':');
        const slotTime = new Date();
        slotTime.setHours(parseInt(hours), parseInt(minutes), 0, 0);

        return slotTime > now;
      });

      const formattedSlots = validSlots.map((slot: any) => {
        // Convert 24h to 12h format
        const [hours, minutes] = slot.start_time.split(':');
        const hour = parseInt(hours);
        const ampm = hour >= 12 ? 'pm' : 'am';
        const displayHour = hour % 12 || 12;
        return `${displayHour}:${minutes.padStart(2, '0')}${ampm}`;
      });

      setTimeSlots(formattedSlots);
      setLoadingTimeSlots(false);
      logger.info('Date selected', { date, slotsGenerated: formattedSlots.length, isToday });
    } else {
      // Fetch specific date availability if not in cache
      try {
        const response = await publicApi.getInstructorAvailability(instructor.user_id.toString(), {
          start_date: date,
          end_date: date,
        });

        if (response.data?.availability_by_date?.[date]) {
          const dayData = response.data.availability_by_date[date];
          const slots = dayData.available_slots || [];

          // Update availability data cache
          setAvailabilityData((prev: any) => ({
            ...prev,
            [date]: dayData,
          }));

          // Process slots
          const now = new Date();
          const isToday = date === now.toISOString().split('T')[0];

          const validSlots = slots.filter((slot: any) => {
            if (!isToday) return true;

            const [hours, minutes] = slot.start_time.split(':');
            const slotTime = new Date();
            slotTime.setHours(parseInt(hours), parseInt(minutes), 0, 0);

            return slotTime > now;
          });

          const formattedSlots = validSlots.map((slot: any) => {
            const [hours, minutes] = slot.start_time.split(':');
            const hour = parseInt(hours);
            const ampm = hour >= 12 ? 'pm' : 'am';
            const displayHour = hour % 12 || 12;
            return `${displayHour}:${minutes.padStart(2, '0')}${ampm}`;
          });

          setTimeSlots(formattedSlots);
          setLoadingTimeSlots(false);
          logger.info('Fetched date-specific availability', { date, slots: formattedSlots.length });
        } else {
          setTimeSlots([]);
          setLoadingTimeSlots(false);
          logger.info('No availability for selected date', { date });
        }
      } catch (error) {
        logger.error('Failed to fetch date-specific availability', error);
        setTimeSlots([]);
        setLoadingTimeSlots(false);
      }
    }
  };

  // Handle time selection
  const handleTimeSelect = (time: string) => {
    setSelectedTime(time);
    logger.info('Time selected', { time });
  };

  // Auto-select first available time when time slots load
  useEffect(() => {
    if (timeSlots.length > 0 && !selectedTime && !loadingTimeSlots) {
      setSelectedTime(timeSlots[0]);
      logger.info('Auto-selected first available time', { time: timeSlots[0] });
    }
  }, [timeSlots, selectedTime, loadingTimeSlots]);

  // Handle duration selection
  const handleDurationSelect = (duration: number) => {
    const previousDuration = selectedDuration;
    setSelectedDuration(duration);

    // Clear selected time if changing duration
    if (previousDuration !== duration && selectedTime) {
      setSelectedTime(null);
    }

    logger.info('Duration selected', { duration, previousDuration });
  };

  if (!isOpen) return null;

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
            <h2 className="text-xl font-medium text-gray-900 dark:text-white">
              Select Your Lesson Time
            </h2>
            <div className="w-10" /> {/* Spacer for centering */}
          </div>

          {/* Instructor Name */}
          <div className="px-4 pt-4 pb-2">
            <p className="text-base text-gray-600 dark:text-gray-400">
              {getInstructorDisplayName()}'s availability
            </p>
          </div>

          {/* Mobile Content */}
          <div className="flex-1 overflow-y-auto px-4 pb-20">
            {/* Calendar Component */}
            <Calendar
              currentMonth={currentMonth}
              selectedDate={selectedDate}
              preSelectedDate={preSelectedDate}
              availableDates={availableDates}
              onDateSelect={handleDateSelect}
              onMonthChange={setCurrentMonth}
            />

            {/* Time Dropdown (shown when date selected) */}
            {showTimeDropdown && (
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

            {/* Duration Buttons (only if multiple durations) */}
            <DurationButtons
              durationOptions={durationOptions}
              selectedDuration={selectedDuration}
              onDurationSelect={handleDurationSelect}
            />

            {/* Summary Section */}
            <SummarySection
              selectedDate={selectedDate}
              selectedTime={selectedTime}
              selectedDuration={selectedDuration}
              price={getCurrentPrice()}
              onContinue={handleContinue}
              isComplete={!!selectedDate && !!selectedTime}
            />
          </div>

          {/* Mobile Sticky CTA - Rendered by SummarySection */}
          <div className="fixed bottom-0 left-0 right-0 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 p-4">
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
      </div>

      {/* Desktop Modal View */}
      <div
        className="hidden md:block fixed inset-0 z-50 overflow-y-auto"
        onClick={handleBackdropClick}
      >
        <div className="flex min-h-screen items-center justify-center p-4">
          {/* Backdrop */}
          <div
            className="fixed inset-0 transition-opacity"
            style={{ backgroundColor: 'var(--modal-backdrop)' }}
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
                className="text-xl font-medium text-gray-900 dark:text-white"
                style={{ color: '#333333' }}
              >
                Select Your Lesson Time
              </h2>
              <button
                onClick={onClose}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
                aria-label="Close modal"
              >
                <X className="h-6 w-6 text-gray-600 dark:text-gray-400" />
              </button>
            </div>

            {/* Instructor Name */}
            <div className="px-8 pt-2 pb-6">
              <p className="text-base" style={{ color: '#666666' }}>
                {getInstructorDisplayName()}'s availability
              </p>
            </div>

            {/* Desktop Content - Split Layout */}
            <div className="flex-1 overflow-y-auto px-8 pb-8">
              <div className="flex gap-8">
                {/* Left Section - Calendar and Controls */}
                <div className="flex-1">
                  {/* Calendar Component */}
                  <Calendar
                    currentMonth={currentMonth}
                    selectedDate={selectedDate}
                    preSelectedDate={preSelectedDate}
                    availableDates={availableDates}
                    onDateSelect={handleDateSelect}
                    onMonthChange={setCurrentMonth}
                  />

                  {/* Time Dropdown (shown when date selected) */}
                  {showTimeDropdown && (
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

                  {/* Duration Buttons (only if multiple durations) */}
                  <DurationButtons
                    durationOptions={durationOptions}
                    selectedDuration={selectedDuration}
                    onDurationSelect={handleDurationSelect}
                  />
                </div>

                {/* Vertical Divider */}
                <div
                  className="w-px bg-gray-200 dark:bg-gray-700"
                  style={{ backgroundColor: '#E8E8E8' }}
                />

                {/* Right Section - Summary and CTA */}
                <div className="w-[200px] flex-shrink-0">
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
            </div>
          </div>
        </div>
      </div>

      {/* Animation Styles */}
      <style jsx>{`
        @keyframes slideUp {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .animate-slideUp {
          animation: slideUp 0.3s ease-out;
        }

        /* Design Token Custom Properties */
        :root {
          --primary-purple: #6b46c1;
          --primary-purple-light: #f9f7ff;
          --text-primary: #333333;
          --text-secondary: #666666;
          --border-default: #e0e0e0;
          --border-light: #e8e8e8;
          --background-hover: #f5f5f5;
        }
      `}</style>

      {/* Global styles for dropdown animations */}
      <style jsx global>{`
        @keyframes dropdownOpen {
          from {
            opacity: 0;
            transform: translateY(-10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        @keyframes dropdownClose {
          from {
            opacity: 1;
            transform: translateY(0);
          }
          to {
            opacity: 0;
            transform: translateY(-10px);
          }
        }

        .animate-dropdownOpen {
          animation: dropdownOpen 0.15s ease-out forwards;
        }

        .animate-dropdownClose {
          animation: dropdownClose 0.15s ease-out forwards;
        }
      `}</style>
    </>
  );
}
