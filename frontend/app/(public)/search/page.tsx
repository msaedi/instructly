// frontend/app/(public)/search/page.tsx
'use client';

import { useEffect, useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Star, MapPin, Check, ChevronLeft, Filter } from 'lucide-react';
import { publicApi } from '@/features/shared/api/client';
import { parseSearchQuery } from '@/features/shared/utils/search-parser';
import { logger } from '@/lib/logger';
import InstructorCard from '@/components/InstructorCard';

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

  // Generate realistic next available times (deterministic for SSR)
  const getNextAvailableSlots = (instructorId: number) => {
    // Some instructors may not have availability (e.g., Sarah Chen with ID 100)
    // Simulate this by having certain instructor IDs return no availability
    const instructorsWithNoAvailability = [100]; // Sarah Chen
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
      const baseHours = [9, 11, 14, 16, 18]; // 9 AM, 11 AM, 2 PM, 4 PM, 6 PM
      const hourIndex = (instructorId + i) % baseHours.length;
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
          <div className="text-center py-12">
            <p className="text-gray-600 text-lg mb-4">No instructors found matching your search.</p>
            <Link href="/" className="text-blue-600 hover:underline">
              Try a different search
            </Link>
          </div>
        ) : (
          <>
            {/* Results Grid */}
            <div className="grid gap-6 md:grid-cols-1 lg:grid-cols-2 xl:grid-cols-3">
              {instructors.map((instructor) => {
                // Add mock rating and reviews
                const enhancedInstructor = {
                  ...instructor,
                  rating: instructor.rating || 4.8,
                  total_reviews: instructor.total_reviews || Math.floor(Math.random() * 100) + 20,
                  verified: true,
                };

                return (
                  <InstructorCard
                    key={instructor.id}
                    instructor={enhancedInstructor}
                    nextAvailableSlots={getNextAvailableSlots(instructor.user_id)}
                  />
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
