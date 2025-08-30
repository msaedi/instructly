// frontend/app/(admin)/admin/analytics/search/components/DateRangeSelector.tsx
'use client';

import { Calendar } from 'lucide-react';
import * as Select from '@radix-ui/react-select';
import { ChevronDown, Check } from 'lucide-react';

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
      <Select.Root value={String(value)} onValueChange={(v) => onChange(Number(v))}>
        <Select.Trigger className="inline-flex items-center justify-between min-w-[170px] rounded-full px-3 py-1.5 bg-white/70 dark:bg-gray-900/50 ring-1 ring-gray-300/70 dark:ring-gray-700/60 text-sm">
          <Select.Value />
          <Select.Icon>
            <ChevronDown className="h-4 w-4 text-gray-500" />
          </Select.Icon>
        </Select.Trigger>
        <Select.Portal>
          <Select.Content className="overflow-hidden rounded-md bg-white dark:bg-gray-800 shadow ring-1 ring-gray-200 dark:ring-gray-700">
            <Select.Viewport className="p-1">
              {DATE_RANGES.map((r) => (
                <Select.Item key={r.value} value={String(r.value)} className="relative flex select-none items-center rounded px-2 py-1.5 text-sm text-gray-800 dark:text-gray-200 data-[highlighted]:bg-gray-100 dark:data-[highlighted]:bg-gray-700 outline-none cursor-pointer">
                  <Select.ItemText>{r.label}</Select.ItemText>
                  <Select.ItemIndicator className="absolute right-2">
                    <Check className="h-4 w-4" />
                  </Select.ItemIndicator>
                </Select.Item>
              ))}
            </Select.Viewport>
          </Select.Content>
        </Select.Portal>
      </Select.Root>
    </div>
  );
}
