'use client';

import { useState } from 'react';

import { FilterButton } from './FilterButton';

const TIME_OPTIONS = [
  { value: 'morning', label: 'Morning', sublabel: '6am - 12pm' },
  { value: 'afternoon', label: 'Afternoon', sublabel: '12pm - 5pm' },
  { value: 'evening', label: 'Evening', sublabel: '5pm - 9pm' },
] as const;

interface TimeFilterProps {
  isOpen: boolean;
  onToggle: () => void;
  value: Array<(typeof TIME_OPTIONS)[number]['value']>;
  onChange: (times: Array<(typeof TIME_OPTIONS)[number]['value']>) => void;
  onClose: () => void;
}

export function TimeFilter({
  isOpen,
  onToggle,
  value,
  onChange,
  onClose,
}: TimeFilterProps) {
  const [draft, setDraft] = useState(value);

  const handleToggle = () => {
    if (!isOpen) {
      setDraft(value);
    }
    onToggle();
  };

  const toggleTime = (time: (typeof TIME_OPTIONS)[number]['value']) => {
    setDraft((prev) => (prev.includes(time) ? prev.filter((t) => t !== time) : [...prev, time]));
  };

  const handleApply = () => {
    onChange(draft);
    onClose();
  };

  const handleClear = () => {
    setDraft([]);
    onChange([]);
    onClose();
  };

  const label =
    value.length > 0
      ? value.length === 1
        ? TIME_OPTIONS.find((option) => option.value === value[0])?.label || 'Time'
        : `${value.length} times`
      : 'Time';

  return (
    <FilterButton
      label={label}
      isOpen={isOpen}
      isActive={value.length > 0}
      onClick={handleToggle}
      onClickOutside={onClose}
    >
      <div className="p-4">
        <h3 className="font-medium text-gray-900 mb-3">Time of Day</h3>

        <div className="space-y-2">
          {TIME_OPTIONS.map((option) => (
            <label
              key={option.value}
              className="flex items-center gap-3 py-2 px-2 rounded-lg cursor-pointer hover:bg-gray-50"
            >
              <input
                type="checkbox"
                checked={draft.includes(option.value)}
                onChange={() => toggleTime(option.value)}
                className="w-4 h-4 rounded border-gray-200 text-purple-600 focus:ring-purple-500"
              />
              <div>
                <div className="text-sm font-medium text-gray-900">{option.label}</div>
                <div className="text-xs text-gray-500">{option.sublabel}</div>
              </div>
            </label>
          ))}
        </div>

        <div className="flex justify-between mt-4 pt-3 border-t border-gray-100">
          <button
            type="button"
            onClick={handleClear}
            className="text-sm text-gray-600 hover:text-gray-900"
          >
            Clear
          </button>
          <button
            type="button"
            onClick={handleApply}
            className="px-4 py-1.5 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700"
          >
            Apply
          </button>
        </div>
      </div>
    </FilterButton>
  );
}
