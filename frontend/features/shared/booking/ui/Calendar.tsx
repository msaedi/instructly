'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

interface CalendarProps {
  currentMonth: Date;
  selectedDate: string | null;
  preSelectedDate?: string;
  availableDates: string[];
  onDateSelect: (date: string) => void;
  onMonthChange: (date: Date) => void;
}

interface DayCell {
  date: Date;
  dateStr: string;
  rowIndex: number;
  isCurrentMonth: boolean;
  isToday: boolean;
  isAvailable: boolean;
  isSelected: boolean;
  isPast: boolean;
  isHidden: boolean;
}

const dayHeaders = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];

const formatDate = (date: Date): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const addDays = (date: Date, days: number): Date => {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
};

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

  const today = useMemo(() => {
    const now = new Date();
    now.setHours(0, 0, 0, 0);
    return now;
  }, []);

  // Get the first day of the month
  const firstDay = useMemo(
    () => new Date(currentMonth.getFullYear(), currentMonth.getMonth(), 1),
    [currentMonth],
  );

  const startDate = useMemo(() => {
    const next = new Date(firstDay);
    next.setDate(next.getDate() - firstDay.getDay()); // Start from Sunday
    return next;
  }, [firstDay]);

  const dayCells = useMemo<DayCell[]>(() => {
    const cells: DayCell[] = [];

    for (let index = 0; index < 42; index += 1) {
      // 6 weeks * 7 days
      const date = addDays(startDate, index);
      const dateStr = formatDate(date);
      const isCurrentMonth = date.getMonth() === currentMonth.getMonth();
      const isToday = date.getTime() === today.getTime();
      const isAvailable = availableDates.includes(dateStr);
      const isSelected = selectedDate === dateStr;
      const isPast = date < today;

      const isHidden =
        (index < 7 && date.getDate() > 7) || // Leading dates from previous month
        (index > 27 && date.getDate() < 15); // Trailing dates from next month

      cells.push({
        date,
        dateStr,
        rowIndex: Math.floor(index / 7),
        isCurrentMonth,
        isToday,
        isAvailable,
        isSelected,
        isPast,
        isHidden,
      });
    }

    return cells;
  }, [availableDates, currentMonth, selectedDate, startDate, today]);

  const rows = useMemo(() => {
    return Array.from({ length: 6 }, (_, rowIndex) =>
      dayCells.slice(rowIndex * 7, rowIndex * 7 + 7),
    );
  }, [dayCells]);

  const dayCellByDate = useMemo(() => {
    const lookup = new Map<string, DayCell>();
    for (const cell of dayCells) {
      if (!cell.isHidden) {
        lookup.set(cell.dateStr, cell);
      }
    }
    return lookup;
  }, [dayCells]);

  const visibleCells = useMemo(() => dayCells.filter((cell) => !cell.isHidden), [dayCells]);

  const [focusedDate, setFocusedDate] = useState<string | null>(null);
  const dayRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const initialFocusDate = useMemo(() => {
    if (!visibleCells.length) {
      return null;
    }
    const todayStr = formatDate(today);
    return (
      (selectedDate && dayCellByDate.has(selectedDate) && selectedDate) ||
      (preSelectedDate && dayCellByDate.has(preSelectedDate) && preSelectedDate) ||
      (dayCellByDate.has(todayStr) ? todayStr : null) ||
      visibleCells[0]?.dateStr ||
      null
    );
  }, [dayCellByDate, preSelectedDate, selectedDate, today, visibleCells]);

  const activeFocusedDate =
    focusedDate && dayCellByDate.has(focusedDate) ? focusedDate : initialFocusDate;

  useEffect(() => {
    if (!activeFocusedDate) {
      return;
    }

    const focusedElement = dayRefs.current[activeFocusedDate];
    if (focusedElement && document.activeElement !== focusedElement) {
      focusedElement.focus();
    }
  }, [activeFocusedDate]);

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

  const moveFocusByDays = (sourceDate: string, dayOffset: number) => {
    const sourceCell = dayCellByDate.get(sourceDate);
    if (!sourceCell) {
      return;
    }

    const targetDateStr = formatDate(addDays(sourceCell.date, dayOffset));
    if (dayCellByDate.has(targetDateStr)) {
      setFocusedDate(targetDateStr);
    }
  };

  const moveFocusToRowBoundary = (rowIndex: number, boundary: 'start' | 'end') => {
    const rowCells = rows[rowIndex] ?? [];
    const visibleRowCells = rowCells.filter((cell) => !cell.isHidden);
    const target =
      boundary === 'start'
        ? visibleRowCells[0]
        : visibleRowCells[visibleRowCells.length - 1];

    if (target) {
      setFocusedDate(target.dateStr);
    }
  };

  const handleDayKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, cell: DayCell) => {
    const isSelectable = cell.isAvailable && !cell.isPast;

    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      moveFocusByDays(cell.dateStr, -1);
      return;
    }

    if (event.key === 'ArrowRight') {
      event.preventDefault();
      moveFocusByDays(cell.dateStr, 1);
      return;
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault();
      moveFocusByDays(cell.dateStr, -7);
      return;
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      moveFocusByDays(cell.dateStr, 7);
      return;
    }

    if (event.key === 'Home') {
      event.preventDefault();
      moveFocusToRowBoundary(cell.rowIndex, 'start');
      return;
    }

    if (event.key === 'End') {
      event.preventDefault();
      moveFocusToRowBoundary(cell.rowIndex, 'end');
      return;
    }

    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (isSelectable) {
        onDateSelect(cell.dateStr);
      }
    }
  };

  return (
    <div>
      {/* Month Navigation */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-medium text-gray-700 dark:text-gray-200">
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
              className={`h-5 w-5 ${
                isMonthInPast() ? 'text-gray-300 dark:text-gray-600' : 'text-gray-600 dark:text-gray-300'
              }`}
            />
          </button>
          <button
            onClick={goToNextMonth}
            className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
            aria-label="Next month"
          >
            <ChevronRight className="h-5 w-5 text-gray-600 dark:text-gray-300" />
          </button>
        </div>
      </div>

      {/* Day Headers */}
      <div className="grid grid-cols-7 mb-2" role="row">
        {dayHeaders.map((day) => (
          <div
            key={day}
            role="columnheader"
            className="text-center text-xs uppercase text-gray-500 dark:text-gray-400"
          >
            {day}
          </div>
        ))}
      </div>

      {/* Calendar Grid */}
      <div
        role="grid"
        aria-label={currentMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
        className="space-y-1"
      >
        {rows.map((row, rowIndex) => (
          <div key={`week-${rowIndex}`} role="row" className="grid grid-cols-7 gap-1">
            {row.map((cell, index) => {
              if (cell.isHidden) {
                return <div key={`empty-${rowIndex}-${index}`} className="h-9" />;
              }

              const isSelectable = cell.isAvailable && !cell.isPast;
              const isFocused = activeFocusedDate === cell.dateStr;
              const dayTextClass = cell.isSelected
                ? 'text-white'
                : isSelectable && cell.isCurrentMonth
                  ? 'text-gray-800 dark:text-gray-100'
                  : cell.isCurrentMonth
                    ? 'text-gray-300 dark:text-gray-500'
                    : 'text-gray-400 dark:text-gray-600';

              return (
                <button
                  key={cell.dateStr}
                  ref={(element) => {
                    dayRefs.current[cell.dateStr] = element;
                  }}
                  data-testid={`cal-day-${cell.dateStr}`}
                  type="button"
                  role="gridcell"
                  onClick={() => {
                    if (isSelectable) {
                      onDateSelect(cell.dateStr);
                    }
                    setFocusedDate(cell.dateStr);
                  }}
                  onFocus={() => setFocusedDate(cell.dateStr)}
                  onKeyDown={(event) => handleDayKeyDown(event, cell)}
                  tabIndex={isFocused ? 0 : -1}
                  aria-selected={cell.isSelected}
                  aria-disabled={!isSelectable}
                  aria-current={cell.isSelected ? 'date' : undefined}
                  className={`
                    h-9 w-9 mx-auto rounded-lg text-base font-medium relative flex items-center justify-center
                    ${dayTextClass}
                    ${cell.isToday ? 'font-bold' : ''}
                    ${
                      isSelectable
                        ? cell.isSelected
                          ? 'cursor-pointer bg-[#7E22CE] hover:bg-[#7E22CE] text-white'
                          : 'cursor-pointer hover:bg-purple-100 dark:hover:bg-purple-900/20'
                        : 'cursor-not-allowed'
                    }
                    transition-colors
                  `}
                  style={{
                    textDecoration: cell.isToday ? 'underline' : 'none',
                    textDecorationThickness: cell.isToday ? '2px' : undefined,
                    textDecorationColor: cell.isToday ? '#6b21a8' : undefined,
                    textUnderlineOffset: cell.isToday ? '4px' : undefined,
                  }}
                >
                  {cell.date.getDate()}
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
