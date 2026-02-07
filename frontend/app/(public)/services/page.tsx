// frontend/app/(public)/services/page.tsx
'use client';

import React, { useEffect, useState, useRef } from 'react';
import Link from 'next/link';
import { Search, Music, BookOpen, Dumbbell, Globe, Palette, Sparkles, type LucideProps } from 'lucide-react';
import type { CategoryServiceDetail, CategoryWithServices as ApiCategoryWithServices } from '@/features/shared/api/types';
import { logger } from '@/lib/logger';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useAllServicesWithInstructors } from '@/hooks/queries/useServices';

// Progressive loading configuration
const INITIAL_SERVICES_COUNT = 15;
const LOAD_MORE_COUNT = 10;

// Map icon_name from backend to Lucide icon components
const ICON_BY_NAME: Record<string, React.ForwardRefExoticComponent<Omit<LucideProps, "ref"> & React.RefAttributes<SVGSVGElement>>> = {
  'music': Music,
  'book-open': BookOpen,
  'dumbbell': Dumbbell,
  'globe': Globe,
  'palette': Palette,
  'sparkles': Sparkles,
  'lightbulb': Sparkles,
};

interface CategoryWithServices {
  id: string;
  name: string;
  icon: React.ForwardRefExoticComponent<Omit<LucideProps, "ref"> & React.RefAttributes<SVGSVGElement>>;
  subtitle: string;
  services: CategoryServiceDetail[];
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
  const { /* isAuthenticated */ } = useAuth();

  // Use React Query hook for fetching services (prevents duplicate API calls)
  const {
    data: servicesData,
    error: queryError,
    isLoading: queryLoading,
  } = useAllServicesWithInstructors();

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
      const categories: CategoryWithServices[] = apiCategories.map((category) => {
        const services = (category.services ?? []).map((service) => ({
          ...service,
          description: service.description ?? '',
          search_terms: service.search_terms ?? [],
          is_active: service.is_active ?? true,
          is_trending: service.is_trending ?? false,
          online_capable: service.online_capable ?? false,
          requires_certification: service.requires_certification ?? false,
        }));
        return {
          id: category.id,
          name: category.name.toUpperCase(),
          icon: ICON_BY_NAME[category.icon_name ?? ''] ?? Search,
          subtitle: category.subtitle ?? '',
          services,
        };
      });
      setCategoriesWithServices(categories);

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
      });

      setLoading(false);
    }
  }, [servicesData, queryError]);

  const displayCategories = categoriesWithServices;

  // Set up intersection observer for progressive loading
  useEffect(() => {
    if (loading || categoriesWithServices.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const categoryId = entry.target.getAttribute('data-category');
            if (categoryId) {
              setVisibleServices((prev) => {
                const currentCount = prev[categoryId] || INITIAL_SERVICES_COUNT;
                const category = categoriesWithServices.find((c) => c.id === categoryId);
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
  }, [loading, categoriesWithServices]);

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
    const visibleServicesList = category.services.slice(0, visibleCount);
    const hasMore = category.services.length > visibleCount;

    return (
      <div className="space-y-1">
        {visibleServicesList.map((service) => {
          const hasInstructors =
            service.instructor_count !== undefined && service.instructor_count > 0;

          if (!hasInstructors) {
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

          return (
            <Link
              key={service.id}
              href={`/search?service_catalog_id=${service.id}&service_name=${encodeURIComponent(service.name)}&from=services`}
              onClick={async () => {
                // Track navigation source as backup
                if (typeof window !== 'undefined') {
                  sessionStorage.setItem('navigationFrom', '/services');
                  logger.debug('Set navigation source from services page', {
                    navigationFrom: '/services',
                    serviceId: service.id,
                  });
                }

                // Don't record here - let the search page handle it with correct counts
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
                    <div className="mt-1" style={{ minHeight: '32px' }}>
                      {category.subtitle ? (
                        <p
                          className="text-xs text-gray-500 dark:text-gray-400 break-words"
                          style={{ lineHeight: '1.2', wordBreak: 'break-word' }}
                        >
                          {category.subtitle}
                        </p>
                      ) : (
                        <div style={{ height: '32px' }} />
                      )}
                    </div>
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
