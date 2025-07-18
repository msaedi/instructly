'use client';

import { logger } from '@/lib/logger';

interface DurationButtonsProps {
  durationOptions: Array<{
    duration: number;
    price: number;
  }>;
  selectedDuration: number;
  onDurationSelect: (duration: number) => void;
}

export default function DurationButtons({
  durationOptions,
  selectedDuration,
  onDurationSelect,
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
      <div className="flex flex-wrap gap-3">
        {durationOptions.map((option) => {
          const isSelected = selectedDuration === option.duration;

          return (
            <button
              key={option.duration}
              onClick={() => onDurationSelect(option.duration)}
              className={`
                h-10 px-5 rounded transition-colors
                ${
                  isSelected
                    ? 'text-white'
                    : 'bg-white dark:bg-gray-900 hover:bg-purple-50 dark:hover:bg-purple-900/20 text-gray-900 dark:text-gray-100'
                }
              `}
              style={{
                border: isSelected ? 'none' : '1px solid #E0E0E0',
                borderRadius: '4px',
                fontSize: '14px',
                backgroundColor: isSelected ? '#6B46C1' : undefined,
                color: isSelected ? '#FFFFFF' : '#333333',
              }}
            >
              {option.duration}m/${option.price}
            </button>
          );
        })}
      </div>
    </div>
  );
}
