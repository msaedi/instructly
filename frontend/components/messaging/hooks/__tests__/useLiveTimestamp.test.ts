import { renderHook, act } from '@testing-library/react';
import { useLiveTimestamp } from '../useLiveTimestamp';

describe('useLiveTimestamp', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('returns initial tick value', () => {
    const { result } = renderHook(() => useLiveTimestamp());
    expect(typeof result.current).toBe('number');
  });

  it('updates tick value on interval', () => {
    const { result } = renderHook(() => useLiveTimestamp(1000)); // 1 second
    const initialTick = result.current;

    // Advance time by 1 second
    act(() => {
      jest.advanceTimersByTime(1000);
    });

    // Tick should have changed
    expect(result.current).toBeGreaterThanOrEqual(initialTick);
  });

  it('uses custom interval', () => {
    const customInterval = 5000;
    const { result } = renderHook(() => useLiveTimestamp(customInterval));
    const initialTick = result.current;

    // Advance by less than interval - tick should not change
    act(() => {
      jest.advanceTimersByTime(4000);
    });
    expect(result.current).toBe(initialTick);

    // Advance past interval - tick should update
    act(() => {
      jest.advanceTimersByTime(2000);
    });
    expect(result.current).toBeGreaterThan(initialTick);
  });

  it('cleans up interval on unmount', () => {
    const clearIntervalSpy = jest.spyOn(global, 'clearInterval');
    const { unmount } = renderHook(() => useLiveTimestamp());

    unmount();

    expect(clearIntervalSpy).toHaveBeenCalled();
    clearIntervalSpy.mockRestore();
  });
});
