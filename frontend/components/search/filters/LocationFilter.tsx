'use client';

import { useState } from 'react';

import { FilterButton } from './FilterButton';
import type { FilterState } from '../filterTypes';

const LOCATION_OPTIONS = [
  { value: 'any', label: 'Any location' },
  { value: 'online', label: 'Online only' },
  { value: 'travels', label: 'Travels to me' },
  { value: 'studio', label: 'At their studio' },
] as const;

interface LocationFilterProps {
  isOpen: boolean;
  onToggle: () => void;
  value: FilterState['location'];
  onChange: (location: FilterState['location']) => void;
  onClose: () => void;
}

export function LocationFilter({
  isOpen,
  onToggle,
  value,
  onChange,
  onClose,
}: LocationFilterProps) {
  const [draft, setDraft] = useState<FilterState['location']>(value);

  const handleToggle = () => {
    if (!isOpen) {
      setDraft(value);
    }
    onToggle();
  };

  const handleApply = () => {
    onChange(draft);
    onClose();
  };

  const handleClear = () => {
    setDraft('any');
    onChange('any');
    onClose();
  };

  const label =
    value !== 'any'
      ? LOCATION_OPTIONS.find((option) => option.value === value)?.label || 'Location'
      : 'Location';

  return (
    <FilterButton
      label={label}
      isOpen={isOpen}
      isActive={value !== 'any'}
      onClick={handleToggle}
      onClickOutside={onClose}
    >
      <div className="p-4">
        <h3 className="font-medium text-gray-900 mb-3">Location</h3>

        <div className="space-y-1">
          {LOCATION_OPTIONS.map((option) => (
            <label
              key={option.value}
              className="flex items-center gap-3 py-2 px-2 rounded-lg cursor-pointer hover:bg-gray-50"
            >
              <input
                type="radio"
                name="location"
                checked={draft === option.value}
                onChange={() => setDraft(option.value)}
                className="w-4 h-4 border-gray-200 text-purple-600 focus:ring-purple-500"
              />
              <span className="text-sm text-gray-700">{option.label}</span>
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
