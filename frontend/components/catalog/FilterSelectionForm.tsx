'use client';

import { useCallback } from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { useSubcategoryFilters } from '@/hooks/queries/useTaxonomy';
import type { SubcategoryFilterResponse, FilterOptionResponse } from '@/features/shared/api/types';

interface FilterSelectionFormProps {
  subcategoryId: string;
  selections: Record<string, string[]>;
  onChange: (selections: Record<string, string[]>) => void;
}

export function FilterSelectionForm({
  subcategoryId,
  selections,
  onChange,
}: FilterSelectionFormProps) {
  const {
    data: filters,
    isLoading,
  } = useSubcategoryFilters(subcategoryId);

  const handleToggle = useCallback(
    (filterKey: string, optionValue: string, filterType: string) => {
      const current = selections[filterKey] ?? [];

      let next: string[];
      if (filterType === 'single_select') {
        next = current.includes(optionValue) ? [] : [optionValue];
      } else {
        next = current.includes(optionValue)
          ? current.filter((v) => v !== optionValue)
          : [...current, optionValue];
      }

      onChange({ ...selections, [filterKey]: next });
    },
    [selections, onChange],
  );

  if (!subcategoryId) return null;

  if (isLoading) {
    return <FilterFormSkeleton />;
  }

  if (!filters || filters.length === 0) {
    return null;
  }

  return (
    <div className="space-y-4">
      {filters.map((filter) => (
        <FilterGroup
          key={filter.filter_key}
          filter={filter}
          selected={selections[filter.filter_key] ?? []}
          onToggle={(value) => handleToggle(filter.filter_key, value, filter.filter_type)}
        />
      ))}
    </div>
  );
}

function FilterGroup({
  filter,
  selected,
  onToggle,
}: {
  filter: SubcategoryFilterResponse;
  selected: string[];
  onToggle: (value: string) => void;
}) {
  const options = filter.options ?? [];
  const sortedOptions = [...options].sort((a, b) => a.display_order - b.display_order);

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
        {filter.filter_display_name}
        {filter.filter_type === 'single_select' && (
          <span className="ml-1 text-xs text-gray-400">(select one)</span>
        )}
      </label>
      <div className="flex flex-wrap gap-2">
        {sortedOptions.map((option) => (
          <FilterOptionButton
            key={option.id}
            option={option}
            isSelected={selected.includes(option.value)}
            onToggle={onToggle}
          />
        ))}
      </div>
    </div>
  );
}

function FilterOptionButton({
  option,
  isSelected,
  onToggle,
}: {
  option: FilterOptionResponse;
  isSelected: boolean;
  onToggle: (value: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onToggle(option.value)}
      className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
        isSelected
          ? 'border-[#7E22CE] bg-[#7E22CE]/10 text-[#7E22CE] dark:border-purple-500 dark:bg-purple-500/20 dark:text-purple-300'
          : 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
      }`}
    >
      {option.display_name}
    </button>
  );
}

function FilterFormSkeleton() {
  return (
    <div className="space-y-4">
      {Array.from({ length: 2 }, (_, i) => (
        <div key={i}>
          <Skeleton className="h-4 w-24 mb-2" />
          <div className="flex gap-2">
            <Skeleton className="h-8 w-20 rounded-lg" />
            <Skeleton className="h-8 w-24 rounded-lg" />
            <Skeleton className="h-8 w-16 rounded-lg" />
          </div>
        </div>
      ))}
    </div>
  );
}
