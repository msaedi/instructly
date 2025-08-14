// frontend/app/(public)/search/page.tsx
'use client';

import { useEffect, useState, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { ChevronLeft, Filter } from 'lucide-react';
import { publicApi } from '@/features/shared/api/client';
import { logger } from '@/lib/logger';
import InstructorCard from '@/components/InstructorCard';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { recordSearch, trackSearchInteraction } from '@/lib/searchTracking';
import { SearchType } from '@/types/enums';
import { Instructor } from '@/types/api';

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

  // Debug logging to track renders
  useEffect(() => {
    logger.debug('SearchPageContent rendered');
  });
  const [instructors, setInstructors] = useState<Instructor[]>([]);
  const [metadata, setMetadata] = useState<SearchMetadata | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [serviceName, setServiceName] = useState<string>('');
  const [previousPath, setPreviousPath] = useState<string>('/');
  const [hasRecordedSearch, setHasRecordedSearch] = useState(false);
  const [fromPage, setFromPage] = useState<string | null>(null);
  const [searchEventId, setSearchEventId] = useState<number | null>(null);
  const [searchTimestamp, setSearchTimestamp] = useState<number | null>(null);

  // Parse search parameters from URL
  const query = searchParams.get('q') || '';
  const category = searchParams.get('category') || '';
  const serviceCatalogId = searchParams.get('service_catalog_id') || '';
  const availableNow = searchParams.get('available_now') === 'true';

  // Reset hasRecordedSearch when search parameters change
  useEffect(() => {
    setHasRecordedSearch(false);
    setServiceName(''); // Also reset service name
  }, [query, category, serviceCatalogId]);

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

  useEffect(() => {
    async function fetchResults() {
      setLoading(true);
      setError(null);

      logger.info('Search page loading', {
        query,
        category,
        serviceCatalogId,
        availableNow,
        page,
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

            setMetadata({
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
            });
          }
        } else if (serviceCatalogId) {
          // Service catalog ID provided - fetch instructors for specific service
          const apiParams = {
            service_catalog_id: serviceCatalogId,  // Now using ULID strings, no parseInt
            page: page,
            per_page: 20,
          };

          logger.info('Filtering by service catalog ID', { serviceCatalogId });

          response = await publicApi.searchInstructors(apiParams);

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
            setMetadata(null); // No legacy metadata structure
          }
        } else {
          // No query provided - this is no longer supported with service-first model
          // The old browsing functionality is disabled since it goes against service-first architecture
          logger.warn('Attempted to browse instructors without service or query', { category });
          setError('Please search for a specific service or use natural language search');
          return;
        }

        // Set the final data
        setInstructors(instructorsData);
        setTotal(totalResults);
      } catch (err) {
        logger.error('Failed to fetch search results', err as Error);
        setError('Failed to load search results');
      } finally {
        setLoading(false);
      }
    }

    fetchResults();
  }, [query, category, serviceCatalogId, availableNow, page]);

  // Fetch service name when serviceCatalogId changes
  useEffect(() => {
    if (serviceCatalogId) {
      const fetchServiceName = async () => {
        try {
          const servicesResponse = await publicApi.getCatalogServices();
          if (servicesResponse.data) {
            const service = servicesResponse.data.find((s) => s.id.toString() === serviceCatalogId);
            if (service) {
              setServiceName(service.name);
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
        // Record search with unified tracker
        const eventId = await recordSearch(
          {
            query: searchQuery,
            search_type: searchType,
            results_count: total,
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

  // Generate realistic next available times (deterministic for SSR)
  const getNextAvailableSlots = (instructorId: string) => {
    // Some instructors may not have availability (e.g., specific ULIDs)
    // Simulate this by having certain instructor IDs return no availability
    const instructorsWithNoAvailability: string[] = []; // Can add specific ULIDs if needed
    if (instructorsWithNoAvailability.includes(instructorId)) {
      return [];
    }

    // Use a fixed base date for SSR consistency (always start from tomorrow)
    const today = new Date();
    today.setHours(0, 0, 0, 0); // Normalize to start of day for consistency

    const slots = [];

    // Always start from tomorrow (24+ hours advance) to comply with booking rules
    for (let i = 0; i < 3; i++) {
      const slotDate = new Date(today);
      slotDate.setDate(today.getDate() + i + 1); // Start from tomorrow

      // Vary times based on instructor ID to make them unique but deterministic
      // Convert ULID string to a number for calculation (use first few chars as seed)
      const baseHours = [9, 11, 14, 16, 18]; // 9 AM, 11 AM, 2 PM, 4 PM, 6 PM
      const idSeed = instructorId.charCodeAt(0) + instructorId.charCodeAt(1);
      const hourIndex = (idSeed + i) % baseHours.length;
      const hour = baseHours[hourIndex];

      slotDate.setHours(hour, 0, 0, 0);

      const displayHour = hour > 12 ? hour - 12 : hour === 0 ? 12 : hour;
      const ampm = hour >= 12 ? 'PM' : 'AM';

      let displayText;
      if (i === 0) {
        displayText = `Tomorrow ${displayHour}:00 ${ampm}`;
      } else if (i === 1) {
        // Day after tomorrow
        const dayName = slotDate.toLocaleDateString('en-US', { weekday: 'short' });
        displayText = `${dayName} ${displayHour}:00 ${ampm}`;
      } else {
        // Future days
        const dayName = slotDate.toLocaleDateString('en-US', { weekday: 'short' });
        displayText = `${dayName} ${displayHour}:00 ${ampm}`;
      }

      slots.push({
        date: slotDate.toISOString().split('T')[0],
        time: `${hour.toString().padStart(2, '0')}:00:00`,
        displayText,
      });
    }

    return slots;
  };

  // Format subject for display
  const formatSubject = (subject: string) => {
    return subject.charAt(0).toUpperCase() + subject.slice(1).replace('_', ' ');
  };

  // Calculate total pages
  const totalPages = Math.ceil(total / 20);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <Link href={previousPath} className="mr-4">
                <ChevronLeft className="h-6 w-6 text-gray-600" />
              </Link>
              <h1 className="text-xl font-semibold text-gray-900">
                {query
                  ? `Results for "${query}"`
                  : serviceCatalogId && serviceName
                    ? `Showing all ${serviceName} instructors`
                    : category
                      ? formatSubject(category)
                      : 'All Instructors'}
              </h1>
              {total > 0 && <span className="ml-2 text-gray-600">({total} found)</span>}
            </div>
            {/* TODO: Implement filter functionality in future iteration */}
            <button
              className="flex items-center px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 dark:border-gray-600 dark:hover:bg-gray-700 dark:text-white opacity-50 cursor-not-allowed"
              disabled
              title="Filters coming soon"
            >
              <Filter className="h-5 w-5 mr-2" />
              Filters
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Show applied filters if metadata available */}
        {metadata &&
          metadata.filters_applied &&
          Object.keys(metadata.filters_applied).length > 0 && (
            <div className="mb-4 text-sm text-gray-600">
              <span className="font-medium">Active filters:</span>
              {metadata.filters_applied.search && (
                <span className="ml-2 px-2 py-1 bg-blue-100 text-blue-800 rounded">
                  Search: {metadata.filters_applied.search}
                </span>
              )}
              {metadata.filters_applied.skill && (
                <span className="ml-2 px-2 py-1 bg-green-100 text-green-800 rounded">
                  Skill: {metadata.filters_applied.skill}
                </span>
              )}
              {metadata.filters_applied.min_price !== undefined && (
                <span className="ml-2 px-2 py-1 bg-yellow-100 text-yellow-800 rounded">
                  Min: ${metadata.filters_applied.min_price}
                </span>
              )}
              {metadata.filters_applied.max_price !== undefined && (
                <span className="ml-2 px-2 py-1 bg-yellow-100 text-yellow-800 rounded">
                  Max: ${metadata.filters_applied.max_price}
                </span>
              )}
            </div>
          )}

        {loading ? (
          <div className="flex justify-center items-center h-64">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          </div>
        ) : error ? (
          <div className="text-center py-12">
            <p className="text-red-600">{error}</p>
            <Link href="/" className="text-blue-600 hover:underline mt-4 inline-block">
              Return to Home
            </Link>
          </div>
        ) : instructors.length === 0 ? (
          <div className="text-center py-12" data-testid="no-results">
            <p className="text-gray-600 text-lg mb-4">No instructors found matching your search.</p>
            <Link href="/" className="text-blue-600 hover:underline">
              Try a different search
            </Link>
          </div>
        ) : (
          <>
            {/* Results Grid */}
            <div className="grid gap-6 md:grid-cols-1 lg:grid-cols-2 xl:grid-cols-3">
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
                };

                return (
                  <div key={instructor.id}>
                    <InstructorCard
                      instructor={enhancedInstructor}
                      nextAvailableSlots={getNextAvailableSlots(instructor.user_id)}
                      onViewProfile={() => handleInteraction('view_profile')}
                      onBookNow={() => handleInteraction('book')}
                      onTimeSlotClick={() => handleInteraction('click')}
                    />
                  </div>
                );
              })}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="mt-8 flex justify-center">
                <nav className="flex items-center space-x-2">
                  <button
                    onClick={() => setPage(Math.max(1, page - 1))}
                    disabled={page === 1}
                    className="px-4 py-2 border border-gray-300 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
                  >
                    Previous
                  </button>
                  <span className="px-4 py-2">
                    Page {page} of {totalPages}
                  </span>
                  <button
                    onClick={() => setPage(Math.min(totalPages, page + 1))}
                    disabled={page === totalPages}
                    className="px-4 py-2 border border-gray-300 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
                  >
                    Next
                  </button>
                </nav>
              </div>
            )}
          </>
        )}
      </main>
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
