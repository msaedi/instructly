import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { convertApiResponse } from '@/lib/react-query/api';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { publicApi, protectedApi } from '@/features/shared/api/client';
import { logger } from '@/lib/logger';
import type {
  CategorySummary,
  CategoryDetail,
  SubcategoryDetail,
  ServiceCatalogDetail,
  ServiceCatalogSummary,
  SubcategoryFilterResponse,
  FilterValidationResponse,
  ValidateFiltersRequest,
} from '@/features/shared/api/types';

/**
 * Slug-based catalog browse hooks.
 *
 * These hooks consume the `/api/v1/catalog/*` endpoints
 * for public taxonomy navigation using URL slugs.
 */

/**
 * All active categories with subcategory counts — for homepage grid.
 */
export function useCatalogCategories() {
  return useQuery<CategorySummary[]>({
    queryKey: queryKeys.catalog.categories,
    queryFn: async () => {
      const response = await publicApi.listCatalogCategories();
      return convertApiResponse(response);
    },
    staleTime: CACHE_TIMES.STATIC, // 1 hour — categories rarely change
    gcTime: CACHE_TIMES.STATIC * 2,
  });
}

/**
 * Category detail by slug — with subcategory listing.
 */
export function useCatalogCategory(slug: string) {
  return useQuery<CategoryDetail>({
    queryKey: queryKeys.catalog.category(slug),
    queryFn: async () => {
      const response = await publicApi.getCatalogCategory(slug);
      return convertApiResponse(response);
    },
    enabled: !!slug,
    staleTime: CACHE_TIMES.STATIC,
    gcTime: CACHE_TIMES.STATIC * 2,
  });
}

/**
 * Subcategory detail by two-slug URL — with services and filters.
 */
export function useCatalogSubcategory(categorySlug: string, subcategorySlug: string) {
  return useQuery<SubcategoryDetail>({
    queryKey: queryKeys.catalog.subcategory(categorySlug, subcategorySlug),
    queryFn: async () => {
      const response = await publicApi.getCatalogSubcategory(categorySlug, subcategorySlug);
      return convertApiResponse(response);
    },
    enabled: !!categorySlug && !!subcategorySlug,
    staleTime: CACHE_TIMES.STATIC,
    gcTime: CACHE_TIMES.STATIC * 2,
  });
}

/**
 * Single service detail by ID.
 */
export function useCatalogService(serviceId: string) {
  return useQuery<ServiceCatalogDetail>({
    queryKey: queryKeys.catalog.service(serviceId),
    queryFn: async () => {
      const response = await publicApi.getCatalogService(serviceId);
      return convertApiResponse(response);
    },
    enabled: !!serviceId,
    staleTime: CACHE_TIMES.STATIC,
    gcTime: CACHE_TIMES.STATIC * 2,
  });
}

/**
 * Services list for a subcategory by ID.
 */
export function useCatalogSubcategoryServices(subcategoryId: string) {
  return useQuery<ServiceCatalogSummary[]>({
    queryKey: queryKeys.catalog.subcategoryServices(subcategoryId),
    queryFn: async () => {
      const response = await publicApi.listCatalogSubcategoryServices(subcategoryId);
      return convertApiResponse(response);
    },
    enabled: !!subcategoryId,
    staleTime: CACHE_TIMES.STATIC,
    gcTime: CACHE_TIMES.STATIC * 2,
  });
}

/**
 * Filter definitions for a subcategory by ID.
 */
export function useCatalogSubcategoryFilters(subcategoryId: string) {
  return useQuery<SubcategoryFilterResponse[]>({
    queryKey: queryKeys.catalog.subcategoryFilters(subcategoryId),
    queryFn: async () => {
      const response = await publicApi.getCatalogSubcategoryFilters(subcategoryId);
      return convertApiResponse(response);
    },
    enabled: !!subcategoryId,
    staleTime: CACHE_TIMES.STATIC,
    gcTime: CACHE_TIMES.STATIC * 2,
  });
}

// ── Mutations ──────────────────────────────────────────────────

/**
 * Update filter selections on an instructor service.
 * Invalidates instructor service queries on success.
 */
export function useUpdateFilterSelections() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      instructorServiceId,
      filterSelections,
    }: {
      instructorServiceId: string;
      filterSelections: Record<string, string[]>;
    }) => {
      const response = await protectedApi.updateFilterSelections(instructorServiceId, {
        filter_selections: filterSelections,
      });
      return convertApiResponse(response);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['instructor', 'services'] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.taxonomy.all });
    },
    onError: (error: Error) => {
      logger.error('filter_selections_update_failed', error);
    },
  });
}

/**
 * Validate filter selections for a catalog service.
 * Returns { valid: boolean; errors: string[] }.
 */
export function useValidateFilters() {
  return useMutation<FilterValidationResponse, Error, ValidateFiltersRequest>({
    mutationFn: async (data) => {
      const response = await protectedApi.validateFilterSelections(data);
      return convertApiResponse(response);
    },
    onError: (error: Error) => {
      logger.error('filter_validation_failed', error);
    },
  });
}
