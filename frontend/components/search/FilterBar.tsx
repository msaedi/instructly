'use client';

import { useCallback, useEffect, useState, useSyncExternalStore, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

import { DateFilter } from './filters/DateFilter';
import { TimeFilter } from './filters/TimeFilter';
import { PriceFilter } from './filters/PriceFilter';
import { LocationFilter } from './filters/LocationFilter';
import { MoreFiltersButton } from './filters/MoreFiltersButton';
import { MoreFiltersModal } from './filters/MoreFiltersModal';
import {
  type ContentFilterSelections,
  type FilterState,
  type SkillLevelOption,
  type TaxonomyContentFilterDefinition,
} from './filterTypes';

interface FilterBarProps {
  filters: FilterState;
  onFiltersChange: (filters: FilterState) => void;
  rightSlot?: ReactNode;
  skillLevelOptions?: SkillLevelOption[];
  taxonomyContentFilters?: TaxonomyContentFilterDefinition[];
  suggestedContentFilters?: ContentFilterSelections;
}

type DropdownKey = 'date' | 'time' | 'price' | 'location';

export function FilterBar({
  filters,
  onFiltersChange,
  rightSlot,
  skillLevelOptions,
  taxonomyContentFilters,
  suggestedContentFilters,
}: FilterBarProps) {
  const [openDropdown, setOpenDropdown] = useState<DropdownKey | null>(null);
  const [isMoreFiltersOpen, setIsMoreFiltersOpen] = useState(false);
  const isClient = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false
  );

  const toggleDropdown = useCallback((name: DropdownKey) => {
    setOpenDropdown((prev) => (prev === name ? null : name));
  }, []);

  const closeDropdowns = useCallback(() => {
    setOpenDropdown(null);
  }, []);

  const openMoreFilters = useCallback(() => {
    setOpenDropdown(null);
    setIsMoreFiltersOpen(true);
  }, []);

  const closeMoreFilters = useCallback(() => {
    setIsMoreFiltersOpen(false);
  }, []);

  useEffect(() => {
    if (!openDropdown && !isMoreFiltersOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpenDropdown(null);
        setIsMoreFiltersOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [openDropdown, isMoreFiltersOpen]);

  return (
    <div className="flex items-center gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <DateFilter
          isOpen={openDropdown === 'date'}
          onToggle={() => toggleDropdown('date')}
          value={filters.date}
          onChange={(date) => onFiltersChange({ ...filters, date })}
          onClose={closeDropdowns}
        />

        <TimeFilter
          isOpen={openDropdown === 'time'}
          onToggle={() => toggleDropdown('time')}
          value={filters.timeOfDay}
          onChange={(timeOfDay) => onFiltersChange({ ...filters, timeOfDay })}
          onClose={closeDropdowns}
        />

        <PriceFilter
          isOpen={openDropdown === 'price'}
          onToggle={() => toggleDropdown('price')}
          min={filters.priceMin}
          max={filters.priceMax}
          onChange={(priceMin, priceMax) =>
            onFiltersChange({ ...filters, priceMin, priceMax })
          }
          onClose={closeDropdowns}
        />

        <LocationFilter
          isOpen={openDropdown === 'location'}
          onToggle={() => toggleDropdown('location')}
          value={filters.location}
          onChange={(location) => onFiltersChange({ ...filters, location })}
          onClose={closeDropdowns}
        />

        <MoreFiltersButton filters={filters} onClick={openMoreFilters} />
      </div>

      {rightSlot ? <div className="ml-auto">{rightSlot}</div> : null}

      {isClient && isMoreFiltersOpen
        ? createPortal(
            <MoreFiltersModal
              isOpen
              onClose={closeMoreFilters}
              filters={filters}
              onFiltersChange={onFiltersChange}
              {...(skillLevelOptions ? { skillLevelOptions } : {})}
              {...(taxonomyContentFilters ? { taxonomyContentFilters } : {})}
              {...(suggestedContentFilters ? { suggestedContentFilters } : {})}
            />,
            document.body
          )
        : null}
    </div>
  );
}
