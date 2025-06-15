// frontend/components/TimeSlotButton.tsx
import React from 'react';

interface TimeSlotButtonProps {
    hour: number;
    isAvailable: boolean;
    isBooked: boolean;
    isPast: boolean;
    onClick: () => void;
    disabled?: boolean;
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
    const getButtonClass = () => {
      const baseClass = isMobile ? 'p-2 rounded text-sm' : 'w-full h-10 rounded transition-colors';
      
      if (isBooked) {
        return `${baseClass} bg-red-400 text-white cursor-not-allowed`;
      }
      
      if (isPast) {
        return isAvailable
          ? `${baseClass} bg-green-300 text-white cursor-not-allowed`
          : `${baseClass} bg-gray-100 text-gray-400 cursor-not-allowed`;
      }
      
      return isAvailable
        ? `${baseClass} bg-green-500 hover:bg-green-600 text-white cursor-pointer`
        : `${baseClass} bg-gray-200 hover:bg-gray-300 cursor-pointer`;
    };
  
    const getTitle = () => {
      if (isBooked) return isMobile ? 'This slot has a booking' : 'This slot has a booking - cannot modify';
      if (isPast) return isMobile ? 'Past time slot' : 'Past time slot - view only';
      return '';
    };
  
    const formatHour = (hour: number) => {
      const displayHour = hour % 12 || 12;
      return `${displayHour}:00`;
    };
  
    return (
      <button
        onClick={onClick}
        disabled={disabled || isPast || isBooked}
        className={getButtonClass()}
        title={getTitle()}
      >
        {isMobile ? (
          <>
            {formatHour(hour)}
            {!isBooked && isAvailable && <span className="ml-1 text-xs">✓</span>}
          </>
        ) : (
          !isBooked && isAvailable && '✓'
        )}
      </button>
    );
  };

export default TimeSlotButton;