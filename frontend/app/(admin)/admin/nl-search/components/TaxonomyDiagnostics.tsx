'use client';

import type { components } from '@/features/shared/api/types';

type SearchMeta = components['schemas']['NLSearchMeta'];
type ContentFilterDefinition = components['schemas']['NLSearchContentFilterDefinition'];

type SubcategorySource = 'explicit' | 'inferred' | 'none';

function getSubcategorySource(meta: SearchMeta): SubcategorySource {
  if (!meta.effective_subcategory_id) {
    return 'none';
  }

  const filtersApplied = meta.filters_applied ?? [];
  if (filtersApplied.includes('subcategory')) {
    return 'explicit';
  }

  return 'inferred';
}

function getHardFiltersApplied(meta: SearchMeta): string[] {
  return (meta.filters_applied ?? []).filter((value) => value === 'subcategory' || value.startsWith('taxonomy:'));
}

function getInferredFilters(meta: SearchMeta): Array<{ key: string; values: string[] }> {
  if (!meta.inferred_filters) {
    return [];
  }

  return Object.entries(meta.inferred_filters)
    .map(([key, values]) => ({
      key,
      values: values.filter((value) => value.trim().length > 0),
    }))
    .filter((entry) => entry.values.length > 0);
}

function getAvailableFilters(meta: SearchMeta): ContentFilterDefinition[] {
  return (meta.available_content_filters ?? []).filter((definition) => definition.options && definition.options.length);
}

function sourceLabel(source: SubcategorySource): string {
  if (source === 'explicit') {
    return 'explicit (URL param)';
  }
  if (source === 'inferred') {
    return 'inferred (top-match consensus)';
  }
  return 'none';
}

export function TaxonomyDiagnostics({ meta }: { meta: SearchMeta }) {
  const inferredFilters = getInferredFilters(meta);
  const availableFilters = getAvailableFilters(meta);
  const hardFiltersApplied = getHardFiltersApplied(meta);
  const subcategorySource = getSubcategorySource(meta);

  return (
    <div className="space-y-4 mt-4">
      <div className="p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Inferred Filters</h3>
        {inferredFilters.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">None inferred</p>
        ) : (
          <ul className="space-y-1 text-sm text-gray-700 dark:text-gray-300">
            {inferredFilters.map((entry) => (
              <li key={entry.key}>
                <span className="font-medium">{entry.key}:</span> {entry.values.join(', ')}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Effective Subcategory</h3>
        {meta.effective_subcategory_id ? (
          <div className="space-y-1 text-sm text-gray-700 dark:text-gray-300">
            <p>
              {meta.effective_subcategory_name ?? 'Unknown'} (ID: {meta.effective_subcategory_id})
            </p>
            <p>Source: {sourceLabel(subcategorySource)}</p>
          </div>
        ) : (
          <div className="space-y-1 text-sm text-gray-500 dark:text-gray-400">
            <p>Effective Subcategory: none</p>
            <p>Source: {sourceLabel(subcategorySource)}</p>
          </div>
        )}
      </div>

      <div className="p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Available Content Filters</h3>
        {availableFilters.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">No filter definitions available</p>
        ) : (
          <ul className="space-y-1 text-sm text-gray-700 dark:text-gray-300">
            {availableFilters.map((definition) => {
              const labels = definition.options?.map((option) => option.value).join(', ') ?? '-';
              return (
                <li key={definition.key}>
                  <span className="font-medium">
                    {definition.label} [{definition.type}]
                  </span>
                  : {labels}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="p-4 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Filter Application Status</h3>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          {hardFiltersApplied.length > 0
            ? `Hard Filters Applied: ${hardFiltersApplied.join(', ')}`
            : 'Hard Filters Applied: none (all inferred filters are soft)'}
        </p>
      </div>
    </div>
  );
}
