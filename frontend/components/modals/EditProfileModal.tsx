// frontend/components/modals/EditProfileModal.tsx
'use client';

import { useState, useEffect } from 'react';
import { X, User, MapPin, Briefcase, Plus, Trash2, DollarSign } from 'lucide-react';
import Modal from '@/components/Modal';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { logger } from '@/lib/logger';
import { InstructorService } from '@/types/instructor';

/**
 * EditProfileModal Component
 *
 * Modal for editing instructor profile information.
 * Updated with professional design system.
 *
 * @component
 */
interface EditProfileModalProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Callback when modal should close */
  onClose: () => void;
  /** Callback when profile is successfully updated */
  onSuccess: () => void;
}

/**
 * Profile data structure for the form
 */
interface ProfileFormData {
  /** Instructor bio/description */
  bio: string;
  /** NYC neighborhoods served */
  areas_of_service: string[];
  /** Years of teaching experience */
  years_experience: number;
  /** Services offered by the instructor */
  services: InstructorService[];
}

export default function EditProfileModal({ isOpen, onClose, onSuccess }: EditProfileModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [profileData, setProfileData] = useState<ProfileFormData>({
    bio: '',
    areas_of_service: [] as string[],
    years_experience: 0,
    services: [] as InstructorService[],
  });
  const [newService, setNewService] = useState<Partial<InstructorService>>({
    skill: '',
    hourly_rate: 50,
    description: '',
  });

  // Skills options (same as in become-instructor)
  const SKILLS_OPTIONS = [
    'Yoga',
    'Meditation',
    'Piano',
    'Music Theory',
    'Spanish',
    'ESL',
    'Personal Training',
    'Nutrition',
    'Photography',
    'Photo Editing',
    'Programming',
    'Web Development',
    'Data Science',
    'Language Tutoring',
    'Art',
    'Drawing',
    'Painting',
    'Dance',
    'Fitness',
    'Cooking',
  ];

  // NYC areas for dropdown
  const nycAreas = [
    'Manhattan',
    'Brooklyn',
    'Queens',
    'Bronx',
    'Staten Island',
    'Upper East Side',
    'Upper West Side',
    'Midtown',
    'Downtown',
    'Williamsburg',
    'Park Slope',
    'Astoria',
    'Long Island City',
  ];

  useEffect(() => {
    if (isOpen) {
      logger.debug('Edit profile modal opened');
      setError(''); // Clear any previous errors when modal opens
      fetchProfile();
    }
  }, [isOpen]);

  /**
   * Fetch instructor profile data
   */
  const fetchProfile = async () => {
    try {
      logger.info('Fetching instructor profile for editing');
      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);

      if (!response.ok) {
        throw new Error('Failed to fetch profile');
      }

      const data = await response.json();

      // Parse areas_of_service if it's a string
      const areasOfService =
        typeof data.areas_of_service === 'string'
          ? JSON.parse(data.areas_of_service)
          : data.areas_of_service;

      setProfileData({
        bio: data.bio || '',
        areas_of_service: areasOfService || [],
        years_experience: data.years_experience || 0,
        services: data.services || [],
      });

      logger.debug('Profile data loaded', {
        servicesCount: data.services?.length || 0,
        areasCount: areasOfService?.length || 0,
      });
    } catch (err) {
      logger.error('Failed to load instructor profile', err);
      setError('Failed to load profile');
    }
  };

  /**
   * Handle profile update submission
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    logger.info('Submitting profile updates', {
      servicesCount: profileData.services.length,
      areasCount: profileData.areas_of_service.length,
    });

    try {
      // Ensure areas_of_service is not empty
      if (profileData.areas_of_service.length === 0) {
        logger.warn('Profile update attempted without areas of service');
        setError('Please select at least one area of service');
        setLoading(false);
        return;
      }

      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(profileData),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to update profile');
      }

      logger.info('Profile updated successfully');
      onSuccess();
      onClose();
    } catch (err: any) {
      logger.error('Failed to update profile', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Add a new service to the profile
   */
  const addService = () => {
    // Check if any field is empty
    if (!newService.skill || !newService.hourly_rate || newService.hourly_rate <= 0) {
      logger.warn('Attempted to add service with invalid data', newService);
      setError('Please select a skill and set a valid hourly rate');
      return;
    }

    // Check for duplicate skills
    if (profileData.services.some((s) => s.skill === newService.skill)) {
      logger.warn('Attempted to add duplicate skill', { skill: newService.skill });
      setError(
        `You already offer ${newService.skill}. Please choose a different skill or update the existing one.`
      );
      return;
    }

    logger.info('Adding new service', newService);
    setError(''); // Clear any previous errors
    setProfileData({
      ...profileData,
      services: [...profileData.services, newService as InstructorService],
    });

    // Reset the form
    setNewService({ skill: '', hourly_rate: 50, description: '' });
  };

  /**
   * Remove a service from the profile
   */
  const removeService = (index: number) => {
    const serviceToRemove = profileData.services[index];
    logger.info('Removing service', { index, skill: serviceToRemove?.skill });

    setProfileData({
      ...profileData,
      services: profileData.services.filter((_, i) => i !== index),
    });
  };

  /**
   * Update a specific field of a service
   */
  const updateService = (index: number, field: keyof InstructorService, value: string | number) => {
    logger.debug('Updating service', { index, field, value });

    const updatedServices = [...profileData.services];
    updatedServices[index] = { ...updatedServices[index], [field]: value };
    setProfileData({ ...profileData, services: updatedServices });
  };

  /**
   * Toggle area of service selection
   */
  const toggleArea = (area: string) => {
    logger.debug('Toggling area of service', { area });

    setProfileData({
      ...profileData,
      areas_of_service: profileData.areas_of_service.includes(area)
        ? profileData.areas_of_service.filter((a) => a !== area)
        : [...profileData.areas_of_service, area],
    });
  };

  if (!isOpen) return null;

  const canSubmit = profileData.services.length > 0 && profileData.areas_of_service.length > 0;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Edit Profile"
      size="lg"
      noPadding
      footer={
        <div className="flex gap-3 justify-end px-6 py-4">
          <button
            type="button"
            onClick={() => {
              logger.debug('Edit profile cancelled');
              onClose();
            }}
            className="px-4 py-2.5 text-gray-700 bg-white border border-gray-300 rounded-lg
                     hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2
                     focus:ring-gray-500 transition-all duration-150 font-medium"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading || !canSubmit}
            className="px-4 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700
                     disabled:opacity-50 disabled:cursor-not-allowed transition-all
                     duration-150 font-medium focus:outline-none focus:ring-2
                     focus:ring-offset-2 focus:ring-indigo-500 flex items-center gap-2"
          >
            {loading ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                <span>Saving...</span>
              </>
            ) : (
              <>
                <User className="w-4 h-4" />
                <span>Save Changes</span>
              </>
            )}
          </button>
        </div>
      }
    >
      <form className="divide-y divide-gray-200">
        {/* Error message */}
        {error && (
          <div className="px-6 py-4">
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex items-center gap-2">
              <X className="w-4 h-4 text-red-600 flex-shrink-0" />
              <p className="text-sm text-red-700">{error}</p>
            </div>
          </div>
        )}

        {/* Bio Section */}
        <div className="px-6 py-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4 flex items-center gap-2">
            <User className="w-5 h-5 text-gray-400" />
            About You
          </h3>
          <div className="space-y-4">
            <div>
              <label htmlFor="bio" className="block text-sm font-medium text-gray-700 mb-2">
                Bio <span className="text-red-500">*</span>
              </label>
              <textarea
                id="bio"
                value={profileData.bio}
                onChange={(e) => setProfileData({ ...profileData, bio: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none
                         focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                rows={4}
                minLength={10}
                maxLength={1000}
                required
                placeholder="Tell students about your teaching style, experience, and what makes you unique..."
              />
              <p className="mt-1 text-sm text-gray-500">{profileData.bio.length}/1000 characters</p>
            </div>

            <div>
              <label htmlFor="experience" className="block text-sm font-medium text-gray-700 mb-2">
                Years of Experience
              </label>
              <input
                id="experience"
                type="number"
                value={profileData.years_experience}
                onChange={(e) =>
                  setProfileData({ ...profileData, years_experience: parseInt(e.target.value) })
                }
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none
                         focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                min="0"
                required
              />
            </div>
          </div>
        </div>

        {/* Areas of Service Section */}
        <div className="px-6 py-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4 flex items-center gap-2">
            <MapPin className="w-5 h-5 text-gray-400" />
            Service Areas
          </h3>
          <p className="text-sm text-gray-600 mb-4">
            Select all NYC areas where you provide services <span className="text-red-500">*</span>
          </p>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {nycAreas.map((area) => (
              <label
                key={area}
                className="flex items-center space-x-2 cursor-pointer p-2 rounded-lg hover:bg-gray-50"
              >
                <input
                  type="checkbox"
                  checked={profileData.areas_of_service.includes(area)}
                  onChange={() => toggleArea(area)}
                  className="rounded text-indigo-600 focus:ring-indigo-500"
                />
                <span className="text-sm">{area}</span>
              </label>
            ))}
          </div>
          {profileData.areas_of_service.length === 0 && (
            <p className="mt-3 text-sm text-red-600">Please select at least one area of service</p>
          )}
        </div>

        {/* Services Section */}
        <div className="px-6 py-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4 flex items-center gap-2">
            <Briefcase className="w-5 h-5 text-gray-400" />
            Services & Rates
            {profileData.services.length > 0 && (
              <span className="text-sm text-gray-500 font-normal">
                ({profileData.services.length} service{profileData.services.length !== 1 ? 's' : ''}
                )
              </span>
            )}
          </h3>

          {/* Add new service form */}
          <div className="mb-6 p-4 border border-gray-200 rounded-lg bg-gray-50">
            <h4 className="text-sm font-medium text-gray-700 mb-3">Add New Service</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-3">
              <div>
                <label htmlFor="new-skill" className="block text-xs text-gray-600 mb-1">
                  Select Skill
                </label>
                <select
                  id="new-skill"
                  value={newService.skill || ''}
                  onChange={(e) => setNewService({ ...newService, skill: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none
                           focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                >
                  <option value="">Choose a skill...</option>
                  {SKILLS_OPTIONS.filter(
                    (skill) => !profileData.services.some((s) => s.skill === skill)
                  ).map((skill) => (
                    <option key={skill} value={skill}>
                      {skill}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="new-rate" className="block text-xs text-gray-600 mb-1">
                  Hourly Rate
                </label>
                <div className="relative">
                  <DollarSign className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    id="new-rate"
                    type="number"
                    value={newService.hourly_rate || 0}
                    onChange={(e) =>
                      setNewService({ ...newService, hourly_rate: parseFloat(e.target.value) || 0 })
                    }
                    className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg focus:outline-none
                             focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    min="0"
                    step="0.01"
                  />
                </div>
              </div>
            </div>
            <div className="mb-3">
              <label htmlFor="new-description" className="block text-xs text-gray-600 mb-1">
                Description (optional)
              </label>
              <textarea
                id="new-description"
                value={newService.description || ''}
                onChange={(e) => setNewService({ ...newService, description: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none
                         focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                rows={2}
                placeholder="Brief description of this service..."
              />
            </div>
            <button
              type="button"
              onClick={addService}
              className="w-full px-3 py-2 bg-indigo-600 text-white text-sm rounded-lg
                       hover:bg-indigo-700 transition-colors focus:outline-none focus:ring-2
                       focus:ring-offset-2 focus:ring-indigo-500 flex items-center justify-center gap-2"
            >
              <Plus className="w-4 h-4" />
              Add Service
            </button>
          </div>

          {/* Existing services list */}
          <div className="space-y-3">
            {profileData.services.map((service, index) => (
              <div key={index} className="p-4 border border-gray-200 rounded-lg bg-white">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-3">
                  <div>
                    <span className="text-sm font-medium text-gray-900">{service.skill}</span>
                  </div>
                  <div>
                    <div className="relative">
                      <DollarSign className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
                      <input
                        type="number"
                        placeholder="Hourly rate"
                        value={service.hourly_rate}
                        onChange={(e) =>
                          updateService(index, 'hourly_rate', parseFloat(e.target.value))
                        }
                        className="w-full pl-9 pr-12 py-2 border border-gray-300 rounded-lg
                                 focus:outline-none focus:ring-2 focus:ring-indigo-500
                                 focus:border-transparent"
                        min="0"
                        step="0.01"
                        required
                      />
                      <span className="absolute right-3 top-1/2 transform -translate-y-1/2 text-sm text-gray-500">
                        /hour
                      </span>
                    </div>
                  </div>
                </div>
                <textarea
                  placeholder="Description (optional)"
                  value={service.description || ''}
                  onChange={(e) => updateService(index, 'description', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none
                           focus:ring-2 focus:ring-indigo-500 focus:border-transparent mb-3"
                  rows={2}
                />
                <button
                  type="button"
                  onClick={() => removeService(index)}
                  className="text-sm text-red-600 hover:text-red-700 transition-colors
                           flex items-center gap-1"
                >
                  <Trash2 className="w-4 h-4" />
                  Remove
                </button>
              </div>
            ))}
          </div>

          {profileData.services.length === 0 && (
            <div className="text-center py-8 text-gray-500">
              <Briefcase className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p>No services added yet. Add your first service above!</p>
            </div>
          )}
        </div>
      </form>
    </Modal>
  );
}
