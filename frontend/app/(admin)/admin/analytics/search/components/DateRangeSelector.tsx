// frontend/app/(admin)/admin/analytics/search/components/DateRangeSelector.tsx
'use client';

import { Calendar } from 'lucide-react';

interface DateRangeSelectorProps {
  value: number;
  onChange: (days: number) => void;
}

const DATE_RANGES = [
  { label: 'Last 7 days', value: 7 },
  { label: 'Last 30 days', value: 30 },
  { label: 'Last 90 days', value: 90 },
];

export function DateRangeSelector({ value, onChange }: DateRangeSelectorProps) {
  return (
    <div className="flex items-center space-x-2">
      <Calendar className="h-5 w-5 text-gray-500 dark:text-gray-400" />
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="px-3 py-1.5 text-sm rounded-full bg-white/70 dark:bg-gray-900/50 backdrop-blur ring-1 ring-gray-300/70 dark:ring-gray-700/60 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
      >
        {DATE_RANGES.map((range) => (
          <option key={range.value} value={range.value}>
            {range.label}
          </option>
        ))}
      </select>
    </div>
  );
}
