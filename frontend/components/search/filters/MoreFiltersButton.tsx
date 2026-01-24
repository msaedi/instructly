'use client';

import type { FilterState } from '../filterTypes';

interface MoreFiltersButtonProps {
  filters: FilterState;
  onClick: () => void;
}

export function MoreFiltersButton({ filters, onClick }: MoreFiltersButtonProps) {
  const activeCount = [
    filters.duration.length > 0,
    filters.level.length > 0,
    filters.audience.length > 0,
    filters.minRating !== 'any',
  ].filter(Boolean).length;

  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-2 rounded-full border text-sm transition-colors ${
        activeCount > 0
          ? 'bg-purple-100 border-purple-300 text-purple-700'
          : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'
      }`}
    >
      <span>More filters</span>
      {activeCount > 0 && (
        <span className="bg-purple-600 text-white text-xs font-medium rounded-full px-1.5 py-0.5 min-w-[20px] text-center">
          {activeCount}
        </span>
      )}
    </button>
  );
}
