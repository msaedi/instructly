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
});
