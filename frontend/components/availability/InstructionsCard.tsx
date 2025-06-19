// frontend/components/availability/InstructionsCard.tsx

/**
 * InstructionsCard Component
 *
 * Displays helpful instructions for using the availability management system.
 * This is a static component that explains the key features and workflows.
 *
 * @component
 * @module components/availability
 */

import React from 'react';
import { Info } from 'lucide-react';

/**
 * Static instructions card for availability management
 *
 * @returns Instructions card component
 *
 * @example
 * ```tsx
 * <InstructionsCard />
 * ```
 */
export default function InstructionsCard(): React.ReactElement {
  return (
    <div className="mt-8 p-4 bg-blue-50 rounded-lg" role="region" aria-label="Instructions">
      <div className="flex items-start gap-2">
        <Info className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" aria-hidden="true" />
        <div className="flex-1">
          <h3 className="font-semibold text-blue-900 mb-2">How it works:</h3>
          <ul className="text-sm text-blue-800 space-y-1" role="list">
            <li>• Each week's schedule is independent - changes only affect the displayed week</li>
            <li>• Use "Save This Week" to save changes for the current week only</li>
            <li>• Use "Copy from Previous Week" to duplicate last week's schedule</li>
            <li>
              • Use "Apply to Future Weeks" to copy this pattern forward with automatic saving
            </li>
            <li>• Presets apply a standard schedule pattern to the current week</li>
            <li>• Navigate between weeks using the arrow buttons</li>
            <li>• Click on booked slots to view booking details</li>
            <li>• Past time slots are read-only and cannot be modified</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
