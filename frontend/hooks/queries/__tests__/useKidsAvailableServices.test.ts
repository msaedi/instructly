import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useKidsAvailableServices } from '../useKidsAvailableServices';
import { publicApi } from '@/features/shared/api/client';

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    getKidsAvailableServices: jest.fn(),
  },
}));

const getKidsAvailableServicesMock = publicApi.getKidsAvailableServices as jest.Mock;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  Wrapper.displayName = 'QueryClientWrapper';
  return Wrapper;
};

describe('useKidsAvailableServices', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('returns kids services on success', async () => {
    const services = [{ id: '1', name: 'Piano', slug: 'piano' }];
    getKidsAvailableServicesMock.mockResolvedValue({ data: services });

    const { result } = renderHook(() => useKidsAvailableServices(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getKidsAvailableServicesMock).toHaveBeenCalledTimes(1);
    expect(result.current.data).toEqual(services);
  });

  it('falls back to an empty list when data is missing', async () => {
    getKidsAvailableServicesMock.mockResolvedValue({ data: undefined });

    const { result } = renderHook(() => useKidsAvailableServices(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([]);
  });

  it('exposes error state when the API fails', async () => {
    getKidsAvailableServicesMock.mockRejectedValueOnce(new Error('Failed'));

    const { result } = renderHook(() => useKidsAvailableServices(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Failed');
  });

  it('does not run when disabled', async () => {
    const { result } = renderHook(() => useKidsAvailableServices(false), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isFetching).toBe(false));
    expect(getKidsAvailableServicesMock).not.toHaveBeenCalled();
  });

  it('runs when enabled after being disabled', async () => {
    const services = [{ id: '1', name: 'Piano', slug: 'piano' }];
    getKidsAvailableServicesMock.mockResolvedValue({ data: services });

    const { result, rerender } = renderHook(
      ({ enabled }) => useKidsAvailableServices(enabled),
      {
        wrapper: createWrapper(),
        initialProps: { enabled: false },
      }
    );

    await waitFor(() => expect(result.current.isFetching).toBe(false));
    expect(getKidsAvailableServicesMock).not.toHaveBeenCalled();

    rerender({ enabled: true });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getKidsAvailableServicesMock).toHaveBeenCalledTimes(1);
  });
});
