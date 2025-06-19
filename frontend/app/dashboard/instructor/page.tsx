// frontend/app/dashboard/instructor/page.tsx
'use client';

import { BRAND } from '@/app/config/brand';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { Edit, Calendar, ExternalLink, LogOut, Trash2 } from 'lucide-react';
import EditProfileModal from '@/components/modals/EditProfileModal';
import DeleteProfileModal from '@/components/modals/DeleteProfileModal';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { logger } from '@/lib/logger';
import { InstructorProfile, getInstructorDisplayName } from '@/types/instructor';

/**
 * InstructorDashboard Component
 *
 * Main dashboard interface for instructors. Provides an overview of their
 * profile, quick stats, and access to key management features.
 *
 * Features:
 * - Profile information display and editing
 * - Quick stats overview (bookings, ratings, earnings)
 * - Quick actions for common tasks (manage availability)
 * - Public profile preview link
 * - Profile deletion option
 * - Authentication protection with redirect
 *
 * @component
 * @example
 * ```tsx
 * // This is a page component, typically accessed via routing
 * // Route: /dashboard/instructor
 * ```
 */
export default function InstructorDashboard() {
  const router = useRouter();
  const [profile, setProfile] = useState<InstructorProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  /**
   * Fetch instructor profile data
   * Redirects to login if not authenticated
   * Handles 404 case for instructors without profiles
   */
  const fetchProfile = async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      logger.warn('No access token found, redirecting to login');
      router.push('/login?redirect=/dashboard/instructor');
      return;
    }

    try {
      logger.info('Fetching instructor profile');
      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);

      if (response.status === 404) {
        logger.warn('No instructor profile found');
        setError('No instructor profile found. Please complete your profile setup.');
        setIsLoading(false);
        return;
      }

      if (!response.ok) {
        throw new Error('Failed to fetch profile');
      }

      const data: InstructorProfile = await response.json();

      // Validate data structure
      if (!data.user || !data.services) {
        logger.error('Invalid profile data structure', undefined, { data });
        throw new Error('Invalid profile data received');
      }

      logger.info('Instructor profile loaded successfully', {
        userId: data.user_id,
        servicesCount: data.services.length,
        areasCount: data.areas_of_service?.length || 0,
      });

      setProfile(data);
    } catch (err) {
      logger.error('Error fetching instructor profile', err);
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    logger.info('Instructor dashboard loaded');
    fetchProfile();
  }, [router]);

  /**
   * Handle user logout
   * Clears authentication token and redirects to home
   */
  const handleLogout = () => {
    logger.info('Instructor logging out');
    localStorage.removeItem('access_token');
    router.push('/');
  };

  /**
   * Handle successful profile update
   * Refreshes profile data and closes modal
   */
  const handleProfileUpdate = () => {
    logger.info('Profile updated, refreshing data');
    fetchProfile();
    setShowEditModal(false);
  };

  /**
   * Handle successful profile deletion
   * Redirects to student dashboard after deletion
   */
  const handleProfileDelete = () => {
    logger.info('Instructor profile deleted, redirecting to student dashboard');
    router.push('/dashboard/student');
  };

  /**
   * Handle navigation to public profile
   */
  const handleViewPublicProfile = () => {
    if (profile) {
      logger.debug('Navigating to public profile', { userId: profile.user_id });
      router.push(`/instructors/${profile.user_id}`);
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  // Error state (no profile found)
  if (error) {
    return (
      <div className="min-h-screen bg-gray-50">
        <nav className="bg-white shadow-sm border-b">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between items-center h-16">
              <Link href="/" className="text-2xl font-bold text-indigo-600">
                {BRAND.name}
              </Link>
              <button
                onClick={handleLogout}
                className="flex items-center text-gray-600 hover:text-gray-900 transition-colors"
              >
                <LogOut className="h-5 w-5 mr-2" />
                Log out
              </button>
            </div>
          </div>
        </nav>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
          <div className="bg-white rounded-lg shadow p-6 text-center">
            <h2 className="text-2xl font-bold text-red-600 mb-4">Error</h2>
            <p className="text-gray-600 mb-6">{error}</p>
            <Link
              href="/become-instructor"
              className="inline-block px-6 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 transition-colors"
              onClick={() => logger.debug('Navigating to become-instructor from error state')}
            >
              Complete Profile Setup
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (!profile) return null;

  // Use the helper function for display name
  const displayName = getInstructorDisplayName(profile);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navbar */}
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link href="/" className="text-2xl font-bold text-indigo-600">
              {BRAND.name}
            </Link>
            <button
              onClick={handleLogout}
              className="flex items-center text-gray-600 hover:text-gray-900 transition-colors"
            >
              <LogOut className="h-5 w-5 mr-2" />
              Log out
            </button>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Link
          href="/"
          className="inline-flex items-center text-gray-600 hover:text-gray-900 mb-4 transition-colors"
          onClick={() => logger.debug('Navigating back to home')}
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Home
        </Link>

        {/* Welcome Section */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-8">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Welcome back, {displayName}!</h1>
          <p className="text-gray-600">Manage your instructor profile and bookings</p>
        </div>

        {/* Quick Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Total Bookings</h3>
            <p className="text-3xl font-bold text-indigo-600">0</p>
            <p className="text-sm text-gray-500 mt-1">Coming soon</p>
          </div>
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Rating</h3>
            <p className="text-3xl font-bold text-indigo-600">-</p>
            <p className="text-sm text-gray-500 mt-1">Not yet available</p>
          </div>
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Total Earnings</h3>
            <p className="text-3xl font-bold text-indigo-600">$0</p>
            <p className="text-sm text-gray-500 mt-1">Payment integration pending</p>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <Link
            href="/dashboard/instructor/availability"
            className="block p-6 bg-white rounded-lg shadow hover:shadow-lg transition-shadow"
            onClick={() => logger.debug('Navigating to availability management')}
          >
            <div className="flex items-center gap-4">
              <Calendar className="w-8 h-8 text-indigo-600" />
              <div>
                <h3 className="text-lg font-semibold">Manage Availability</h3>
                <p className="text-gray-600">Set your weekly schedule and available hours</p>
              </div>
            </div>
          </Link>
          {/* Placeholder for future quick actions */}
          <div className="p-6 bg-gray-100 rounded-lg border-2 border-dashed border-gray-300">
            <div className="text-center text-gray-500">
              <p className="font-semibold">More features coming soon</p>
              <p className="text-sm mt-1">Booking management, analytics, and more</p>
            </div>
          </div>
        </div>

        {/* Profile Section */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-8">
          <div className="flex justify-between items-start mb-6">
            <h2 className="text-xl font-bold text-gray-900">Profile Information</h2>
            <button
              onClick={() => {
                logger.debug('Opening edit profile modal');
                setShowEditModal(true);
              }}
              className="flex items-center px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 transition-colors"
            >
              <Edit className="h-4 w-4 mr-2" />
              Edit Profile
            </button>
          </div>

          <div className="space-y-6">
            {/* Bio Section */}
            <div>
              <h3 className="text-sm font-medium text-gray-500 mb-1">Bio</h3>
              <p className="text-gray-900">{profile.bio}</p>
            </div>

            {/* Services Section */}
            <div>
              <h3 className="text-sm font-medium text-gray-500 mb-2">Services & Pricing</h3>
              <div className="space-y-2">
                {profile.services.map((service) => (
                  <div
                    key={service.id}
                    className="flex justify-between items-center p-3 bg-gray-50 rounded-lg"
                  >
                    <div>
                      <span className="font-medium">{service.skill}</span>
                      {service.description && (
                        <p className="text-sm text-gray-600">{service.description}</p>
                      )}
                    </div>
                    <span className="font-semibold text-indigo-600">${service.hourly_rate}/hr</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Additional Info */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h3 className="text-sm font-medium text-gray-500 mb-1">Areas of Service</h3>
                <p className="text-gray-900">{profile.areas_of_service.join(', ')}</p>
              </div>
              <div>
                <h3 className="text-sm font-medium text-gray-500 mb-1">Experience</h3>
                <p className="text-gray-900">{profile.years_experience} years</p>
              </div>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap gap-4">
          <button
            onClick={handleViewPublicProfile}
            className="flex items-center px-6 py-3 bg-white border border-gray-300 text-gray-700 rounded-md hover:bg-gray-50 transition-colors"
          >
            <ExternalLink className="h-5 w-5 mr-2" />
            View Public Profile
          </button>
          <button
            onClick={() => {
              logger.debug('Opening delete profile modal');
              setShowDeleteModal(true);
            }}
            className="flex items-center px-6 py-3 bg-red-50 border border-red-300 text-red-700 rounded-md hover:bg-red-100 transition-colors"
          >
            <Trash2 className="h-5 w-5 mr-2" />
            Delete Instructor Profile
          </button>
        </div>
      </div>

      {/* Modals */}
      {showEditModal && (
        <EditProfileModal
          isOpen={showEditModal}
          onClose={() => setShowEditModal(false)}
          onSuccess={handleProfileUpdate}
        />
      )}
      {showDeleteModal && (
        <DeleteProfileModal
          isOpen={showDeleteModal}
          onClose={() => setShowDeleteModal(false)}
          onSuccess={handleProfileDelete}
        />
      )}
    </div>
  );
}
