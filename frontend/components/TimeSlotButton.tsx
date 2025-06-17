// frontend/components/TimeSlotButton.tsx
import React from 'react';
import { logger } from '@/lib/logger';

/**
 * TimeSlotButton Component
 * 
 * Displays a single time slot button in the availability calendar.
 * Visual state changes based on availability, booking status, and time (past/future).
 * 
 * Visual States:
 * - Available (future): Green background, clickable
 * - Unavailable (future): Gray background, clickable
 * - Booked: Red background, not clickable
 * - Past + Available: Light green background, not clickable
 * - Past + Unavailable: Light gray background, not clickable
 * 
 * Features:
 * - Dynamic visual states based on slot status
 * - Accessibility support with ARIA labels
 * - Mobile-responsive design
 * - Structured logging for debugging
 * 
 * @component
 */
interface TimeSlotButtonProps {
  /** The hour (0-23) this slot represents */
  hour: number;
  /** Whether this slot is marked as available */
  isAvailable: boolean;
  /** Whether this slot has a booking */
  isBooked: boolean;
  /** Whether this slot is in the past */
  isPast: boolean;
  /** Click handler for toggling availability */
  onClick: () => void;
  /** Whether the button is disabled */
  disabled?: boolean;
  /** Whether to render in mobile mode */
  isMobile?: boolean;
}

const TimeSlotButton: React.FC<TimeSlotButtonProps> = ({
  hour,
  isAvailable,
  isBooked,
  isPast,
  onClick,
  disabled = false,
  isMobile = false
}) => {
  /**
   * Determine the CSS classes based on button state
   */
  const getButtonClass = (): string => {
    const baseClass = isMobile 
      ? 'p-2 rounded text-sm' 
      : 'w-full h-10 rounded transition-colors';
    
    // Booked slots - highest priority
    if (isBooked) {
      return `${baseClass} bg-red-400 text-white cursor-not-allowed`;
    }
    
    // Past slots - read-only
    if (isPast) {
      return isAvailable
        ? `${baseClass} bg-green-300 text-white cursor-not-allowed`
        : `${baseClass} bg-gray-100 text-gray-400 cursor-not-allowed`;
    }
    
    // Future slots - interactive
    return isAvailable
      ? `${baseClass} bg-green-500 hover:bg-green-600 text-white cursor-pointer`
      : `${baseClass} bg-gray-200 hover:bg-gray-300 cursor-pointer`;
  };

  /**
   * Get tooltip text based on button state
   */
  const getTitle = (): string => {
    if (isBooked) {
      return isMobile 
        ? 'This slot has a booking' 
        : 'This slot has a booking - cannot modify';
    }
    if (isPast) {
      return isMobile 
        ? 'Past time slot' 
        : 'Past time slot - view only';
    }
    return '';
  };

  /**
   * Format hour for mobile display
   * @param hour - Hour in 24-hour format
   * @returns Formatted time string (e.g., "9:00")
   */
  const formatHour = (hour: number): string => {
    const displayHour = hour % 12 || 12;
    return `${displayHour}:00`;
  };

  /**
   * Handle click events with logging
   */
  const handleClick = () => {
    logger.debug('Time slot button clicked', {
      hour,
      isAvailable,
      isBooked,
      isPast,
      disabled,
      isMobile,
      action: isAvailable ? 'make_unavailable' : 'make_available'
    });
    
    onClick();
  };

  // Log render in development for debugging
  logger.debug('TimeSlotButton rendered', {
    hour,
    state: {
      isAvailable,
      isBooked,
      isPast,
      disabled
    },
    isMobile
  });

  return (
    <button
      onClick={handleClick}
      disabled={disabled || isPast || isBooked}
      className={getButtonClass()}
      title={getTitle()}
      aria-label={`Time slot ${formatHour(hour)} - ${
        isBooked ? 'booked' : 
        isPast ? 'past' : 
        isAvailable ? 'available' : 'unavailable'
      }`}
    >
      {isMobile ? (
        <>
          {formatHour(hour)}
          {!isBooked && isAvailable && <span className="ml-1 text-xs">✓</span>}
        </>
      ) : (
        // Desktop view - just show checkmark for available slots
        !isBooked && isAvailable && '✓'
      )}
    </button>
  );
};

export default TimeSlotButton;