'use client';

import { useEffect, useMemo } from 'react';
import { useSubcategoryFilters } from '@/hooks/queries/useTaxonomy';
import { formatFilterLabel } from '@/lib/taxonomy/formatFilterLabel';
import { normalizeSelectionValues } from '@/lib/taxonomy/filterHelpers';
import type { FilterSelections } from '@/lib/taxonomy/filterHelpers';
import type { SubcategoryFilterResponse } from '@/features/shared/api/types';

/**
 * Minimal service shape consumed by RefineFiltersSection.
 * Both the onboarding SelectedService and the dashboard SelectedService
 * satisfy this interface without coupling to either.
 */
export type RefineFiltersServiceSlice = {
  catalog_service_id: string;
  subcategory_id: string;
  name?: string | null;
  filter_selections: Record<string, string[]>;
};

type RefineFiltersSectionProps = {
  service: RefineFiltersServiceSlice;
  expanded: boolean;
  onToggleExpanded: (serviceId: string) => void;
  onInitializeMissingFilters: (
    serviceId: string,
    defaults: FilterSelections
  ) => void;
  onSetFilterValues: (
    serviceId: string,
    filterKey: string,
    values: string[]
  ) => void;
};

export function RefineFiltersSection({
  service,
  expanded,
  onToggleExpanded,
  onInitializeMissingFilters,
  onSetFilterValues,
}: RefineFiltersSectionProps) {
  const { data: subcategoryFilters = [], isLoading } = useSubcategoryFilters(
    service.subcategory_id
  );

  const additionalFilters = useMemo(
    () =>
      subcategoryFilters.filter((filter) => filter.filter_key !== 'skill_level'),
    [subcategoryFilters]
  );

  useEffect(() => {
    if (!additionalFilters.length) {
      return;
    }

    const defaults: FilterSelections = {};
    for (const filter of additionalFilters) {
      if (service.filter_selections[filter.filter_key]) {
        continue;
      }
      const allValues = (filter.options ?? []).map((option) => option.value);
      if (allValues.length > 0) {
        defaults[filter.filter_key] = allValues;
      }
    }

    if (Object.keys(defaults).length > 0) {
      onInitializeMissingFilters(service.catalog_service_id, defaults);
    }
  }, [
    additionalFilters,
    onInitializeMissingFilters,
    service.catalog_service_id,
    service.filter_selections,
  ]);

  if (!service.subcategory_id || additionalFilters.length === 0) {
    return null;
  }

  return (
    <div className="bg-white rounded-lg p-3 border border-gray-200">
      <div className="w-full flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-gray-900 select-text">
          Refine what you teach (optional)
        </p>
        <button
          type="button"
          onClick={() => onToggleExpanded(service.catalog_service_id)}
          aria-expanded={expanded}
          aria-controls={`refine-filters-${service.catalog_service_id}`}
          aria-label={`Toggle refine filters for ${service.name ?? 'this service'}`}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-gray-200 text-gray-600 hover:bg-gray-100"
        >
          <svg
            className={`h-4 w-4 transition-transform ${
              expanded ? 'rotate-180' : ''
            }`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M19 9l-7 7-7-7"
            />
          </svg>
        </button>
      </div>

      {expanded && (
        <div id={`refine-filters-${service.catalog_service_id}`} className="mt-3 space-y-3">
          {isLoading ? (
            <div className="text-xs text-gray-500">Loading filters...</div>
          ) : (
            additionalFilters.map((filter: SubcategoryFilterResponse) => {
              const selectedValues = service.filter_selections[filter.filter_key] ?? [];
              const options = [...(filter.options ?? [])].sort(
                (a, b) => (a.display_order ?? 0) - (b.display_order ?? 0)
              );

              return (
                <div key={`${service.catalog_service_id}-${filter.filter_key}`}>
                  <p className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2">
                    {filter.filter_display_name}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {options.map((option) => {
                      const isSelected = selectedValues.includes(option.value);
                      return (
                        <button
                          key={option.id}
                          type="button"
                          onClick={() => {
                            let nextValues: string[];
                            if (filter.filter_type === 'single_select') {
                              nextValues = isSelected ? [] : [option.value];
                            } else {
                              const candidate = isSelected
                                ? selectedValues.filter((value) => value !== option.value)
                                : [...selectedValues, option.value];
                              nextValues = normalizeSelectionValues(candidate);
                            }
                            onSetFilterValues(
                              service.catalog_service_id,
                              filter.filter_key,
                              nextValues
                            );
                          }}
                          className={`px-2.5 py-1.5 text-xs rounded-md transition-colors ${
                            isSelected
                              ? 'bg-purple-100 text-[#7E22CE] border border-purple-300'
                              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                          }`}
                        >
                          {formatFilterLabel(option.value, option.display_name)}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
