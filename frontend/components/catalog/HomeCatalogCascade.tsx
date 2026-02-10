'use client';

import { type ComponentType, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  BookOpen,
  Disc3,
  Globe,
  Dumbbell,
  Music,
  Palette,
  Sparkles,
  Trophy,
} from 'lucide-react';

import type { CategoryServiceDetail } from '@/features/shared/api/types';
import { useAllServicesWithInstructors, useServiceCategories } from '@/hooks/queries/useServices';
import { useSubcategoriesByCategory } from '@/hooks/queries/useTaxonomy';
import { logger } from '@/lib/logger';
import { recordSearch } from '@/lib/searchTracking';
import { CURRENT_AUDIENCE, type AudienceMode } from '@/lib/audience';
import { SearchType } from '@/types/enums';

type IconComponent = ComponentType<{
  size?: number;
  strokeWidth?: number;
  className?: string;
}>;

type CategoryPill = {
  icon: IconComponent;
  id: string;
  name: string;
  subtitle: string;
};

type FilteredSubcategory = {
  id: string;
  name: string;
  services: CategoryServiceDetail[];
};

const ICON_MAP: Record<string, IconComponent> = {
  palette: Palette,
  dumbbell: Dumbbell,
  disc: Disc3,
  trophy: Trophy,
  'book-open': BookOpen,
  globe: Globe,
  music: Music,
  sparkles: Sparkles,
  lightbulb: Sparkles,
};

const FALLBACK_CATEGORIES: CategoryPill[] = [
  {
    icon: BookOpen,
    id: 'fallback-tutoring',
    name: 'Tutoring & Test Prep',
    subtitle: 'SAT prep, math tutoring & more',
  },
  {
    icon: Music,
    id: 'fallback-music',
    name: 'Music',
    subtitle: 'Piano, guitar, voice & more',
  },
  {
    icon: Sparkles,
    id: 'fallback-dance',
    name: 'Dance',
    subtitle: 'Ballet, hip-hop, salsa & more',
  },
  {
    icon: Globe,
    id: 'fallback-languages',
    name: 'Languages',
    subtitle: 'Spanish, French & more',
  },
  {
    icon: Dumbbell,
    id: 'fallback-sports',
    name: 'Sports & Fitness',
    subtitle: 'Tennis, swimming & more',
  },
  {
    icon: Palette,
    id: 'fallback-arts',
    name: 'Arts',
    subtitle: 'Drawing, painting & more',
  },
  {
    icon: Sparkles,
    id: 'fallback-hobbies',
    name: 'Hobbies & Life Skills',
    subtitle: 'Cooking, gardening & more',
  },
];

function hasInstructorSupply(service: CategoryServiceDetail): boolean {
  const count =
    typeof service.instructor_count === 'number'
      ? service.instructor_count
      : typeof service.active_instructors === 'number'
        ? service.active_instructors
        : 0;

  return count > 0;
}

function isEligibleForAudience(service: CategoryServiceDetail, audience: AudienceMode): boolean {
  const rawGroups = Array.isArray(service.eligible_age_groups)
    ? service.eligible_age_groups
    : [];

  if (rawGroups.length === 0) {
    return false;
  }

  const normalized = rawGroups.map((group) => group.toLowerCase());
  return normalized.includes(audience);
}

function sortServices(services: CategoryServiceDetail[]): CategoryServiceDetail[] {
  return [...services].sort((a, b) => {
    const orderA = a.display_order ?? Number.MAX_SAFE_INTEGER;
    const orderB = b.display_order ?? Number.MAX_SAFE_INTEGER;
    if (orderA !== orderB) {
      return orderA - orderB;
    }
    return a.name.localeCompare(b.name);
  });
}

function toId(value: unknown): string {
  return typeof value === 'string' ? value : String(value ?? '');
}

export function HomeCatalogCascade({ isAuthenticated }: { isAuthenticated: boolean }) {
  const router = useRouter();

  const [selectedCategory, setSelectedCategory] = useState<string>(() => {
    if (typeof window === 'undefined') {
      return '';
    }
    return sessionStorage.getItem('homeSelectedCategory') ?? '';
  });
  const [selectedSubcategory, setSelectedSubcategory] = useState<string>('');

  const { data: categoriesData, isError: categoriesError } = useServiceCategories();
  const { data: servicesData, isError: servicesError } = useAllServicesWithInstructors();

  useEffect(() => {
    if (categoriesError || servicesError) {
      logger.warn('categories_fetch_failed', { categoriesError, servicesError });
    }
  }, [categoriesError, servicesError]);

  const filteredServicesByCategory = useMemo(() => {
    const next = new Map<string, CategoryServiceDetail[]>();

    (servicesData?.categories ?? []).forEach((category) => {
      const categoryId = toId(category.id);
      if (!categoryId) {
        return;
      }

      const filtered = sortServices(
        (category.services ?? []).filter(
          (service) =>
            hasInstructorSupply(service) &&
            isEligibleForAudience(service, CURRENT_AUDIENCE)
        )
      );

      if (filtered.length > 0) {
        next.set(categoryId, filtered);
      }
    });

    return next;
  }, [servicesData]);

  const categories = useMemo<CategoryPill[]>(() => {
    const fromCategoriesApi = (categoriesData ?? [])
      .slice()
      .sort((a, b) => (a.display_order ?? 999) - (b.display_order ?? 999))
      .map((category) => ({
        icon: ICON_MAP[category.icon_name ?? ''] || Sparkles,
        id: toId(category.id),
        name: category.name,
        subtitle: category.subtitle ?? '',
      }));

    const fromServicesApi = (servicesData?.categories ?? []).map((category) => ({
      icon: ICON_MAP[category.icon_name ?? ''] || Sparkles,
      id: toId(category.id),
      name: category.name,
      subtitle: category.subtitle ?? '',
    }));

    const usingFallback =
      fromCategoriesApi.length === 0 && fromServicesApi.length === 0;

    const base = fromCategoriesApi.length > 0
      ? fromCategoriesApi
      : fromServicesApi.length > 0
        ? fromServicesApi
        : FALLBACK_CATEGORIES;

    if (usingFallback && (categoriesError || servicesError)) {
      logger.warn('Using fallback categories due to API failure');
    }

    if ((servicesData?.categories ?? []).length === 0) {
      return base;
    }

    return base.filter((category) => filteredServicesByCategory.has(category.id));
  }, [categoriesData, servicesData, filteredServicesByCategory, categoriesError, servicesError]);

  const selectedCategoryIsValid =
    selectedCategory !== '' && categories.some((category) => category.id === selectedCategory);
  const activeCategory = selectedCategoryIsValid
    ? selectedCategory
    : categories[0]?.id ?? '';
  const selectedCategoryForSubcategories = filteredServicesByCategory.has(activeCategory)
    ? activeCategory
    : '';
  const { data: subcategoriesData } = useSubcategoriesByCategory(selectedCategoryForSubcategories);

  const filteredSubcategories = useMemo<FilteredSubcategory[]>(() => {
    if (!selectedCategoryForSubcategories) {
      return [];
    }

    const services = filteredServicesByCategory.get(selectedCategoryForSubcategories) ?? [];
    const grouped = new Map<string, CategoryServiceDetail[]>();

    services.forEach((service) => {
      const subcategoryId = toId(service.subcategory_id);
      if (!subcategoryId) {
        return;
      }
      if (!grouped.has(subcategoryId)) {
        grouped.set(subcategoryId, []);
      }
      grouped.get(subcategoryId)?.push(service);
    });

    const next: FilteredSubcategory[] = [];
    const seen = new Set<string>();

    (subcategoriesData ?? []).forEach((subcategory) => {
      const subcategoryServices = grouped.get(subcategory.id) ?? [];
      if (subcategoryServices.length === 0) {
        return;
      }

      next.push({
        id: subcategory.id,
        name: subcategory.name,
        services: sortServices(subcategoryServices),
      });
      seen.add(subcategory.id);
    });

    grouped.forEach((subcategoryServices, subcategoryId) => {
      if (seen.has(subcategoryId) || subcategoryServices.length === 0) {
        return;
      }

      logger.warn('HomeCatalogCascade: orphaned subcategory not found in API data', {
        subcategoryId,
        serviceCount: subcategoryServices.length,
      });
      next.push({
        id: subcategoryId,
        name: 'Other',
        services: sortServices(subcategoryServices),
      });
    });

    return next;
  }, [filteredServicesByCategory, selectedCategoryForSubcategories, subcategoriesData]);

  const activeSelectedSubcategory = filteredSubcategories.some(
    (subcategory) => subcategory.id === selectedSubcategory
  )
    ? selectedSubcategory
    : '';

  const selectedSubcategoryData = filteredSubcategories.find(
    (subcategory) => subcategory.id === activeSelectedSubcategory
  );

  const servicePills = selectedSubcategoryData?.services ?? [];

  const persistNavContext = (categoryId: string) => {
    if (typeof window === 'undefined') {
      return;
    }

    sessionStorage.setItem('navigationFrom', '/');
    if (categoryId) {
      sessionStorage.setItem('homeSelectedCategory', categoryId);
      return;
    }

    sessionStorage.removeItem('homeSelectedCategory');
  };

  const buildSearchHref = (service: CategoryServiceDetail): string => {
    const params = new URLSearchParams({
      service_catalog_id: toId(service.id),
      service_name: service.name,
      audience: CURRENT_AUDIENCE,
      from: 'home',
    });

    const subcategoryId = toId(service.subcategory_id);
    if (subcategoryId) {
      params.set('subcategory_id', subcategoryId);
    }

    return `/search?${params.toString()}`;
  };

  const navigateToService = (service: CategoryServiceDetail) => {
    persistNavContext(activeCategory);
    router.push(buildSearchHref(service));
  };

  const handleCategoryClick = async (categoryId: string, categoryName: string) => {
    setSelectedCategory(categoryId);
    setSelectedSubcategory('');

    persistNavContext(categoryId);

    await recordSearch(
      {
        query: `${categoryName} lessons`,
        search_type: SearchType.CATEGORY,
        results_count: null,
      },
      isAuthenticated
    );
  };

  const handleSubcategoryClick = (subcategory: FilteredSubcategory) => {
    if (subcategory.services.length === 1) {
      const singletonService = subcategory.services[0];
      if (singletonService) {
        navigateToService(singletonService);
      }
      return;
    }

    setSelectedSubcategory(subcategory.id);
  };

  const moreHref = `/services?audience=${encodeURIComponent(CURRENT_AUDIENCE)}`;

  return (
    <>
      <section className="py-2 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-2xl mx-auto">
          <div className="flex justify-center items-start space-x-10 ml-15">
            {categories.map((category) => {
              const IconComponent = category.icon;
              const categoryId = toId(category.id);
              const isSelected = categoryId === activeCategory;
              const isFallback = categoryId.startsWith('fallback-');

              return (
                <button
                  type="button"
                  key={categoryId}
                  disabled={isFallback}
                  onClick={isFallback ? undefined : () => {
                    void handleCategoryClick(categoryId, category.name);
                  }}
                  className={`group flex flex-col items-center transition-colors duration-200 relative w-20 select-none ${isFallback ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                >
                  <IconComponent
                    size={32}
                    strokeWidth={1.5}
                    className={`mb-2 transition-colors ${
                      isSelected
                        ? 'text-gray-900 dark:text-gray-100'
                        : 'text-gray-500 group-hover:text-gray-900 dark:group-hover:text-gray-100'
                    }`}
                  />
                  <p
                    className={`text-sm font-medium mb-1 transition-colors whitespace-nowrap ${
                      isSelected
                        ? 'text-gray-900 dark:text-gray-100'
                        : 'text-gray-500 group-hover:text-gray-900 dark:group-hover:text-gray-100'
                    }`}
                  >
                    {category.name}
                  </p>
                  {isSelected && (
                    <div className="absolute -bottom-3 left-1/2 transform -translate-x-1/2 w-16 h-1 bg-[#FFD700] rounded-full" />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </section>

      <section className="py-6 bg-transparent dark:bg-transparent">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex flex-wrap justify-center gap-2 min-h-[48px] items-center">
            {!activeCategory ? (
              <p className="text-sm text-gray-500 dark:text-gray-400 italic">
                Select a category to browse subcategories
              </p>
            ) : filteredSubcategories.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400 italic">No services available in this category</p>
            ) : (
              <>
                {filteredSubcategories.map((subcategory, index) => (
                  <button
                    type="button"
                    key={subcategory.id}
                    onClick={() => handleSubcategoryClick(subcategory)}
                    className="group relative px-4 py-2 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-full text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600 hover:border-gray-300 dark:hover:border-gray-500 hover:text-gray-900 dark:hover:text-white transition-all duration-200 cursor-pointer animate-fade-in-up"
                    style={{
                      animationDelay: `${index * 50}ms`,
                      animationFillMode: 'both',
                    }}
                  >
                    {subcategory.name}
                    {subcategory.services.length > 1 && (
                      <span className="ml-1 text-xs text-gray-500 dark:text-gray-400">
                        ({subcategory.services.length})
                      </span>
                    )}
                    <span className="absolute inset-0 rounded-full border-2 border-transparent group-hover:border-[#FFD700] transition-all duration-200 opacity-0 group-hover:opacity-100" />
                  </button>
                ))}
              </>
            )}

            <Link
              key={`more-${activeCategory || 'all'}`}
              href={moreHref}
              onClick={() => {
                if (typeof window !== 'undefined') {
                  sessionStorage.setItem('navigationFrom', '/');
                  if (activeCategory) {
                    sessionStorage.setItem('homeSelectedCategory', activeCategory);
                  }
                }
              }}
              className="group relative px-4 py-2 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-full text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600 hover:border-gray-300 dark:hover:border-gray-500 hover:text-gray-900 dark:hover:text-white transition-all duration-200 cursor-pointer animate-fade-in-up"
              style={{ animationFillMode: 'both' }}
            >
              •••
              <span className="absolute inset-0 rounded-full border-2 border-transparent group-hover:border-[#FFD700] transition-all duration-200 opacity-0 group-hover:opacity-100" />
            </Link>
          </div>

          {selectedSubcategoryData && servicePills.length > 1 && (
            <div className="mt-3 flex flex-wrap justify-center gap-2 min-h-[40px] items-center">
              {servicePills.map((service, index) => (
                <Link
                  key={service.id}
                  href={buildSearchHref(service)}
                  onClick={() => {
                    persistNavContext(activeCategory);
                    logger.debug('Set navigation source from homepage', {
                      navigationFrom: '/',
                      serviceId: service.id,
                      audience: CURRENT_AUDIENCE,
                    });
                  }}
                  className="group relative px-4 py-2 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-full text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600 hover:border-gray-300 dark:hover:border-gray-500 hover:text-gray-900 dark:hover:text-white transition-all duration-200 cursor-pointer animate-fade-in-up"
                  style={{
                    animationDelay: `${index * 50}ms`,
                    animationFillMode: 'both',
                  }}
                >
                  {service.name}
                  <span className="absolute inset-0 rounded-full border-2 border-transparent group-hover:border-[#FFD700] transition-all duration-200 opacity-0 group-hover:opacity-100" />
                </Link>
              ))}
            </div>
          )}
        </div>
      </section>
    </>
  );
}
