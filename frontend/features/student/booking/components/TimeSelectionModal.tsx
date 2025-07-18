'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { X, ArrowLeft } from 'lucide-react';
import { logger } from '@/lib/logger';

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
  // Component state
  const [selectedDate, setSelectedDate] = useState<string | null>(preSelectedDate || null);
  const [selectedTime, setSelectedTime] = useState<string | null>(null);
  const [selectedDuration, setSelectedDuration] = useState<number>(60); // Default
  const [currentMonth, setCurrentMonth] = useState<Date>(new Date());
  const [showTimeDropdown, setShowTimeDropdown] = useState(!!preSelectedDate);
  const [availableDates, setAvailableDates] = useState<string[]>([]);
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
    }
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
            {/* TODO: Calendar Component */}
            <div className="bg-gray-100 dark:bg-gray-800 rounded-lg p-4 mb-4">
              <p className="text-gray-500">Calendar Component Placeholder</p>
            </div>

            {/* TODO: Time Dropdown (shown when date selected) */}
            {showTimeDropdown && (
              <div className="bg-gray-100 dark:bg-gray-800 rounded-lg p-4 mb-4">
                <p className="text-gray-500">Time Dropdown Placeholder</p>
              </div>
            )}

            {/* TODO: Duration Buttons (only if multiple durations) */}
            <div className="bg-gray-100 dark:bg-gray-800 rounded-lg p-4 mb-4">
              <p className="text-gray-500">Duration Buttons Placeholder</p>
            </div>

            {/* TODO: Summary Section */}
            <div className="bg-gray-100 dark:bg-gray-800 rounded-lg p-4">
              <p className="text-gray-500">Summary Section Placeholder</p>
            </div>
          </div>

          {/* Mobile Sticky CTA */}
          <div className="fixed bottom-0 left-0 right-0 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 p-4">
            <button
              onClick={handleContinue}
              disabled={!selectedDate || !selectedTime}
              className="w-full bg-purple-600 hover:bg-purple-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-medium py-3 px-4 rounded-lg transition-colors"
              style={{ backgroundColor: selectedDate && selectedTime ? '#6B46C1' : undefined }}
            >
              Continue
            </button>
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
                  {/* TODO: Calendar Component */}
                  <div className="bg-gray-100 dark:bg-gray-800 rounded-lg p-4 mb-4">
                    <p className="text-gray-500">Calendar Component Placeholder</p>
                  </div>

                  {/* TODO: Time Dropdown (shown when date selected) */}
                  {showTimeDropdown && (
                    <div className="bg-gray-100 dark:bg-gray-800 rounded-lg p-4 mb-4">
                      <p className="text-gray-500">Time Dropdown Placeholder</p>
                    </div>
                  )}

                  {/* TODO: Duration Buttons (only if multiple durations) */}
                  <div className="bg-gray-100 dark:bg-gray-800 rounded-lg p-4">
                    <p className="text-gray-500">Duration Buttons Placeholder</p>
                  </div>
                </div>

                {/* Vertical Divider */}
                <div
                  className="w-px bg-gray-200 dark:bg-gray-700"
                  style={{ backgroundColor: '#E8E8E8' }}
                />

                {/* Right Section - Summary and CTA */}
                <div className="w-[200px]">
                  {/* TODO: Summary Section */}
                  <div className="bg-gray-100 dark:bg-gray-800 rounded-lg p-4 mb-6">
                    <p className="text-gray-500">Summary Section Placeholder</p>
                  </div>

                  {/* Desktop CTA Button */}
                  <button
                    onClick={handleContinue}
                    disabled={!selectedDate || !selectedTime}
                    className="w-full bg-purple-600 hover:bg-purple-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-medium py-3 px-4 rounded-lg transition-colors"
                    style={{
                      backgroundColor: selectedDate && selectedTime ? '#6B46C1' : undefined,
                    }}
                  >
                    Continue
                  </button>
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
