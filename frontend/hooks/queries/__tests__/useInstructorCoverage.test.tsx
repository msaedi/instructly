import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useInstructorCoverage } from '../useInstructorCoverage';

jest.mock('@/lib/apiBase', () => ({
  withApiBase: (path: string) => path,
}));

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'QueryClientWrapper';
  return Wrapper;
};

describe('useInstructorCoverage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('does not fetch when ids are empty', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ type: 'FeatureCollection', features: [] }),
    } as Response);

    const { result } = renderHook(() => useInstructorCoverage([]), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isFetching).toBe(false));
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it('fetches coverage for unique, sorted ids', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ type: 'FeatureCollection', features: [] }),
    } as Response);

    const { result } = renderHook(() => useInstructorCoverage(['b', 'a', 'a']), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/v1/addresses/coverage/bulk?ids=a%2Cb',
      expect.objectContaining({ credentials: 'include' })
    );

    fetchSpy.mockRestore();
  });

  it('surfaces an error when coverage fetch fails', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue({
      ok: false,
    } as Response);

    const { result } = renderHook(() => useInstructorCoverage(['a']), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    fetchSpy.mockRestore();
  });
});
