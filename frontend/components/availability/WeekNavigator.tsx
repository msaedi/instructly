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
import { ChevronLeft, ChevronRight, Calendar } from 'lucide-react';
import { formatWeekRange } from '@/lib/availability/dateHelpers';
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

  const weekRangeDisplay = formatWeekRange(currentWeekStart);

  return (
    <div className="mb-6 bg-white rounded-lg shadow p-4">
      <div className="flex items-center justify-between">
        {/* Previous Week Button */}
        <button
          onClick={() => handleNavigate('prev')}
          disabled={disabled}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors
                   disabled:opacity-50 disabled:cursor-not-allowed
                   focus:outline-none focus:ring-2 focus:ring-offset-2
                   focus:ring-indigo-500"
          title="Previous week"
          aria-label="Go to previous week"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>

        {/* Week Display */}
        <div className="text-center flex-1">
          <div className="flex items-center justify-center gap-2 mb-1">
            <Calendar className="w-5 h-5 text-gray-500" aria-hidden="true" />
            <h2 className="text-xl font-semibold">{weekRangeDisplay}</h2>
          </div>
          <p className="text-sm text-gray-600">
            Edit availability for this specific week
            {hasUnsavedChanges && (
              <span className="text-amber-600 font-medium ml-2">(unsaved changes)</span>
            )}
          </p>
        </div>

        {/* Next Week Button */}
        <button
          onClick={() => handleNavigate('next')}
          disabled={disabled}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors
                   disabled:opacity-50 disabled:cursor-not-allowed
                   focus:outline-none focus:ring-2 focus:ring-offset-2
                   focus:ring-indigo-500"
          title="Next week"
          aria-label="Go to next week"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
