'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useEffect } from 'react';

interface CalendarProps {
  currentMonth: Date;
  selectedDate: string | null;
  preSelectedDate?: string;
  availableDates: string[];
  onDateSelect: (date: string) => void;
  onMonthChange: (date: Date) => void;
}

export default function Calendar({
  currentMonth,
  selectedDate,
  preSelectedDate,
  availableDates,
  onDateSelect,
  onMonthChange,
}: CalendarProps) {
  // Handle pre-selection on mount
  useEffect(() => {
    if (preSelectedDate && !selectedDate) {
      // Auto-select pre-selected date if not already selected
      const isAvailable = availableDates.includes(preSelectedDate);
      if (isAvailable) {
        onDateSelect(preSelectedDate);
      }
    }
  }, [preSelectedDate, selectedDate, availableDates, onDateSelect]);

  // Get the first day of the month
  const firstDay = new Date(currentMonth.getFullYear(), currentMonth.getMonth(), 1);
  const startDate = new Date(firstDay);
  startDate.setDate(startDate.getDate() - firstDay.getDay()); // Start from Sunday

  // Generate calendar days
  const days = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  for (let i = 0; i < 42; i++) {
    // 6 weeks * 7 days
    const date = new Date(startDate);
    date.setDate(startDate.getDate() + i);
    days.push(date);
  }

  // Format date to YYYY-MM-DD
  const formatDate = (date: Date): string => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  // Check if month is in the past
  const isMonthInPast = () => {
    const now = new Date();
    return (
      currentMonth.getFullYear() < now.getFullYear() ||
      (currentMonth.getFullYear() === now.getFullYear() && currentMonth.getMonth() < now.getMonth())
    );
  };

  // Navigate months
  const goToPreviousMonth = () => {
    if (!isMonthInPast()) {
      const newMonth = new Date(currentMonth);
      newMonth.setMonth(newMonth.getMonth() - 1);
      onMonthChange(newMonth);
    }
  };

  const goToNextMonth = () => {
    const newMonth = new Date(currentMonth);
    newMonth.setMonth(newMonth.getMonth() + 1);
    onMonthChange(newMonth);
  };

  // Day headers
  const dayHeaders = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];

  return (
    <div>
      {/* Month Navigation */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-medium" style={{ color: '#333333' }}>
          {currentMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
        </h3>
        <div className="flex items-center gap-2">
          <button
            onClick={goToPreviousMonth}
            disabled={isMonthInPast()}
            className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label="Previous month"
          >
            <ChevronLeft
              className="h-5 w-5"
              style={{
                color: isMonthInPast() ? '#CCCCCC' : '#666666',
              }}
            />
          </button>
          <button
            onClick={goToNextMonth}
            className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
            aria-label="Next month"
          >
            <ChevronRight className="h-5 w-5" style={{ color: '#666666' }} />
          </button>
        </div>
      </div>

      {/* Day Headers */}
      <div className="grid grid-cols-7 mb-2">
        {dayHeaders.map((day) => (
          <div key={day} className="text-center text-xs uppercase" style={{ color: '#999999' }}>
            {day}
          </div>
        ))}
      </div>

      {/* Calendar Grid */}
      <div className="grid grid-cols-7 gap-1">
        {days.map((date, index) => {
          const dateStr = formatDate(date);
          const isCurrentMonth = date.getMonth() === currentMonth.getMonth();
          const isToday = date.getTime() === today.getTime();
          const isAvailable = availableDates.includes(dateStr);
          const isSelected = selectedDate === dateStr;
          const isPast = date < today;

          // Don't render dates outside current month view
          if (
            (index < 7 && date.getDate() > 7) || // Skip leading dates from previous month
            (index > 27 && date.getDate() < 15) // Skip trailing dates from next month
          ) {
            return <div key={index} className="h-9" />;
          }

          return (
            <button
              key={index}
              onClick={() => isAvailable && !isPast && onDateSelect(dateStr)}
              disabled={!isAvailable || isPast}
              className={`
                h-9 w-9 mx-auto rounded-lg text-base font-medium relative flex items-center justify-center
                ${isCurrentMonth ? '' : 'text-gray-400 dark:text-gray-600'}
                ${isToday ? 'font-bold' : ''}
                ${
                  isAvailable && !isPast
                    ? isSelected
                      ? 'cursor-pointer bg-[#7E22CE] hover:bg-[#7E22CE] text-white'
                      : 'cursor-pointer hover:bg-purple-100 dark:hover:bg-purple-900/20'
                    : 'cursor-not-allowed'
                }
                transition-colors
              `}
              style={{
                color: isSelected ? '#FFFFFF' : (isAvailable && !isPast && isCurrentMonth ? '#333333' : '#CCCCCC'),
                textDecoration: isToday ? 'underline' : 'none',
                textDecorationThickness: isToday ? '2px' : undefined,
                textDecorationColor: isToday ? '#6b21a8' : undefined,
                textUnderlineOffset: isToday ? '4px' : undefined,
              }}
            >
              {date.getDate()}
            </button>
          );
        })}
      </div>
    </div>
  );
}
