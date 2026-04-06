import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { SelectionMode } from '@/components/neighborhoods/types';

type UseNeighborhoodSelectionOptions = {
  value?: string[];
  defaultValue?: string[];
  selectionMode?: SelectionMode;
  onSelectionChange?: (keys: string[]) => void;
};

export type UseNeighborhoodSelectionReturn = {
  selectedKeys: Set<string>;
  toggle: (key: string) => void;
  selectAll: (keys: string[]) => void;
  clearAll: (keys?: string[]) => void;
  isSelected: (key: string) => boolean;
  selectedCount: number;
  selectedArray: string[];
};

function normalizeKeys(keys?: string[]): string[] {
  if (!Array.isArray(keys)) {
    return [];
  }
  return Array.from(
    new Set(
      keys
        .map((key) => key.trim())
        .filter((key) => key.length > 0),
    ),
  );
}

export function useNeighborhoodSelection({
  value,
  defaultValue,
  selectionMode = 'multi',
  onSelectionChange,
}: UseNeighborhoodSelectionOptions): UseNeighborhoodSelectionReturn {
  const controlledValue = useMemo(() => normalizeKeys(value), [value]);
  const defaultSelection = useMemo(() => normalizeKeys(defaultValue), [defaultValue]);

  const [uncontrolledKeys, setUncontrolledKeys] = useState<Set<string>>(
    () => new Set(defaultSelection),
  );
  const selectedKeys = useMemo(
    () => new Set(value !== undefined ? controlledValue : uncontrolledKeys),
    [controlledValue, uncontrolledKeys, value],
  );
  const selectedKeysRef = useRef(selectedKeys);
  const onSelectionChangeRef = useRef(onSelectionChange);

  useEffect(() => {
    selectedKeysRef.current = selectedKeys;
  }, [selectedKeys]);

  useEffect(() => {
    onSelectionChangeRef.current = onSelectionChange;
  }, [onSelectionChange]);

  const emitSelection = useCallback(
    (next: Set<string>) => {
      onSelectionChangeRef.current?.(Array.from(next));
    },
    [],
  );

  const commitSelection = useCallback(
    (next: Set<string>) => {
      selectedKeysRef.current = next;
      if (value === undefined) {
        setUncontrolledKeys(new Set(next));
      }
      emitSelection(next);
    },
    [emitSelection, value],
  );

  const toggle = useCallback(
    (key: string) => {
      const normalizedKey = key.trim();
      if (!normalizedKey) {
        return;
      }
      const currentSelection = new Set(selectedKeysRef.current);
      const next =
        selectionMode === 'single'
          ? currentSelection.has(normalizedKey)
            ? new Set<string>()
            : new Set<string>([normalizedKey])
          : currentSelection;
      if (selectionMode === 'multi') {
        if (next.has(normalizedKey)) {
          next.delete(normalizedKey);
        } else {
          next.add(normalizedKey);
        }
      }
      commitSelection(next);
    },
    [commitSelection, selectionMode],
  );

  const selectAll = useCallback(
    (keys: string[]) => {
      const normalizedKeys = normalizeKeys(keys);
      const firstKey = normalizedKeys[0];
      if (normalizedKeys.length === 0 || (selectionMode === 'single' && !firstKey)) {
        return;
      }
      const currentSelection = new Set(selectedKeysRef.current);
      const next =
        selectionMode === 'single'
          ? new Set<string>(firstKey ? [firstKey] : [])
          : new Set<string>([...currentSelection, ...normalizedKeys]);
      commitSelection(next);
    },
    [commitSelection, selectionMode],
  );

  const clearAll = useCallback(
    (keys?: string[]) => {
      const normalizedKeys = normalizeKeys(keys);
      const next = new Set(selectedKeysRef.current);
      if (normalizedKeys.length === 0) {
        next.clear();
      } else {
        for (const key of normalizedKeys) {
          next.delete(key);
        }
      }
      commitSelection(next);
    },
    [commitSelection],
  );

  const selectedArray = useMemo(() => Array.from(selectedKeys), [selectedKeys]);
  const selectedCount = selectedArray.length;

  const isSelected = useCallback(
    (key: string) => selectedKeys.has(key),
    [selectedKeys],
  );

  return {
    selectedKeys,
    toggle,
    selectAll,
    clearAll,
    isSelected,
    selectedCount,
    selectedArray,
  };
}
