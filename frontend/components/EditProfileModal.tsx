// frontend/components/EditProfileModal.tsx
"use client";

import { useState, useEffect } from "react";
import { X } from "lucide-react";
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { logger } from '@/lib/logger';

/**
 * Service interface for instructor services
 */
interface Service {
  id?: number;
  skill: string;
  hourly_rate: number;
  description: string;
}

/**
 * EditProfileModal Component
 * 
 * Modal for editing instructor profile information including bio, areas of service,
 * years of experience, and services offered.
 * 
 * Features:
 * - Multi-service management with add/remove functionality
 * - Duplicate skill prevention
 * - Area of service selection (NYC neighborhoods)
 * - Real-time validation
 * - Loading and error states
 * 
 * @component
 * @example
 * ```tsx
 * <EditProfileModal
 *   isOpen={showEditModal}
 *   onClose={() => setShowEditModal(false)}
 *   onSuccess={handleProfileUpdated}
 * />
 * ```
 */
interface EditProfileModalProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Callback when modal should close */
  onClose: () => void;
  /** Callback when profile is successfully updated */
  onSuccess: () => void;
}

export default function EditProfileModal({ 
  isOpen, 
  onClose, 
  onSuccess 
}: EditProfileModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [profileData, setProfileData] = useState({
    bio: "",
    areas_of_service: [] as string[],
    years_experience: 0,
    services: [] as Service[],
  });
  const [newService, setNewService] = useState<Service>({
    skill: "",
    hourly_rate: 50,
    description: "",
  });

  // Skills options (same as in become-instructor)
  const SKILLS_OPTIONS = [
    "Yoga", "Meditation", "Piano", "Music Theory", "Spanish", "ESL",
    "Personal Training", "Nutrition", "Photography", "Photo Editing",
    "Programming", "Web Development", "Data Science", "Language Tutoring",
    "Art", "Drawing", "Painting", "Dance", "Fitness", "Cooking"
  ];

  // NYC areas for dropdown
  const nycAreas = [
    "Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island",
    "Upper East Side", "Upper West Side", "Midtown", "Downtown",
    "Williamsburg", "Park Slope", "Astoria", "Long Island City",
  ];

  useEffect(() => {
    if (isOpen) {
      logger.debug('Edit profile modal opened');
      setError(""); // Clear any previous errors when modal opens
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
        throw new Error("Failed to fetch profile");
      }

      const data = await response.json();
      
      // Parse areas_of_service if it's a string
      const areasOfService = typeof data.areas_of_service === 'string' 
        ? JSON.parse(data.areas_of_service) 
        : data.areas_of_service;
      
      setProfileData({
        bio: data.bio || "",
        areas_of_service: areasOfService || [],
        years_experience: data.years_experience || 0,
        services: data.services || [],
      });
      
      logger.debug('Profile data loaded', { 
        servicesCount: data.services?.length || 0,
        areasCount: areasOfService?.length || 0 
      });
    } catch (err) {
      logger.error('Failed to load instructor profile', err);
      setError("Failed to load profile");
    }
  };

  /**
   * Handle profile update submission
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    logger.info('Submitting profile updates', {
      servicesCount: profileData.services.length,
      areasCount: profileData.areas_of_service.length
    });

    try {
      // Ensure areas_of_service is not empty
      if (profileData.areas_of_service.length === 0) {
        logger.warn('Profile update attempted without areas of service');
        setError("Please select at least one area of service");
        setLoading(false);
        return;
      }

      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(profileData),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to update profile");
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
    if (!newService.skill || newService.hourly_rate <= 0) {
      logger.warn('Attempted to add service with invalid data', newService);
      setError("Please select a skill and set a valid hourly rate");
      return;
    }

    // Check for duplicate skills
    if (profileData.services.some(s => s.skill === newService.skill)) {
      logger.warn('Attempted to add duplicate skill', { skill: newService.skill });
      setError(`You already offer ${newService.skill}. Please choose a different skill or update the existing one.`);
      return;
    }

    logger.info('Adding new service', newService);
    setError(""); // Clear any previous errors
    setProfileData({
      ...profileData,
      services: [...profileData.services, { ...newService }],
    });
    
    // Reset the form
    setNewService({ skill: "", hourly_rate: 50, description: "" });
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
  const updateService = (index: number, field: keyof Service, value: string | number) => {
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
        ? profileData.areas_of_service.filter(a => a !== area)
        : [...profileData.areas_of_service, area],
    });
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex justify-between items-center p-6 border-b">
          <h2 className="text-2xl font-bold">Edit Profile</h2>
          <button 
            onClick={() => {
              logger.debug('Edit profile modal closed');
              onClose();
            }} 
            className="text-gray-500 hover:text-gray-700 transition-colors"
            aria-label="Close modal"
          >
            <X size={24} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6">
          {/* Error message */}
          {error && (
            <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded" role="alert">
              {error}
            </div>
          )}

          {/* Bio */}
          <div className="mb-6">
            <label htmlFor="bio" className="block text-sm font-medium text-gray-700 mb-2">
              Bio (Tell students about yourself)
            </label>
            <textarea
              id="bio"
              value={profileData.bio}
              onChange={(e) => setProfileData({ ...profileData, bio: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
              rows={4}
              minLength={10}
              maxLength={1000}
              required
              aria-describedby="bio-help"
            />
            <p id="bio-help" className="mt-1 text-sm text-gray-500">
              {profileData.bio.length}/1000 characters
            </p>
          </div>

          {/* Years of Experience */}
          <div className="mb-6">
            <label htmlFor="experience" className="block text-sm font-medium text-gray-700 mb-2">
              Years of Experience
            </label>
            <input
              id="experience"
              type="number"
              value={profileData.years_experience}
              onChange={(e) => setProfileData({ ...profileData, years_experience: parseInt(e.target.value) })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
              min="0"
              required
            />
          </div>

          {/* Areas of Service */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Areas of Service (Select all that apply)
            </label>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {nycAreas.map((area) => (
                <label key={area} className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={profileData.areas_of_service.includes(area)}
                    onChange={() => toggleArea(area)}
                    className="rounded text-indigo-600 focus:ring-indigo-500"
                    aria-label={`Service area: ${area}`}
                  />
                  <span className="text-sm">{area}</span>
                </label>
              ))}
            </div>
            {profileData.areas_of_service.length === 0 && (
              <p className="mt-2 text-sm text-red-600">
                Please select at least one area of service
              </p>
            )}
          </div>

          {/* Services */}
          <div className="mb-6">
            <div className="flex justify-between items-center mb-2">
              <label className="block text-sm font-medium text-gray-700">
                Services & Rates
              </label>
              {profileData.services.length > 0 && (
                <span className="text-sm text-gray-500">
                  {profileData.services.length} service{profileData.services.length !== 1 ? 's' : ''}
                </span>
              )}
            </div>
            
            {/* Add new service form */}
            <div className="mb-4 p-4 border border-gray-200 rounded-md bg-gray-50">
              <h4 className="text-sm font-medium text-gray-700 mb-3">Add New Service</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="new-skill" className="block text-xs text-gray-600 mb-1">
                    Select Skill
                  </label>
                  <select
                    id="new-skill"
                    value={newService.skill}
                    onChange={(e) => setNewService({...newService, skill: e.target.value})}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="">Choose a skill...</option>
                    {SKILLS_OPTIONS.filter(skill => 
                      !profileData.services.some(s => s.skill === skill)
                    ).map(skill => (
                      <option key={skill} value={skill}>{skill}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="new-rate" className="block text-xs text-gray-600 mb-1">
                    Hourly Rate ($)
                  </label>
                  <input
                    id="new-rate"
                    type="number"
                    value={newService.hourly_rate}
                    onChange={(e) => setNewService({...newService, hourly_rate: parseFloat(e.target.value) || 0})}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    min="0"
                    step="0.01"
                  />
                </div>
              </div>
              <div className="mt-3">
                <label htmlFor="new-description" className="block text-xs text-gray-600 mb-1">
                  Description (optional)
                </label>
                <textarea
                  id="new-description"
                  value={newService.description}
                  onChange={(e) => setNewService({...newService, description: e.target.value})}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  rows={2}
                  placeholder="Brief description of this service..."
                />
              </div>
              <button
                type="button"
                onClick={addService}
                className="mt-3 w-full px-3 py-2 bg-indigo-600 text-white text-sm rounded-md hover:bg-indigo-700 transition-colors"
              >
                Add Service
              </button>
            </div>
            
            {/* Existing services list */}
            {profileData.services.map((service, index) => (
              <div key={index} className="mb-4 p-4 border border-gray-200 rounded-md">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <span className="font-medium">{service.skill}</span>
                  </div>
                  <div className="flex items-center">
                    <span className="mr-2">$</span>
                    <input
                      type="number"
                      placeholder="Hourly rate"
                      value={service.hourly_rate}
                      onChange={(e) => updateService(index, 'hourly_rate', parseFloat(e.target.value))}
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      min="0"
                      step="0.01"
                      required
                      aria-label={`Hourly rate for ${service.skill}`}
                    />
                    <span className="ml-2">/hour</span>
                  </div>
                </div>
                <textarea
                  placeholder="Description (optional)"
                  value={service.description}
                  onChange={(e) => updateService(index, 'description', e.target.value)}
                  className="mt-2 w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  rows={2}
                  aria-label={`Description for ${service.skill}`}
                />
                <button
                  type="button"
                  onClick={() => removeService(index)}
                  className="mt-2 text-sm text-red-600 hover:text-red-700 transition-colors"
                >
                  Remove
                </button>
              </div>
            ))}
            
            {profileData.services.length === 0 && (
              <p className="text-gray-500 text-center py-4">
                No services added yet. Add your first service above!
              </p>
            )}
          </div>

          {/* Action buttons */}
          <div className="flex justify-end space-x-3">
            <button
              type="button"
              onClick={() => {
                logger.debug('Edit profile cancelled');
                onClose();
              }}
              className="px-4 py-2 text-gray-700 bg-gray-200 rounded-md hover:bg-gray-300 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || profileData.services.length === 0 || profileData.areas_of_service.length === 0}
              className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "Saving..." : "Save Changes"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}