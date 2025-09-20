// frontend/components/modals/ApplyToFutureWeeksModal.tsx

/**
 * ApplyToFutureWeeksModal Component
 *
 * Modal for applying the current week's schedule to future weeks.
 * Allows selection of end date with various options.
 *
 * @component
 * @module components/modals
 */

import React, { useState, useEffect } from 'react';
import { Calendar, Info } from 'lucide-react';
import Modal from '@/components/Modal';
import { formatDateForAPI, getEndDateForOption } from '@/lib/availability/dateHelpers';
import { logger } from '@/lib/logger';

/**
 * Props for ApplyToFutureWeeksModal component
 */
interface ApplyToFutureWeeksModalProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Callback when modal is closed */
  onClose: () => void;
  /** Callback when apply is confirmed */
  onConfirm: (endDate: string) => void;
  /** Whether the current week has any availability */
  hasAvailability: boolean;
  /** Current week start date */
  currentWeekStart: Date;
}

/**
 * Options for applying to future weeks
 */
type ApplyOption = 'end-of-year' | 'date' | 'indefinitely';

/**
 * Modal for applying schedule to future weeks
 *
 * @param {ApplyToFutureWeeksModalProps} props - Component props
 * @returns Modal component or null if not open
 *
 * @example
 * ```tsx
 * <ApplyToFutureWeeksModal
 *   isOpen={showApplyModal}
 *   onClose={() => setShowApplyModal(false)}
 *   onConfirm={handleApplyToFuture}
 *   hasAvailability={Object.keys(weekSchedule).length > 0}
 *   currentWeekStart={currentWeekStart}
 * />
 * ```
 */
export default function ApplyToFutureWeeksModal({
  isOpen,
  onClose,
  onConfirm,
  hasAvailability,
  currentWeekStart,
}: ApplyToFutureWeeksModalProps): React.ReactElement | null {
  const [selectedOption, setSelectedOption] = useState<ApplyOption>('end-of-year');
  const [customDate, setCustomDate] = useState<string>('');

  /**
   * Initialize default custom date
   */
  useEffect(() => {
    if (isOpen && !customDate) {
      // Default to end of next month
      const defaultDate = new Date();
      defaultDate.setMonth(defaultDate.getMonth() + 2, 0);
      setCustomDate(formatDateForAPI(defaultDate));
    }
  }, [isOpen, customDate]);

  if (!isOpen) return null;

  /**
   * Handle confirm action
   */
  const handleConfirm = () => {
    const endDate = getEndDateForOption(selectedOption, customDate);

    logger.info('Apply to future weeks confirmed', {
      option: selectedOption,
      endDate,
      hasAvailability,
    });

    onConfirm(endDate);
    onClose();
  };

  /**
   * Get minimum date for date picker (next week)
   */
  const getMinDate = (): string => {
    const nextWeek = new Date(currentWeekStart);
    nextWeek.setDate(nextWeek.getDate() + 7);
    return formatDateForAPI(nextWeek);
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Apply Schedule to Future Weeks" size="md">
      <div className="space-y-6">
        {/* Description */}
        <div className="flex items-start gap-3">
          <Info className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
          <div className="flex-1 text-sm text-gray-600">
            <p>
              {hasAvailability
                ? "This will copy the current week's schedule to future weeks and save automatically."
                : 'This will clear the schedule for future weeks and save automatically.'}
            </p>
            <p className="mt-2">
              <strong>Note:</strong> Existing bookings in future weeks will be preserved.
            </p>
          </div>
        </div>

        {/* Date Options */}
        <div className="space-y-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="radio"
              value="end-of-year"
              checked={selectedOption === 'end-of-year'}
              onChange={() => setSelectedOption('end-of-year')}
              className="w-4 h-4 text-indigo-600 focus:ring-indigo-500"
            />
            <span className="text-gray-700">Until end of this year</span>
          </label>

          <div>
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="radio"
                value="date"
                checked={selectedOption === 'date'}
                onChange={() => setSelectedOption('date')}
                className="w-4 h-4 text-indigo-600 focus:ring-indigo-500"
              />
              <span className="text-gray-700">Until specific date</span>
            </label>

            {selectedOption === 'date' && (
              <div className="ml-7 mt-2">
                <input
                  type="date"
                  value={customDate}
                  onChange={(e) => setCustomDate(e.target.value)}
                  min={getMinDate()}
                  className="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none
                           focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                  aria-label="Select end date"
                />
              </div>
            )}
          </div>

          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="radio"
              value="indefinitely"
              checked={selectedOption === 'indefinitely'}
              onChange={() => setSelectedOption('indefinitely')}
              className="w-4 h-4 text-indigo-600 focus:ring-indigo-500"
            />
            <span className="text-gray-700">Apply indefinitely (1 year)</span>
          </label>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-3 justify-end pt-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg
                     hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2
                     focus:ring-gray-500 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-[#7E22CE]
                     focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#7E22CE]
                     transition-colors flex items-center gap-2"
          >
            <Calendar className="w-4 h-4" />
            <span>Apply & Save</span>
          </button>
        </div>
      </div>
    </Modal>
  );
}
