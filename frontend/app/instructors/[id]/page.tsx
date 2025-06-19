// frontend/app/instructors/[id]/page.tsx
'use client';

/**
 * Individual Instructor Profile Page
 *
 * This page displays detailed information about a specific instructor,
 * including their bio, services with pricing, areas served, and experience.
 * Provides actions to book a session or message the instructor.
 *
 * @module instructors/[id]/page
 */

import { useState, useEffect, use } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, MessageCircle, Calendar } from 'lucide-react';
import { fetchAPI } from '@/lib/api';
import { BRAND } from '@/app/config/brand';
import { logger } from '@/lib/logger';

// Import centralized types
import type { InstructorProfile } from '@/types/instructor';
import { RequestStatus } from '@/types/api';
import { getErrorMessage } from '@/types/common';

/**
 * Instructor Profile Page Component
 *
 * Displays detailed information about a specific instructor
 *
 * @component
 * @param {Object} props - Component props
 * @param {Promise<{id: string}>} props.params - Route parameters containing instructor ID
 * @returns {JSX.Element} The instructor profile page
 */
export default function InstructorProfilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [instructor, setInstructor] = useState<InstructorProfile | null>(null);
  const [requestStatus, setRequestStatus] = useState<RequestStatus>(RequestStatus.IDLE);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    /**
     * Fetch instructor profile data from API
     */
    const fetchInstructor = async () => {
      logger.info('Fetching instructor profile', { instructorId: id });
      setRequestStatus(RequestStatus.LOADING);

      try {
        logger.time(`fetchInstructor-${id}`);
        const response = await fetchAPI(`/instructors/${id}`);
        logger.timeEnd(`fetchInstructor-${id}`);

        if (!response.ok) {
          if (response.status === 404) {
            logger.warn('Instructor not found', {
              instructorId: id,
              status: response.status,
            });
            throw new Error('Instructor not found');
          }

          logger.error('Failed to fetch instructor profile', null, {
            instructorId: id,
            status: response.status,
            statusText: response.statusText,
          });
          throw new Error('Failed to fetch instructor profile');
        }

        const data: InstructorProfile = await response.json();
        logger.info('Instructor profile fetched successfully', {
          instructorId: id,
          userId: data.user_id,
          servicesCount: data.services.length,
          areasCount: data.areas_of_service.length,
        });

        setInstructor(data);
        setRequestStatus(RequestStatus.SUCCESS);
      } catch (err) {
        const errorMessage = getErrorMessage(err);
        logger.error('Error fetching instructor profile', err, {
          instructorId: id,
          errorMessage,
        });

        setError(errorMessage);
        setRequestStatus(RequestStatus.ERROR);
      }
    };

    if (id) {
      fetchInstructor();
    } else {
      logger.warn('No instructor ID provided in route params');
      setError('Invalid instructor ID');
      setRequestStatus(RequestStatus.ERROR);
    }
  }, [id]);

  /**
   * Handle back navigation to instructors list
   */
  const handleBackClick = () => {
    logger.info('Navigating back to instructors list from profile', {
      instructorId: id,
    });
    router.push('/instructors');
  };

  /**
   * Handle book session button click
   */
  const handleBookSession = () => {
    logger.info('Book session clicked', {
      instructorId: id,
      instructorName: instructor?.user.full_name,
    });
    // TODO: Implement booking flow navigation
    logger.warn('Book session not yet implemented', { instructorId: id });
  };

  /**
   * Handle message instructor button click
   */
  const handleMessageInstructor = () => {
    logger.info('Message instructor clicked', {
      instructorId: id,
      instructorName: instructor?.user.full_name,
    });
    // TODO: Implement messaging feature
    logger.warn('Messaging feature not yet implemented', { instructorId: id });
  };

  // Loading state
  if (requestStatus === RequestStatus.LOADING) {
    logger.debug('Rendering loading state for instructor profile', { instructorId: id });
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div
          className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"
          role="status"
          aria-label="Loading instructor profile"
        ></div>
      </div>
    );
  }

  // Error state
  if (requestStatus === RequestStatus.ERROR) {
    logger.debug('Rendering error state for instructor profile', {
      instructorId: id,
      error,
    });
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-red-500 mb-2">Error</h2>
          <p className="text-gray-600 dark:text-gray-400 mb-4">{error}</p>
          <button
            onClick={handleBackClick}
            className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
            aria-label="Go back to instructors list"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Browse
          </button>
        </div>
      </div>
    );
  }

  // Instructor not found (should not happen after error handling above)
  if (!instructor) {
    logger.error('Instructor data is null after successful fetch', null, {
      instructorId: id,
    });
    return null;
  }

  logger.debug('Rendering instructor profile', {
    instructorId: id,
    instructorName: instructor.user.full_name,
  });

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="container mx-auto px-4 py-8">
        {/* Back Button */}
        <button
          onClick={handleBackClick}
          className="flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 mb-8 transition-colors"
          aria-label="Go back to instructors list"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Browse
        </button>

        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg overflow-hidden">
          {/* Header Section */}
          <div className="p-8 border-b dark:border-gray-700">
            <h1 className="text-3xl font-bold mb-4 dark:text-white">{instructor.user.full_name}</h1>
            <div className="flex flex-wrap gap-4 text-gray-600 dark:text-gray-400">
              <div className="flex items-center gap-2">
                <svg
                  className="h-5 w-5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
                  />
                </svg>
                <span>Areas: {instructor.areas_of_service.join(', ')}</span>
              </div>
              <div className="flex items-center gap-2">
                <svg
                  className="h-5 w-5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <span>{instructor.years_experience} years experience</span>
              </div>
            </div>
          </div>

          {/* Main Content */}
          <div className="p-8">
            {/* Services & Pricing Section */}
            <section className="mb-8" aria-labelledby="services-heading">
              <h2 id="services-heading" className="text-xl font-semibold mb-4 dark:text-white">
                Services & Pricing
              </h2>
              <div className="space-y-3">
                {instructor.services.map((service) => (
                  <div
                    key={service.id}
                    className="flex justify-between items-start p-4 bg-gray-50 dark:bg-gray-700 rounded-lg"
                  >
                    <div>
                      <h3 className="font-medium text-gray-900 dark:text-white">{service.skill}</h3>
                      {service.description && (
                        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                          {service.description}
                        </p>
                      )}
                    </div>
                    <div className="text-lg font-semibold text-blue-600 dark:text-blue-400">
                      ${service.hourly_rate}/hr
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* Bio Section */}
            <section className="mb-8" aria-labelledby="about-heading">
              <h2 id="about-heading" className="text-xl font-semibold mb-4 dark:text-white">
                About
              </h2>
              <p className="text-gray-700 dark:text-gray-300 leading-relaxed">{instructor.bio}</p>
            </section>

            {/* Action Buttons */}
            <div className="flex flex-col sm:flex-row gap-4">
              <button
                onClick={handleBookSession}
                className="flex-1 flex items-center justify-center gap-2 bg-blue-500 text-white px-6 py-3 rounded-lg hover:bg-blue-600 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                aria-label={`Book a session with ${instructor.user.full_name}`}
              >
                <Calendar className="h-5 w-5" />
                Book a Session
              </button>
              <button
                onClick={handleMessageInstructor}
                className="flex-1 flex items-center justify-center gap-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 px-6 py-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500"
                aria-label={`Send a message to ${instructor.user.full_name}`}
              >
                <MessageCircle className="h-5 w-5" />
                Message Instructor
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
