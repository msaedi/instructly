import React from 'react';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import {
  useCatalogCategories,
  useCatalogCategory,
  useCatalogSubcategory,
  useCatalogService,
  useCatalogSubcategoryServices,
  useCatalogSubcategoryFilters,
  useUpdateFilterSelections,
  useValidateFilters,
} from '../useCatalogBrowse';
import { publicApi, protectedApi } from '@/features/shared/api/client';

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    listCatalogCategories: jest.fn(),
    getCatalogCategory: jest.fn(),
    getCatalogSubcategory: jest.fn(),
    getCatalogService: jest.fn(),
    listCatalogSubcategoryServices: jest.fn(),
    getCatalogSubcategoryFilters: jest.fn(),
  },
  protectedApi: {
    updateFilterSelections: jest.fn(),
    validateFilterSelections: jest.fn(),
  },
}));

const listCatalogCategoriesMock = publicApi.listCatalogCategories as jest.Mock;
const getCatalogCategoryMock = publicApi.getCatalogCategory as jest.Mock;
const getCatalogSubcategoryMock = publicApi.getCatalogSubcategory as jest.Mock;
const getCatalogServiceMock = publicApi.getCatalogService as jest.Mock;
const listCatalogSubcategoryServicesMock = publicApi.listCatalogSubcategoryServices as jest.Mock;
const getCatalogSubcategoryFiltersMock = publicApi.getCatalogSubcategoryFilters as jest.Mock;
const updateFilterSelectionsMock = protectedApi.updateFilterSelections as jest.Mock;
const validateFilterSelectionsMock = protectedApi.validateFilterSelections as jest.Mock;

let queryClient: QueryClient;

const createWrapper = () => {
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'QueryClientWrapper';
  return Wrapper;
};

describe('useCatalogBrowse hooks', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
  });

  afterEach(() => {
    queryClient.clear();
  });

  // ─── useCatalogCategories ─────────────────────────────────────

  describe('useCatalogCategories', () => {
    it('fetches and returns the category list', async () => {
      const mockData = [
        { id: 'CAT01', slug: 'music', name: 'Music', description: 'All music', subcategory_count: 5 },
        { id: 'CAT02', slug: 'sports', name: 'Sports', description: null, subcategory_count: 3 },
      ];
      listCatalogCategoriesMock.mockResolvedValue({ data: mockData, status: 200 });

      const { result } = renderHook(() => useCatalogCategories(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual(mockData);
      expect(listCatalogCategoriesMock).toHaveBeenCalledTimes(1);
    });

    it('propagates API errors', async () => {
      listCatalogCategoriesMock.mockResolvedValue({ error: 'Server error', status: 500 });

      const { result } = renderHook(() => useCatalogCategories(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(result.current.data).toBeUndefined();
    });

    it('propagates network failures', async () => {
      listCatalogCategoriesMock.mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useCatalogCategories(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(result.current.error?.message).toBe('Network error');
    });
  });

  // ─── useCatalogCategory ───────────────────────────────────────

  describe('useCatalogCategory', () => {
    it('fetches category detail by slug', async () => {
      const mockData = {
        id: 'CAT01',
        slug: 'music',
        name: 'Music',
        description: 'All music',
        meta_title: null,
        meta_description: null,
        subcategories: [
          { id: 'SUB01', slug: 'piano', name: 'Piano', description: null, service_count: 4 },
        ],
      };
      getCatalogCategoryMock.mockResolvedValue({ data: mockData, status: 200 });

      const { result } = renderHook(() => useCatalogCategory('music'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual(mockData);
      expect(getCatalogCategoryMock).toHaveBeenCalledWith('music');
    });

    it('is disabled when slug is empty', async () => {
      const { result } = renderHook(() => useCatalogCategory(''), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.fetchStatus).toBe('idle'));
      expect(getCatalogCategoryMock).not.toHaveBeenCalled();
    });

    it('propagates 404 as error', async () => {
      getCatalogCategoryMock.mockResolvedValue({ error: 'Not found', status: 404 });

      const { result } = renderHook(() => useCatalogCategory('nonexistent'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(result.current.data).toBeUndefined();
    });
  });

  // ─── useCatalogSubcategory ────────────────────────────────────

  describe('useCatalogSubcategory', () => {
    it('fetches subcategory detail by two slugs', async () => {
      const mockData = {
        id: 'SUB01',
        slug: 'piano',
        name: 'Piano',
        description: 'Piano lessons',
        meta_title: null,
        meta_description: null,
        category: { id: 'CAT01', name: 'Music' },
        services: [{ id: 'SVC01', slug: 'classical-piano', name: 'Classical Piano' }],
        filters: [],
      };
      getCatalogSubcategoryMock.mockResolvedValue({ data: mockData, status: 200 });

      const { result } = renderHook(() => useCatalogSubcategory('music', 'piano'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual(mockData);
      expect(getCatalogSubcategoryMock).toHaveBeenCalledWith('music', 'piano');
    });

    it('is disabled when categorySlug is empty', async () => {
      const { result } = renderHook(() => useCatalogSubcategory('', 'piano'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.fetchStatus).toBe('idle'));
      expect(getCatalogSubcategoryMock).not.toHaveBeenCalled();
    });

    it('is disabled when subcategorySlug is empty', async () => {
      const { result } = renderHook(() => useCatalogSubcategory('music', ''), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.fetchStatus).toBe('idle'));
      expect(getCatalogSubcategoryMock).not.toHaveBeenCalled();
    });

    it('is disabled when both slugs are empty', async () => {
      const { result } = renderHook(() => useCatalogSubcategory('', ''), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.fetchStatus).toBe('idle'));
      expect(getCatalogSubcategoryMock).not.toHaveBeenCalled();
    });

    it('propagates 404 for mismatched category slug', async () => {
      getCatalogSubcategoryMock.mockResolvedValue({ error: 'Not found', status: 404 });

      const { result } = renderHook(() => useCatalogSubcategory('tutoring', 'piano'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isError).toBe(true));
    });
  });

  // ─── useCatalogService ────────────────────────────────────────

  describe('useCatalogService', () => {
    const SERVICE_ID = '01HABCSVC000000000000000001';

    it('fetches service detail by ID', async () => {
      const mockData = {
        id: SERVICE_ID,
        slug: 'classical-piano',
        name: 'Classical Piano',
        eligible_age_groups: ['kids', 'teens', 'adults'],
        default_duration_minutes: 60,
        description: 'Classical piano instruction',
        price_floor_in_person_cents: null,
        price_floor_online_cents: null,
        subcategory_id: 'SUB01',
        subcategory_name: 'Piano',
      };
      getCatalogServiceMock.mockResolvedValue({ data: mockData, status: 200 });

      const { result } = renderHook(() => useCatalogService(SERVICE_ID), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual(mockData);
      expect(getCatalogServiceMock).toHaveBeenCalledWith(SERVICE_ID);
    });

    it('is disabled when serviceId is empty', async () => {
      const { result } = renderHook(() => useCatalogService(''), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.fetchStatus).toBe('idle'));
      expect(getCatalogServiceMock).not.toHaveBeenCalled();
    });

    it('propagates 404 for missing service', async () => {
      getCatalogServiceMock.mockResolvedValue({ error: 'Not found', status: 404 });

      const { result } = renderHook(() => useCatalogService('INVALID'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isError).toBe(true));
    });
  });

  // ─── useCatalogSubcategoryServices ────────────────────────────

  describe('useCatalogSubcategoryServices', () => {
    const SUBCATEGORY_ID = '01HABCSUB000000000000000001';

    it('fetches services list for a subcategory', async () => {
      const mockData = [
        { id: 'SVC01', slug: 'classical-piano', name: 'Classical Piano', eligible_age_groups: ['adults'], default_duration_minutes: 60 },
        { id: 'SVC02', slug: 'jazz-piano', name: 'Jazz Piano', eligible_age_groups: ['teens'], default_duration_minutes: 45 },
      ];
      listCatalogSubcategoryServicesMock.mockResolvedValue({ data: mockData, status: 200 });

      const { result } = renderHook(() => useCatalogSubcategoryServices(SUBCATEGORY_ID), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toHaveLength(2);
      expect(listCatalogSubcategoryServicesMock).toHaveBeenCalledWith(SUBCATEGORY_ID);
    });

    it('is disabled when subcategoryId is empty', async () => {
      const { result } = renderHook(() => useCatalogSubcategoryServices(''), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.fetchStatus).toBe('idle'));
      expect(listCatalogSubcategoryServicesMock).not.toHaveBeenCalled();
    });
  });

  // ─── useCatalogSubcategoryFilters ─────────────────────────────

  describe('useCatalogSubcategoryFilters', () => {
    const SUBCATEGORY_ID = '01HABCSUB000000000000000002';

    it('fetches filter definitions for a subcategory', async () => {
      const mockData = [
        {
          filter_key: 'grade_level',
          filter_display_name: 'Grade Level',
          filter_type: 'multi_select',
          options: [
            { id: 'OPT01', value: 'elementary', display_name: 'Elementary', display_order: 1 },
            { id: 'OPT02', value: 'middle', display_name: 'Middle School', display_order: 2 },
          ],
        },
      ];
      getCatalogSubcategoryFiltersMock.mockResolvedValue({ data: mockData, status: 200 });

      const { result } = renderHook(() => useCatalogSubcategoryFilters(SUBCATEGORY_ID), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toHaveLength(1);
      expect(result.current.data?.[0]?.options).toHaveLength(2);
    });

    it('is disabled when subcategoryId is empty', async () => {
      const { result } = renderHook(() => useCatalogSubcategoryFilters(''), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.fetchStatus).toBe('idle'));
      expect(getCatalogSubcategoryFiltersMock).not.toHaveBeenCalled();
    });

    it('returns empty array for subcategory without filters', async () => {
      getCatalogSubcategoryFiltersMock.mockResolvedValue({ data: [], status: 200 });

      const { result } = renderHook(() => useCatalogSubcategoryFilters(SUBCATEGORY_ID), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual([]);
    });
  });

  // ─── useUpdateFilterSelections ────────────────────────────────

  describe('useUpdateFilterSelections', () => {
    it('calls updateFilterSelections with correct payload', async () => {
      const mockResponse = {
        id: 'IS01',
        catalog_service_id: 'SVC01',
        name: 'Classical Piano',
        category: 'Music',
        hourly_rate: 50,
      };
      updateFilterSelectionsMock.mockResolvedValue({ data: mockResponse, status: 200 });

      const { result } = renderHook(() => useUpdateFilterSelections(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({
          instructorServiceId: 'IS01',
          filterSelections: { grade_level: ['elementary', 'middle'] },
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(updateFilterSelectionsMock).toHaveBeenCalledWith('IS01', {
        filter_selections: { grade_level: ['elementary', 'middle'] },
      });
    });

    it('propagates API errors on failure', async () => {
      updateFilterSelectionsMock.mockResolvedValue({ error: 'Forbidden', status: 403 });

      const { result } = renderHook(() => useUpdateFilterSelections(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({
          instructorServiceId: 'IS01',
          filterSelections: { grade_level: ['invalid'] },
        });
      });

      await waitFor(() => expect(result.current.isError).toBe(true));
    });

    it('invalidates queries on success', async () => {
      updateFilterSelectionsMock.mockResolvedValue({
        data: { id: 'IS01', name: 'Piano' },
        status: 200,
      });

      const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');

      const { result } = renderHook(() => useUpdateFilterSelections(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({
          instructorServiceId: 'IS01',
          filterSelections: { grade_level: ['elementary'] },
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['instructor', 'services'] });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['taxonomy'] });
    });
  });

  // ─── useValidateFilters ───────────────────────────────────────

  describe('useValidateFilters', () => {
    it('validates filter selections and returns valid=true', async () => {
      const mockResponse = { valid: true, errors: [] };
      validateFilterSelectionsMock.mockResolvedValue({ data: mockResponse, status: 200 });

      const { result } = renderHook(() => useValidateFilters(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({
          service_catalog_id: 'SVC01',
          filter_selections: { grade_level: ['elementary'] },
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual(mockResponse);
      expect(validateFilterSelectionsMock).toHaveBeenCalledWith({
        service_catalog_id: 'SVC01',
        filter_selections: { grade_level: ['elementary'] },
      });
    });

    it('returns validation errors for invalid selections', async () => {
      const mockResponse = {
        valid: false,
        errors: ['Invalid option "invalid" for filter "grade_level"'],
      };
      validateFilterSelectionsMock.mockResolvedValue({ data: mockResponse, status: 200 });

      const { result } = renderHook(() => useValidateFilters(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({
          service_catalog_id: 'SVC01',
          filter_selections: { grade_level: ['invalid'] },
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.valid).toBe(false);
      expect(result.current.data?.errors).toHaveLength(1);
    });

    it('propagates network errors', async () => {
      validateFilterSelectionsMock.mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useValidateFilters(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({
          service_catalog_id: 'SVC01',
          filter_selections: {},
        });
      });

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(result.current.error?.message).toBe('Network error');
    });
  });

  // ─── Query key isolation ──────────────────────────────────────

  describe('query key isolation', () => {
    it('different category slugs produce independent queries', async () => {
      getCatalogCategoryMock
        .mockResolvedValueOnce({ data: { id: 'C1', slug: 'music', name: 'Music' }, status: 200 })
        .mockResolvedValueOnce({ data: { id: 'C2', slug: 'sports', name: 'Sports' }, status: 200 });

      const wrapper = createWrapper();

      const { result: result1 } = renderHook(() => useCatalogCategory('music'), { wrapper });
      const { result: result2 } = renderHook(() => useCatalogCategory('sports'), { wrapper });

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
      });

      expect(result1.current.data?.name).toBe('Music');
      expect(result2.current.data?.name).toBe('Sports');
      expect(getCatalogCategoryMock).toHaveBeenCalledTimes(2);
    });

    it('different subcategory slug pairs produce independent queries', async () => {
      getCatalogSubcategoryMock
        .mockResolvedValueOnce({ data: { id: 'S1', slug: 'piano', name: 'Piano' }, status: 200 })
        .mockResolvedValueOnce({ data: { id: 'S2', slug: 'guitar', name: 'Guitar' }, status: 200 });

      const wrapper = createWrapper();

      const { result: result1 } = renderHook(
        () => useCatalogSubcategory('music', 'piano'),
        { wrapper }
      );
      const { result: result2 } = renderHook(
        () => useCatalogSubcategory('music', 'guitar'),
        { wrapper }
      );

      await waitFor(() => {
        expect(result1.current.isSuccess).toBe(true);
        expect(result2.current.isSuccess).toBe(true);
      });

      expect(result1.current.data?.name).toBe('Piano');
      expect(result2.current.data?.name).toBe('Guitar');
    });
  });
});
