import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useInstructorSearchInfinite } from '../useInstructorSearch';
import { publicApi } from '@/features/shared/api/client';
import { validateWithZod } from '@/features/shared/api/validation';

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    searchWithNaturalLanguage: jest.fn(),
    searchInstructors: jest.fn(),
  },
}));

jest.mock('@/features/shared/api/validation', () => ({
  validateWithZod: jest.fn(),
}));

jest.mock('@/features/shared/api/schemas/searchList', () => ({
  loadSearchListSchema: {},
}));

const searchWithNaturalLanguageMock = publicApi.searchWithNaturalLanguage as jest.Mock;
const searchInstructorsMock = publicApi.searchInstructors as jest.Mock;
const validateWithZodMock = validateWithZod as jest.Mock;

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

describe('useInstructorSearchInfinite', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('runs catalog search and reports next page when available', async () => {
    const payload = {
      items: [{ id: 'inst-1' }],
      total: 2,
      page: 1,
      per_page: 20,
      has_next: true,
      has_prev: false,
    };

    searchInstructorsMock.mockResolvedValue({ status: 200, data: payload });
    validateWithZodMock.mockResolvedValue(payload);

    const { result } = renderHook(
      () => useInstructorSearchInfinite({ serviceCatalogId: 'svc-1' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(searchInstructorsMock).toHaveBeenCalled();
    expect(result.current.hasNextPage).toBe(true);
  });

  it('does not report next page when catalog has_next is false', async () => {
    const payload = {
      items: [{ id: 'inst-2' }],
      total: 1,
      page: 1,
      per_page: 20,
      has_next: false,
      has_prev: false,
    };

    searchInstructorsMock.mockResolvedValue({ status: 200, data: payload });
    validateWithZodMock.mockResolvedValue(payload);

    const { result } = renderHook(
      () => useInstructorSearchInfinite({ serviceCatalogId: 'svc-2' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.hasNextPage).toBe(false);
  });

  it('runs natural language search without pagination', async () => {
    searchWithNaturalLanguageMock.mockResolvedValue({
      status: 200,
      data: { results: [], meta: { total_results: 0 } },
    });

    const { result } = renderHook(
      () => useInstructorSearchInfinite({ searchQuery: 'piano' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(searchWithNaturalLanguageMock).toHaveBeenCalledWith('piano', {});
    expect(result.current.hasNextPage).toBe(false);
  });

  it('passes taxonomy params through infinite catalog search', async () => {
    const payload = {
      items: [{ id: 'inst-3' }],
      total: 1,
      page: 1,
      per_page: 20,
      has_next: false,
      has_prev: false,
    };
    searchInstructorsMock.mockResolvedValue({ status: 200, data: payload });
    validateWithZodMock.mockResolvedValue(payload);

    const { result } = renderHook(
      () =>
        useInstructorSearchInfinite({
          serviceCatalogId: 'svc-3',
          skillLevelCsv: 'advanced',
          subcategoryId: 'subcat-22',
          contentFiltersParam: 'goal:enrichment',
        }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(searchInstructorsMock).toHaveBeenCalledWith({
      service_catalog_id: 'svc-3',
      skill_level: 'advanced',
      subcategory_id: 'subcat-22',
      content_filters: 'goal:enrichment',
      page: 1,
      per_page: 20,
    });
  });
});
