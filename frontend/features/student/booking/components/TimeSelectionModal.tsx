'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { X, ArrowLeft } from 'lucide-react';
import { logger } from '@/lib/logger';
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
    services: Array<{ duration_options: number[] }>;
  };
  preSelectedDate?: string; // From search context (format: "YYYY-MM-DD")
  onTimeSelected: (selection: { date: string; time: string; duration: number }) => void;
}

export default function TimeSelectionModal({
  isOpen,
  onClose,
  instructor,
  preSelectedDate,
  onTimeSelected,
}: TimeSelectionModalProps) {
  // Mock duration options for testing - replace with real instructor data
  const mockDurationOptions = [
    { duration: 30, price: 75 },
    { duration: 60, price: 120 },
    { duration: 90, price: 165 },
  ];
  // For single duration test: [{ duration: 60, price: 120 }]

  // Component state
  const [selectedDate, setSelectedDate] = useState<string | null>(preSelectedDate || null);
  const [selectedTime, setSelectedTime] = useState<string | null>(null);
  // Pre-select middle duration option by default
  const [selectedDuration, setSelectedDuration] = useState<number>(
    mockDurationOptions.length > 1
      ? mockDurationOptions[Math.floor(mockDurationOptions.length / 2)].duration
      : mockDurationOptions[0]?.duration || 60
  );
  const [currentMonth, setCurrentMonth] = useState<Date>(new Date());
  const [showTimeDropdown, setShowTimeDropdown] = useState(!!preSelectedDate);
  const [availableDates, setAvailableDates] = useState<string[]>([
    // Mock data - replace with actual API call
    '2024-01-17',
    '2024-01-18',
    '2024-01-19',
    '2024-01-22',
    '2024-01-23',
    '2024-01-24',
    '2024-01-25',
    '2024-01-26',
    '2024-01-29',
    '2024-01-30',
  ]);
  const [timeSlots, setTimeSlots] = useState<string[]>([]);

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
    const option = mockDurationOptions.find((opt) => opt.duration === selectedDuration);
    return option?.price || 0;
  };

  // Handle date selection
  const handleDateSelect = (date: string) => {
    setSelectedDate(date);
    setShowTimeDropdown(true);
    // Generate mock time slots based on duration
    const mockTimeSlots =
      selectedDuration === 30
        ? ['9:00am', '9:30am', '10:00am', '10:30am', '11:00am', '1:00pm', '1:30pm', '2:00pm']
        : selectedDuration === 60
          ? ['9:00am', '10:00am', '11:00am', '1:00pm', '2:00pm', '3:00pm']
          : ['9:00am', '10:30am', '1:00pm', '2:30pm']; // 90 min

    setTimeSlots(mockTimeSlots);
    logger.info('Date selected', { date, slotsGenerated: mockTimeSlots.length });
  };

  // Handle time selection
  const handleTimeSelect = (time: string) => {
    setSelectedTime(time);
    logger.info('Time selected', { time });
  };

  // Handle duration selection
  const handleDurationSelect = (duration: number) => {
    const previousDuration = selectedDuration;
    setSelectedDuration(duration);

    // Clear selected time if changing duration
    if (previousDuration !== duration && selectedTime) {
      setSelectedTime(null);
    }

    // Update time slots based on new duration
    if (selectedDate) {
      const mockTimeSlots =
        duration === 30
          ? ['9:00am', '9:30am', '10:00am', '10:30am', '11:00am', '1:00pm', '1:30pm', '2:00pm']
          : duration === 60
            ? ['9:00am', '10:00am', '11:00am', '1:00pm', '2:00pm', '3:00pm']
            : ['9:00am', '10:30am', '1:00pm', '2:30pm']; // 90 min

      setTimeSlots(mockTimeSlots);
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
                />
              </div>
            )}

            {/* Duration Buttons (only if multiple durations) */}
            <DurationButtons
              durationOptions={mockDurationOptions}
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
          <div className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" />

          {/* Modal */}
          <div
            ref={modalRef}
            tabIndex={-1}
            className="relative bg-white dark:bg-gray-900 rounded-lg shadow-xl w-full max-w-[600px] max-h-[90vh] overflow-hidden animate-slideUp"
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
            <div className="px-8 pb-8">
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
                      />
                    </div>
                  )}

                  {/* Duration Buttons (only if multiple durations) */}
                  <DurationButtons
                    durationOptions={mockDurationOptions}
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
                <div className="w-[200px]">
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
    </>
  );
}
