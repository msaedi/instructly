// frontend/app/(public)/search/page.tsx
'use client';

import { useEffect, useState, Suspense, useCallback, useRef } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { publicApi } from '@/features/shared/api/client';
import { logger } from '@/lib/logger';
import InstructorCard from '@/components/InstructorCard';
import dynamic from 'next/dynamic';
const InstructorCoverageMap = dynamic(() => import('@/components/maps/InstructorCoverageMap'), { ssr: false });
import { useAuth } from '@/features/shared/hooks/useAuth';
import { recordSearch, trackSearchInteraction } from '@/lib/searchTracking';
import { SearchType } from '@/types/enums';
import { Instructor } from '@/types/api';
import { useBackgroundConfig } from '@/lib/config/backgroundProvider';
import TimeSelectionModal from '@/features/student/booking/components/TimeSelectionModal';
import UserProfileDropdown from '@/components/UserProfileDropdown';

interface SearchMetadata {
  filters_applied: Record<string, any>;
  pagination: {
    skip: number;
    limit: number;
    count: number;
  };
  total_matches: number;
  active_instructors: number;
}

function SearchPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const { setActivity, clearOverrides } = useBackgroundConfig();

  // Debug logging to track renders
  useEffect(() => {
    logger.debug('SearchPageContent rendered');
  });
  const [instructors, setInstructors] = useState<Instructor[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [total, setTotal] = useState(0);
  const [serviceName, setServiceName] = useState<string>('');
  const [serviceSlug, setServiceSlug] = useState<string>('');
  const [previousPath, setPreviousPath] = useState<string>('/');
  const [hasRecordedSearch, setHasRecordedSearch] = useState(false);
  const [fromPage, setFromPage] = useState<string | null>(null);
  const [searchEventId, setSearchEventId] = useState<number | null>(null);
  const [searchTimestamp, setSearchTimestamp] = useState<number | null>(null);
  const [rateLimit, setRateLimit] = useState<{ seconds: number } | null>(null);
  const [showTimeSelection, setShowTimeSelection] = useState(false);
  const [timeSelectionContext, setTimeSelectionContext] = useState<any>(null);

  // Refs for infinite scroll
  const observerRef = useRef<IntersectionObserver | null>(null);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);

  // State for highlighting neighborhoods on hover
  const [hoveredInstructorId, setHoveredInstructorId] = useState<string | null>(null);
  const [showCoverage, setShowCoverage] = useState<boolean>(true);
  const [coverageGeoJSON, setCoverageGeoJSON] = useState<any | null>(null);

  // Inline banner for rate limit
  const RateLimitBanner = () =>
    rateLimit ? (
      <div className="mb-4 rounded-md bg-yellow-50 border border-yellow-200 text-yellow-900 px-3 py-2 text-sm">
        Our hamsters are sprinting. Give them {rateLimit.seconds}s.
      </div>
    ) : null;

  // Parse search parameters from URL
  const query = searchParams.get('q') || '';
  const category = searchParams.get('category') || '';
  const serviceCatalogId = searchParams.get('service_catalog_id') || '';
  const availableNow = searchParams.get('available_now') === 'true';

  // Reset hasRecordedSearch and pagination when search parameters change
  useEffect(() => {
    setHasRecordedSearch(false);
    setServiceName(''); // Also reset service name
    setPage(1);
    setInstructors([]);
    setHasMore(true);
  }, [query, category, serviceCatalogId]);

  // Set background activity from query/category when present
  useEffect(() => {
    // Prefer query as activity, else category
    const activity = (query || category || '').trim();
    if (activity) {
      setActivity(activity);
    } else {
      // If no query or category, clear activity to allow default background
      setActivity(null);
    }
    // Intentionally do NOT clear on unmount so instructor profile can inherit
  }, [query, category, setActivity]);

  // When navigating via service_catalog_id, set background using the resolved service slug (prefer)
  useEffect(() => {
    if (serviceCatalogId && (serviceSlug || serviceName)) {
      setActivity((serviceSlug || serviceName).toLowerCase());
    }
  }, [serviceCatalogId, serviceSlug, serviceName, setActivity]);

  // Determine where user came from
  useEffect(() => {
    if (typeof window !== 'undefined') {
      // Check URL parameters first for explicit source
      const urlParams = new URLSearchParams(window.location.search);
      const fromParam = urlParams.get('from');

      logger.debug('Navigation tracking', {
        fromParam,
        sessionStorage: sessionStorage.getItem('navigationFrom'),
        referrer: document.referrer,
      });

      if (fromParam) {
        // URL parameter takes precedence
        logger.debug('Using URL parameter for navigation', { from: fromParam });
        setFromPage(fromParam);
        if (fromParam === 'services') {
          setPreviousPath('/services');
        } else if (fromParam === 'home') {
          setPreviousPath('/');
        } else {
          setPreviousPath('/');
        }
      } else {
        // Check sessionStorage for navigation tracking
        const navHistory = sessionStorage.getItem('navigationFrom');

        if (navHistory) {
          logger.debug('Using sessionStorage navigation', { path: navHistory });
          setPreviousPath(navHistory);
          // Clear after a delay to ensure it's been used
          setTimeout(() => {
            sessionStorage.removeItem('navigationFrom');
          }, 500);
        } else {
          // Fallback to referrer checking
          const referrer = document.referrer;
          logger.debug('Using referrer', { referrer });

          if (referrer) {
            try {
              const referrerUrl = new URL(referrer);
              const currentUrl = new URL(window.location.href);

              // Only use referrer if it's from the same origin
              if (referrerUrl.origin === currentUrl.origin) {
                const pathname = referrerUrl.pathname;
                logger.debug('Referrer pathname', { pathname });

                if (pathname === '/services') {
                  setPreviousPath('/services');
                } else if (pathname === '/' || pathname === '') {
                  setPreviousPath('/');
                } else {
                  // Default to homepage for other paths
                  setPreviousPath('/');
                }
              }
            } catch (e) {
              // If URL parsing fails, default to homepage
              logger.error('Error parsing referrer', e as Error);
              setPreviousPath('/');
            }
          } else {
            logger.debug('No referrer, defaulting to homepage');
            setPreviousPath('/');
          }
        }
      }
    }
  }, []);

  // Fetch results function
  const fetchResults = useCallback(async (pageNum: number, append: boolean = false) => {
    if (!append) {
      setLoading(true);
    } else {
      setLoadingMore(true);
    }
    setError(null);

    logger.info('Search page loading', {
      query,
      category,
      serviceCatalogId,
      availableNow,
      page: pageNum,
      append,
    });

    try {
      let response;
      let instructorsData: Instructor[] = [];
      let totalResults = 0;

      // Use natural language search if we have a query
      if (query) {
        logger.info('Using natural language search', {
          query,
          endpoint: '/api/search/instructors',
        });

        // Use the new natural language search endpoint
        const nlResponse = await publicApi.searchWithNaturalLanguage(query);

          logger.info('Natural language API Response received', {
            hasError: !!nlResponse.error,
            hasData: !!nlResponse.data,
            status: nlResponse.status,
          });

          if (nlResponse.error) {
            logger.error('API Error', new Error(nlResponse.error), { status: nlResponse.status });
            setError(nlResponse.error);
            return;
          } else if (nlResponse.data) {
            // Map the new response format to the existing instructor format
            // For now, we'll need to fetch full instructor details for each result
            // This is a temporary solution until we update the UI to work with the new format

            logger.info('Natural language search results', {
              totalFound: nlResponse.data.total_found,
              resultsCount: nlResponse.data.results.length,
              parsed: nlResponse.data.parsed,
            });

            // Map the new API response format to the existing instructor format
            instructorsData = nlResponse.data.results.map(
              (result: any) =>
                ({
                  id: result.instructor?.id || '',
                  user_id: result.instructor?.id || '', // Using instructor.id as user_id
                  bio: result.instructor?.bio || '',
                  areas_of_service: result.instructor?.areas_of_service
                    ? result.instructor.areas_of_service.split(', ')
                    : [],
                  years_experience: result.instructor?.years_experience || 0,
                  user: {
                    first_name: result.instructor?.first_name || 'Unknown',
                    last_initial: result.instructor?.last_initial || '',
                    // No email for privacy
                  },
                  services: [
                    {
                      id: result.service?.id || 1,
                      service_catalog_id: result.service?.id || 1,
                      hourly_rate:
                        result.offering?.hourly_rate || result.service?.actual_min_price || 0,
                      description:
                        result.offering?.description || result.service?.description || '',
                      duration_options: result.offering?.duration_options || [60],
                      is_active: true,
                    },
                  ],
                  // Add match score for sorting
                  relevance_score: result.match_score || 0,
                }) as Instructor & { relevance_score: number }
            );

            // Sort by relevance score
            instructorsData.sort(
              (a: any, b: any) => (b.relevance_score || 0) - (a.relevance_score || 0)
            );

            totalResults = nlResponse.data.total_found;

            // Set search metadata with null safety checks - check both old and new response formats
            const maxPrice =
              nlResponse.data.parsed?.constraints?.max_price || nlResponse.data.parsed?.price?.max;
            const searchDate =
              nlResponse.data.parsed?.constraints?.date || nlResponse.data.parsed?.time?.date;
            const searchLocation =
              nlResponse.data.parsed?.constraints?.location ||
              nlResponse.data.parsed?.location?.area;

            // Natural language search doesn't support pagination yet, so we load all results at once
            setHasMore(false);

            /* setMetadata({
              filters_applied: {
                search: query,
                ...(maxPrice && { max_price: maxPrice }),
                ...(searchDate && { date: searchDate }),
                ...(searchLocation && { location: searchLocation }),
              },
              pagination: {
                skip: 0,
                limit: 20,
                count: nlResponse.data.results.length,
              },
              total_matches: nlResponse.data.total_found,
              active_instructors: nlResponse.data.total_found,
            }); */
            // Cache observability candidates from search response for persistence on record
            try {
              const obs = (nlResponse.data.search_metadata as any)?.observability_candidates || [];
              (window as any).__lastObsCandidates = Array.isArray(obs) ? obs : [];
            } catch {}
          }
        } else if (serviceCatalogId) {
          // Service catalog ID provided - fetch instructors for specific service
        const apiParams = {
          service_catalog_id: serviceCatalogId,  // Now using ULID strings, no parseInt
          page: pageNum,
          per_page: 20,
        };

          logger.info('Filtering by service catalog ID', { serviceCatalogId });

          response = await publicApi.searchInstructors(apiParams);

          // Handle rate limit: auto-retry once and show inline banner
          if (!response.data && response.status === 429 && (response as any).retryAfterSeconds) {
            const secs = (response as any).retryAfterSeconds as number;
            setRateLimit({ seconds: secs });
            await new Promise((r) => setTimeout(r, secs * 1000));
            response = await publicApi.searchInstructors(apiParams);
            setRateLimit(null);
          }

          logger.info('API Response received', {
            hasError: !!response.error,
            hasData: !!response.data,
            status: response.status,
          });

          if (response.error) {
            logger.error('API Error', new Error(response.error), { status: response.status });
            setError(response.error);
            return;
          } else if (response.data) {
            // API now always returns standardized paginated response
            logger.info('Received standardized paginated response', {
              count: response.data.items.length,
              total: response.data.total,
              page: response.data.page,
            });

            instructorsData = response.data.items;
            totalResults = response.data.total;
            // Check if there are more pages
            const totalPages = Math.ceil(totalResults / 20);
            setHasMore(pageNum < totalPages);
          }
        } else {
          // No query provided - this is no longer supported with service-first model
          // The old browsing functionality is disabled since it goes against service-first architecture
          logger.warn('Attempted to browse instructors without service or query', { category });
          setError('Please search for a specific service or use natural language search');
          return;
        }

      // Set the final data
      if (append) {
        setInstructors(prev => [...prev, ...instructorsData]);
      } else {
        setInstructors(instructorsData);
      }
      setTotal(totalResults);
    } catch (err) {
      logger.error('Failed to fetch search results', err as Error);
      setError('Failed to load search results');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [query, category, serviceCatalogId, availableNow]);

  // Initial fetch
  useEffect(() => {
    fetchResults(1, false);
  }, [query, category, serviceCatalogId, availableNow, fetchResults]);

  // Fetch bulk coverage when instructor list changes
  useEffect(() => {
    const fetchCoverage = async () => {
      try {
        // Collect visible instructor user_ids
        const ids = Array.from(new Set((instructors || []).map((i) => i.user_id).filter(Boolean)));
        if (!ids.length) {
          setCoverageGeoJSON({ type: 'FeatureCollection', features: [] });
          return;
        }
        const params = new URLSearchParams({ ids: ids.join(',') });
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
        const res = await fetch(`${apiUrl}/api/addresses/coverage/bulk?${params.toString()}`);
        if (!res.ok) {
          setCoverageGeoJSON({ type: 'FeatureCollection', features: [] });
          return;
        }
        const data = await res.json();
        setCoverageGeoJSON(data);
      } catch (e) {
        setCoverageGeoJSON({ type: 'FeatureCollection', features: [] });
      }
    };
    fetchCoverage();
  }, [instructors]);

  // Set up infinite scroll observer
  useEffect(() => {
    if (observerRef.current) {
      observerRef.current.disconnect();
    }

    observerRef.current = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loadingMore && !loading) {
          const nextPage = page + 1;
          setPage(nextPage);
          fetchResults(nextPage, true);
        }
      },
      { threshold: 0.1 }
    );

    if (loadMoreRef.current) {
      observerRef.current.observe(loadMoreRef.current);
    }

    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect();
      }
    };
  }, [hasMore, loadingMore, loading, page, fetchResults]);

  // Fetch service metadata when serviceCatalogId changes
  useEffect(() => {
    if (serviceCatalogId) {
      const fetchServiceName = async () => {
        try {
          const servicesResponse = await publicApi.getCatalogServices();
          if (servicesResponse.data) {
            const service = servicesResponse.data.find((s) => s.id.toString() === serviceCatalogId);
            if (service) {
              setServiceName(service.name);
              setServiceSlug(service.slug);
            }
          }
        } catch (err) {
          logger.error('Failed to fetch service name', err as Error);
        }
      };
      fetchServiceName();
    }
  }, [serviceCatalogId]);

  // Record search when we have all necessary data
  useEffect(() => {
    const recordSearchIfReady = async () => {
      logger.debug('recordSearchIfReady called', {
        hasRecordedSearch,
        loading,
        query,
        category,
        serviceCatalogId,
        serviceName,
        total,
      });

      // Skip if already recorded
      if (hasRecordedSearch) {
        logger.debug('Skipping - already recorded');
        return;
      }

      // Skip if we don't have results yet
      // We need to wait for loading to finish
      if (loading) {
        logger.debug('Skipping - still loading');
        return;
      }

      // Determine if we have all required data
      const hasRequiredData = query || category || (serviceCatalogId && serviceName);

      if (!hasRequiredData) {
        logger.debug('Skipping - no required data', {
          query: !!query,
          category: !!category,
          serviceCatalogId: !!serviceCatalogId,
          serviceName: !!serviceName,
        });
        return;
      }

      // Determine search query and type
      const searchQuery = query || serviceName || category || 'Unknown search';
      let searchType: SearchType = SearchType.NATURAL_LANGUAGE;

      if (query) {
        // Determine if this is a search history click or a new natural language search
        if (fromPage === 'recent') {
          searchType = SearchType.SEARCH_HISTORY;
        } else {
          searchType = SearchType.NATURAL_LANGUAGE;
        }
      } else if (serviceCatalogId && serviceName) {
        searchType = SearchType.SERVICE_PILL;
      } else if (category) {
        searchType = SearchType.CATEGORY;
      }

      logger.debug('About to record search', {
        searchQuery,
        searchType,
        total,
      });

      try {
        const observabilityCandidates = (typeof window !== 'undefined' && (window as any).__lastObsCandidates) || [];
        const eventId = await recordSearch(
          {
            query: searchQuery,
            search_type: searchType,
            results_count: total,
            observability_candidates: observabilityCandidates,
          },
          isAuthenticated
        );

        if (eventId) {
          setSearchEventId(eventId);
          setSearchTimestamp(Date.now() / 1000); // Store timestamp in seconds
          logger.info('Search recorded successfully with event ID', {
            query: searchQuery,
            searchType,
            resultsCount: total,
            isAuthenticated,
            searchEventId: eventId,
          });
        }

        setHasRecordedSearch(true);
      } catch (error) {
        logger.error('Error in search tracking:', error as Error, {
          searchQuery,
          searchType,
          resultsCount: total,
          isAuthenticated,
        });
      }
    };

    recordSearchIfReady();
  }, [
    query,
    category,
    serviceCatalogId,
    serviceName,
    total,
    loading,
    hasRecordedSearch,
    isAuthenticated,
    fromPage,
  ]);

  // Fetch next available slot for each instructor
  const [nextAvailableByInstructor, setNextAvailableByInstructor] = useState<Record<string, {date: string; time: string; displayText: string}>>({});

  useEffect(() => {
    const fetchAvailabilities = async () => {
      try {
        const updates: Record<string, {date: string; time: string; displayText: string}> = {};
        const today = new Date();
        const startDate = new Date(today);
        const endDate = new Date(startDate);
        endDate.setDate(startDate.getDate() + 14); // look ahead 2 weeks
        const formatDate = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;

        await Promise.all(
          instructors.map(async (i) => {
            try {
              const { data, status } = await publicApi.getInstructorAvailability(i.user_id, {
                start_date: formatDate(startDate),
                end_date: formatDate(endDate),
              });
              if (!data || status !== 200) {
                return;
              }
              const byDate = data.availability_by_date || {};
              const dates = Object.keys(byDate).sort();

              // Find the first available slot
              for (const d of dates) {
                const day = byDate[d];
                if (day?.is_blackout || !day?.available_slots?.length) continue;

                const firstSlot = day.available_slots[0];
                const date = new Date(d);
                const [hours, minutes] = firstSlot.start_time.split(':').map(Number);
                const dateStr = date.toLocaleDateString('en-US', {
                  weekday: 'short',
                  month: 'short',
                  day: 'numeric'
                });
                const timeStr = new Date(2000, 0, 1, hours, minutes).toLocaleTimeString('en-US', {
                  hour: 'numeric',
                  minute: '2-digit',
                  hour12: true
                });

                updates[i.user_id] = {
                  date: d,
                  time: firstSlot.start_time,
                  displayText: `${dateStr}, ${timeStr}`
                };
                break;
              }
            } catch (e) {
              // ignore errors for individual instructors
            }
          })
        );

        if (Object.keys(updates).length) {
          setNextAvailableByInstructor(updates);
        }
      } catch (e) {
        // ignore batch errors
      }
    };

    if (instructors && instructors.length) {
      fetchAvailabilities();
    }
  }, [instructors]);

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full">
          <Link href="/" className="inline-block">
            <h1 className="text-3xl font-bold text-purple-700 hover:text-purple-800 transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
          </Link>
          <div className="pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex">
        {/* Left Side - Filter and Instructor Cards */}
        <div className="flex-1 overflow-visible">
          {/* Filter Bar - Scrolls with content */}
          <div className="px-6 py-4">
            <div className="bg-white/95 backdrop-blur-sm rounded-xl border border-gray-200 p-4">
              <div className="flex items-center justify-between">
                <div className="flex gap-6">
                  {/* Date filters group */}
                  <div className="bg-gray-100 rounded-lg px-1 py-1 flex gap-1">
                    <button className="px-4 py-2 bg-white rounded-md text-sm font-medium cursor-pointer">
                      Today
                    </button>
                    <button className="px-4 py-2 text-gray-600 hover:bg-gray-50 rounded-md text-sm cursor-pointer">
                      This Week
                    </button>
                    <button className="px-4 py-2 text-gray-600 hover:bg-gray-50 rounded-md text-sm cursor-pointer">
                      Choose Date
                    </button>
                  </div>

                  {/* Time filters group */}
                  <div className="bg-gray-100 rounded-lg px-1 py-1 flex gap-1">
                    <button className="px-4 py-2 text-gray-600 hover:bg-gray-50 rounded-md text-sm cursor-pointer">
                      Morning
                    </button>
                    <button className="px-4 py-2 text-gray-600 hover:bg-gray-50 rounded-md text-sm cursor-pointer">
                      Afternoon
                    </button>
                  </div>

                  {/* More Filters button */}
                  <button className="px-4 py-2 border border-gray-300 rounded-lg text-sm hover:bg-gray-50 cursor-pointer">
                    More Filters
                  </button>
                </div>

                {/* Sort section */}
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-600">Sort by:</span>
                  <button className="px-4 py-2 border border-gray-300 rounded-lg text-sm hover:bg-gray-50 flex items-center gap-2 cursor-pointer">
                    <span>Recommended</span>
                    <span className="text-gray-500">▼</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Instructor Cards */}
          <div className="overflow-y-auto p-6 scrollbar-hide h-[calc(100vh-15rem)]"
               style={{
                 scrollbarWidth: 'none',
                 msOverflowStyle: 'none',
               }}>
          {/* Rate limit banner */}
          <RateLimitBanner />

          {loading ? (
            <div className="flex justify-center items-center h-64">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-700"></div>
            </div>
          ) : error ? (
            <div className="text-center py-12">
              <p className="text-red-600">{error}</p>
              <Link href="/" className="text-purple-700 hover:underline mt-4 inline-block">
                Return to Home
              </Link>
            </div>
          ) : instructors.length === 0 ? (
            <div className="text-center py-12" data-testid="no-results">
              <p className="text-gray-600 text-lg mb-4">No instructors found matching your search.</p>
              <Link href="/" className="text-purple-700 hover:underline">
                Try a different search
              </Link>
            </div>
          ) : (
            <>
              {/* Results - Single column layout */}
              <div className="space-y-6">
                {instructors.map((instructor, index) => {
                  // Add mock rating and reviews
                  const enhancedInstructor = {
                    ...instructor,
                    rating: instructor.rating || 4.8,
                    total_reviews: instructor.total_reviews || Math.floor(Math.random() * 100) + 20,
                    verified: true,
                  };

                  const handleInteraction = (
                    interactionType:
                      | 'click'
                      | 'hover'
                      | 'bookmark'
                      | 'view_profile'
                      | 'contact'
                      | 'book' = 'click'
                  ) => {
                    const currentTime = Date.now() / 1000; // Current time in seconds
                    const timeToInteraction = searchTimestamp ? currentTime - searchTimestamp : null;

                    logger.info('Instructor interaction', {
                      searchEventId,
                      instructorId: instructor.id,
                      instructorUserId: instructor.user_id,
                      position: index + 1,
                      isAuthenticated,
                      interactionType,
                      timeToInteraction,
                    });

                    if (searchEventId) {
                      trackSearchInteraction(
                        searchEventId,
                        interactionType,
                        instructor.user_id, // Use user_id instead of id
                        index + 1,
                        isAuthenticated,
                        timeToInteraction
                      );
                    } else {
                      logger.warn('No searchEventId available for interaction tracking');
                    }

                    if (interactionType === 'view_profile') {
                      router.push(`/instructors/${instructor.user_id}`);
                    }
                  };

                  return (
                    <div
                      key={instructor.id}
                      onMouseEnter={() => setHoveredInstructorId(instructor.user_id)}
                      onMouseLeave={() => setHoveredInstructorId(null)}
                    >
                      <InstructorCard
                        instructor={enhancedInstructor}
                        nextAvailableSlot={nextAvailableByInstructor[instructor.user_id]}
                        onViewProfile={() => handleInteraction('view_profile')}
                        onBookNow={(e) => {
                          e?.preventDefault?.();
                          e?.stopPropagation?.();
                          handleInteraction('book');
                          // Open time selection modal when "More options" is clicked
                          setShowTimeSelection(true);
                          setTimeSelectionContext({
                            instructor: enhancedInstructor,
                            preSelectedDate: null,
                            preSelectedTime: null,
                            serviceId: enhancedInstructor.services?.[0]?.id,
                          });
                        }}
                      />
                    </div>
                  );
                })}
              </div>

              {/* Infinite scroll loading indicator */}
              {hasMore && (
                <div ref={loadMoreRef} className="mt-8 flex justify-center py-4">
                  {loadingMore && (
                    <div className="flex items-center gap-2">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-700"></div>
                      <span className="text-gray-600">Loading more instructors...</span>
                    </div>
                  )}
                </div>
              )}

              {/* End of results message */}
              {!hasMore && instructors.length > 0 && (
                <div className="mt-8 text-center text-gray-600 py-4">
                  You've reached the end of {total} results
                </div>
              )}
            </>
          )}
          </div>
        </div>

        {/* Right Side - Map */}
        <div className="w-1/3 hidden xl:block">
          <div className="pl-0 pr-6 pt-4 pb-6">
            <div className="bg-white/95 backdrop-blur-sm rounded-xl border border-gray-200 p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm text-gray-600">Show coverage</div>
                <label className="inline-flex items-center cursor-pointer">
                  <input type="checkbox" className="sr-only peer" checked={showCoverage} onChange={() => setShowCoverage((v) => !v)} />
                  <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-600 relative" />
                </label>
              </div>
              <InstructorCoverageMap
                height="calc(100vh - 12rem)"
                featureCollection={coverageGeoJSON}
                showCoverage={showCoverage}
                highlightInstructorId={hoveredInstructorId}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Time Selection Modal */}
      {showTimeSelection && timeSelectionContext && (
        <TimeSelectionModal
          isOpen={showTimeSelection}
          onClose={() => setShowTimeSelection(false)}
          instructor={{
            user_id: timeSelectionContext.instructor.user_id,
            user: timeSelectionContext.instructor.user,
            services: timeSelectionContext.instructor.services || [],
          }}
          preSelectedDate={timeSelectionContext.preSelectedDate}
          preSelectedTime={timeSelectionContext.preSelectedTime}
          serviceId={timeSelectionContext.serviceId}
        />
      )}
    </div>
  );
}

export default function SearchResultsPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
        </div>
      }
    >
      <SearchPageContent />
    </Suspense>
  );
}
