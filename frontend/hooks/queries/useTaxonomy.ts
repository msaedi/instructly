import { useQuery } from '@tanstack/react-query';
import { convertApiResponse } from '@/lib/react-query/api';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { publicApi } from '@/features/shared/api/client';
import type {
  AgeGroup,
  CategoryTreeNode,
  CategoryWithSubcategories,
  CatalogService,
  InstructorFilterContext,
  SubcategoryBrief,
  SubcategoryFilterResponse,
  SubcategoryWithServices,
} from '@/features/shared/api/types';

/**
 * 3-level taxonomy React Query hooks
 *
 * These hooks provide cached access to the taxonomy structure:
 * Category → Subcategory → Service, plus flexible filters.
 */

/**
 * Full 3-level category tree — for browse pages and onboarding.
 * Returns all categories, each with subcategories and their services.
 */
export function useCategoriesWithSubcategories() {
  return useQuery<CategoryWithSubcategories[]>({
    queryKey: queryKeys.taxonomy.categoriesWithSubcategories,
    queryFn: async () => {
      const response = await publicApi.getCategoriesWithSubcategories();
      return convertApiResponse(response);
    },
    staleTime: CACHE_TIMES.STATIC, // 1 hour — taxonomy rarely changes
    gcTime: CACHE_TIMES.STATIC * 2,
  });
}

/**
 * Full 3-level tree for a single category (category → subcategories → services).
 * Used for onboarding flows and category detail pages.
 */
export function useCategoryTree(categoryId: string) {
  return useQuery<CategoryTreeNode>({
    queryKey: queryKeys.taxonomy.categoryTree(categoryId),
    queryFn: async () => {
      const response = await publicApi.getCategoryTree(categoryId);
      return convertApiResponse(response);
    },
    enabled: !!categoryId,
    staleTime: CACHE_TIMES.STATIC,
    gcTime: CACHE_TIMES.STATIC * 2,
  });
}

/**
 * Subcategories for a category — lightweight briefs for drill-down navigation.
 */
export function useSubcategoriesByCategory(categoryId: string) {
  return useQuery<SubcategoryBrief[]>({
    queryKey: queryKeys.taxonomy.subcategoriesByCategory(categoryId),
    queryFn: async () => {
      const response = await publicApi.getSubcategoriesByCategory(categoryId);
      return convertApiResponse(response);
    },
    enabled: !!categoryId,
    staleTime: CACHE_TIMES.STATIC,
    gcTime: CACHE_TIMES.STATIC * 2,
  });
}

/**
 * Subcategory with its services — for subcategory detail pages.
 */
export function useSubcategory(subcategoryId: string) {
  return useQuery<SubcategoryWithServices>({
    queryKey: queryKeys.taxonomy.subcategory(subcategoryId),
    queryFn: async () => {
      const response = await publicApi.getSubcategoryWithServices(subcategoryId);
      return convertApiResponse(response);
    },
    enabled: !!subcategoryId,
    staleTime: CACHE_TIMES.STATIC,
    gcTime: CACHE_TIMES.STATIC * 2,
  });
}

/**
 * Available filters for a subcategory — for search sidebar and onboarding.
 */
export function useSubcategoryFilters(subcategoryId: string) {
  return useQuery<SubcategoryFilterResponse[]>({
    queryKey: queryKeys.taxonomy.subcategoryFilters(subcategoryId),
    queryFn: async () => {
      const response = await publicApi.getSubcategoryFilters(subcategoryId);
      return convertApiResponse(response);
    },
    enabled: !!subcategoryId,
    staleTime: CACHE_TIMES.SLOW, // 15 min
    gcTime: CACHE_TIMES.SLOW * 2,
  });
}

/**
 * Services eligible for a specific age group — for age-filtered browsing.
 */
export function useServicesByAgeGroup(ageGroup: AgeGroup) {
  return useQuery<CatalogService[]>({
    queryKey: queryKeys.taxonomy.servicesByAgeGroup(ageGroup),
    queryFn: async () => {
      const response = await publicApi.getServicesByAgeGroup(ageGroup);
      return convertApiResponse(response);
    },
    enabled: !!ageGroup,
    staleTime: CACHE_TIMES.STATIC,
    gcTime: CACHE_TIMES.STATIC * 2,
  });
}

/**
 * Filter context for instructor service editing.
 * Returns available filters and current selections for a service's subcategory.
 */
export function useServiceFilterContext(serviceId: string) {
  return useQuery<InstructorFilterContext>({
    queryKey: queryKeys.taxonomy.filterContext(serviceId),
    queryFn: async () => {
      const response = await publicApi.getServiceFilterContext(serviceId);
      return convertApiResponse(response);
    },
    enabled: !!serviceId,
    staleTime: CACHE_TIMES.FREQUENT, // 5 min — instructor may be editing
    gcTime: CACHE_TIMES.FREQUENT * 2,
  });
}
