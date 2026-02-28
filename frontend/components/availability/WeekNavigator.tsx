// frontend/components/availability/WeekNavigator.tsx

/**
 * WeekNavigator Component
 *
 * Provides week navigation controls with current week display.
 * Shows week date range and navigation arrows for moving between weeks.
 *
 * @component
 * @module components/availability
 */

import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { logger } from '@/lib/logger';

/**
 * Props for WeekNavigator component
 */
interface WeekNavigatorProps {
  /** Current week's start date (Monday) */
  currentWeekStart: Date;
  /** Callback for navigation */
  onNavigate: (direction: 'prev' | 'next') => void;
  /** Whether navigation is disabled */
  disabled?: boolean;
  /** Whether to show unsaved changes warning */
  hasUnsavedChanges?: boolean;
  /** Whether to show the subtitle line under the week */
  showSubtitle?: boolean;
}

/**
 * Week navigation component with date display
 *
 * @param {WeekNavigatorProps} props - Component props
 * @returns Week navigator component
 *
 * @example
 * ```tsx
 * <WeekNavigator
 *   currentWeekStart={currentWeekStart}
 *   onNavigate={navigateWeek}
 *   hasUnsavedChanges={hasUnsavedChanges}
 * />
 * ```
 */
export default function WeekNavigator({
  currentWeekStart,
  onNavigate,
  disabled = false,
  hasUnsavedChanges = false,
  showSubtitle = true,
}: WeekNavigatorProps): React.ReactElement {
  /**
   * Handle navigation with logging
   */
  const handleNavigate = (direction: 'prev' | 'next') => {
    logger.debug('Week navigation requested', {
      direction,
      hasUnsavedChanges,
    });
    onNavigate(direction);
  };

  // Show month + year. If the week spans two different months/years, show both.
  const start = currentWeekStart;
  const end = new Date(currentWeekStart.getTime() + 6 * 24 * 60 * 60 * 1000);
  const sMonth = start.toLocaleDateString('en-US', { month: 'long' });
  const eMonth = end.toLocaleDateString('en-US', { month: 'long' });
  const sYear = start.getFullYear();
  const eYear = end.getFullYear();
  let weekRangeDisplay = '';
  if (sYear === eYear) {
    if (sMonth === eMonth) {
      weekRangeDisplay = `${sMonth} ${sYear}`;
    } else {
      weekRangeDisplay = `${sMonth} – ${eMonth} ${sYear}`;
    }
  } else {
    weekRangeDisplay = `${sMonth} ${sYear} – ${eMonth} ${eYear}`;
  }

  const weekStartAttribute = new Date(currentWeekStart);
  weekStartAttribute.setHours(0, 0, 0, 0);
  const weekStartISO = weekStartAttribute.toISOString().slice(0, 10);

  return (
    <div
      className="mb-6 bg-white rounded-lg border border-gray-200 p-5 shadow-sm insta-surface-card insta-availability-week-nav"
      data-testid="week-header"
      data-week-start={weekStartISO}
    >
      <div className="flex items-center justify-between">
        {/* Previous Week Button */}
        <button
          onClick={() => handleNavigate('prev')}
          disabled={disabled}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors
                   disabled:opacity-50 disabled:cursor-not-allowed
                   focus:outline-none focus:ring-2 focus:ring-offset-2
                   focus:ring-[#7E22CE]"
          title="Previous week"
          aria-label="Go to previous week"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>

        {/* Week Display */}
        <div className="text-center flex-1">
          <div className="flex items-center justify-center mb-1">
            <h2 className="text-2xl font-bold text-gray-900">{weekRangeDisplay}</h2>
          </div>
          {showSubtitle && (
            <p className="text-sm text-gray-600">
              Edit availability for this specific week
              {hasUnsavedChanges && (
                <span className="text-amber-600 font-medium ml-2">(unsaved changes)</span>
              )}
            </p>
          )}
        </div>

        {/* Next Week Button */}
        <button
          onClick={() => handleNavigate('next')}
          disabled={disabled}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors
                   disabled:opacity-50 disabled:cursor-not-allowed
                   focus:outline-none focus:ring-2 focus:ring-offset-2
                   focus:ring-[#7E22CE]"
          title="Next week"
          aria-label="Go to next week"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
