// frontend/app/instructors/page.tsx

/**
 * Browse Instructors Page
 *
 * This page displays a searchable grid of all available instructors.
 * Users can search by instructor name or skills they teach.
 * Each instructor card shows their services, pricing, experience, and areas served.
 *
 * @module instructors/page
 */

import Link from 'next/link';
import { BRAND } from '@/app/config/brand';
import { logger } from '@/lib/logger';
import { publicApi } from '@/features/shared/api/client';
import SearchInput from '@/components/SearchInput';

// Import centralized types
import type { InstructorProfile, InstructorService } from '@/types/instructor';
import { getErrorMessage } from '@/types/common';

/**
 * Main instructors browse page component
 *
 * @component
 * @returns {JSX.Element} The instructors browse page
 */
export default async function InstructorsPage({
  searchParams,
}: {
  searchParams: Promise<{ search?: string }>;
}) {
  const resolvedSearchParams = await searchParams;
  const urlSearchQuery = resolvedSearchParams.search || '';

  // Fetch instructors server-side
  let instructors: InstructorProfile[] = [];
  let error: string | null = null;

  try {
    // Use new API client with proper filtering
    const response = await publicApi.searchInstructors({
      search: urlSearchQuery || undefined,
    });

    if (response.data) {
      // Handle both filtered and unfiltered responses
      if (Array.isArray(response.data)) {
        instructors = response.data as InstructorProfile[];
      } else if (response.data.instructors) {
        instructors = response.data.instructors as InstructorProfile[];
      } else {
        instructors = [];
      }
    } else {
      throw new Error(response.error || 'Failed to fetch instructors');
    }
  } catch (err) {
    error = getErrorMessage(err);
  }

  /**
   * Get the minimum hourly rate from an instructor's services
   *
   * @param {InstructorService[]} services - Array of services
   * @returns {number} Minimum hourly rate
   */
  const getMinimumRate = (services: InstructorService[]): number => {
    if (services.length === 0) return 0;
    return Math.min(...services.map((s) => s.hourly_rate));
  };

  // Error state
  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-red-500 text-center">
          <h2 className="text-2xl font-bold mb-2">Error</h2>
          <p>{error}</p>
          <Link
            href="/instructors"
            className="mt-4 inline-block px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            Try Again
          </Link>
        </div>
      </div>
    );
  }

  return (
    <>
      {/* Simple Navbar */}
      <nav className="bg-white dark:bg-gray-800 shadow-sm border-b dark:border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link
              href="/"
              className="text-2xl font-bold text-indigo-600 dark:text-indigo-400"
              onClick={() => logger.info('Navigating to home from navbar')}
            >
              {BRAND.name}
            </Link>
            <Link
              href="/"
              className="text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100"
              onClick={() => logger.info('Navigating to home from back link')}
            >
              Back to Home
            </Link>
          </div>
        </div>
      </nav>

      <div className="container mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-center mb-8 dark:text-white">
          Find Your Perfect Instructor
        </h1>

        {/* Search Bar */}
        <SearchInput initialValue={urlSearchQuery} />

        {/* Results summary */}
        {urlSearchQuery && (
          <p className="text-center text-gray-600 dark:text-gray-400 mb-4">
            Found {instructors.length} instructor
            {instructors.length !== 1 ? 's' : ''}
            {urlSearchQuery && ` matching "${urlSearchQuery}"`}
          </p>
        )}

        {/* Instructor Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {instructors.map((instructor) => (
            <div
              key={instructor.id}
              className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow"
            >
              <h2 className="text-xl font-semibold mb-2 dark:text-white">
                {instructor.user.full_name}
              </h2>
              <p className="text-gray-600 dark:text-gray-300 mb-4 line-clamp-3">
                {instructor.bio.length > 100
                  ? `${instructor.bio.substring(0, 100)}...`
                  : instructor.bio}
              </p>

              {/* Services with individual pricing */}
              <div className="mb-4">
                <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
                  Services:
                </h3>
                <div className="space-y-1">
                  {instructor.services.map((service) => (
                    <div key={service.id} className="flex justify-between items-center">
                      <span className="text-sm text-gray-600 dark:text-gray-400">
                        {service.skill}
                      </span>
                      <span className="text-sm font-medium dark:text-white">
                        ${service.hourly_rate}/hr
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Areas of Service */}
              <div className="mb-4">
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Areas: {instructor.areas_of_service.join(', ')}
                </p>
              </div>

              {/* Experience and pricing summary */}
              <div className="flex justify-between items-center mb-4 text-sm text-gray-600 dark:text-gray-400">
                <span>{instructor.years_experience} years exp.</span>
                <span className="text-xs">From ${getMinimumRate(instructor.services)}/hr</span>
              </div>

              <Link
                href={`/instructors/${instructor.user_id}`}
                className="w-full bg-blue-500 text-white py-2 rounded-lg hover:bg-blue-600 dark:bg-blue-600 dark:hover:bg-blue-700 transition-colors text-center block"
                aria-label={`View profile for ${instructor.user.full_name}`}
              >
                View Profile
              </Link>
            </div>
          ))}
        </div>

        {/* Empty state */}
        {instructors.length === 0 && (
          <div className="text-center text-gray-500 dark:text-gray-400 mt-8">
            <p className="text-lg">No instructors found matching your search.</p>
            {urlSearchQuery && (
              <Link
                href="/instructors"
                className="mt-4 text-blue-500 hover:text-blue-600 underline inline-block"
              >
                Clear search
              </Link>
            )}
          </div>
        )}
      </div>
    </>
  );
}
