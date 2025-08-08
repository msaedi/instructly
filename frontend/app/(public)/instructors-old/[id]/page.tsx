'use client';
// frontend/app/(public)/instructors-old/[id]/page.tsx

import { useParams } from 'next/navigation';
import Link from 'next/link';
import { Star, MapPin, Check, Clock, BookOpen } from 'lucide-react';
import { publicApi } from '@/features/shared/api/client';
import AvailabilityCalendar from '@/components/AvailabilityCalendar';
import InstructorProfileNav from '@/components/InstructorProfileNav';

// Mock instructor data - replace with actual API when available
const getMockInstructorData = (id: string) => {
  return {
    id: id,
    user_id: parseInt(id),
    bio: 'Passionate piano instructor with over 5 years of experience teaching students of all ages and skill levels. I believe in making music fun and accessible while building strong technical foundations.',
    areas_of_service: ['Manhattan', 'Brooklyn', 'Virtual'],
    years_experience: 5,
    min_advance_booking_hours: 2,
    buffer_time_minutes: 15,
    created_at: '2023-01-15T10:00:00Z',
    user: {
      full_name: 'Sarah Chen',
      email: 'sarah@example.com',
    },
    services: [
      {
        id: 1,
        skill: 'Piano',
        hourly_rate: 75,
        description: 'Classical and contemporary piano lessons for all levels',
        duration: 60,
        is_active: true,
      },
      {
        id: 2,
        skill: 'Music Theory',
        hourly_rate: 60,
        description: 'Comprehensive music theory and composition',
        duration: 60,
        is_active: true,
      },
    ],
    // Additional profile fields
    rating: 4.9,
    total_reviews: 127,
    total_hours_taught: 850,
    education: 'Master of Music, Juilliard School',
    languages: ['English', 'Mandarin'],
    verified: true,
  };
};

export default function InstructorProfilePage() {
  const params = useParams();
  const instructorId = params.id as string;

  // For now, use mock data. Replace with actual API call:
  // const response = await publicApi.getInstructorProfile(instructorId);
  // if (response.error || !response.data) {
  //   notFound();
  // }
  // const instructor = response.data;

  const instructor = getMockInstructorData(instructorId);

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
                    {instructor.services.map((s) => s.skill).join(', ')} Expert
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
                      <h4 className="font-medium text-gray-900 dark:text-white">{service.skill}</h4>
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
                      <span>{service.duration} minutes</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right Column - Availability Calendar */}
          <div className="lg:col-span-2">
            <AvailabilityCalendar instructorId={instructorId} instructor={instructor as any} />
          </div>
        </div>
      </div>
    </div>
  );
}
