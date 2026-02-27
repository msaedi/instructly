// frontend/app/(public)/services/page.tsx
'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Search, Music, BookOpen, Disc3, Dumbbell, Globe, Palette, Sparkles, Trophy, type LucideProps } from 'lucide-react';
import type { CategoryServiceDetail, CategoryWithServices as ApiCategoryWithServices } from '@/features/shared/api/types';
import { logger } from '@/lib/logger';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useAllServicesWithInstructors } from '@/hooks/queries/useServices';
import { useCategoriesWithSubcategories } from '@/hooks/queries/useTaxonomy';
import { CURRENT_AUDIENCE, type AudienceMode } from '@/lib/audience';

// Progressive loading configuration
const INITIAL_SERVICES_COUNT = 15;
const LOAD_MORE_COUNT = 10;

// Map icon_name from backend to Lucide icon components
const ICON_BY_NAME: Record<string, React.ForwardRefExoticComponent<Omit<LucideProps, "ref"> & React.RefAttributes<SVGSVGElement>>> = {
  'music': Music,
  'book-open': BookOpen,
  'disc': Disc3,
  'dumbbell': Dumbbell,
  'globe': Globe,
  'palette': Palette,
  'sparkles': Sparkles,
  'trophy': Trophy,
  'lightbulb': Sparkles,
};

interface CategoryWithServices {
  id: string;
  name: string;
  icon: React.ForwardRefExoticComponent<Omit<LucideProps, "ref"> & React.RefAttributes<SVGSVGElement>>;
  services: CategoryServiceDetail[];
  subcategories: {
    id: string;
    name: string;
    services: CategoryServiceDetail[];
  }[];
}

const VALID_AUDIENCE_MODES: AudienceMode[] = ['toddler', 'kids', 'teens', 'adults'];

function normalizeAudienceMode(value: string | null): AudienceMode {
  if (!value) {
    return CURRENT_AUDIENCE;
  }
  const normalized = value.toLowerCase();
  return VALID_AUDIENCE_MODES.includes(normalized as AudienceMode)
    ? (normalized as AudienceMode)
    : CURRENT_AUDIENCE;
}

function isEligibleForAudience(service: CategoryServiceDetail, audience: AudienceMode): boolean {
  const groups = Array.isArray(service.eligible_age_groups) ? service.eligible_age_groups : [];
  if (groups.length === 0) {
    return false;
  }
  return groups.map((group) => group.toLowerCase()).includes(audience);
}

function hasActiveInstructors(service: CategoryServiceDetail): boolean {
  return (service.active_instructors ?? 0) > 0;
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

export default function AllServicesPage() {
  // Add custom CSS for 6-column grid
  const customGridStyle = `
    @media (min-width: 1400px) and (max-width: 1535px) {
      .services-grid {
        grid-template-columns: repeat(6, minmax(0, 1fr));
      }
    }
  `;

  const [categoriesWithServices, setCategoriesWithServices] = useState<CategoryWithServices[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [visibleServices, setVisibleServices] = useState<Record<string, number>>({});
  const categoryRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const searchParams = useSearchParams();
  const { /* isAuthenticated */ } = useAuth();

  // Use React Query hook for fetching services (prevents duplicate API calls)
  const {
    data: servicesData,
    error: queryError,
    isLoading: queryLoading,
  } = useAllServicesWithInstructors();
  const { data: taxonomyCategories } = useCategoriesWithSubcategories();

  const activeAudience = normalizeAudienceMode(
    searchParams.get('audience') ?? searchParams.get('age_group')
  );
  const selectedCategoryId = searchParams.get('category_id');
  const subcategoryNameByCategory = useMemo(() => {
    const categoryMap = new Map<string, Map<string, string>>();
    (taxonomyCategories ?? []).forEach((category) => {
      const subMap = new Map<string, string>();
      (category.subcategories ?? []).forEach((subcategory) => {
        subMap.set(subcategory.id, subcategory.name);
      });
      categoryMap.set(category.id, subMap);
    });
    return categoryMap;
  }, [taxonomyCategories]);

  // Sync loading state with React Query
  useEffect(() => {
    setLoading(queryLoading);
  }, [queryLoading]);

  useEffect(() => {
    // Handle React Query error
    if (queryError) {
      logger.error('Failed to fetch services', queryError as Error);
      setError('Failed to load services. Please try again later.');
      setLoading(false);
      return;
    }

    // If React Query has the data, use it (hook extracts .data automatically)
    if (servicesData) {
      const apiCategories: ApiCategoryWithServices[] = servicesData.categories ?? [];
      const categories: CategoryWithServices[] = apiCategories
        .map((category) => {
          const subcategoryNames = subcategoryNameByCategory.get(category.id) ?? new Map<string, string>();
          const services = sortServices(
            (category.services ?? [])
              .filter((service) => isEligibleForAudience(service, activeAudience))
              .map((service) => ({
                ...service,
                description: service.description ?? '',
                search_terms: service.search_terms ?? [],
                is_active: service.is_active ?? true,
                is_trending: service.is_trending ?? false,
                online_capable: service.online_capable ?? false,
                requires_certification: service.requires_certification ?? false,
              }))
          );

          const groupedBySubcategory = new Map<string, CategoryServiceDetail[]>();
          services.forEach((service) => {
            if (!groupedBySubcategory.has(service.subcategory_id)) {
              groupedBySubcategory.set(service.subcategory_id, []);
            }
            groupedBySubcategory.get(service.subcategory_id)?.push(service);
          });

          const subcategories: CategoryWithServices['subcategories'] = [];
          const seenSubcategories = new Set<string>();

          subcategoryNames.forEach((name, subcategoryId) => {
            const groupedServices = groupedBySubcategory.get(subcategoryId) ?? [];
            if (groupedServices.length === 0) {
              return;
            }
            subcategories.push({
              id: subcategoryId,
              name,
              services: groupedServices,
            });
            seenSubcategories.add(subcategoryId);
          });

          groupedBySubcategory.forEach((groupedServices, subcategoryId) => {
            if (groupedServices.length === 0 || seenSubcategories.has(subcategoryId)) {
              return;
            }
            subcategories.push({
              id: subcategoryId,
              name: 'Other',
              services: groupedServices,
            });
          });

          return {
            id: category.id,
            name: category.name.toUpperCase(),
            icon: ICON_BY_NAME[category.icon_name ?? ''] ?? Search,
            services,
            subcategories,
          };
        })
        .filter((category) => category.services.length > 0);

      setCategoriesWithServices(categories);
      setError(null);

      // Initialize visible services count for each category
      const initialVisible: Record<string, number> = {};
      categories.forEach((cat) => {
        initialVisible[cat.id] = INITIAL_SERVICES_COUNT;
      });
      setVisibleServices(initialVisible);

        logger.info('Loaded all services with instructor data', {
          categoriesCount: categories.length,
          totalServices: servicesData.metadata.total_services,
          cached: servicesData.metadata.cached_for_seconds,
          audience: activeAudience,
        });

      setLoading(false);
    }
  }, [activeAudience, queryError, servicesData, subcategoryNameByCategory]);

  const displayCategories = useMemo(() => {
    if (!selectedCategoryId) {
      return categoriesWithServices;
    }

    const filtered = categoriesWithServices.filter((category) => category.id === selectedCategoryId);
    return filtered.length > 0 ? filtered : categoriesWithServices;
  }, [categoriesWithServices, selectedCategoryId]);

  // Set up intersection observer for progressive loading
  useEffect(() => {
    if (loading || displayCategories.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const categoryId = entry.target.getAttribute('data-category');
            if (categoryId) {
              setVisibleServices((prev) => {
                const currentCount = prev[categoryId] || INITIAL_SERVICES_COUNT;
                const category = displayCategories.find((c) => c.id === categoryId);
                const totalServices = category?.services.length || 0;

                if (currentCount < totalServices) {
                  return {
                    ...prev,
                    [categoryId]: Math.min(currentCount + LOAD_MORE_COUNT, totalServices),
                  };
                }
                return prev;
              });
            }
          }
        });
      },
      {
        root: null,
        rootMargin: '100px',
        threshold: 0.1,
      }
    );

    // Observe load more triggers
    Object.entries(categoryRefs.current).forEach(([catId, element]) => {
      if (element) {
        const loadMoreElement = element.querySelector(`[data-load-more="${catId}"]`);
        if (loadMoreElement) {
          observer.observe(loadMoreElement);
        }
      }
    });

    return () => observer.disconnect();
  }, [loading, displayCategories]);

  if (loading) {
    return (
      <div className="min-h-screen bg-white dark:bg-gray-900">
        <div className="flex items-center justify-center h-screen">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-white dark:bg-gray-900">
        <div className="flex items-center justify-center h-screen">
          <div className="text-center">
            <p className="text-red-600 dark:text-red-400 mb-4">{error}</p>
            <Link href="/" className="text-blue-600 dark:text-blue-400 hover:underline">
              Return to homepage
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // Render services for a category
  const renderCategoryServices = (category: CategoryWithServices) => {
    const visibleCount = visibleServices[category.id] || INITIAL_SERVICES_COUNT;
    const hasMore = category.services.length > visibleCount;

    let remaining = visibleCount;
    const visibleSubcategories = category.subcategories
      .map((subcategory) => {
        if (remaining <= 0) {
          return {
            ...subcategory,
            visibleServices: [] as CategoryServiceDetail[],
          };
        }

        const visibleServicesForSubcategory = subcategory.services.slice(0, remaining);
        remaining = Math.max(remaining - visibleServicesForSubcategory.length, 0);

        return {
          ...subcategory,
          visibleServices: visibleServicesForSubcategory,
        };
      })
      .filter((subcategory) => subcategory.visibleServices.length > 0);

    return (
      <div className="space-y-3">
        {visibleSubcategories.map((subcategory) => (
          <div key={subcategory.id} className="space-y-1">
            <h4 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              {subcategory.name}
            </h4>
            <div className="space-y-1">
              {subcategory.visibleServices.map((service) => {
                if (!hasActiveInstructors(service)) {
                  return (
                    <div
                      key={service.id}
                      className="group block text-sm px-2 py-0.5 -mx-2 rounded cursor-not-allowed relative"
                    >
                      <span className="flex text-gray-400 dark:text-gray-600 opacity-60 dark:opacity-50">
                        <span className="flex-shrink-0 mr-1">•</span>
                        <span className="break-words">{service.name}</span>
                      </span>
                      {/* Tooltip on hover */}
                      <div
                        className="absolute left-0 bottom-full mb-2 px-3 py-1 bg-gray-900 text-white text-xs rounded-md opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 pointer-events-none z-50"
                        style={{ whiteSpace: 'nowrap' }}
                      >
                        No instructors available yet - check back soon!
                        {/* Tooltip arrow */}
                        <div className="absolute top-full left-4 w-0 h-0 border-l-4 border-l-transparent border-r-4 border-r-transparent border-t-4 border-t-gray-900"></div>
                      </div>
                    </div>
                  );
                }

                const searchParams = new URLSearchParams({
                  service_catalog_id: service.id,
                  service_name: service.name,
                  audience: activeAudience,
                  from: 'services',
                });
                if (service.subcategory_id) {
                  searchParams.set('subcategory_id', service.subcategory_id);
                }

                return (
                  <Link
                    key={service.id}
                    href={`/search?${searchParams.toString()}`}
                    onClick={async () => {
                      if (typeof window !== 'undefined') {
                        sessionStorage.setItem('navigationFrom', '/services');
                        logger.debug('Set navigation source from services page', {
                          navigationFrom: '/services',
                          serviceId: service.id,
                          audience: activeAudience,
                        });
                      }
                    }}
                    className="group block text-sm text-gray-700 dark:text-gray-300 hover:bg-[#FFD700] hover:!text-gray-900 px-2 py-0.5 -mx-2 rounded transition-all duration-200 cursor-pointer"
                  >
                    <span className="flex">
                      <span className="flex-shrink-0 mr-1">•</span>
                      <span className="break-words">{service.name}</span>
                    </span>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
        {hasMore && (
          <div data-load-more={category.id} data-category={category.id} className="h-4" />
        )}
      </div>
    );
  };

  // Categories are rendered as columns with their services

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: customGridStyle }} />
      <div className="min-h-screen bg-white dark:bg-gray-900">
        {/* Header Section */}
        <header className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
              {/* Logo */}
              <Link href="/" className="text-3xl font-bold text-[#7E22CE] dark:text-purple-400 hover:text-[#7E22CE] transition-colors">
                iNSTAiNSTRU
              </Link>

              {/* Hero Image Placeholder */}
              <div className="w-full lg:w-96 h-32 lg:h-24 bg-gradient-to-r from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
                <span className="text-white text-sm opacity-75">[Hero Image]</span>
              </div>

              {/* Tagline */}
              <div className="flex items-center gap-4">
                <p className="text-lg font-medium text-gray-900 dark:text-gray-100">
                  Your next skill unlocks here
                </p>
                <Search className="h-5 w-5 text-gray-400" />
              </div>
            </div>
          </div>
        </header>

        {/* 7-Column Grid */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="services-grid grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-7 gap-4 items-start">
            {displayCategories.map((category) => (
              <div
                key={category.id}
                ref={(el) => {
                  if (el) categoryRefs.current[category.id] = el;
                }}
                className="flex flex-col min-h-0"
              >
                {/* Category Header */}
                <div className="mb-4">
                  <div className="pb-2 border-b border-gray-200 dark:border-gray-700">
                    <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2 h-6">
                      {React.createElement(category.icon, { className: "h-5 w-5 flex-shrink-0" })}
                      <span className="whitespace-nowrap">{category.name}</span>
                    </h3>
                  </div>
                </div>

                {/* Services List */}
                <div className="flex-1 overflow-visible">{renderCategoryServices(category)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
