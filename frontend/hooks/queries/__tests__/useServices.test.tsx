import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import {
  useServiceCategories,
  useAllServicesWithInstructors,
  useServicesByCategory,
  useServicesInfiniteSearch,
  useProgressiveLoading,
  usePrefetchServices,
  useServicesCatalog,
} from '../useServices';
import { publicApi } from '@/features/shared/api/client';

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    getServiceCategories: jest.fn(),
    getAllServicesWithInstructors: jest.fn(),
    getCatalogServices: jest.fn(),
  },
}));

jest.mock('@/lib/apiBase', () => ({
  withApiBase: (path: string) => path,
}));

const getServiceCategoriesMock = publicApi.getServiceCategories as jest.Mock;
const getAllServicesWithInstructorsMock = publicApi.getAllServicesWithInstructors as jest.Mock;
const getCatalogServicesMock = publicApi.getCatalogServices as jest.Mock;

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

describe('useServices hooks', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('loads service categories', async () => {
    getServiceCategoriesMock.mockResolvedValue({
      data: [{ id: 'cat-1', name: 'Music' }],
      status: 200,
    });

    const { result } = renderHook(() => useServiceCategories(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([{ id: 'cat-1', name: 'Music' }]);
    expect(getServiceCategoriesMock).toHaveBeenCalledTimes(1);
  });

  it('loads services with instructor counts', async () => {
    getAllServicesWithInstructorsMock.mockResolvedValue({
      data: { categories: [{ id: 'cat-1', name: 'Music', services: [] }] },
      status: 200,
    });

    const { result } = renderHook(() => useAllServicesWithInstructors(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ categories: [{ id: 'cat-1', name: 'Music', services: [] }] });
  });

  it('loads services for a category when enabled', async () => {
    getCatalogServicesMock.mockResolvedValue({
      data: [{ id: 'svc-1', name: 'Piano', slug: 'piano' }],
      status: 200,
    });

    const { result } = renderHook(() => useServicesByCategory('music'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getCatalogServicesMock).toHaveBeenCalledWith('music');
    expect(result.current.data).toEqual([{ id: 'svc-1', name: 'Piano', slug: 'piano' }]);
  });

  it('loads full services catalog', async () => {
    getCatalogServicesMock.mockResolvedValue({
      data: [{ id: 'svc-1', name: 'Piano', subcategory_id: '01HABCTESTSUBCAT0000000001', description: 'Piano lessons' }],
      status: 200,
    });

    const { result } = renderHook(() => useServicesCatalog(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([
      { id: 'svc-1', name: 'Piano', subcategory_id: '01HABCTESTSUBCAT0000000001', description: 'Piano lessons' },
    ]);
    expect(getCatalogServicesMock).toHaveBeenCalled();
  });

  it('does not fetch services by category when disabled', async () => {
    const { result } = renderHook(() => useServicesByCategory('music', false), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isFetching).toBe(false));
    expect(getCatalogServicesMock).not.toHaveBeenCalled();
  });

  it('supports infinite search pagination', async () => {
    const fetchMock = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ services: [{ id: 'svc-1' }], hasMore: true, nextPage: 1 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ services: [{ id: 'svc-2' }], hasMore: false }),
      });
    const originalFetch = global.fetch;
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const { result } = renderHook(
      () => useServicesInfiniteSearch({ query: 'piano', minPrice: 10 }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.fetchNextPage();
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const secondCallUrl = fetchMock.mock.calls[1][0] as string;
    expect(secondCallUrl).toContain('page=1');

    global.fetch = originalFetch;
  });

  it('includes all filter parameters in search query', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ services: [], hasMore: false }),
    });
    const originalFetch = global.fetch;
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const { result } = renderHook(
      () => useServicesInfiniteSearch({
        query: 'music',
        category: 'instruments',
        minPrice: 20,
        maxPrice: 100,
        onlineOnly: true,
        certificationRequired: true,
      }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const callUrl = fetchMock.mock.calls[0][0] as string;
    expect(callUrl).toContain('q=music');
    expect(callUrl).toContain('category=instruments');
    expect(callUrl).toContain('min_price=20');
    expect(callUrl).toContain('max_price=100');
    expect(callUrl).toContain('online_only=true');
    expect(callUrl).toContain('certification_required=true');

    global.fetch = originalFetch;
  });

  it('exposes error state when infinite search fails', async () => {
    const fetchMock = jest.fn().mockResolvedValue({ ok: false });
    const originalFetch = global.fetch;
    global.fetch = fetchMock as unknown as typeof global.fetch;

    const { result } = renderHook(
      () => useServicesInfiniteSearch({ query: 'piano' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isError).toBe(true));

    global.fetch = originalFetch;
  });

  it('manages progressive loading counts', async () => {
    const { result, rerender } = renderHook(
      ({ total }) => useProgressiveLoading(total, 5),
      { initialProps: { total: 12 } }
    );

    expect(result.current.visibleCount).toBe(5);
    expect(result.current.hasMore).toBe(true);

    act(() => {
      result.current.loadMore();
    });

    expect(result.current.visibleCount).toBe(12);
    expect(result.current.hasMore).toBe(false);

    rerender({ total: 3 });

    await waitFor(() => {
      expect(result.current.visibleCount).toBe(5);
    });
  });

  it('prefetches service data', async () => {
    getServiceCategoriesMock.mockResolvedValue({ data: [], status: 200 });
    getAllServicesWithInstructorsMock.mockResolvedValue({ data: { categories: [] }, status: 200 });
    getCatalogServicesMock.mockResolvedValue({ data: [], status: 200 });

    const { result } = renderHook(() => usePrefetchServices(), { wrapper: createWrapper() });

    act(() => {
      result.current.categories();
      result.current.all();
      result.current.byCategory('music');
    });

    await waitFor(() => {
      expect(getServiceCategoriesMock).toHaveBeenCalled();
      expect(getAllServicesWithInstructorsMock).toHaveBeenCalled();
      expect(getCatalogServicesMock).toHaveBeenCalledWith('music');
    });
  });
});
