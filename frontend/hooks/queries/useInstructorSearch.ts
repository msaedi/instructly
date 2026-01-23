import { useQuery } from '@tanstack/react-query';

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
  page?: number;
  perPage?: number;
  enabled?: boolean;
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
      page,
      per_page: perPage,
    }),
    enabled: queryEnabled,
    staleTime: CACHE_TIMES.FAST * 2, // 2 minutes
    queryFn: async () => {
      if (hasSearchQuery) {
        const response = await publicApi.searchWithNaturalLanguage(trimmedQuery);
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

      throw toSearchError('Missing search criteria');
    },
  });
}
