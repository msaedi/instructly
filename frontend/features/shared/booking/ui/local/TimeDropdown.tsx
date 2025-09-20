'use client';

import { useState, useRef, useEffect } from 'react';

interface TimeDropdownProps {
  selectedTime: string | null;
  timeSlots: string[];
  isVisible: boolean;
  onTimeSelect: (time: string) => void;
  disabled?: boolean;
  isLoading?: boolean;
}

export default function TimeDropdown({ selectedTime, timeSlots, isVisible, onTimeSelect, disabled = false, isLoading = false }: TimeDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (timeSlots.length === 1 && !selectedTime && timeSlots[0]) {
      onTimeSelect(timeSlots[0]);
    }
  }, [timeSlots, selectedTime, onTimeSelect]);

  if (!isVisible) return null;
  const hasNoTimes = timeSlots.length === 0;

  return (
    <div className="w-full md:w-80 mb-4 relative">
      <button
        ref={buttonRef}
        onClick={() => !disabled && !hasNoTimes && !isLoading && setIsOpen((o) => !o)}
        disabled={disabled || hasNoTimes || isLoading}
        className={`w-full h-11 px-4 py-3 text-left rounded-lg border border-gray-300 flex items-center justify-between ${hasNoTimes ? 'bg-gray-100 cursor-not-allowed' : 'bg-white hover:bg-gray-50'}`}
      >
        <span className={timeSlots.length === 1 && selectedTime ? 'flex items-center gap-1' : ''}>
          {isLoading ? 'Loading available times...' : hasNoTimes ? 'No times available for this date' : selectedTime || 'Select time'}
        </span>
        {!hasNoTimes && !isLoading && (
          <svg className={`w-5 h-5 transition-transform ${isOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </button>

      {isOpen && !hasNoTimes && (
        <div className="absolute left-0 right-0 mt-1 bg-white rounded-lg shadow-xl border border-gray-200 z-50">
          <div className="py-2 max-h-60 overflow-auto">
            {timeSlots.map((time, index) => (
              <button
                key={time}
                onClick={() => { onTimeSelect(time); setIsOpen(false); }}
                className={`w-full text-left px-4 py-3 transition-all hover:bg-gray-50 ${selectedTime === time ? 'bg-purple-50 text-[#7E22CE] font-medium' : 'text-gray-900'} ${index !== timeSlots.length - 1 ? 'border-b border-gray-100' : ''}`}
                style={{ fontSize: '15px', lineHeight: '20px' }}
              >
                <div className="flex items-center justify-between">
                  <span>{time}</span>
                  {selectedTime === time && (
                    <svg className="w-5 h-5 text-[#7E22CE]" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
