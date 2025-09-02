// frontend/app/(public)/services/page.tsx
'use client';

import { useEffect, useState, useRef, useMemo } from 'react';
import Link from 'next/link';
import { Search, Music, BookOpen, Dumbbell, Globe, Palette, Baby, Sparkles } from 'lucide-react';
import { publicApi, type CatalogService } from '@/features/shared/api/client';
import { logger } from '@/lib/logger';
import { useAuth } from '@/features/shared/hooks/useAuth';
// Removed recordSearch and SearchType - tracking now handled by search page
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/react-query/queryClient';

// Progressive loading configuration
const INITIAL_SERVICES_COUNT = 15;
const LOAD_MORE_COUNT = 10;

// Category configuration with exact names and icons from homepage
const CATEGORY_CONFIG = [
  {
    id: 1,
    slug: 'music',
    name: 'MUSIC',
    icon: Music,
  },
  {
    id: 2,
    slug: 'tutoring',
    name: 'TUTORING',
    icon: BookOpen,
  },
  {
    id: 3,
    slug: 'sports-fitness',
    name: 'SPORTS & FITNESS',
    icon: Dumbbell,
  },
  {
    id: 4,
    slug: 'language',
    name: 'LANGUAGE',
    icon: Globe,
  },
  {
    id: 5,
    slug: 'arts',
    name: 'ARTS',
    icon: Palette,
  },
  {
    id: 6,
    slug: 'kids',
    name: 'KIDS',
    icon: Baby,
  },
  {
    id: 7,
    slug: 'hidden-gems',
    name: 'HIDDEN GEMS',
    icon: Sparkles,
  },
];

interface CategoryWithServices {
  id: string;
  slug: string;
  name: string;
  icon: React.ComponentType; // Lucide icon component
  subtitle: string;
  services: CatalogService[];
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
  const [kidsServices, setKidsServices] = useState<Array<{ id: string; name: string; slug: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [visibleServices, setVisibleServices] = useState<Record<string, number>>({});
  const categoryRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const { /* isAuthenticated */ } = useAuth();

  // Load kids-available services independently so they show regardless of which data path loads
  useEffect(() => {
    const fetchKids = async () => {
      try {
        const res = await publicApi.getKidsAvailableServices();
        if (res.data) setKidsServices(res.data);
      } catch {
        // non-fatal
      }
    };
    fetchKids();
  }, []);

  // Add React Query hook for fetching services
  const {
    data: servicesResponse,
    error: queryError,
    isLoading: queryLoading,
  } = useQuery({
    queryKey: queryKeys.services?.withInstructors || ['services', 'withInstructors'],
    queryFn: () => publicApi.getAllServicesWithInstructors(),
    staleTime: 1000 * 60 * 15, // 15 minutes - service counts change moderately
    gcTime: 1000 * 60 * 30, // 30 minutes
  });

  // Sync loading state with React Query
  useEffect(() => {
    setLoading(queryLoading);
  }, [queryLoading]);

  useEffect(() => {
    // Handle React Query error
    if (queryError) {
      logger.error('Failed to fetch services', queryError as Error);
      setError('Failed to load services. Please try again later.');
      return;
    }

    // If React Query has the data, use it
    if (servicesResponse) {
      if (servicesResponse.error) {
        logger.error(
          'Failed to fetch services with instructors',
          new Error(servicesResponse.error)
        );
        setError('Failed to load services');
        setLoading(false);
        return;
      }

      if (!servicesResponse.data) {
        logger.error('No services data received');
        setError('No services available');
        setLoading(false);
        return;
      }

      // Transform the response to match our component's expected structure
      const categories: CategoryWithServices[] = servicesResponse.data.categories.map(
        (category: { id: string; slug: string; name: string; subtitle: string; services: unknown[] }) => {
          // Find matching emoji from CATEGORY_CONFIG
          const config = CATEGORY_CONFIG.find((c) => c.slug === category.slug);

          return {
            id: category.id,
            slug: category.slug,
            name: category.name.toUpperCase(), // Ensure uppercase for consistency
            icon: config?.icon || Search, // Default icon if not found
            subtitle: category.subtitle,
            services: category.services.map((service: { id: string; category_id: string; name: string; slug: string }) => ({
              id: service.id,
              category_id: service.category_id,
              name: service.name,
              slug: service.slug,
              description: service.description,
              search_terms: service.search_terms,
              display_order: service.display_order,
              online_capable: service.online_capable,
              requires_certification: service.requires_certification,
              is_active: service.is_active,
              instructor_count: service.instructor_count,
              actual_min_price: service.actual_min_price,
              actual_max_price: service.actual_max_price,
            })),
          };
        }
      );
      setCategoriesWithServices(categories);

      // Initialize visible services count for each category
      const initialVisible: Record<string, number> = {};
      categories.forEach((cat) => {
        initialVisible[cat.slug] = INITIAL_SERVICES_COUNT;
      });
      setVisibleServices(initialVisible);

      logger.info('Loaded all services with instructor data', {
        categoriesCount: categories.length,
        totalServices: servicesResponse.data.metadata.total_services,
        cached: servicesResponse.data.metadata.cached_for_seconds,
      });

      setLoading(false);
      return;
    }

    // Fallback to original fetching logic if React Query data not available
    const fetchServices = async () => {
      try {
        setLoading(true);
        setError(null);

        // Use the new optimized endpoint
        const response = await publicApi.getAllServicesWithInstructors();

        if (response.error) {
          logger.error('Failed to fetch services with instructors', new Error(response.error));
          setError('Failed to load services');
          return;
        }

        if (!response.data) {
          logger.error('No services data received');
          setError('No services available');
          return;
        }

        // Transform the response to match our component's expected structure
        const categories: CategoryWithServices[] = response.data.categories.map((category) => {
          // Find matching emoji from CATEGORY_CONFIG
          const config = CATEGORY_CONFIG.find((c) => c.slug === category.slug);

          return {
            id: category.id,
            slug: category.slug,
            name: category.name.toUpperCase(), // Ensure uppercase for consistency
            icon: config?.icon || Search, // Default icon if not found
            subtitle: category.subtitle,
            services: category.services.map((service: { id: string; category_id: string; name: string; slug: string }) => ({
              id: service.id,
              category_id: service.category_id,
              name: service.name,
              slug: service.slug,
              description: service.description,
              search_terms: service.search_terms,
              display_order: service.display_order,
              online_capable: service.online_capable,
              requires_certification: service.requires_certification,
              is_active: service.is_active,
              instructor_count: service.instructor_count,
              actual_min_price: service.actual_min_price,
              actual_max_price: service.actual_max_price,
            })),
          };
        });

        setCategoriesWithServices(categories);

        // Initialize visible services count for each category
        const initialVisible: Record<string, number> = {};
        categories.forEach((cat) => {
          initialVisible[cat.slug] = INITIAL_SERVICES_COUNT;
        });
        setVisibleServices(initialVisible);

        logger.info('Loaded all services with instructor data', {
          categoriesCount: categories.length,
          totalServices: response.data.metadata.total_services,
          cached: response.data.metadata.cached_for_seconds,
        });
      } catch (err) {
        logger.error('Failed to fetch services', err as Error);
        setError('Failed to load services. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    fetchServices();
  }, [servicesResponse, queryError]);

  // Derive display categories with kids services injected at render-time to avoid race conditions
  const displayCategories = useMemo(() => {
    const clone = categoriesWithServices.map((c) => ({ ...c, services: [...c.services] }));
    const kidsCat = clone.find((c) => c.slug === 'kids');
    if (kidsCat && kidsServices.length) {
      const existingIds = new Set(kidsCat.services.map((s) => s.id));
      const injected = kidsServices
        .filter((ks) => !existingIds.has(ks.id))
        .map((ks): CatalogService => ({
          id: ks.id,
          category_id: kidsCat.id,
          name: ks.name,
          slug: ks.slug,
          description: '',
          search_terms: [],
          display_order: 0,
          online_capable: true,
          requires_certification: false,
          is_active: true,
          instructor_count: 1,
          actual_min_price: undefined,
          actual_max_price: undefined,
        }));
      kidsCat.services = [...injected, ...kidsCat.services];
    }
    return clone;
  }, [categoriesWithServices, kidsServices]);

  // Set up intersection observer for progressive loading
  useEffect(() => {
    if (loading || categoriesWithServices.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const categorySlug = entry.target.getAttribute('data-category');
            if (categorySlug) {
              setVisibleServices((prev) => {
                const currentCount = prev[categorySlug] || INITIAL_SERVICES_COUNT;
                const category = categoriesWithServices.find((c) => c.slug === categorySlug);
                const totalServices = category?.services.length || 0;

                if (currentCount < totalServices) {
                  return {
                    ...prev,
                    [categorySlug]: Math.min(currentCount + LOAD_MORE_COUNT, totalServices),
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
    Object.entries(categoryRefs.current).forEach(([slug, element]) => {
      if (element) {
        const loadMoreElement = element.querySelector(`[data-load-more="${slug}"]`);
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
    const visibleCount = visibleServices[category.slug] || INITIAL_SERVICES_COUNT;
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
          <div data-load-more={category.slug} data-category={category.slug} className="h-4" />
        )}
      </div>
    );
  };

  // (No separate Kids column; we render kidsServices inside the existing Kids category below)

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: customGridStyle }} />
      <div className="min-h-screen bg-white dark:bg-gray-900">
        {/* Header Section */}
        <header className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
              {/* Logo */}
              <Link href="/" className="text-3xl font-bold text-purple-700 dark:text-purple-400 hover:text-purple-800 transition-colors">
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
                key={category.slug}
                ref={(el) => {
                  if (el) categoryRefs.current[category.slug] = el;
                }}
                className="flex flex-col min-h-0"
              >
                {/* Category Header */}
                <div className="mb-4">
                  <div className="pb-2 border-b border-gray-200 dark:border-gray-700">
                    <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2 h-6">
                      <category.icon className="h-5 w-5 flex-shrink-0" />
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
