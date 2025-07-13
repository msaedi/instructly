'use client';

import { useEffect, useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Star, MapPin, Check, ChevronLeft, Filter } from 'lucide-react';
import { publicApi } from '@/features/shared/api/client';
import { parseSearchQuery } from '@/features/shared/utils/search-parser';
import { logger } from '@/lib/logger';

interface Service {
  id: number;
  skill: string;
  hourly_rate: number;
  description?: string;
  duration_override?: number;
  duration: number;
}

interface Instructor {
  id: number;
  user_id: number;
  bio: string;
  areas_of_service: string[];
  years_experience: number;
  user: {
    full_name: string;
    email: string;
  };
  services: Service[];
  // Mock fields for now
  rating?: number;
  total_reviews?: number;
  total_hours_taught?: number;
}

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
  const [instructors, setInstructors] = useState<Instructor[]>([]);
  const [metadata, setMetadata] = useState<SearchMetadata | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  // Parse search parameters from URL
  const query = searchParams.get('q') || '';
  const category = searchParams.get('category') || '';
  const availableNow = searchParams.get('available_now') === 'true';

  useEffect(() => {
    async function fetchResults() {
      setLoading(true);
      setError(null);

      logger.info('Search page loading', {
        query,
        category,
        availableNow,
        page,
      });

      try {
        // Build API parameters
        const limit = 20;
        const skip = (page - 1) * limit;
        let apiParams: Record<string, any> = { skip, limit };

        // Handle search query
        if (query) {
          // Parse natural language query
          const parsed = parseSearchQuery(query);
          logger.debug('Parsed search query', {
            originalQuery: query,
            parsedQuery: parsed,
          });

          // If parser found specific skills, use skill parameter
          // Otherwise use general text search
          if (parsed.subjects.length > 0) {
            // Use the first subject as the skill filter
            apiParams.skill = parsed.subjects[0];
          } else {
            // Use general text search
            apiParams.search = query;
          }

          // Add price filters if parsed
          if (parsed.min_rate !== undefined) {
            apiParams.min_price = parsed.min_rate;
          }
          if (parsed.max_rate !== undefined) {
            apiParams.max_price = parsed.max_rate;
          }
        }

        // Handle category filter
        if (category) {
          apiParams.skill = category;
          logger.info('Filtering by category', { category });
        }

        // Log the API call parameters
        logger.info('Calling instructor API', {
          endpoint: '/instructors',
          params: apiParams,
        });

        // Fetch results from backend
        const response = await publicApi.searchInstructors(apiParams);

        logger.info('API Response received', {
          hasError: !!response.error,
          hasData: !!response.data,
          status: response.status,
        });

        if (response.error) {
          logger.error('API Error', new Error(response.error), { status: response.status });
          setError(response.error);
        } else if (response.data) {
          // Check if response has metadata (filtered results) or is just an array
          if (Array.isArray(response.data)) {
            // No filters applied - simple array response
            logger.info('Received simple array response', {
              count: response.data.length,
            });
            setInstructors(response.data);
            setTotal(response.data.length);
            setMetadata(null);
          } else {
            // Filters applied - response with metadata
            logger.info('Received filtered response with metadata', {
              instructorCount: response.data.instructors.length,
              metadata: response.data.metadata,
            });
            setInstructors(response.data.instructors);
            setTotal(response.data.metadata.active_instructors);
            setMetadata(response.data.metadata);
          }
        }
      } catch (err) {
        logger.error('Failed to fetch search results', err as Error);
        setError('Failed to load search results');
      } finally {
        setLoading(false);
      }
    }

    fetchResults();
  }, [query, category, availableNow, page]);

  // Mock next available times (in real app, would come from API)
  const getNextAvailableTimes = (instructorId: string) => {
    const times = [
      { day: 'Today', time: '2:00 PM' },
      { day: 'Tomorrow', time: '10:00 AM' },
      { day: 'Wed', time: '9:00 AM' },
    ];
    return times.slice(0, 3);
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
              <Link href="/" className="mr-4">
                <ChevronLeft className="h-6 w-6 text-gray-600" />
              </Link>
              <h1 className="text-xl font-semibold text-gray-900">
                {query
                  ? `Results for "${query}"`
                  : category
                    ? formatSubject(category)
                    : 'All Instructors'}
              </h1>
              {total > 0 && <span className="ml-2 text-gray-600">({total} found)</span>}
            </div>
            <button className="flex items-center px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50">
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
          <div className="text-center py-12">
            <p className="text-gray-600 text-lg mb-4">No instructors found matching your search.</p>
            <Link href="/" className="text-blue-600 hover:underline">
              Try a different search
            </Link>
          </div>
        ) : (
          <>
            {/* Results Grid */}
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {instructors.map((instructor) => (
                <div
                  key={instructor.id}
                  className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden hover:shadow-lg transition-shadow"
                >
                  <div className="p-6">
                    {/* Header with photo placeholder and name */}
                    <div className="flex items-start mb-4">
                      <div className="w-20 h-20 bg-gray-200 rounded-lg mr-4 flex-shrink-0">
                        <div className="w-full h-full flex items-center justify-center text-gray-400">
                          Photo
                        </div>
                      </div>
                      <div className="flex-1">
                        <h3 className="font-semibold text-lg text-gray-900">
                          {instructor.user.full_name}
                        </h3>
                        <p className="text-gray-600">
                          {instructor.services.map((s) => formatSubject(s.skill)).join(', ')} Expert
                        </p>
                        <div className="flex items-center mt-1">
                          <Star className="h-4 w-4 text-yellow-500 fill-current" />
                          <span className="ml-1 text-sm font-medium">
                            {instructor.rating || 4.8}
                          </span>
                          <span className="text-sm text-gray-600 ml-1">
                            ({instructor.total_reviews || Math.floor(Math.random() * 100) + 20}{' '}
                            reviews)
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Info row */}
                    <div className="flex items-center text-sm text-gray-600 mb-4">
                      <MapPin className="h-4 w-4 mr-1" />
                      <span>{instructor.areas_of_service[0] || 'Manhattan'}</span>
                      <span className="mx-2">·</span>
                      <span className="font-medium text-gray-900">
                        ${instructor.services[0]?.hourly_rate || 0}/hour
                      </span>
                    </div>

                    {/* Features */}
                    <div className="space-y-2 mb-4">
                      <div className="flex items-center text-sm text-gray-600">
                        <Check className="h-4 w-4 text-green-600 mr-2" />
                        Background checked
                      </div>
                      <div className="flex items-center text-sm text-gray-600">
                        <Check className="h-4 w-4 text-green-600 mr-2" />
                        Teaches all levels
                      </div>
                      <div className="flex items-center text-sm text-gray-600">
                        <Check className="h-4 w-4 text-green-600 mr-2" />
                        {instructor.years_experience} years experience
                      </div>
                    </div>

                    {/* Next available times */}
                    <div className="mb-4">
                      <p className="text-sm font-medium text-gray-900 mb-2">Next available:</p>
                      <div className="flex gap-2 flex-wrap">
                        {getNextAvailableTimes(String(instructor.id)).map((slot, idx) => (
                          <button
                            key={idx}
                            className="px-3 py-2 bg-gray-100 rounded-lg text-sm hover:bg-gray-200"
                          >
                            <div className="font-medium">{slot.day}</div>
                            <div className="text-gray-600">{slot.time}</div>
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex gap-3">
                      <Link
                        href={`/instructors/${instructor.id}`}
                        className="flex-1 text-center py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
                      >
                        View Profile
                      </Link>
                      <Link
                        href={`/book/${instructor.id}`}
                        className="flex-1 text-center py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                      >
                        Book Now →
                      </Link>
                    </div>
                  </div>
                </div>
              ))}
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
