// frontend/components/availability/ActionButtons.tsx

/**
 * ActionButtons Component
 *
 * Primary action buttons for availability management including save,
 * copy from previous week, and apply to future weeks functionality.
 *
 * @component
 * @module components/availability
 */

import React from 'react';
import { Save, Copy, CalendarDays, Loader2 } from 'lucide-react';
import { logger } from '@/lib/logger';

/**
 * Props for ActionButtons component
 */
interface ActionButtonsProps {
  /** Save current week callback */
  onSave: () => void;
  /** Copy from previous week callback */
  onCopyPrevious: () => void;
  /** Apply to future weeks callback */
  onApplyFuture: () => void;
  /** Whether save operation is in progress */
  isSaving?: boolean;
  /** Whether validation is in progress */
  isValidating?: boolean;
  /** Whether there are unsaved changes */
  hasUnsavedChanges?: boolean;
  /** Whether buttons should be disabled */
  disabled?: boolean;
}

/**
 * Action buttons for availability management
 *
 * @param {ActionButtonsProps} props - Component props
 * @returns Action buttons component
 *
 * @example
 * ```tsx
 * <ActionButtons
 *   onSave={handleSave}
 *   onCopyPrevious={copyFromPreviousWeek}
 *   onApplyFuture={handleApplyToFutureWeeks}
 *   isSaving={isSaving}
 *   hasUnsavedChanges={hasUnsavedChanges}
 * />
 * ```
 */
export default function ActionButtons({
  onSave,
  onCopyPrevious,
  onApplyFuture,
  isSaving = false,
  isValidating = false,
  hasUnsavedChanges = false,
  disabled = false,
}: ActionButtonsProps): React.ReactElement {
  /**
   * Handle button clicks with logging
   */
  const handleAction = (action: string, callback: () => void) => {
    logger.info(`Action button clicked: ${action}`);
    callback();
  };

  const saveDisabled = disabled || isSaving || !hasUnsavedChanges || isValidating;
  const otherDisabled = disabled || isSaving;

  return (
    <div className="mb-6 flex flex-wrap gap-3 justify-between">
      {/* Left side - Copy and Apply buttons */}
      <div className="flex gap-3">
        <button
          onClick={() => handleAction('copy-previous', onCopyPrevious)}
          disabled={otherDisabled}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg
                   hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed
                   transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2
                   focus:ring-blue-500"
          aria-label="Copy schedule from previous week"
        >
          <Copy className="w-4 h-4" />
          <span>Copy from Previous Week</span>
        </button>

        <button
          onClick={() => handleAction('apply-future', onApplyFuture)}
          disabled={otherDisabled}
          className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg
                   hover:bg-[#7E22CE] disabled:opacity-50 disabled:cursor-not-allowed
                   transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2
                   focus:ring-[#7E22CE]"
          aria-label="Apply current schedule to future weeks"
        >
          <CalendarDays className="w-4 h-4" />
          <span>Apply to Future Weeks</span>
        </button>
      </div>

      {/* Right side - Save button */}
      <button
        onClick={() => handleAction('save', onSave)}
        disabled={saveDisabled}
        className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg
                 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed
                 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2
                 focus:ring-green-500"
        aria-label={isValidating ? 'Validating changes' : 'Save changes for this week'}
      >
        {isSaving || isValidating ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Save className="w-4 h-4" />
        )}
        <span>{isValidating ? 'Validating...' : isSaving ? 'Saving...' : 'Save This Week'}</span>
      </button>
    </div>
  );
}
