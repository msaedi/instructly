import { useInfiniteQuery, useQuery } from '@tanstack/react-query';

import { publicApi, type NaturalLanguageSearchResponse } from '@/features/shared/api/client';
import { validateWithZod } from '@/features/shared/api/validation';
import { loadSearchListSchema } from '@/features/shared/api/schemas/searchList';
import { CACHE_TIMES, queryKeys } from '@/lib/react-query/queryClient';

type CatalogSearchResponse = {
  items: unknown[];
  total: number;
  page: number;
  per_page: number;
  has_next: boolean;
  has_prev: boolean;
};

export type InstructorSearchResult =
  | { mode: 'nl'; data: NaturalLanguageSearchResponse }
  | { mode: 'catalog'; data: CatalogSearchResponse };

export type InstructorSearchError = Error & {
  status?: number;
  retryAfterSeconds?: number;
};

export type InstructorSearchParams = {
  searchQuery?: string;
  serviceCatalogId?: string;
  skillLevelCsv?: string;
  subcategoryId?: string;
  contentFiltersParam?: string;
  page?: number;
  perPage?: number;
  enabled?: boolean;
};

type InstructorSearchFetchParams = {
  trimmedQuery: string;
  serviceCatalogId: string;
  page: number;
  perPage: number;
  skillLevelCsv?: string;
  subcategoryId?: string;
  contentFiltersParam?: string;
  hasSearchQuery: boolean;
  hasCatalogId: boolean;
};

const toSearchError = (
  message: string,
  status?: number,
  retryAfterSeconds?: number
): InstructorSearchError => {
  const error = new Error(message) as InstructorSearchError;
  if (typeof status === 'number') {
    error.status = status;
  }
  if (typeof retryAfterSeconds === 'number') {
    error.retryAfterSeconds = retryAfterSeconds;
  }
  return error;
};

export function useInstructorSearch(params: InstructorSearchParams) {
  const {
    searchQuery = '',
    serviceCatalogId = '',
    skillLevelCsv,
    subcategoryId,
    contentFiltersParam,
    page = 1,
    perPage = 20,
    enabled = true,
  } = params;

  const trimmedQuery = searchQuery.trim();
  const hasSearchQuery = trimmedQuery.length > 0;
  const hasCatalogId = Boolean(serviceCatalogId);
  const queryEnabled = enabled && (hasSearchQuery || hasCatalogId);

  return useQuery<InstructorSearchResult, InstructorSearchError>({
    queryKey: queryKeys.instructors.search({
      query: trimmedQuery || undefined,
      service_catalog_id: serviceCatalogId || undefined,
      skill_level: skillLevelCsv || undefined,
      subcategory_id: subcategoryId || undefined,
      content_filters: contentFiltersParam || undefined,
      page,
      per_page: perPage,
    }),
    enabled: queryEnabled,
    staleTime: CACHE_TIMES.FAST * 2, // 2 minutes
    queryFn: () =>
      fetchInstructorSearch({
        trimmedQuery,
        serviceCatalogId,
        page,
        perPage,
        ...(skillLevelCsv ? { skillLevelCsv } : {}),
        ...(subcategoryId ? { subcategoryId } : {}),
        ...(contentFiltersParam ? { contentFiltersParam } : {}),
        hasSearchQuery,
        hasCatalogId,
      }),
  });
}

export function useInstructorSearchInfinite(params: InstructorSearchParams) {
  const {
    searchQuery = '',
    serviceCatalogId = '',
    skillLevelCsv,
    subcategoryId,
    contentFiltersParam,
    perPage = 20,
    enabled = true,
  } = params;

  const trimmedQuery = searchQuery.trim();
  const hasSearchQuery = trimmedQuery.length > 0;
  const hasCatalogId = Boolean(serviceCatalogId);
  const queryEnabled = enabled && (hasSearchQuery || hasCatalogId);

  return useInfiniteQuery<InstructorSearchResult, InstructorSearchError>({
    queryKey: queryKeys.instructors.search({
      query: trimmedQuery || undefined,
      service_catalog_id: serviceCatalogId || undefined,
      skill_level: skillLevelCsv || undefined,
      subcategory_id: subcategoryId || undefined,
      content_filters: contentFiltersParam || undefined,
      per_page: perPage,
    }),
    enabled: queryEnabled,
    staleTime: CACHE_TIMES.FAST * 2, // 2 minutes
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      fetchInstructorSearch({
        trimmedQuery,
        serviceCatalogId,
        page: typeof pageParam === 'number' ? pageParam : 1,
        perPage,
        ...(skillLevelCsv ? { skillLevelCsv } : {}),
        ...(subcategoryId ? { subcategoryId } : {}),
        ...(contentFiltersParam ? { contentFiltersParam } : {}),
        hasSearchQuery,
        hasCatalogId,
      }),
    getNextPageParam: (lastPage) => {
      if (lastPage.mode !== 'catalog') return undefined;
      if (!lastPage.data.has_next) return undefined;
      const currentPage = Number.isFinite(lastPage.data.page) ? lastPage.data.page : 1;
      return currentPage + 1;
    },
  });
}

const fetchInstructorSearch = async (
  params: InstructorSearchFetchParams
): Promise<InstructorSearchResult> => {
  const {
    trimmedQuery,
    serviceCatalogId,
    page,
    perPage,
    skillLevelCsv,
    subcategoryId,
    contentFiltersParam,
    hasSearchQuery,
    hasCatalogId,
  } = params;

  if (hasSearchQuery) {
    const response = await publicApi.searchWithNaturalLanguage(trimmedQuery, {
      ...(skillLevelCsv ? { skill_level: skillLevelCsv } : {}),
      ...(subcategoryId ? { subcategory_id: subcategoryId } : {}),
      ...(contentFiltersParam ? { content_filters: contentFiltersParam } : {}),
    });
    if (response.status === 429) {
      const secs = (response as { retryAfterSeconds?: number }).retryAfterSeconds;
      throw toSearchError(
        response.error || 'Our hamsters are sprinting. Please try again shortly.',
        response.status,
        secs
      );
    }
    if (response.error) {
      throw toSearchError(response.error, response.status);
    }
    if (!response.data) {
      throw toSearchError('No data in response', response.status);
    }
    return { mode: 'nl', data: response.data };
  }

  if (hasCatalogId) {
    const response = await publicApi.searchInstructors({
      service_catalog_id: serviceCatalogId,
      ...(skillLevelCsv ? { skill_level: skillLevelCsv } : {}),
      ...(subcategoryId ? { subcategory_id: subcategoryId } : {}),
      ...(contentFiltersParam ? { content_filters: contentFiltersParam } : {}),
      page,
      per_page: perPage,
    });

    if (response.status === 429) {
      const secs = (response as { retryAfterSeconds?: number }).retryAfterSeconds;
      throw toSearchError(
        response.error || 'Our hamsters are sprinting. Please try again shortly.',
        response.status,
        secs
      );
    }

    if (response.error) {
      throw toSearchError(response.error, response.status);
    }
    if (!response.data) {
      throw toSearchError('No data in response', response.status);
    }

    const validated = await validateWithZod<CatalogSearchResponse>(
      loadSearchListSchema,
      response.data,
      { endpoint: 'GET /instructors' }
    );

    return { mode: 'catalog', data: validated };
  }

  // Defensive: Should never reach here due to query.enabled check,
  // but guards against future code changes
  throw toSearchError('Missing search criteria');
};
