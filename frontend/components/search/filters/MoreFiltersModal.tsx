'use client';

import { useState } from 'react';
import { X } from 'lucide-react';

import {
  type TaxonomyContentFilterDefinition,
  UNIVERSAL_SKILL_LEVEL_OPTIONS,
  type FilterState,
  type SkillLevelOption,
} from '../filterTypes';

const DURATION_OPTIONS = [
  { value: 30, label: '30 min' },
  { value: 45, label: '45 min' },
  { value: 60, label: '60 min' },
] as const;

const RATING_OPTIONS = [
  { value: 'any', label: 'Any' },
  { value: '4', label: '4+ stars' },
  { value: '4.5', label: '4.5+ stars' },
] as const;

interface MoreFiltersModalProps {
  isOpen: boolean;
  onClose: () => void;
  filters: FilterState;
  onFiltersChange: (filters: FilterState) => void;
  skillLevelOptions?: SkillLevelOption[];
  taxonomyContentFilters?: TaxonomyContentFilterDefinition[];
}

export function MoreFiltersModal({
  isOpen,
  onClose,
  filters,
  onFiltersChange,
  skillLevelOptions = UNIVERSAL_SKILL_LEVEL_OPTIONS,
  taxonomyContentFilters = [],
}: MoreFiltersModalProps) {
  const [draft, setDraft] = useState({
    duration: filters.duration,
    skillLevel: filters.skillLevel,
    contentFilters: filters.contentFilters,
    minRating: filters.minRating,
  });

  const toggleArrayValue = <T,>(list: T[], value: T): T[] =>
    list.includes(value) ? list.filter((item) => item !== value) : [...list, value];

  const handleApply = () => {
    onFiltersChange({
      ...filters,
      ...draft,
    });
    onClose();
  };

  const handleClear = () => {
    const cleared = {
      duration: [] as FilterState['duration'],
      skillLevel: [] as FilterState['skillLevel'],
      contentFilters: {} as FilterState['contentFilters'],
      minRating: 'any' as const,
    };
    setDraft(cleared);
    onFiltersChange({
      ...filters,
      ...cleared,
    });
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden="true" />

      <div
        className="relative bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 max-h-[85vh] flex flex-col"
        role="dialog"
        aria-modal="true"
        aria-label="More filters"
      >
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <h2 className="text-lg font-semibold">More filters</h2>
          <button
            type="button"
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-full"
            aria-label="Close more filters"
          >
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">Duration</h3>
            <div className="flex flex-wrap gap-2">
              {DURATION_OPTIONS.map((option) => (
                <label
                  key={option.value}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg cursor-pointer border ${
                    draft.duration.includes(option.value)
                      ? 'bg-purple-100 border-purple-300 text-purple-700'
                      : 'bg-white border-gray-100 text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={draft.duration.includes(option.value)}
                    onChange={() =>
                      setDraft((current) => ({
                        ...current,
                        duration: toggleArrayValue(current.duration, option.value),
                      }))
                    }
                    className="sr-only"
                  />
                  <span className="text-sm">{option.label}</span>
                </label>
              ))}
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">
              Skill Level
            </h3>
            <div className="flex flex-wrap gap-2">
              {skillLevelOptions.map((option) => (
                <label
                  key={option.value}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg cursor-pointer border ${
                    draft.skillLevel.includes(option.value)
                      ? 'bg-purple-100 border-purple-300 text-purple-700'
                      : 'bg-white border-gray-100 text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={draft.skillLevel.includes(option.value)}
                    onChange={() =>
                      setDraft((current) => ({
                        ...current,
                        skillLevel: toggleArrayValue(current.skillLevel, option.value),
                      }))
                    }
                    className="sr-only"
                  />
                  <span className="text-sm">{option.label}</span>
                </label>
              ))}
            </div>
          </div>

          {taxonomyContentFilters.map((filterDefinition) => (
            <div key={filterDefinition.key}>
              <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">
                {filterDefinition.label}
              </h3>
              <div className="flex flex-wrap gap-2">
                {filterDefinition.options.map((option) => {
                  const selectedValues = draft.contentFilters[filterDefinition.key] ?? [];
                  const isSelected = selectedValues.includes(option.value);

                  return (
                    <label
                      key={option.value}
                      className={`flex items-center gap-2 px-4 py-2 rounded-lg cursor-pointer border ${
                        isSelected
                          ? 'bg-purple-100 border-purple-300 text-purple-700'
                          : 'bg-white border-gray-100 text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() =>
                          setDraft((current) => {
                            const nextValues = toggleArrayValue(
                              current.contentFilters[filterDefinition.key] ?? [],
                              option.value
                            );
                            const nextContentFilters = { ...current.contentFilters };
                            if (nextValues.length > 0) {
                              nextContentFilters[filterDefinition.key] = nextValues;
                            } else {
                              delete nextContentFilters[filterDefinition.key];
                            }

                            return {
                              ...current,
                              contentFilters: nextContentFilters,
                            };
                          })
                        }
                        className="sr-only"
                      />
                      <span className="text-sm">{option.label}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          ))}

          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">Min Rating</h3>
            <div className="flex flex-wrap gap-2">
              {RATING_OPTIONS.map((option) => (
                <label
                  key={option.value}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg cursor-pointer border ${
                    draft.minRating === option.value
                      ? 'bg-purple-100 border-purple-300 text-purple-700'
                      : 'bg-white border-gray-100 text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <input
                    type="radio"
                    name="minRating"
                    checked={draft.minRating === option.value}
                    onChange={() =>
                      setDraft((current) => ({
                        ...current,
                        minRating: option.value,
                      }))
                    }
                    className="sr-only"
                  />
                  <span className="text-sm">{option.label}</span>
                </label>
              ))}
            </div>
          </div>
        </div>

        <div className="flex justify-between p-4 border-t border-gray-100">
          <button
            type="button"
            onClick={handleClear}
            className="px-4 py-2 text-gray-600 hover:text-gray-900"
          >
            Clear All
          </button>
          <button
            type="button"
            onClick={handleApply}
            className="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
          >
            Apply
          </button>
        </div>
      </div>
    </div>
  );
}
