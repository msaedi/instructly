'use client';

import { logger } from '@/lib/logger';

interface DurationButtonsProps {
  durationOptions: Array<{
    duration: number;
    price: number;
  }>;
  selectedDuration: number;
  onDurationSelect: (duration: number) => void;
  disabledDurations?: number[];
}

export default function DurationButtons({
  durationOptions,
  selectedDuration,
  onDurationSelect,
  disabledDurations = [],
}: DurationButtonsProps) {
  logger.debug('DurationButtons rendered', {
    durationOptions,
    optionsLength: durationOptions.length,
    selectedDuration,
  });

  // Only show if instructor has multiple duration options
  if (durationOptions.length <= 1) {
    logger.debug('DurationButtons hiding - not enough options', {
      optionsLength: durationOptions.length,
    });
    return null;
  }

  return (
    <div className="mt-4">
      <div className="flex items-center gap-4">
        <p className="text-sm font-medium text-gray-700">Session duration:</p>
        <div className="flex gap-4">
          {durationOptions.map((option) => {
            const isSelected = selectedDuration === option.duration;
            const isDisabled = disabledDurations.includes(option.duration);
            const radioName = `duration-modal-${Date.now()}`; // Unique name to avoid conflicts

            return (
              <label
                key={option.duration}
                className={`flex items-center cursor-pointer ${isDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <input
                  type="radio"
                  name={radioName}
                  value={option.duration}
                  checked={isSelected}
                  onChange={() => !isDisabled && onDurationSelect(option.duration)}
                  disabled={isDisabled}
                  className="w-4 h-4 text-purple-700 accent-purple-700 border-gray-300 focus:ring-purple-500"
                />
                <span className="ml-2 text-sm text-gray-700">
                  {option.duration} min (${option.price})
                </span>
              </label>
            );
          })}
        </div>
      </div>
    </div>
  );
}
