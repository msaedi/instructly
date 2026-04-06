import { act, renderHook } from '@testing-library/react';

import { useNeighborhoodSelection } from '../useNeighborhoodSelection';

describe('useNeighborhoodSelection', () => {
  it('handles uncontrolled multi-select flows, ignores blank keys, and preserves the last multi-select item', () => {
    const onSelectionChange = jest.fn();

    const { result } = renderHook(() =>
      useNeighborhoodSelection({
        defaultValue: [' ues ', 'ues', ''],
        onSelectionChange,
      }),
    );

    expect(result.current.selectedArray).toEqual(['ues']);
    expect(result.current.selectedCount).toBe(1);
    expect(result.current.isSelected('ues')).toBe(true);

    act(() => {
      result.current.toggle('   ');
    });

    expect(result.current.selectedArray).toEqual(['ues']);

    act(() => {
      result.current.toggle('chelsea');
    });

    expect(new Set(result.current.selectedArray)).toEqual(new Set(['ues', 'chelsea']));

    act(() => {
      result.current.toggle('ues');
    });

    expect(result.current.selectedArray).toEqual(['chelsea']);

    act(() => {
      result.current.selectAll([]);
    });

    expect(result.current.selectedArray).toEqual(['chelsea']);

    act(() => {
      result.current.selectAll(['chelsea', 'harlem', 'harlem', '  ']);
    });

    expect(new Set(result.current.selectedArray)).toEqual(new Set(['chelsea', 'harlem']));

    act(() => {
      result.current.clearAll(['harlem']);
    });

    expect(result.current.selectedArray).toEqual(['chelsea']);

    act(() => {
      result.current.clearAll();
    });

    expect(result.current.selectedArray).toEqual(['chelsea']);
    expect(result.current.selectedCount).toBe(1);
    expect(onSelectionChange).toHaveBeenCalled();
  });

  it('does not deselect the final selected item in multi-select mode', () => {
    const { result } = renderHook(() =>
      useNeighborhoodSelection({
        defaultValue: ['ues'],
      }),
    );

    act(() => {
      result.current.toggle('ues');
    });

    expect(result.current.selectedArray).toEqual(['ues']);
  });

  it('does not clear a filtered subset when that would remove the last selected item in multi-select mode', () => {
    const { result } = renderHook(() =>
      useNeighborhoodSelection({
        defaultValue: ['ues'],
      }),
    );

    act(() => {
      result.current.clearAll(['ues']);
    });

    expect(result.current.selectedArray).toEqual(['ues']);
  });

  it('supports controlled single-select replacement and deselection', () => {
    const onSelectionChange = jest.fn();

    const { result, rerender } = renderHook(
      ({ value }: { value: string[] }) =>
        useNeighborhoodSelection({
          value,
          selectionMode: 'single',
          onSelectionChange,
        }),
      {
        initialProps: { value: ['ues'] },
      },
    );

    expect(result.current.selectedArray).toEqual(['ues']);
    expect(result.current.isSelected('ues')).toBe(true);

    act(() => {
      result.current.toggle('chelsea');
    });

    expect(onSelectionChange).toHaveBeenLastCalledWith(['chelsea']);

    rerender({ value: ['chelsea'] });
    expect(result.current.selectedArray).toEqual(['chelsea']);

    act(() => {
      result.current.toggle('chelsea');
    });

    expect(onSelectionChange).toHaveBeenLastCalledWith([]);

    rerender({ value: [] });
    expect(result.current.selectedArray).toEqual([]);

    act(() => {
      result.current.selectAll(['harlem', 'ues']);
    });

    expect(onSelectionChange).toHaveBeenLastCalledWith(['harlem']);
  });

  it('memoizes the returned API when inputs stay the same', () => {
    const value = ['ues'];

    const { result, rerender } = renderHook(
      ({ selected }: { selected: string[] }) =>
        useNeighborhoodSelection({
          value: selected,
        }),
      {
        initialProps: { selected: value },
      }
    );

    const initialResult = result.current;

    rerender({ selected: value });

    expect(result.current).toBe(initialResult);
  });
});
