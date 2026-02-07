import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import {
  useCategoriesWithSubcategories,
  useCategoryTree,
  useSubcategoriesByCategory,
  useSubcategory,
  useSubcategoryFilters,
  useServicesByAgeGroup,
  useServiceFilterContext,
} from '../useTaxonomy';
import { publicApi } from '@/features/shared/api/client';

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    getCategoriesWithSubcategories: jest.fn(),
    getCategoryTree: jest.fn(),
    getSubcategoriesByCategory: jest.fn(),
    getSubcategoryWithServices: jest.fn(),
    getSubcategoryFilters: jest.fn(),
    getServicesByAgeGroup: jest.fn(),
    getServiceFilterContext: jest.fn(),
  },
}));

const getCategoriesWithSubcategoriesMock =
  publicApi.getCategoriesWithSubcategories as jest.Mock;
const getCategoryTreeMock = publicApi.getCategoryTree as jest.Mock;
const getSubcategoriesByCategoryMock =
  publicApi.getSubcategoriesByCategory as jest.Mock;
const getSubcategoryWithServicesMock =
  publicApi.getSubcategoryWithServices as jest.Mock;
const getSubcategoryFiltersMock = publicApi.getSubcategoryFilters as jest.Mock;
const getServicesByAgeGroupMock = publicApi.getServicesByAgeGroup as jest.Mock;
const getServiceFilterContextMock =
  publicApi.getServiceFilterContext as jest.Mock;

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

describe('useTaxonomy hooks', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ─── useCategoriesWithSubcategories ────────────────────────────────

  describe('useCategoriesWithSubcategories', () => {
    it('fetches and returns the full category browse list', async () => {
      const mockData = [
        {
          id: '01HABCCAT000000000000000001',
          name: 'Music',
          subtitle: 'Learn an instrument',
          description: 'Musical instruction',
          display_order: 1,
          icon_name: 'music',
          subcategories: [
            { id: '01HABCSUB000000000000000001', name: 'Strings', service_count: 5 },
            { id: '01HABCSUB000000000000000002', name: 'Woodwinds', service_count: 3 },
          ],
        },
      ];
      getCategoriesWithSubcategoriesMock.mockResolvedValue({
        data: mockData,
        status: 200,
      });

      const { result } = renderHook(() => useCategoriesWithSubcategories(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual(mockData);
      expect(getCategoriesWithSubcategoriesMock).toHaveBeenCalledTimes(1);
    });

    it('propagates API errors to the error state', async () => {
      getCategoriesWithSubcategoriesMock.mockResolvedValue({
        error: 'Internal server error',
        status: 500,
      });

      const { result } = renderHook(() => useCategoriesWithSubcategories(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(result.current.error).toBeTruthy();
      expect(result.current.data).toBeUndefined();
    });

    it('propagates network failures', async () => {
      getCategoriesWithSubcategoriesMock.mockRejectedValue(
        new Error('Network error')
      );

      const { result } = renderHook(() => useCategoriesWithSubcategories(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(result.current.error?.message).toBe('Network error');
    });
  });

  // ─── useCategoryTree ───────────────────────────────────────────────

  describe('useCategoryTree', () => {
    const CATEGORY_ID = '01HABCCAT000000000000000001';

    it('fetches a full 3-level tree for a category', async () => {
      const mockTree = {
        id: CATEGORY_ID,
        name: 'Music',
        subcategories: [
          {
            id: '01HABCSUB000000000000000001',
            name: 'Strings',
            category_id: CATEGORY_ID,
            display_order: 1,
            services: [
              { id: '01HABCSVC000000000000000001', name: 'Guitar', slug: 'guitar' },
            ],
          },
        ],
      };
      getCategoryTreeMock.mockResolvedValue({ data: mockTree, status: 200 });

      const { result } = renderHook(() => useCategoryTree(CATEGORY_ID), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual(mockTree);
      expect(getCategoryTreeMock).toHaveBeenCalledWith(CATEGORY_ID);
    });

    it('does NOT fetch when categoryId is empty string', async () => {
      const { result } = renderHook(() => useCategoryTree(''), {
        wrapper: createWrapper(),
      });

      // Should remain idle — the `enabled: !!categoryId` guard should prevent fetching
      await waitFor(() => expect(result.current.fetchStatus).toBe('idle'));
      expect(getCategoryTreeMock).not.toHaveBeenCalled();
      expect(result.current.data).toBeUndefined();
    });

    it('passes the exact categoryId to the API (no mutation)', async () => {
      const weirdId = '  01HABCCAT000000000000000001  ';
      getCategoryTreeMock.mockResolvedValue({ data: { id: weirdId }, status: 200 });

      const { result } = renderHook(() => useCategoryTree(weirdId), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      // Bug hunt: verify hook doesn't trim or transform the ID
      expect(getCategoryTreeMock).toHaveBeenCalledWith(weirdId);
    });
  });

  // ─── useSubcategoriesByCategory ────────────────────────────────────

  describe('useSubcategoriesByCategory', () => {
    const CATEGORY_ID = '01HABCCAT000000000000000002';

    it('fetches subcategory briefs for a category', async () => {
      const mockBriefs = [
        { id: '01HABCSUB000000000000000003', name: 'Ballet', service_count: 4 },
        { id: '01HABCSUB000000000000000004', name: 'Hip-Hop', service_count: 2 },
      ];
      getSubcategoriesByCategoryMock.mockResolvedValue({
        data: mockBriefs,
        status: 200,
      });

      const { result } = renderHook(
        () => useSubcategoriesByCategory(CATEGORY_ID),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toHaveLength(2);
      expect(getSubcategoriesByCategoryMock).toHaveBeenCalledWith(CATEGORY_ID);
    });

    it('is disabled for empty categoryId', async () => {
      const { result } = renderHook(
        () => useSubcategoriesByCategory(''),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.fetchStatus).toBe('idle'));
      expect(getSubcategoriesByCategoryMock).not.toHaveBeenCalled();
    });
  });

  // ─── useSubcategory ────────────────────────────────────────────────

  describe('useSubcategory', () => {
    const SUBCATEGORY_ID = '01HABCSUB000000000000000005';

    it('fetches a subcategory with its services', async () => {
      const mockSubcategory = {
        id: SUBCATEGORY_ID,
        name: 'Classical Piano',
        category_id: '01HABCCAT000000000000000001',
        display_order: 1,
        services: [
          { id: '01HABCSVC000000000000000002', name: 'Classical Piano', slug: 'classical-piano' },
          { id: '01HABCSVC000000000000000003', name: 'Jazz Piano', slug: 'jazz-piano' },
        ],
      };
      getSubcategoryWithServicesMock.mockResolvedValue({
        data: mockSubcategory,
        status: 200,
      });

      const { result } = renderHook(() => useSubcategory(SUBCATEGORY_ID), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.services).toHaveLength(2);
      expect(getSubcategoryWithServicesMock).toHaveBeenCalledWith(SUBCATEGORY_ID);
    });

    it('is disabled for empty subcategoryId', async () => {
      const { result } = renderHook(() => useSubcategory(''), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.fetchStatus).toBe('idle'));
      expect(getSubcategoryWithServicesMock).not.toHaveBeenCalled();
    });

    it('handles server returning null data', async () => {
      getSubcategoryWithServicesMock.mockResolvedValue({
        data: null,
        status: 200,
      });

      const { result } = renderHook(() => useSubcategory(SUBCATEGORY_ID), {
        wrapper: createWrapper(),
      });

      // convertApiResponse throws on null data — should surface as error
      await waitFor(() => expect(result.current.isError).toBe(true));
    });
  });

  // ─── useSubcategoryFilters ─────────────────────────────────────────

  describe('useSubcategoryFilters', () => {
    const SUBCATEGORY_ID = '01HABCSUB000000000000000006';

    it('fetches filter definitions for a subcategory', async () => {
      const mockFilters = [
        {
          id: '01HABCFLT000000000000000001',
          name: 'Instrument Type',
          filter_type: 'multi_select',
          options: [
            { id: '01HABCOPT000000000000000001', label: 'Acoustic', value: 'acoustic' },
            { id: '01HABCOPT000000000000000002', label: 'Electric', value: 'electric' },
          ],
        },
      ];
      getSubcategoryFiltersMock.mockResolvedValue({
        data: mockFilters,
        status: 200,
      });

      const { result } = renderHook(
        () => useSubcategoryFilters(SUBCATEGORY_ID),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toHaveLength(1);
      expect(result.current.data?.[0]?.options).toHaveLength(2);
    });

    it('is disabled for empty subcategoryId', async () => {
      const { result } = renderHook(() => useSubcategoryFilters(''), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.fetchStatus).toBe('idle'));
      expect(getSubcategoryFiltersMock).not.toHaveBeenCalled();
    });
  });

  // ─── useServicesByAgeGroup ─────────────────────────────────────────

  describe('useServicesByAgeGroup', () => {
    it('fetches services for an age group', async () => {
      const mockServices = [
        { id: '01HABCSVC000000000000000004', name: 'Kids Piano', slug: 'kids-piano' },
        { id: '01HABCSVC000000000000000005', name: 'Kids Guitar', slug: 'kids-guitar' },
      ];
      getServicesByAgeGroupMock.mockResolvedValue({
        data: mockServices,
        status: 200,
      });

      const { result } = renderHook(
        () => useServicesByAgeGroup('children'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toHaveLength(2);
      expect(getServicesByAgeGroupMock).toHaveBeenCalledWith('children');
    });

    it('passes different age groups correctly', async () => {
      getServicesByAgeGroupMock.mockResolvedValue({ data: [], status: 200 });

      const { result } = renderHook(
        () => useServicesByAgeGroup('adults'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(getServicesByAgeGroupMock).toHaveBeenCalledWith('adults');
    });

    it('is disabled when ageGroup is empty string (falsy)', async () => {
      // Bug hunt: the hook uses `enabled: !!ageGroup`. An empty string
      // is falsy, so it should NOT fetch. This catches a potential bug
      // where a component passes '' as a default before user selects.
      const { result } = renderHook(
        () => useServicesByAgeGroup('' as 'adults'),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.fetchStatus).toBe('idle'));
      expect(getServicesByAgeGroupMock).not.toHaveBeenCalled();
    });
  });

  // ─── useServiceFilterContext ────────────────────────────────────────

  describe('useServiceFilterContext', () => {
    const SERVICE_ID = '01HABCSVC000000000000000006';

    it('fetches filter context for a service', async () => {
      const mockContext = {
        available_filters: [
          {
            id: '01HABCFLT000000000000000002',
            name: 'Level',
            filter_type: 'single_select',
            options: [
              { id: '01HABCOPT000000000000000003', label: 'Beginner', value: 'beginner' },
            ],
          },
        ],
        current_selections: {},
      };
      getServiceFilterContextMock.mockResolvedValue({
        data: mockContext,
        status: 200,
      });

      const { result } = renderHook(
        () => useServiceFilterContext(SERVICE_ID),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.available_filters).toHaveLength(1);
      expect(result.current.data?.current_selections).toEqual({});
      expect(getServiceFilterContextMock).toHaveBeenCalledWith(SERVICE_ID);
    });

    it('is disabled for empty serviceId', async () => {
      const { result } = renderHook(() => useServiceFilterContext(''), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.fetchStatus).toBe('idle'));
      expect(getServiceFilterContextMock).not.toHaveBeenCalled();
    });

    it('propagates 404 as error (service not found)', async () => {
      getServiceFilterContextMock.mockResolvedValue({
        error: 'Service not found',
        status: 404,
      });

      const { result } = renderHook(
        () => useServiceFilterContext(SERVICE_ID),
        { wrapper: createWrapper() }
      );

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(result.current.data).toBeUndefined();
    });
  });

  // ─── Cross-cutting: query key isolation ─────────────────────────────

  describe('query key isolation', () => {
    it('different categoryIds produce independent queries', async () => {
      getCategoryTreeMock
        .mockResolvedValueOnce({ data: { id: 'cat-1', name: 'Music' }, status: 200 })
        .mockResolvedValueOnce({ data: { id: 'cat-2', name: 'Dance' }, status: 200 });

      const wrapper = createWrapper();

      const { result: result1 } = renderHook(
        () => useCategoryTree('cat-1'),
        { wrapper }
      );
      const { result: result2 } = renderHook(
        () => useCategoryTree('cat-2'),
        { wrapper }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
      });

      // Bug hunt: verify each query got the right data, not a cache collision
      expect(result1.current.data).toEqual({ id: 'cat-1', name: 'Music' });
      expect(result2.current.data).toEqual({ id: 'cat-2', name: 'Dance' });
      expect(getCategoryTreeMock).toHaveBeenCalledTimes(2);
    });
  });
});
