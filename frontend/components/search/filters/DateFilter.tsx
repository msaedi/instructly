'use client';

import { useState } from 'react';
import { format } from 'date-fns';

import { FilterButton } from './FilterButton';

interface DateFilterProps {
  isOpen: boolean;
  onToggle: () => void;
  value: string | null;
  onChange: (date: string | null) => void;
  onClose: () => void;
}

export function DateFilter({
  isOpen,
  onToggle,
  value,
  onChange,
  onClose,
}: DateFilterProps) {
  const [draft, setDraft] = useState<string | null>(value);

  const handleToggle = () => {
    if (!isOpen) {
      setDraft(value);
    }
    onToggle();
  };

  const handleApply = () => {
    onChange(draft || null);
    onClose();
  };

  const handleClear = () => {
    setDraft(null);
    onChange(null);
    onClose();
  };

  const label = value ? format(new Date(`${value}T00:00:00`), 'MMM d') : 'Date';
  const todayIso = format(new Date(), 'yyyy-MM-dd');

  return (
    <FilterButton
      label={label}
      isOpen={isOpen}
      isActive={Boolean(value)}
      onClick={handleToggle}
      onClickOutside={onClose}
    >
      <div className="p-4">
        <h3 className="font-medium text-gray-900 mb-3">Select Date</h3>

        <input
          type="date"
          value={draft ?? ''}
          onChange={(event) => setDraft(event.target.value || null)}
          min={todayIso}
          aria-label="Select date"
          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white text-gray-700 placeholder:text-gray-400 focus:outline-none focus:ring-0 focus:border-gray-300"
        />

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
