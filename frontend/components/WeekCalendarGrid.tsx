// frontend/components/WeekCalendarGrid.tsx
import React from 'react';
import { logger } from '@/lib/logger';

/**
 * DateInfo interface for week dates
 */
interface DateInfo {
  date: Date;
  dateStr: string;
  dayOfWeek: string;
  fullDate: string;
}

/**
 * WeekCalendarGrid Component
 *
 * Displays a week-based calendar grid for managing availability.
 * Supports both desktop (table) and mobile (list) views with configurable hour ranges.
 *
 * Features:
 * - Configurable start and end hours
 * - Responsive design (table on desktop, list on mobile)
 * - Custom cell renderers for flexibility
 * - Past date indication
 * - Week navigation support
 * - Structured logging for debugging
 *
 * @component
 * @example
 * ```tsx
 * <WeekCalendarGrid
 *   weekDates={weekDates}
 *   startHour={8}
 *   endHour={20}
 *   renderCell={(date, hour) => <TimeSlotButton {...props} />}
 *   renderMobileCell={(date, hour) => <TimeSlotButton isMobile {...props} />}
 * />
 * ```
 */
interface WeekCalendarGridProps {
  /** Array of date information for the week */
  weekDates: DateInfo[];
  /** Starting hour for the grid (0-23) */
  startHour?: number;
  /** Ending hour for the grid (0-23) */
  endHour?: number;
  /** Function to render each cell in desktop view */
  renderCell: (date: string, hour: number) => React.ReactNode;
  /** Optional function to render cells in mobile view */
  renderMobileCell?: (date: string, hour: number) => React.ReactNode;
  /** Optional callback for week navigation */
  onNavigateWeek?: (direction: 'prev' | 'next') => void;
  /** Optional display string for current week */
  currentWeekDisplay?: string;
}

const WeekCalendarGrid: React.FC<WeekCalendarGridProps> = ({
  weekDates,
  startHour = 8,
  endHour = 20,
  renderCell,
  renderMobileCell,
  onNavigateWeek,
  currentWeekDisplay,
}) => {
  /**
   * Generate array of hours based on start and end times
   */
  const hours = Array.from({ length: endHour - startHour + 1 }, (_, i) => startHour + i);

  /**
   * Format hour for display
   * @param hour - Hour in 24-hour format
   * @returns Formatted time string (e.g., "9:00 AM")
   */
  const formatHour = (hour: number): string => {
    const period = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour % 12 || 12;
    return `${displayHour}:00 ${period}`;
  };

  /**
   * Check if a date is in the past
   * @param dateStr - Date string in YYYY-MM-DD format
   * @returns Whether the date is before today
   */
  const isPastDate = (dateStr: string): boolean => {
    const date = new Date(dateStr);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    date.setHours(0, 0, 0, 0);
    return date < today;
  };

  // Log component initialization
  logger.debug('WeekCalendarGrid initialized', {
    weekStartDate: weekDates[0]?.fullDate,
    weekEndDate: weekDates[weekDates.length - 1]?.fullDate,
    hourRange: { startHour, endHour },
    totalHours: hours.length,
    daysInWeek: weekDates.length,
    hasNavigation: !!onNavigateWeek,
  });

  /**
   * Handle week navigation with logging
   */
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _handleNavigateWeek = (direction: 'prev' | 'next') => {
    logger.info('Week navigation triggered', {
      direction,
      currentWeek: currentWeekDisplay || weekDates[0]?.fullDate,
    });

    if (onNavigateWeek) {
      onNavigateWeek(direction);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      {/* Header */}
      <div className="mb-4">
        <h3 className="text-lg font-semibold">Week Schedule</h3>
        <p className="text-sm text-gray-600">Click time slots to toggle availability</p>
      </div>

      {/* Desktop Grid View */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full table-fixed">
          <thead>
            <tr>
              <th className="text-left p-2 text-gray-600 w-24">Time</th>
              {weekDates.map((dateInfo, index) => {
                const isPast = isPastDate(dateInfo.fullDate);
                logger.debug('Rendering day header', {
                  day: dateInfo.dayOfWeek,
                  date: dateInfo.fullDate,
                  isPast,
                });

                return (
                  <th key={index} className="text-center p-2 text-gray-600 w-32">
                    <div className="font-semibold capitalize">{dateInfo.dayOfWeek}</div>
                    <div className="text-sm font-normal">{dateInfo.dateStr}</div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {hours.map((hour) => (
              <tr key={hour} className="border-t">
                <td className="p-2 text-sm text-gray-600 w-24">{formatHour(hour)}</td>
                {weekDates.map((dateInfo) => (
                  <td key={`${dateInfo.fullDate}-${hour}`} className="p-1 w-32">
                    {renderCell(dateInfo.fullDate, hour)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile List View */}
      <div className="md:hidden space-y-4">
        {weekDates.map((dateInfo, index) => {
          const isPast = isPastDate(dateInfo.fullDate);

          logger.debug('Rendering mobile day view', {
            day: dateInfo.dayOfWeek,
            date: dateInfo.fullDate,
            isPast,
            index,
          });

          return (
            <div key={index} className={`border rounded-lg p-4 ${isPast ? 'bg-gray-50' : ''}`}>
              <h3 className="font-semibold capitalize mb-1">{dateInfo.dayOfWeek}</h3>
              <p className="text-sm text-gray-600 mb-3">
                {dateInfo.dateStr}
                {isPast && <span className="text-gray-500 ml-2">(Past date)</span>}
              </p>
              <div className="grid grid-cols-3 gap-2">
                {hours.map((hour) => (
                  <React.Fragment key={`${dateInfo.fullDate}-${hour}`}>
                    {renderMobileCell
                      ? renderMobileCell(dateInfo.fullDate, hour)
                      : renderCell(dateInfo.fullDate, hour)}
                  </React.Fragment>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default WeekCalendarGrid;
