// frontend/components/availability/PresetButtons.tsx

/**
 * PresetButtons Component
 * 
 * Displays preset schedule buttons for quick availability setup.
 * Allows instructors to apply common schedule patterns with one click.
 * 
 * @component
 * @module components/availability
 */

import React from 'react';
import { Clock, Sun, Moon, Calendar, Trash2 } from 'lucide-react';
import { getPresetKeys, getPresetDisplayName } from '@/lib/availability/constants';
import { logger } from '@/lib/logger';

/**
 * Props for PresetButtons component
 */
interface PresetButtonsProps {
  /** Callback when a preset is selected */
  onPresetSelect: (presetKey: string) => void;
  /** Callback when clear week is clicked */
  onClearWeek: () => void;
  /** Whether buttons should be disabled */
  disabled?: boolean;
}

/**
 * Icon mapping for preset types
 */
const PRESET_ICONS: Record<string, React.ReactNode> = {
  'weekday_9_to_5': <Clock className="w-4 h-4" />,
  'mornings_only': <Sun className="w-4 h-4" />,
  'evenings_only': <Moon className="w-4 h-4" />,
  'weekends_only': <Calendar className="w-4 h-4" />
};

/**
 * Preset schedule buttons for quick availability setup
 * 
 * @param {PresetButtonsProps} props - Component props
 * @returns Preset buttons component
 * 
 * @example
 * ```tsx
 * <PresetButtons
 *   onPresetSelect={(preset) => applyPresetToWeek(preset)}
 *   onClearWeek={() => setShowClearConfirm(true)}
 *   disabled={isSaving}
 * />
 * ```
 */
export default function PresetButtons({
  onPresetSelect,
  onClearWeek,
  disabled = false
}: PresetButtonsProps): React.ReactElement {
  const presetKeys = getPresetKeys();
  
  /**
   * Handle preset button click
   */
  const handlePresetClick = (presetKey: string) => {
    logger.info('Preset selected', { preset: presetKey });
    onPresetSelect(presetKey);
  };
  
  /**
   * Handle clear week click
   */
  const handleClearClick = () => {
    logger.info('Clear week requested');
    onClearWeek();
  };
  
  return (
    <div className="mb-8">
      <h3 className="text-lg font-semibold mb-4">Quick Presets</h3>
      <div className="flex flex-wrap gap-3" role="group" aria-label="Schedule presets">
        {presetKeys.map((presetKey) => (
          <button
            key={presetKey}
            onClick={() => handlePresetClick(presetKey)}
            disabled={disabled}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg 
                     hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed
                     transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 
                     focus:ring-indigo-500"
            aria-label={`Apply ${getPresetDisplayName(presetKey)} schedule`}
          >
            {PRESET_ICONS[presetKey]}
            <span>{getPresetDisplayName(presetKey)}</span>
          </button>
        ))}
        
        <div className="border-l border-gray-300 mx-2" aria-hidden="true" />
        
        <button
          onClick={handleClearClick}
          disabled={disabled}
          className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg 
                   hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed
                   transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 
                   focus:ring-red-500"
          aria-label="Clear all availability for this week"
        >
          <Trash2 className="w-4 h-4" />
          <span>Clear Week</span>
        </button>
      </div>
    </div>
  );
}