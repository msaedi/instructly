'use client';

import { useState, useMemo } from 'react';
import { ChevronDown, ChevronRight, Check, Search } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import {
  useCategoriesWithSubcategories,
  useCategoryTree,
} from '@/hooks/queries/useTaxonomy';

export interface SelectedService {
  serviceId: string;
  serviceName: string;
  subcategoryId: string;
  subcategoryName: string;
  categoryId: string;
  categoryName: string;
}

interface CatalogServicePickerProps {
  selected: SelectedService[];
  onChange: (services: SelectedService[]) => void;
  maxSelections?: number;
}

export function CatalogServicePicker({
  selected,
  onChange,
  maxSelections,
}: CatalogServicePickerProps) {
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);
  const [searchFilter, setSearchFilter] = useState('');

  const {
    data: categories,
    isLoading: categoriesLoading,
  } = useCategoriesWithSubcategories();

  const {
    data: categoryTree,
    isLoading: treeLoading,
  } = useCategoryTree(expandedCategory ?? '');

  const selectedIds = useMemo(
    () => new Set(selected.map((s) => s.serviceId)),
    [selected],
  );

  const toggleService = (service: SelectedService) => {
    if (selectedIds.has(service.serviceId)) {
      onChange(selected.filter((s) => s.serviceId !== service.serviceId));
    } else if (!maxSelections || selected.length < maxSelections) {
      onChange([...selected, service]);
    }
  };

  const toggleCategory = (categoryId: string) => {
    setExpandedCategory((prev) => (prev === categoryId ? null : categoryId));
  };

  if (categoriesLoading) {
    return <PickerSkeleton />;
  }

  if (!categories || categories.length === 0) {
    return (
      <p className="text-gray-500 dark:text-gray-400 text-sm py-4">
        No categories available.
      </p>
    );
  }

  const normalizedFilter = searchFilter.toLowerCase().trim();

  return (
    <div className="space-y-4">
      {/* Search */}
      <div className="relative">
        <Search
          size={16}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
        />
        <input
          type="text"
          placeholder="Search skills..."
          value={searchFilter}
          onChange={(e) => setSearchFilter(e.target.value)}
          className="w-full pl-9 pr-4 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/30 focus:border-[#7E22CE]"
        />
      </div>

      {/* Selected pills */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {selected.map((s) => (
            <button
              key={s.serviceId}
              type="button"
              onClick={() => toggleService(s)}
              className="inline-flex items-center gap-1.5 px-3 py-1 text-sm rounded-full bg-[#7E22CE]/10 text-[#7E22CE] dark:bg-purple-500/20 dark:text-purple-300 hover:bg-[#7E22CE]/20 transition-colors"
            >
              {s.serviceName}
              <span className="text-xs">&times;</span>
            </button>
          ))}
        </div>
      )}

      {/* Category accordion */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg divide-y divide-gray-200 dark:divide-gray-700 overflow-hidden">
        {categories.map((category) => {
          const isExpanded = expandedCategory === category.id;
          const subcategories = category.subcategories ?? [];
          const subcategoryCount = subcategories.length;

          return (
            <div key={category.id}>
              <button
                type="button"
                onClick={() => toggleCategory(category.id)}
                className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                <div>
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {category.name}
                  </span>
                  {subcategoryCount > 0 && (
                    <span className="ml-2 text-xs text-gray-400">
                      {subcategoryCount} subcategor{subcategoryCount === 1 ? 'y' : 'ies'}
                    </span>
                  )}
                </div>
                {isExpanded ? (
                  <ChevronDown size={16} className="text-gray-400" />
                ) : (
                  <ChevronRight size={16} className="text-gray-400" />
                )}
              </button>

              {isExpanded && (
                <CategoryServices
                  categoryId={category.id}
                  categoryName={category.name}
                  tree={categoryTree}
                  treeLoading={treeLoading}
                  selectedIds={selectedIds}
                  searchFilter={normalizedFilter}
                  onToggle={toggleService}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CategoryServices({
  categoryId,
  categoryName,
  tree,
  treeLoading,
  selectedIds,
  searchFilter,
  onToggle,
}: {
  categoryId: string;
  categoryName: string;
  tree: { subcategories?: { id: string; name: string; services?: { id: string; name: string }[] }[] } | undefined;
  treeLoading: boolean;
  selectedIds: Set<string>;
  searchFilter: string;
  onToggle: (service: SelectedService) => void;
}) {
  if (treeLoading || !tree) {
    return (
      <div className="px-4 py-3 space-y-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-4 w-40" />
      </div>
    );
  }

  const subcategories = tree.subcategories ?? [];

  return (
    <div className="bg-gray-50 dark:bg-gray-900/50">
      {subcategories.map((sub) => {
        const services = (sub.services ?? []).filter(
          (svc) => !searchFilter || svc.name.toLowerCase().includes(searchFilter),
        );

        if (searchFilter && services.length === 0) return null;

        return (
          <div key={sub.id} className="px-4 py-2">
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1.5">
              {sub.name}
            </p>
            <div className="space-y-0.5">
              {services.map((svc) => {
                const isSelected = selectedIds.has(svc.id);
                return (
                  <button
                    key={svc.id}
                    type="button"
                    onClick={() =>
                      onToggle({
                        serviceId: svc.id,
                        serviceName: svc.name,
                        subcategoryId: sub.id,
                        subcategoryName: sub.name,
                        categoryId,
                        categoryName,
                      })
                    }
                    className={`w-full flex items-center gap-2 px-3 py-1.5 text-sm rounded-md transition-colors ${
                      isSelected
                        ? 'bg-[#7E22CE]/10 text-[#7E22CE] dark:bg-purple-500/20 dark:text-purple-300'
                        : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                    }`}
                  >
                    {isSelected ? (
                      <Check size={14} className="flex-shrink-0" />
                    ) : (
                      <span className="w-3.5 flex-shrink-0" />
                    )}
                    {svc.name}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function PickerSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-9 w-full rounded-lg" />
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
        {Array.from({ length: 5 }, (_, i) => (
          <div
            key={i}
            className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 dark:border-gray-700 last:border-b-0"
          >
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-3 w-16" />
          </div>
        ))}
      </div>
    </div>
  );
}
