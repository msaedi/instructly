import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useInstructorSearch } from '../useInstructorSearch';
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

describe('useInstructorSearch', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('runs natural language search with trimmed query', async () => {
    searchWithNaturalLanguageMock.mockResolvedValue({
      status: 200,
      data: { results: [], meta: { total_results: 0 } },
    });

    const { result } = renderHook(
      () => useInstructorSearch({ searchQuery: '  piano lessons  ' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(searchWithNaturalLanguageMock).toHaveBeenCalledWith('piano lessons', {});
    expect(result.current.data?.mode).toBe('nl');
  });

  it('forwards skill level and subcategory context to NL search', async () => {
    searchWithNaturalLanguageMock.mockResolvedValue({
      status: 200,
      data: { results: [], meta: { total_results: 0 } },
    });

    const { result } = renderHook(
      () =>
        useInstructorSearch({
          searchQuery: 'piano',
          skillLevelCsv: 'beginner,advanced',
          subcategoryId: 'subcat-1',
        }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(searchWithNaturalLanguageMock).toHaveBeenCalledWith('piano', {
      skill_level: 'beginner,advanced',
      subcategory_id: 'subcat-1',
    });
  });

  it('surfaces rate limit metadata on NL search', async () => {
    searchWithNaturalLanguageMock.mockResolvedValue({
      status: 429,
      error: 'Rate limited',
      retryAfterSeconds: 12,
    });

    const { result } = renderHook(
      () => useInstructorSearch({ searchQuery: 'piano' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.status).toBe(429);
    expect(result.current.error?.retryAfterSeconds).toBe(12);
  });

  it('runs catalog search and validates payload', async () => {
    const catalogPayload = {
      items: [{ id: 'inst-1' }],
      total: 1,
      page: 2,
      per_page: 10,
      has_next: false,
      has_prev: true,
    };
    searchInstructorsMock.mockResolvedValue({
      status: 200,
      data: catalogPayload,
    });
    validateWithZodMock.mockResolvedValue(catalogPayload);

    const { result } = renderHook(
      () => useInstructorSearch({ serviceCatalogId: 'svc-1', page: 2, perPage: 10 }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(searchInstructorsMock).toHaveBeenCalledWith({
      service_catalog_id: 'svc-1',
      page: 2,
      per_page: 10,
    });
    expect(validateWithZodMock).toHaveBeenCalled();
    expect(result.current.data?.mode).toBe('catalog');
  });

  it('forwards skill level and subcategory context to catalog search', async () => {
    const catalogPayload = {
      items: [{ id: 'inst-1' }],
      total: 1,
      page: 1,
      per_page: 20,
      has_next: false,
      has_prev: false,
    };
    searchInstructorsMock.mockResolvedValue({
      status: 200,
      data: catalogPayload,
    });
    validateWithZodMock.mockResolvedValue(catalogPayload);

    const { result } = renderHook(
      () =>
        useInstructorSearch({
          serviceCatalogId: 'svc-1',
          skillLevelCsv: 'intermediate',
          subcategoryId: 'subcat-1',
        }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(searchInstructorsMock).toHaveBeenCalledWith({
      service_catalog_id: 'svc-1',
      skill_level: 'intermediate',
      subcategory_id: 'subcat-1',
      page: 1,
      per_page: 20,
    });
  });

  it('does not run when no search criteria provided', async () => {
    const { result } = renderHook(() => useInstructorSearch({}), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isFetching).toBe(false));
    expect(searchWithNaturalLanguageMock).not.toHaveBeenCalled();
    expect(searchInstructorsMock).not.toHaveBeenCalled();
  });

  it('returns an error when catalog search fails', async () => {
    searchInstructorsMock.mockResolvedValue({
      status: 500,
      error: 'Server error',
    });

    const { result } = renderHook(
      () => useInstructorSearch({ serviceCatalogId: 'svc-1' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.status).toBe(500);
  });

  it('throws when NL search response has no data', async () => {
    searchWithNaturalLanguageMock.mockResolvedValue({
      status: 200,
      data: null,
    });

    const { result } = renderHook(
      () => useInstructorSearch({ searchQuery: 'piano' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('No data in response');
  });

  it('throws when NL search returns an error message', async () => {
    searchWithNaturalLanguageMock.mockResolvedValue({
      status: 400,
      error: 'Bad query format',
    });

    const { result } = renderHook(
      () => useInstructorSearch({ searchQuery: 'invalid<<>>' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Bad query format');
    expect(result.current.error?.status).toBe(400);
  });

  it('surfaces rate limit metadata on catalog search', async () => {
    searchInstructorsMock.mockResolvedValue({
      status: 429,
      error: 'Rate limited',
      retryAfterSeconds: 30,
    });

    const { result } = renderHook(
      () => useInstructorSearch({ serviceCatalogId: 'svc-1' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.status).toBe(429);
    expect(result.current.error?.retryAfterSeconds).toBe(30);
  });

  it('throws when catalog search response has no data', async () => {
    searchInstructorsMock.mockResolvedValue({
      status: 200,
      data: null,
    });

    const { result } = renderHook(
      () => useInstructorSearch({ serviceCatalogId: 'svc-1' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('No data in response');
  });

  it('uses default error message for rate limit without custom message', async () => {
    searchWithNaturalLanguageMock.mockResolvedValue({
      status: 429,
      // No error message provided, should use default
      retryAfterSeconds: 5,
    });

    const { result } = renderHook(
      () => useInstructorSearch({ searchQuery: 'piano' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Our hamsters are sprinting. Please try again shortly.');
  });

  it('uses default error message for catalog rate limit without custom message', async () => {
    searchInstructorsMock.mockResolvedValue({
      status: 429,
      // No error message provided, should use default
      retryAfterSeconds: 10,
    });

    const { result } = renderHook(
      () => useInstructorSearch({ serviceCatalogId: 'svc-1' }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Our hamsters are sprinting. Please try again shortly.');
    expect(result.current.error?.retryAfterSeconds).toBe(10);
  });
});
