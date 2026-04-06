import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { fetchAPI } from '@/lib/api';

import { useNeighborhoodPolygons } from '../useNeighborhoodPolygons';

jest.mock('@/lib/api', () => ({
  fetchAPI: jest.fn(),
}));

const fetchAPIMock = fetchAPI as jest.MockedFunction<typeof fetchAPI>;

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

  it('loads polygon geojson when enabled', async () => {
    fetchAPIMock.mockResolvedValue({
      ok: true,
      json: async () => ({
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
      }),
    } as Response);

    const { result } = renderHook(() => useNeighborhoodPolygons('nyc', true), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(fetchAPIMock).toHaveBeenCalledWith(
      '/api/v1/addresses/neighborhoods/polygons?market=nyc',
    );
    expect(result.current.data?.type).toBe('FeatureCollection');
    expect(result.current.data?.features).toHaveLength(1);
  });

  it('surfaces fetch failures and respects disabled mode', async () => {
    fetchAPIMock.mockResolvedValue({
      ok: false,
    } as Response);

    const { result } = renderHook(() => useNeighborhoodPolygons('nyc', false), {
      wrapper: createWrapper(),
    });

    expect(fetchAPIMock).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe('idle');

    const enabledResult = renderHook(() => useNeighborhoodPolygons('nyc', true), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(enabledResult.result.current.isError).toBe(true);
    });
  });
});
