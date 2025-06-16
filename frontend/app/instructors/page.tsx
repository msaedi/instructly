// frontend/app/instructors/page.tsx
"use client";

/**
 * Browse Instructors Page
 * 
 * This page displays a searchable grid of all available instructors.
 * Users can search by instructor name or skills they teach.
 * Each instructor card shows their services, pricing, experience, and areas served.
 * 
 * @module instructors/page
 */

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import Link from "next/link";
import { fetchAPI, API_ENDPOINTS } from '@/lib/api';
import { BRAND } from '@/app/config/brand';
import { logger } from '@/lib/logger';

// Import centralized types
import type { InstructorProfile, InstructorService } from '@/types/instructor';
import { RequestStatus } from '@/types/api';
import { getErrorMessage } from '@/types/common';

/**
 * Main instructors browse page component
 * 
 * @component
 * @returns {JSX.Element} The instructors browse page
 */
export default function InstructorsPage() {
  // State management with proper typing
  const [instructors, setInstructors] = useState<InstructorProfile[]>([]);
  const [filteredInstructors, setFilteredInstructors] = useState<InstructorProfile[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [requestStatus, setRequestStatus] = useState<RequestStatus>(RequestStatus.IDLE);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  /**
   * Fetch instructors from the API
   */
  useEffect(() => {
    const fetchInstructors = async () => {
      logger.info('Fetching instructors list');
      setRequestStatus(RequestStatus.LOADING);
      
      try {
        logger.time('fetchInstructors');
        const response = await fetchAPI(API_ENDPOINTS.INSTRUCTORS);
        
        if (!response.ok) {
          throw new Error(`Failed to fetch instructors: ${response.status} ${response.statusText}`);
        }
        
        const data: InstructorProfile[] = await response.json();
        logger.timeEnd('fetchInstructors');
        
        logger.info('Instructors fetched successfully', { 
          count: data.length,
          hasServices: data.filter(i => i.services.length > 0).length
        });
        
        setInstructors(data);
        setFilteredInstructors(data);
        setRequestStatus(RequestStatus.SUCCESS);
      } catch (err) {
        const errorMessage = getErrorMessage(err);
        logger.error('Failed to fetch instructors', err, { 
          endpoint: API_ENDPOINTS.INSTRUCTORS 
        });
        
        setError(errorMessage);
        setRequestStatus(RequestStatus.ERROR);
      }
    };

    fetchInstructors();
  }, []);

  /**
   * Filter instructors based on search query
   */
  useEffect(() => {
    if (!searchQuery.trim()) {
      setFilteredInstructors(instructors);
      return;
    }

    logger.time('filterInstructors');
    logger.debug('Filtering instructors', { 
      query: searchQuery, 
      totalInstructors: instructors.length 
    });
    
    const searchLower = searchQuery.toLowerCase().trim();
    const filtered = instructors.filter((instructor) => {
      // Search by name
      const nameMatch = instructor.user.full_name.toLowerCase().includes(searchLower);
      
      // Search by skills
      const skillMatch = instructor.services.some((service) => 
        service.skill.toLowerCase().includes(searchLower)
      );
      
      // Search by areas (bonus search capability)
      const areaMatch = instructor.areas_of_service.some((area) =>
        area.toLowerCase().includes(searchLower)
      );
      
      return nameMatch || skillMatch || areaMatch;
    });
    
    logger.timeEnd('filterInstructors');
    logger.debug('Filter results', { 
      query: searchQuery,
      resultsCount: filtered.length,
      filteredOut: instructors.length - filtered.length
    });
    
    setFilteredInstructors(filtered);
  }, [searchQuery, instructors]);

  /**
   * Handle instructor card click
   * 
   * @param {number} userId - The user ID of the instructor
   */
  const handleViewProfile = (userId: number) => {
    logger.info('Navigating to instructor profile', { userId });
    router.push(`/instructors/${userId}`);
  };

  /**
   * Get the minimum hourly rate from an instructor's services
   * 
   * @param {InstructorService[]} services - Array of services
   * @returns {number} Minimum hourly rate
   */
  const getMinimumRate = (services: InstructorService[]): number => {
    if (services.length === 0) return 0;
    return Math.min(...services.map(s => s.hourly_rate));
  };

  // Loading state
  if (requestStatus === RequestStatus.LOADING) {
    logger.debug('Rendering loading state');
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  // Error state
  if (requestStatus === RequestStatus.ERROR) {
    logger.debug('Rendering error state', { error });
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-red-500 text-center">
          <h2 className="text-2xl font-bold mb-2">Error</h2>
          <p>{error}</p>
          <button 
            onClick={() => window.location.reload()} 
            className="mt-4 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  logger.debug('Rendering instructors page', { 
    totalInstructors: instructors.length,
    displayedInstructors: filteredInstructors.length,
    hasSearchQuery: !!searchQuery
  });

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
        <div className="max-w-2xl mx-auto mb-8">
          <div className="relative">
            <input
              type="text"
              placeholder="Search by name, skill, or area..."
              value={searchQuery}
              onChange={(e) => {
                const newQuery = e.target.value;
                logger.debug('Search query changed', { 
                  oldQuery: searchQuery, 
                  newQuery 
                });
                setSearchQuery(newQuery);
              }}
              className="w-full px-4 py-2 pl-10 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:border-gray-700 dark:text-white"
              aria-label="Search instructors"
            />
            <Search className="absolute left-3 top-2.5 h-5 w-5 text-gray-400" aria-hidden="true" />
          </div>
        </div>

        {/* Results summary */}
        {searchQuery && (
          <p className="text-center text-gray-600 dark:text-gray-400 mb-4">
            Found {filteredInstructors.length} instructor{filteredInstructors.length !== 1 ? 's' : ''} 
            {searchQuery && ` matching "${searchQuery}"`}
          </p>
        )}

        {/* Instructor Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredInstructors.map((instructor) => (
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
                  Areas: {instructor.areas_of_service.join(", ")}
                </p>
              </div>

              {/* Experience and pricing summary */}
              <div className="flex justify-between items-center mb-4 text-sm text-gray-600 dark:text-gray-400">
                <span>{instructor.years_experience} years exp.</span>
                <span className="text-xs">
                  From ${getMinimumRate(instructor.services)}/hr
                </span>
              </div>

              <button
                onClick={() => handleViewProfile(instructor.user_id)}
                className="w-full bg-blue-500 text-white py-2 rounded-lg hover:bg-blue-600 transition-colors"
                aria-label={`View profile for ${instructor.user.full_name}`}
              >
                View Profile
              </button>
            </div>
          ))}
        </div>

        {/* Empty state */}
        {filteredInstructors.length === 0 && (
          <div className="text-center text-gray-500 dark:text-gray-400 mt-8">
            <p className="text-lg">No instructors found matching your search.</p>
            {searchQuery && (
              <button
                onClick={() => {
                  logger.info('Clearing search query');
                  setSearchQuery("");
                }}
                className="mt-4 text-blue-500 hover:text-blue-600 underline"
              >
                Clear search
              </button>
            )}
          </div>
        )}
      </div>
    </>
  );
}