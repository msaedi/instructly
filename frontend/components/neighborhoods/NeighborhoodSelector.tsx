'use client';

import dynamic from 'next/dynamic';
import clsx from 'clsx';
import {
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import type { SelectorDisplayItem } from '@/features/shared/api/types';
import { useNeighborhoodSelectorData } from '@/hooks/queries/useNeighborhoodSelectorData';
import { useNeighborhoodPolygons } from '@/hooks/queries/useNeighborhoodPolygons';
import { useNeighborhoodSelection } from '@/hooks/useNeighborhoodSelection';

import { BoroughSection } from './BoroughSection';
import { NeighborhoodSearch } from './NeighborhoodSearch';
import {
  getMatchPriority,
  matchSelectorItem,
  normalizeSearchText,
  type SearchMatch,
  type SelectionMode,
} from './types';

const DynamicNeighborhoodSelectorMap = dynamic(
  () => import('./NeighborhoodSelectorMap'),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full min-h-[400px] items-center justify-center rounded-[28px] border border-gray-200 bg-white/95 text-sm text-gray-500 shadow-sm dark:border-gray-800 dark:bg-gray-900/80 dark:text-gray-400">
        Loading map…
      </div>
    ),
  },
);

type NeighborhoodSelectorProps = {
  market?: string;
  value?: string[];
  defaultValue?: string[];
  selectionMode?: SelectionMode;
  onSelectionChange?: (keys: string[], items: SelectorDisplayItem[]) => void;
  context?: 'onboarding' | 'dashboard' | 'apply';
  className?: string;
  showMap?: boolean;
};

type BoroughGroup = {
  borough: string;
  items: SelectorDisplayItem[];
};

function titleForContext(context: NeighborhoodSelectorProps['context']) {
  if (context === 'apply') {
    return {
      title: 'Choose your primary neighborhood',
      subtitle: 'Pick the main neighborhood you plan to teach in.',
      searchPlaceholder: 'Search NYC neighborhoods...',
    };
  }

  return {
    title: 'Select the neighborhoods where you teach',
    subtitle: 'Select all neighborhoods you’re willing to travel to for lessons.',
    searchPlaceholder: 'Search neighborhoods...',
  };
}

function sortMatchedItems(
  items: SelectorDisplayItem[],
  matchByKey: Map<string, SearchMatch>,
): SelectorDisplayItem[] {
  return [...items].sort((left, right) => {
    const leftRank = getMatchPriority(matchByKey.get(left.display_key)?.rank ?? null);
    const rightRank = getMatchPriority(matchByKey.get(right.display_key)?.rank ?? null);
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    if (left.display_order !== right.display_order) {
      return left.display_order - right.display_order;
    }
    return left.display_name.localeCompare(right.display_name);
  });
}

function NeighborhoodSelectorMapPanel({
  market,
  selectedKeys,
  hoveredKey,
  onHoverKey,
  onToggleKey,
}: {
  market: string;
  selectedKeys: Set<string>;
  hoveredKey: string | null;
  onHoverKey: (key: string | null) => void;
  onToggleKey: (key: string) => void;
}) {
  const { data, isLoading, isError } = useNeighborhoodPolygons(market, true);

  if (isLoading) {
    return (
      <div className="flex h-full min-h-[400px] items-center justify-center rounded-[28px] border border-gray-200 bg-white/95 text-sm text-gray-500 shadow-sm dark:border-gray-800 dark:bg-gray-900/80 dark:text-gray-400">
        Loading map…
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex h-full min-h-[400px] items-center justify-center rounded-[28px] border border-gray-200 bg-white/95 px-6 text-center text-sm text-gray-500 shadow-sm dark:border-gray-800 dark:bg-gray-900/80 dark:text-gray-400">
        Unable to load neighborhood polygons right now.
      </div>
    );
  }

  return (
    <DynamicNeighborhoodSelectorMap
      featureCollection={data ?? null}
      selectedKeys={selectedKeys}
      onToggleKey={onToggleKey}
      hoveredKey={hoveredKey}
      onHoverKey={onHoverKey}
    />
  );
}

export function NeighborhoodSelector({
  market = 'nyc',
  value,
  defaultValue,
  selectionMode = 'multi',
  onSelectionChange,
  context = 'dashboard',
  className,
  showMap = true,
}: NeighborhoodSelectorProps) {
  const {
    data,
    isLoading,
    isError,
    allItems,
    itemByKey,
    boroughs,
  } = useNeighborhoodSelectorData(market);
  const emittedSignatureRef = useRef<string>('');
  const emitSelectionChange = useCallback(
    (keys: string[]) => {
      if (!onSelectionChange) {
        return;
      }
      const signature = keys.join('|');
      emittedSignatureRef.current = signature;
      const items = keys.flatMap((key) => {
        const item = itemByKey.get(key);
        return item ? [item] : [];
      });
      onSelectionChange(keys, items);
    },
    [itemByKey, onSelectionChange],
  );
  const {
    selectedKeys,
    selectedArray,
    toggle,
    selectAll,
    clearAll,
  } = useNeighborhoodSelection({
    selectionMode,
    onSelectionChange: emitSelectionChange,
    ...(value !== undefined ? { value } : {}),
    ...(defaultValue !== undefined ? { defaultValue } : {}),
  });
  const [query, setQuery] = useState('');
  const deferredQuery = useDeferredValue(query);
  const normalizedQuery = useMemo(
    () => normalizeSearchText(deferredQuery),
    [deferredQuery],
  );
  const searchActive = normalizedQuery.length > 0;
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);
  const manualExpandedRef = useRef<Set<string>>(new Set());
  const [manualExpandedBoroughs, setManualExpandedBoroughs] = useState<Set<string>>(new Set());

  const primaryGroups = useMemo(
    () =>
      data?.boroughs.map((boroughGroup) => ({
        borough: boroughGroup.borough,
        items: boroughGroup.items,
      })) ?? [],
    [data],
  );

  const defaultExpandedBoroughs = useMemo(() => {
    const selected = primaryGroups
      .filter((group) =>
        group.items.some((item) => selectedKeys.has(item.display_key)),
      )
      .map((group) => group.borough);
    if (selected.length > 0) {
      return selected;
    }
    const firstBorough = boroughs[0];
    return firstBorough ? [firstBorough] : [];
  }, [boroughs, primaryGroups, selectedKeys]);

  useEffect(() => {
    setManualExpandedBoroughs((previous) => {
      if (previous.size > 0) {
        return new Set(
          [...previous].filter((borough) => boroughs.includes(borough)),
        );
      }
      const next = new Set(defaultExpandedBoroughs);
      manualExpandedRef.current = next;
      return next;
    });
  }, [boroughs, defaultExpandedBoroughs]);

  const matchByKey = useMemo(() => {
    const next = new Map<string, SearchMatch>();
    if (!searchActive) {
      return next;
    }
    for (const item of allItems) {
      const match = matchSelectorItem(item, normalizedQuery);
      if (match.rank !== null) {
        next.set(item.display_key, match);
      }
    }
    return next;
  }, [allItems, normalizedQuery, searchActive]);

  const searchAliasByKey = useMemo(() => {
    const next = new Map<string, string | null>();
    matchByKey.forEach((match, key) => {
      if (match.rank !== 'display_name' && match.matchedTerm) {
        next.set(key, match.matchedTerm);
      }
    });
    return next;
  }, [matchByKey]);

  const visibleGroups = useMemo<BoroughGroup[]>(() => {
    if (!searchActive) {
      return primaryGroups;
    }

    const groups = new Map<string, Map<string, SelectorDisplayItem>>();
    for (const borough of boroughs) {
      groups.set(borough, new Map());
    }

    for (const item of allItems) {
      if (!matchByKey.has(item.display_key)) {
        continue;
      }

      groups.get(item.borough)?.set(item.display_key, item);
      for (const extraBorough of item.additional_boroughs ?? []) {
        groups.get(extraBorough)?.set(item.display_key, item);
      }
    }

    return boroughs.map((borough) => {
      const boroughItems = Array.from(groups.get(borough)?.values() ?? []);
      return {
        borough,
        items: sortMatchedItems(boroughItems, matchByKey),
      };
    });
  }, [allItems, boroughs, matchByKey, primaryGroups, searchActive]);

  const expandedBoroughs = useMemo(
    () =>
      searchActive
        ? new Set(
            visibleGroups
              .filter((group) => group.items.length > 0)
              .map((group) => group.borough),
          )
        : manualExpandedBoroughs,
    [manualExpandedBoroughs, searchActive, visibleGroups],
  );

  const selectedItems = useMemo(
    () =>
      selectedArray.flatMap((key) => {
        const item = itemByKey.get(key);
        return item ? [item] : [];
      }),
    [itemByKey, selectedArray],
  );

  useEffect(() => {
    if (!onSelectionChange) {
      return;
    }
    if (selectedArray.length > 0 && allItems.length === 0) {
      return;
    }
    const signature = selectedArray.join('|');
    if (emittedSignatureRef.current === signature) {
      return;
    }
    emittedSignatureRef.current = signature;
    onSelectionChange(selectedArray, selectedItems);
  }, [allItems.length, onSelectionChange, selectedArray, selectedItems]);

  const copy = titleForContext(context);

  if (isLoading) {
    return (
      <div className="rounded-[28px] border border-gray-200 bg-white/95 p-6 text-sm text-gray-500 shadow-sm dark:border-gray-800 dark:bg-gray-900/80 dark:text-gray-400">
        Loading neighborhoods…
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded-[28px] border border-gray-200 bg-white/95 p-6 text-sm text-gray-500 shadow-sm dark:border-gray-800 dark:bg-gray-900/80 dark:text-gray-400">
        Unable to load neighborhoods right now.
      </div>
    );
  }

  return (
    <section className={clsx('space-y-4', className)} data-testid="service-areas-card">
      <div className="space-y-1">
        <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
          {copy.title}
        </h2>
        <p className="text-sm text-gray-600 dark:text-gray-400">{copy.subtitle}</p>
      </div>

      <div className="flex flex-col gap-4 md:h-[600px] md:flex-row">
        <div className="w-full overflow-y-auto md:w-1/2">
          <div className="rounded-[28px] border border-gray-200 bg-white/95 p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900/80">
            <NeighborhoodSearch
              query={query}
              onQueryChange={setQuery}
              placeholder={copy.searchPlaceholder}
            />

            <div className="mt-4 space-y-3">
              {visibleGroups.map((group) => (
                <BoroughSection
                  key={group.borough}
                  borough={group.borough}
                  items={group.items}
                  selectedKeys={selectedKeys}
                  hoveredKey={hoveredKey}
                  onHoverKey={setHoveredKey}
                  onToggle={toggle}
                  onSelectAll={() =>
                    selectAll(group.items.map((item) => item.display_key))
                  }
                  onClearAll={() =>
                    clearAll(group.items.map((item) => item.display_key))
                  }
                  isExpanded={expandedBoroughs.has(group.borough)}
                  onToggleExpand={() => {
                    if (searchActive) {
                      return;
                    }
                    setManualExpandedBoroughs((previous) => {
                      const next = new Set(previous);
                      if (next.has(group.borough)) {
                        next.delete(group.borough);
                      } else {
                        next.add(group.borough);
                      }
                      manualExpandedRef.current = next;
                      return next;
                    });
                  }}
                  selectionMode={selectionMode}
                  searchActive={searchActive}
                  matchInfo={searchAliasByKey}
                />
              ))}
            </div>
          </div>
        </div>

        {showMap ? (
          <div className="w-full md:sticky md:top-0 md:h-full md:w-1/2">
            <NeighborhoodSelectorMapPanel
              market={market}
              selectedKeys={selectedKeys}
              hoveredKey={hoveredKey}
              onHoverKey={setHoveredKey}
              onToggleKey={toggle}
            />
          </div>
        ) : null}
      </div>
    </section>
  );
}
