'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { X } from 'lucide-react';

import {
  type ContentFilterSelections,
  type TaxonomyContentFilterDefinition,
  UNIVERSAL_SKILL_LEVEL_OPTIONS,
  type FilterState,
  type SkillLevelOption,
} from '../filterTypes';
import { logger } from '@/lib/logger';
import { useFocusTrap } from '@/hooks/useFocusTrap';
import { useScrollLock } from '@/hooks/useScrollLock';

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

const EMPTY_TAXONOMY_CONTENT_FILTERS: TaxonomyContentFilterDefinition[] = [];
const EMPTY_SUGGESTED_CONTENT_FILTERS: ContentFilterSelections = {};
function FilterChipGroup<T extends string | number>({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: readonly { value: T; label: string }[];
  selected: readonly T[];
  onToggle: (value: T) => void;
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-700 mb-3 uppercase tracking-wide">{label}</h3>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => (
          <label
            key={String(option.value)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg cursor-pointer border ${
              selected.includes(option.value)
                ? 'bg-purple-100 border-purple-300 text-purple-700'
                : 'bg-white border-gray-100 text-gray-700 hover:bg-gray-50'
            }`}
          >
            <input
              type="checkbox"
              checked={selected.includes(option.value)}
              onChange={() => onToggle(option.value)}
              className="sr-only"
            />
            <span className="text-sm">{option.label}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

interface MoreFiltersModalProps {
  isOpen: boolean;
  onClose: () => void;
  filters: FilterState;
  onFiltersChange: (filters: FilterState) => void;
  skillLevelOptions?: SkillLevelOption[];
  taxonomyContentFilters?: TaxonomyContentFilterDefinition[];
  suggestedContentFilters?: ContentFilterSelections;
}

interface MoreFiltersModalContentProps {
  onClose: () => void;
  filters: FilterState;
  onFiltersChange: (filters: FilterState) => void;
  skillLevelOptions: SkillLevelOption[];
  taxonomyContentFilters: TaxonomyContentFilterDefinition[];
  suggestedContentFilters: ContentFilterSelections;
}

function buildInitialDraft(
  filters: FilterState,
  taxonomyContentFilters: TaxonomyContentFilterDefinition[],
  suggestedContentFilters: ContentFilterSelections
) {
  const mergedContentFilters: ContentFilterSelections = { ...filters.contentFilters };
  for (const filterDefinition of taxonomyContentFilters) {
    if ((mergedContentFilters[filterDefinition.key] ?? []).length > 0) {
      continue;
    }

    const suggestedValues = suggestedContentFilters[filterDefinition.key] ?? [];
    if (!suggestedValues.length) continue;

    const allowedValues = new Set(filterDefinition.options.map((option) => option.value));
    const nextValues = suggestedValues.filter((value) => allowedValues.has(value));
    if (nextValues.length > 0) {
      mergedContentFilters[filterDefinition.key] = nextValues;
    }
  }

  return {
    duration: filters.duration,
    skillLevel: filters.skillLevel,
    contentFilters: mergedContentFilters,
    minRating: filters.minRating,
  };
}

function MoreFiltersModalContent({
  onClose,
  filters,
  onFiltersChange,
  skillLevelOptions,
  taxonomyContentFilters,
  suggestedContentFilters,
}: MoreFiltersModalContentProps) {
  const [draft, setDraft] = useState(() =>
    buildInitialDraft(filters, taxonomyContentFilters, suggestedContentFilters)
  );
  const modalRef = useRef<HTMLDivElement | null>(null);
  const titleId = useId();

  useEffect(() => {
    if (process.env.NODE_ENV === 'production') return;
    logger.debug('[search:taxonomy] MoreFiltersModal taxonomy props', {
      taxonomyContentFilterCount: taxonomyContentFilters.length,
      taxonomyContentFilterKeys: taxonomyContentFilters.map((filter) => filter.key),
    });
  }, [taxonomyContentFilters]);

  useFocusTrap({
    isOpen: true,
    containerRef: modalRef,
    onEscape: onClose,
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

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center">
      <div className="insta-dialog-backdrop bg-black/50" onClick={onClose} aria-hidden="true" />

      <div
        ref={modalRef}
        className="insta-dialog-panel relative w-full max-w-md mx-4 max-h-[85vh] flex flex-col"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <h2 id={titleId} className="text-lg font-semibold">More filters</h2>
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
          <FilterChipGroup
            label="Duration"
            options={DURATION_OPTIONS}
            selected={draft.duration}
            onToggle={(value) =>
              setDraft((current) => ({
                ...current,
                duration: toggleArrayValue(current.duration, value),
              }))
            }
          />

          <FilterChipGroup
            label="Skill Level"
            options={skillLevelOptions}
            selected={draft.skillLevel}
            onToggle={(value) =>
              setDraft((current) => ({
                ...current,
                skillLevel: toggleArrayValue(current.skillLevel, value),
              }))
            }
          />

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
                            const currentValues = current.contentFilters[filterDefinition.key] ?? [];
                            const nextValues = filterDefinition.filter_type === 'single_select'
                              ? currentValues.includes(option.value)
                                ? []
                                : [option.value]
                              : toggleArrayValue(currentValues, option.value);
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

export function MoreFiltersModal({
  isOpen,
  onClose,
  filters,
  onFiltersChange,
  skillLevelOptions = UNIVERSAL_SKILL_LEVEL_OPTIONS,
  taxonomyContentFilters = EMPTY_TAXONOMY_CONTENT_FILTERS,
  suggestedContentFilters = EMPTY_SUGGESTED_CONTENT_FILTERS,
}: MoreFiltersModalProps) {
  useScrollLock(isOpen);
  if (!isOpen) return null;

  return (
    <MoreFiltersModalContent
      onClose={onClose}
      filters={filters}
      onFiltersChange={onFiltersChange}
      skillLevelOptions={skillLevelOptions}
      taxonomyContentFilters={taxonomyContentFilters}
      suggestedContentFilters={suggestedContentFilters}
    />
  );
}
