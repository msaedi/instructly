import { act, renderHook, waitFor } from '@testing-library/react';

import { useSWRCustom } from '../useSWRCustom';

describe('useSWRCustom', () => {
  it('does not fetch when key is null', () => {
    const fetcher = jest.fn();

    const { result } = renderHook(() => useSWRCustom(null, fetcher));

    expect(result.current.isLoading).toBe(false);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('fetches data when key is provided', async () => {
    const fetcher = jest.fn().mockResolvedValue('payload');

    const { result } = renderHook(() => useSWRCustom('key', fetcher));

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(fetcher).toHaveBeenCalledWith('key');
    expect(result.current.data).toBe('payload');
  });

  it('sets error when the fetcher rejects', async () => {
    const fetcher = jest.fn().mockRejectedValue(new Error('Boom'));

    const { result } = renderHook(() => useSWRCustom('key', fetcher));

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.error).toBeInstanceOf(Error);
  });

  it('refreshes on the configured interval', async () => {
    jest.useFakeTimers();
    const fetcher = jest.fn().mockResolvedValue('payload');

    const { result } = renderHook(() =>
      useSWRCustom('key', fetcher, { refreshInterval: 1000 })
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetcher).toHaveBeenCalledTimes(1);

    await act(async () => {
      jest.advanceTimersByTime(1000);
      await Promise.resolve();
    });

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(result.current.isLoading).toBe(false);

    jest.useRealTimers();
  });

  it('stops refreshing after unmount', async () => {
    jest.useFakeTimers();
    const fetcher = jest.fn().mockResolvedValue('payload');

    const { unmount } = renderHook(() =>
      useSWRCustom('key', fetcher, { refreshInterval: 1000 })
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetcher).toHaveBeenCalledTimes(1);

    unmount();

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    expect(fetcher).toHaveBeenCalledTimes(1);

    jest.useRealTimers();
  });

  it('handles key changing from valid to null', async () => {
    const fetcher = jest.fn().mockResolvedValue('payload');

    const { result, rerender } = renderHook(
      ({ key }: { key: string | null }) => useSWRCustom(key, fetcher),
      { initialProps: { key: 'initial-key' as string | null } }
    );

    await waitFor(() => expect(result.current.data).toBe('payload'));
    expect(fetcher).toHaveBeenCalledTimes(1);

    rerender({ key: null });

    // Should stop loading when key becomes null
    await waitFor(() => expect(result.current.isLoading).toBe(false));
  });

  it('refetches when key changes', async () => {
    const fetcher = jest
      .fn()
      .mockResolvedValueOnce('first')
      .mockResolvedValueOnce('second');

    const { result, rerender } = renderHook(
      ({ key }: { key: string }) => useSWRCustom(key, fetcher),
      { initialProps: { key: 'key-1' } }
    );

    await waitFor(() => expect(result.current.data).toBe('first'));
    expect(fetcher).toHaveBeenCalledWith('key-1');

    rerender({ key: 'key-2' });

    await waitFor(() => expect(result.current.data).toBe('second'));
    expect(fetcher).toHaveBeenCalledWith('key-2');
  });

  it('does not poll when refreshInterval is 0', async () => {
    jest.useFakeTimers();
    const fetcher = jest.fn().mockResolvedValue('payload');

    renderHook(() =>
      useSWRCustom('key', fetcher, { refreshInterval: 0 })
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetcher).toHaveBeenCalledTimes(1);

    await act(async () => {
      jest.advanceTimersByTime(5000);
      await Promise.resolve();
    });

    // No additional calls since refreshInterval is 0
    expect(fetcher).toHaveBeenCalledTimes(1);

    jest.useRealTimers();
  });

  it('preserves stale data when fetcher rejects', async () => {
    const fetcher = jest
      .fn()
      .mockResolvedValueOnce('initial-data')
      .mockRejectedValueOnce(new Error('network fail'));

    jest.useFakeTimers();

    const { result } = renderHook(() =>
      useSWRCustom('key', fetcher, { refreshInterval: 1000 })
    );

    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.data).toBe('initial-data');
    expect(result.current.error).toBeUndefined();

    await act(async () => {
      jest.advanceTimersByTime(1000);
      await Promise.resolve();
    });

    // Error is set but data is preserved
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.data).toBe('initial-data');

    jest.useRealTimers();
  });
});
