// frontend/app/instructors/[id]/page.tsx

import { notFound } from 'next/navigation';
import Link from 'next/link';
import { Star, MapPin, Check, Clock, BookOpen } from 'lucide-react';
import { publicApi } from '@/features/shared/api/client';
import AvailabilityCalendar from '@/components/AvailabilityCalendar';
import InstructorProfileNav from '@/components/InstructorProfileNav';
import { logger } from '@/lib/logger';

// Force dynamic rendering to avoid build-time API calls
export const dynamic = 'force-dynamic';

interface InstructorProfilePageProps {
  params: Promise<{ id: string }>;
}

// Define the instructor data type based on what we expect from the API
interface InstructorData {
  user_id: number;
  bio: string;
  areas_of_service: string[];
  years_experience: number;
  min_advance_booking_hours: number;
  buffer_time_minutes: number;
  created_at: string;
  updated_at?: string;
  user: {
    full_name: string;
    email: string;
  };
  services: Array<{
    id: number;
    service_catalog_id: number;
    name?: string;
    hourly_rate: number;
    description?: string;
    duration_options: number[];
    is_active?: boolean;
  }>;
  // Additional fields that might come from the API
  rating?: number;
  total_reviews?: number;
  total_hours_taught?: number;
  education?: string;
  languages?: string[];
  verified?: boolean;
}

export default async function InstructorProfilePage({ params }: InstructorProfilePageProps) {
  const resolvedParams = await params;
  const instructorId = resolvedParams.id;

  logger.info('Loading instructor profile page', { instructorId });

  let instructor: InstructorData | null = null;
  let error: string | null = null;

  try {
    // Use the direct instructor profile endpoint
    const response = await publicApi.getInstructorProfile(instructorId);

    logger.debug('API Response received', {
      hasData: !!response.data,
      hasError: !!response.error,
      status: response.status,
    });

    if (response.error) {
      logger.error('API Error from get instructor profile', undefined, { error: response.error });
      throw new Error(response.error);
    }

    if (response.data) {
      instructor = {
        ...response.data,
        // Add default values for fields that might not be in the API response
        rating: response.data.rating || 4.8,
        total_reviews: response.data.total_reviews || Math.floor(Math.random() * 200) + 50,
        total_hours_taught:
          response.data.total_hours_taught || Math.floor(Math.random() * 1000) + 500,
        education: response.data.education || 'Professional Music Education',
        languages: response.data.languages || ['English'],
        verified: response.data.verified !== undefined ? response.data.verified : true,
      };
    } else {
      notFound();
    }
  } catch (err) {
    logger.error('Error fetching instructor', err, { instructorId });
    error = 'Failed to load instructor profile';
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Error</h1>
          <p className="text-gray-600 dark:text-gray-400 mb-4">{error}</p>
          <Link
            href="/search"
            className="inline-block px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Back to Search
          </Link>
        </div>
      </div>
    );
  }

  if (!instructor) {
    notFound();
  }

  const getMinimumRate = () => {
    if (instructor.services.length === 0) return 0;
    return Math.min(...instructor.services.map((s) => s.hourly_rate));
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Navigation */}
      <InstructorProfileNav instructorName={instructor.user.full_name} />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid lg:grid-cols-3 gap-8">
          {/* Left Column - Instructor Info */}
          <div className="lg:col-span-1 space-y-6">
            {/* Profile Card */}
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              {/* Photo and Basic Info */}
              <div className="flex items-start mb-6">
                <div className="w-20 h-20 bg-gray-200 dark:bg-gray-700 rounded-lg mr-4 flex-shrink-0">
                  <div className="w-full h-full flex items-center justify-center text-gray-400 text-xs">
                    80×80px
                  </div>
                </div>
                <div className="flex-1">
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-1">
                    {instructor.user.full_name}
                  </h2>
                  <p className="text-gray-600 dark:text-gray-300 mb-2">
                    {instructor.services
                      .map((s) => s.name || `Service ${s.service_catalog_id}`)
                      .join(', ')}{' '}
                    Expert
                  </p>
                  <div className="flex items-center">
                    <Star className="h-4 w-4 text-yellow-500 fill-current" />
                    <span className="ml-1 text-sm font-medium dark:text-white">
                      {instructor.rating}
                    </span>
                    <span className="text-sm text-gray-600 dark:text-gray-400 ml-1">
                      ({instructor.total_reviews} reviews)
                    </span>
                  </div>
                </div>
              </div>

              {/* Location and Rate */}
              <div className="flex items-center text-sm text-gray-600 dark:text-gray-400 mb-4">
                <MapPin className="h-4 w-4 mr-1" />
                <span>{instructor.areas_of_service[0]}</span>
                <span className="mx-2">·</span>
                <span className="font-medium text-gray-900 dark:text-white">
                  From ${getMinimumRate()}/hour
                </span>
              </div>

              {/* Features */}
              <div className="space-y-2 mb-6">
                {instructor.verified && (
                  <div className="flex items-center text-sm text-gray-600 dark:text-gray-400">
                    <Check className="h-4 w-4 text-green-600 mr-2" />
                    Background verified
                  </div>
                )}
                <div className="flex items-center text-sm text-gray-600 dark:text-gray-400">
                  <Check className="h-4 w-4 text-green-600 mr-2" />
                  Teaches all levels
                </div>
                <div className="flex items-center text-sm text-gray-600 dark:text-gray-400">
                  <Check className="h-4 w-4 text-green-600 mr-2" />
                  {instructor.years_experience} years experience
                </div>
                <div className="flex items-center text-sm text-gray-600 dark:text-gray-400">
                  <BookOpen className="h-4 w-4 text-green-600 mr-2" />
                  {instructor.total_hours_taught}+ hours taught
                </div>
              </div>

              {/* Education */}
              {instructor.education && (
                <div className="mb-4">
                  <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    Education
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{instructor.education}</p>
                </div>
              )}

              {/* Languages */}
              {instructor.languages && instructor.languages.length > 0 && (
                <div className="mb-4">
                  <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    Languages
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    {instructor.languages.join(', ')}
                  </p>
                </div>
              )}

              {/* Areas of Service */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                  Areas of Service
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {instructor.areas_of_service.join(', ')}
                </p>
              </div>
            </div>

            {/* About Section */}
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">About</h3>
              <p className="text-gray-600 dark:text-gray-300 leading-relaxed">{instructor.bio}</p>
            </div>

            {/* Services */}
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                Services & Pricing
              </h3>
              <div className="space-y-4">
                {instructor.services.map((service) => (
                  <div
                    key={service.id}
                    className="border border-gray-200 dark:border-gray-600 rounded-lg p-4"
                  >
                    <div className="flex justify-between items-start mb-2">
                      <h4 className="font-medium text-gray-900 dark:text-white">
                        {service.name || `Service ${service.service_catalog_id}`}
                      </h4>
                      <span className="text-lg font-semibold text-gray-900 dark:text-white">
                        ${service.hourly_rate}/hr
                      </span>
                    </div>
                    {service.description && (
                      <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                        {service.description}
                      </p>
                    )}
                    <div className="flex items-center text-sm text-gray-500 dark:text-gray-400">
                      <Clock className="h-4 w-4 mr-1" />
                      <span>{service.duration_options?.join(', ') || '60'} minutes</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right Column - Availability Calendar */}
          <div className="lg:col-span-2">
            <AvailabilityCalendar
              instructorId={instructor.user_id.toString()}
              instructor={{
                ...instructor,
                id: instructor.user_id,
                services: instructor.services.map((service) => ({
                  ...service,
                  skill: service.name || `Service ${service.service_catalog_id}`,
                  duration: service.duration_options[0] || 60,
                })),
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
