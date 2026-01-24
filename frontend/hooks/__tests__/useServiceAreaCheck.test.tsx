import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { instructorService } from '@/services/instructorService';

jest.mock('@/services/instructorService', () => ({
  instructorService: {
    checkServiceArea: jest.fn(),
  },
}));

jest.unmock('@/hooks/useServiceAreaCheck');

const { useServiceAreaCheck } = jest.requireActual('../useServiceAreaCheck') as typeof import('../useServiceAreaCheck');

const checkServiceAreaMock = instructorService.checkServiceArea as jest.Mock;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnMount: false },
    },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'QueryClientWrapper';
  return { Wrapper };
};

describe('useServiceAreaCheck', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('does not fetch when coordinates are missing', async () => {
    const { Wrapper } = createWrapper();

    renderHook(
      () => useServiceAreaCheck({ instructorId: 'inst-1', lat: undefined, lng: 73.9 }),
      { wrapper: Wrapper }
    );

    await waitFor(() => {
      expect(checkServiceAreaMock).not.toHaveBeenCalled();
    });
  });

  it('fetches when all params are provided', async () => {
    checkServiceAreaMock.mockResolvedValue({
      instructor_id: 'inst-1',
      is_covered: true,
      coordinates: { lat: 40.7, lng: -73.9 },
    });
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useServiceAreaCheck({ instructorId: 'inst-1', lat: 40.7, lng: -73.9 }),
      { wrapper: Wrapper }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(checkServiceAreaMock).toHaveBeenCalledWith('inst-1', 40.7, -73.9);
  });

  it('returns is_covered status', async () => {
    checkServiceAreaMock.mockResolvedValue({
      instructor_id: 'inst-2',
      is_covered: false,
      coordinates: { lat: 40.7, lng: -73.9 },
    });
    const { Wrapper } = createWrapper();

    const { result } = renderHook(
      () => useServiceAreaCheck({ instructorId: 'inst-2', lat: 40.7, lng: -73.9 }),
      { wrapper: Wrapper }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.is_covered).toBe(false);
  });

  it('caches results for the same coordinates', async () => {
    checkServiceAreaMock.mockResolvedValue({
      instructor_id: 'inst-3',
      is_covered: true,
      coordinates: { lat: 40.7, lng: -73.9 },
    });
    const { Wrapper } = createWrapper();

    const { result, rerender } = renderHook(
      (props: { instructorId: string; lat: number; lng: number }) => useServiceAreaCheck(props),
      {
        wrapper: Wrapper,
        initialProps: { instructorId: 'inst-3', lat: 40.7, lng: -73.9 },
      }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    rerender({ instructorId: 'inst-3', lat: 40.7, lng: -73.9 });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(checkServiceAreaMock).toHaveBeenCalledTimes(1);
  });
});
