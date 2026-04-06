import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { queryFn } from '@/lib/react-query/api';

import { useNeighborhoodSelectorData } from '../useNeighborhoodSelectorData';

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

describe('useNeighborhoodSelectorData', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('loads selector metadata and derived indexes', async () => {
    queryFnMock.mockReturnValue(async () => ({
      market: 'nyc',
      boroughs: [
        {
          borough: 'Manhattan',
          items: [
            {
              borough: 'Manhattan',
              display_key: 'ues',
              display_name: 'Upper East Side',
              display_order: 1,
              nta_ids: ['MN01'],
              search_terms: [{ term: 'Upper East Side', type: 'display_name' }],
              additional_boroughs: [],
            },
          ],
        },
        {
          borough: 'Brooklyn',
          items: [
            {
              borough: 'Brooklyn',
              display_key: 'park-slope',
              display_name: 'Park Slope',
              display_order: 2,
              nta_ids: ['BK01'],
              search_terms: [{ term: 'Park Slope', type: 'display_name' }],
              additional_boroughs: [],
            },
          ],
        },
      ],
      total_items: 2,
    }));

    const { result } = renderHook(() => useNeighborhoodSelectorData('nyc'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(queryFnMock).toHaveBeenCalledWith('/api/v1/addresses/neighborhoods/selector', {
      params: { market: 'nyc' },
    });
    expect(result.current.allItems.map((item) => item.display_key)).toEqual([
      'ues',
      'park-slope',
    ]);
    expect(result.current.itemByKey.get('ues')?.display_name).toBe('Upper East Side');
    expect(result.current.boroughs).toEqual(['Manhattan', 'Brooklyn']);
  });

  it('surfaces fetch failures and keeps derived collections empty', async () => {
    queryFnMock.mockReturnValue(async () => {
      throw new Error('Failed to load neighborhood selector');
    });

    const { result } = renderHook(() => useNeighborhoodSelectorData('nyc'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.allItems).toEqual([]);
    expect(result.current.boroughs).toEqual([]);
    expect(result.current.itemByKey.size).toBe(0);
  });
});
