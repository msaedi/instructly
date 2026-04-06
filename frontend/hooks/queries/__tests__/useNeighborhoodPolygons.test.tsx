import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { queryFn } from '@/lib/react-query/api';

import { useNeighborhoodPolygons } from '../useNeighborhoodPolygons';

jest.mock('@/lib/react-query/api', () => ({
  queryFn: jest.fn(),
}));

const queryFnMock = queryFn as jest.MockedFunction<typeof queryFn>;

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('useNeighborhoodPolygons', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('uses default market and enabled values when omitted', async () => {
    queryFnMock.mockReturnValue(async () => ({
      type: 'FeatureCollection',
      features: [],
    }));

    const { result } = renderHook(() => useNeighborhoodPolygons(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(queryFnMock).toHaveBeenCalledWith('/api/v1/addresses/neighborhoods/polygons', {
      params: { market: 'nyc' },
    });
    expect(result.current.data?.features).toEqual([]);
  });

  it('loads polygon geojson when enabled', async () => {
    queryFnMock.mockReturnValue(async () => ({
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          geometry: {
            type: 'Polygon',
            coordinates: [[[-74, 40.7], [-73.9, 40.7], [-73.9, 40.8], [-74, 40.8], [-74, 40.7]]],
          },
          properties: {
            id: 'MN01',
            display_key: 'ues',
            display_name: 'Upper East Side',
            borough: 'Manhattan',
            region_name: 'Upper East Side',
          },
        },
      ],
    }));

    const { result } = renderHook(() => useNeighborhoodPolygons('nyc', true), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(queryFnMock).toHaveBeenCalledWith('/api/v1/addresses/neighborhoods/polygons', {
      params: { market: 'nyc' },
    });
    expect(result.current.data?.type).toBe('FeatureCollection');
    expect(result.current.data?.features).toHaveLength(1);
  });

  it('surfaces fetch failures and respects disabled mode', async () => {
    queryFnMock.mockReturnValue(async () => {
      throw new Error('Failed to load neighborhood polygons');
    });

    const { result } = renderHook(() => useNeighborhoodPolygons('nyc', false), {
      wrapper: createWrapper(),
    });

    expect(queryFnMock).toHaveBeenCalledWith('/api/v1/addresses/neighborhoods/polygons', {
      params: { market: 'nyc' },
    });
    expect(result.current.fetchStatus).toBe('idle');

    const enabledResult = renderHook(() => useNeighborhoodPolygons('nyc', true), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(enabledResult.result.current.isError).toBe(true);
    });
  });
});
