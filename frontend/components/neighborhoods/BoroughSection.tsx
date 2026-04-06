import clsx from 'clsx';
import { ChevronDown } from 'lucide-react';

import type { SelectorDisplayItem } from '@/features/shared/api/types';

import type { SelectionMode } from './types';
import { isLongDisplayName } from './types';

type BoroughSectionProps = {
  borough: string;
  items: SelectorDisplayItem[];
  selectedKeys: Set<string>;
  hoveredKey?: string | null;
  onHoverKey?: (key: string | null) => void;
  onToggle: (key: string) => void;
  onSelectAll: () => void;
  onClearAll: () => void;
  isExpanded: boolean;
  onToggleExpand: () => void;
  selectionMode: SelectionMode;
  searchActive?: boolean;
  matchInfo?: Map<string, string | null>;
};

function boroughTestId(borough: string): string {
  return `neighborhood-borough-${borough.toLowerCase().replace(/\s+/g, '-')}`;
}

export function BoroughSection({
  borough,
  items,
  selectedKeys,
  hoveredKey = null,
  onHoverKey,
  onToggle,
  onSelectAll,
  onClearAll,
  isExpanded,
  onToggleExpand,
  selectionMode,
  searchActive = false,
  matchInfo,
}: BoroughSectionProps) {
  const selectedCount = items.filter((item) => selectedKeys.has(item.display_key)).length;
  const showCollapsedCount = !isExpanded && selectedCount > 0;
  const showExpandedCount = isExpanded;

  return (
    <section className="rounded-2xl border border-gray-200/90 bg-white/90 shadow-sm dark:border-gray-800 dark:bg-gray-900/70">
      <div className="flex items-start justify-between gap-3 px-4 py-3">
        <button
          type="button"
          onClick={onToggleExpand}
          className="flex min-w-0 flex-1 items-center justify-between gap-3 text-left"
          aria-expanded={isExpanded}
          data-testid={boroughTestId(borough)}
        >
          <div className="min-w-0">
            <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {borough}{' '}
              {showExpandedCount ? (
                <span className="text-gray-500 dark:text-gray-400">
                  ({selectedCount} selected)
                </span>
              ) : showCollapsedCount ? (
                <span className="text-gray-500 dark:text-gray-400">({selectedCount})</span>
              ) : null}
            </div>
            {searchActive && items.length === 0 ? (
              <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">No matches</div>
            ) : null}
          </div>
          <ChevronDown
            className={clsx(
              'h-4 w-4 shrink-0 text-gray-500 transition-transform duration-150 dark:text-gray-400',
              isExpanded && 'rotate-180',
            )}
          />
        </button>
        {isExpanded && selectionMode === 'multi' && items.length > 0 ? (
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onSelectAll();
              }}
              className="cursor-pointer text-xs font-medium text-(--color-brand-dark) transition-colors duration-150 hover:text-purple-800"
            >
              Select all
            </button>
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onClearAll();
              }}
              className="cursor-pointer text-xs font-medium text-gray-500 transition-colors duration-150 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200"
            >
              Clear all
            </button>
          </div>
        ) : null}
      </div>

      {isExpanded ? (
        <div className="border-t border-gray-100 px-4 py-4 dark:border-gray-800">
          {items.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-gray-200 px-4 py-6 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
              {searchActive ? 'No neighborhoods match this search.' : 'No neighborhoods available.'}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              {items.map((item) => {
                const isSelected = selectedKeys.has(item.display_key);
                const isHovered = hoveredKey === item.display_key;
                const aliasHint = searchActive ? matchInfo?.get(item.display_key) : null;
                const showInlineAliasHint = Boolean(aliasHint && isLongDisplayName(item.display_name));

                return (
                  <button
                    key={`${borough}-${item.display_key}`}
                    type="button"
                    onClick={() => onToggle(item.display_key)}
                    onMouseEnter={() => onHoverKey?.(item.display_key)}
                    onMouseLeave={() => onHoverKey?.(null)}
                    aria-pressed={isSelected}
                    data-testid={`neighborhood-chip-${item.display_key}`}
                    className={clsx(
                      'cursor-pointer rounded-2xl border px-3 py-2 text-left transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-purple-200',
                      isLongDisplayName(item.display_name) && 'col-span-2',
                      isSelected
                        ? 'border-purple-200 bg-[var(--color-brand-lavender)] text-[var(--color-brand-dark)]'
                        : 'border-gray-200 bg-gray-50 text-gray-700 hover:border-purple-200 hover:bg-purple-50 dark:border-gray-700 dark:bg-gray-800/80 dark:text-gray-200 dark:hover:border-purple-500/40 dark:hover:bg-gray-800',
                      isHovered && 'ring-2 ring-purple-200',
                    )}
                    title={aliasHint ? `Matches: ${aliasHint}` : item.display_name}
                  >
                    <span
                      className={clsx(
                        'block text-sm font-medium',
                        isSelected && 'text-[var(--color-brand-dark)]',
                      )}
                    >
                      {item.display_name}
                    </span>
                    {showInlineAliasHint && aliasHint ? (
                      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        Matches: {aliasHint}
                      </div>
                    ) : null}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
