'use client';

import { useState, useRef, useEffect, useCallback, useId, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { createPortal } from 'react-dom';

interface TimeDropdownProps {
  selectedTime: string | null;
  timeSlots: string[];
  isVisible: boolean;
  onTimeSelect: (time: string) => void;
  disabled?: boolean;
  isLoading?: boolean;
}

export default function TimeDropdown({
  selectedTime,
  timeSlots,
  isVisible,
  onTimeSelect,
  disabled = false,
  isLoading = false,
}: TimeDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, left: 0, width: 0 });
  const [isAnimating, setIsAnimating] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const listboxId = useId();
  const hasNoTimes = timeSlots.length === 0;
  const hasSingleTime = timeSlots.length === 1;
  const selectedIndex = selectedTime ? timeSlots.findIndex((time) => time === selectedTime) : -1;

  const getClampedIndex = useCallback(
    (index: number) => Math.max(0, Math.min(index, timeSlots.length - 1)),
    [timeSlots.length],
  );

  // Calculate dropdown position
  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setDropdownPosition({
        top: rect.bottom + window.scrollY + 4, // 4px gap
        left: rect.left + window.scrollX,
        width: rect.width,
      });
    }
  }, [isOpen]);

  // Handle open/close with animation
  const handleOpen = useCallback((preferredIndex?: number) => {
    const fallbackIndex = selectedIndex >= 0 ? selectedIndex : 0;
    const nextIndex =
      typeof preferredIndex === 'number' ? getClampedIndex(preferredIndex) : fallbackIndex;

    setActiveIndex(nextIndex);
    setIsAnimating(true);
    setIsOpen(true);
  }, [getClampedIndex, selectedIndex]);

  const handleClose = useCallback((restoreFocus = false) => {
    setIsAnimating(false);
    setActiveIndex(-1);
    setTimeout(() => {
      setIsOpen(false);
      if (restoreFocus) {
        requestAnimationFrame(() => {
          buttonRef.current?.focus();
        });
      }
    }, 150); // Wait for animation
  }, []);

  const handleSelect = useCallback(
    (time: string) => {
      onTimeSelect(time);
      handleClose(true);
    },
    [handleClose, onTimeSelect],
  );

  // Handle clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        buttonRef.current &&
        !buttonRef.current.contains(event.target as Node) &&
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        handleClose();
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [handleClose, isOpen]);

  useEffect(() => {
    if (!isOpen || activeIndex < 0) {
      return;
    }

    const rafId = requestAnimationFrame(() => {
      optionRefs.current[activeIndex]?.focus();
    });

    return () => {
      cancelAnimationFrame(rafId);
    };
  }, [activeIndex, isOpen]);

  // Auto-select if only one time available
  useEffect(() => {
    if (timeSlots.length === 1 && !selectedTime && timeSlots[0]) {
      onTimeSelect(timeSlots[0]);
    }
  }, [timeSlots, selectedTime, onTimeSelect]);

  if (!isVisible) {
    return null;
  }

  // Format display text
  const getDisplayText = () => {
    if (isLoading) {
      return 'Loading available times...';
    }
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

  const handleTriggerKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (disabled || hasNoTimes || isLoading) {
      return;
    }

    const lastIndex = timeSlots.length - 1;

    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (isOpen) {
        handleClose(true);
      } else {
        handleOpen();
      }
      return;
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (isOpen) {
        setActiveIndex((prev) => (prev < 0 ? 0 : Math.min(prev + 1, lastIndex)));
      } else {
        const nextIndex = selectedIndex >= 0 ? Math.min(selectedIndex + 1, lastIndex) : 0;
        handleOpen(nextIndex);
      }
      return;
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (isOpen) {
        setActiveIndex((prev) => (prev < 0 ? lastIndex : Math.max(prev - 1, 0)));
      } else {
        const nextIndex = selectedIndex >= 0 ? Math.max(selectedIndex - 1, 0) : lastIndex;
        handleOpen(nextIndex);
      }
      return;
    }

    if (event.key === 'Escape' && isOpen) {
      event.preventDefault();
      handleClose(true);
    }
  };

  const handleListboxKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const lastIndex = timeSlots.length - 1;

    if (event.key === 'Escape') {
      event.preventDefault();
      handleClose(true);
      return;
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex((prev) => (prev < 0 ? 0 : Math.min(prev + 1, lastIndex)));
      return;
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((prev) => (prev < 0 ? lastIndex : Math.max(prev - 1, 0)));
      return;
    }

    if (event.key === 'Home') {
      event.preventDefault();
      setActiveIndex(0);
      return;
    }

    if (event.key === 'End') {
      event.preventDefault();
      setActiveIndex(lastIndex);
      return;
    }

    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      const indexToSelect = activeIndex >= 0 ? activeIndex : selectedIndex >= 0 ? selectedIndex : 0;
      const time = timeSlots[indexToSelect];
      if (time) {
        handleSelect(time);
      }
    }
  };

  // Render dropdown menu using portal
  const renderDropdown = () => {
    if (!isOpen || hasNoTimes || typeof window === 'undefined') return null;

    return createPortal(
      <div
        ref={dropdownRef}
        id={listboxId}
        role="listbox"
        aria-label="Select lesson time"
        onKeyDown={handleListboxKeyDown}
        className={`bg-white rounded-lg shadow-xl border border-gray-200 ${
          isAnimating ? 'animate-dropdownOpen' : 'animate-dropdownClose'
        }`}
        style={{
          position: 'absolute',
          top: `${dropdownPosition.top}px`,
          left: `${dropdownPosition.left}px`,
          width: `${dropdownPosition.width}px`,
          zIndex: 10000,
          boxShadow: '0 10px 40px rgba(0, 0, 0, 0.15)',
        }}
      >
        <div className="py-2 max-h-60 overflow-y-auto">
          {timeSlots.map((time, index) => (
            <button
              key={time}
              ref={(element) => {
                optionRefs.current[index] = element;
              }}
              id={`${listboxId}-option-${index}`}
              type="button"
              role="option"
              tabIndex={activeIndex === index ? 0 : -1}
              aria-selected={selectedTime === time}
              onFocus={() => setActiveIndex(index)}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => {
                handleSelect(time);
              }}
              className={`
                w-full text-left px-4 py-3 transition-all duration-150
                hover:bg-gray-50 active:bg-gray-100
                ${
                  selectedTime === time
                    ? 'bg-purple-50 text-[#7E22CE] font-medium'
                    : 'text-gray-900'
                }
                ${index !== timeSlots.length - 1 ? 'border-b border-gray-100' : ''}
              `}
              style={{
                fontSize: '15px',
                lineHeight: '20px',
              }}
            >
              <div className="flex items-center justify-between">
                <span>{time}</span>
                {selectedTime === time && (
                  <svg className="w-5 h-5 text-[#7E22CE]" fill="currentColor" viewBox="0 0 20 20">
                    <path
                      fillRule="evenodd"
                      d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                      clipRule="evenodd"
                    />
                  </svg>
                )}
              </div>
              {hasSingleTime && (
                <span className="text-sm text-gray-500 mt-0.5">Only time available</span>
              )}
            </button>
          ))}
        </div>
      </div>,
      document.body
    );
  };

  return (
    <div className="w-full md:w-80 mb-4">
      {/* Dropdown Button */}
      <button
        ref={buttonRef}
        type="button"
        onClick={() =>
          !disabled && !hasNoTimes && !isLoading && (isOpen ? handleClose(true) : handleOpen())
        }
        onKeyDown={handleTriggerKeyDown}
        disabled={disabled || hasNoTimes || isLoading}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={isOpen ? listboxId : undefined}
        className={`
          w-full h-11 px-4 py-3 text-left rounded-lg border border-gray-300
          flex items-center justify-between
          transition-colors
          ${hasNoTimes || isLoading ? 'text-gray-500 dark:text-gray-400' : 'text-gray-900 dark:text-gray-100'}
          ${
            hasNoTimes
              ? 'bg-gray-100 dark:bg-gray-800 cursor-not-allowed'
              : 'bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer'
          }
          ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
          ${isOpen ? 'ring-2 ring-[#7E22CE]' : ''}
        `}
        style={{
          fontSize: '16px',
          fontStyle: hasNoTimes && !isLoading ? 'italic' : 'normal',
        }}
      >
        <span className={hasSingleTime && selectedTime ? 'flex items-center gap-1' : ''}>
          {getDisplayText()}
        </span>
        {!hasNoTimes && !isLoading && (
          <svg
            className={`w-5 h-5 transition-transform ${isOpen ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </button>

      {/* Render dropdown using portal */}
      {renderDropdown()}
    </div>
  );
}
