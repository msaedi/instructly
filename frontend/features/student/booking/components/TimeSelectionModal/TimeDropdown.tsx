'use client';

import { useState, useRef, useEffect } from 'react';

interface TimeDropdownProps {
  selectedTime: string | null;
  timeSlots: string[];
  isVisible: boolean;
  onTimeSelect: (time: string) => void;
  disabled?: boolean;
}

export default function TimeDropdown({
  selectedTime,
  timeSlots,
  isVisible,
  onTimeSelect,
  disabled = false,
}: TimeDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Handle clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Auto-select if only one time available
  useEffect(() => {
    if (timeSlots.length === 1 && !selectedTime) {
      onTimeSelect(timeSlots[0]);
    }
  }, [timeSlots, selectedTime, onTimeSelect]);

  if (!isVisible) {
    return null;
  }

  const hasNoTimes = timeSlots.length === 0;
  const hasSingleTime = timeSlots.length === 1;

  // Format display text
  const getDisplayText = () => {
    if (hasNoTimes) {
      return 'No times available for this date';
    }
    if (selectedTime) {
      if (hasSingleTime) {
        return `${selectedTime} (only time available)`;
      }
      return selectedTime;
    }
    return 'Select time';
  };

  return (
    <div className="relative w-full md:w-80" ref={dropdownRef}>
      {/* Dropdown Button */}
      <button
        onClick={() => !disabled && !hasNoTimes && setIsOpen(!isOpen)}
        disabled={disabled || hasNoTimes}
        className={`
          w-full h-11 px-4 py-3 text-left rounded
          flex items-center justify-between
          transition-colors
          ${
            hasNoTimes
              ? 'bg-gray-100 dark:bg-gray-800 cursor-not-allowed'
              : 'bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer'
          }
          ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
        `}
        style={{
          border: '1px solid #E0E0E0',
          borderRadius: '4px',
          fontSize: '16px',
          color: hasNoTimes ? '#999999' : '#333333',
          fontStyle: hasNoTimes ? 'italic' : 'normal',
        }}
      >
        <span className={hasSingleTime && selectedTime ? 'flex items-center gap-1' : ''}>
          {getDisplayText()}
          {hasSingleTime && selectedTime && (
            <span style={{ fontSize: '14px', color: '#666666' }}>
              {/* Suffix is included in getDisplayText() */}
            </span>
          )}
        </span>
        {!hasNoTimes && (
          <span className="text-gray-600 dark:text-gray-400" style={{ marginRight: '4px' }}>
            ▼
          </span>
        )}
      </button>

      {/* Dropdown Options */}
      {isOpen && !hasNoTimes && (
        <div
          className="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-gray-900 rounded shadow-lg overflow-hidden z-50"
          style={{
            border: '1px solid #E0E0E0',
            borderRadius: '4px',
            maxHeight: '300px',
            overflowY: 'auto',
          }}
        >
          {timeSlots.map((time) => (
            <button
              key={time}
              onClick={() => {
                onTimeSelect(time);
                setIsOpen(false);
              }}
              className={`
                w-full text-left px-4 py-3 transition-colors
                hover:bg-gray-50 dark:hover:bg-gray-800
                ${selectedTime === time ? 'bg-purple-50 dark:bg-purple-900/20' : ''}
              `}
              style={{
                height: '40px',
                fontSize: '16px',
                color: '#333333',
                backgroundColor: selectedTime === time ? '#F9F7FF' : undefined,
              }}
            >
              {time}
              {hasSingleTime && ' (only time available)'}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
