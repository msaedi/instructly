// frontend/app/become-instructor/page.tsx
'use client';

/**
 * Become Instructor Page
 *
 * This page handles the instructor onboarding process for students who want
 * to become instructors. It's a multi-step form that collects services offered,
 * pricing, experience, bio, and areas served. The page checks if the user is
 * already an instructor and prevents duplicate profiles.
 *
 * @module become-instructor/page
 */

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Check, ChevronLeft, ChevronRight, X, AlertCircle } from 'lucide-react';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { BRAND } from '@/app/config/brand';
import { logger } from '@/lib/logger';

// Import centralized types
import type { InstructorService } from '@/types/instructor';
import { RequestStatus } from '@/types/api';
import { getErrorMessage } from '@/types/common';
import { useAuth, hasRole, type User } from '@/features/shared/hooks/useAuth';
import { RoleName } from '@/types/enums';

/**
 * Form data interface for instructor onboarding
 */
interface InstructorOnboardingData {
  services: InstructorService[];
  yearsExperience: number;
  bio: string;
  areasOfService: string[];
}

/**
 * New service form interface (before adding to services list)
 */
interface NewServiceForm {
  skill: string;
  hourly_rate: number;
  description: string;
}

// Predefined options
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

const NYC_AREAS = [
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
  'Astoria',
  'Long Island City',
  'Park Slope',
];

/**
 * Become Instructor Page Component
 *
 * Multi-step form for instructor onboarding
 *
 * @component
 * @returns {JSX.Element} The become instructor page
 */
export default function BecomeInstructorPage() {
  const router = useRouter();
  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState<InstructorOnboardingData>({
    services: [],
    yearsExperience: 0,
    bio: '',
    areasOfService: [],
  });
  const [newService, setNewService] = useState<NewServiceForm>({
    skill: '',
    hourly_rate: 50,
    description: '',
  });
  const [userRole, setUserRole] = useState<string | null>(null);
  const [requestStatus, setRequestStatus] = useState<RequestStatus>(RequestStatus.IDLE);
  const [authCheckStatus, setAuthCheckStatus] = useState<RequestStatus>(RequestStatus.LOADING);
  const [showSuccess, setShowSuccess] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  logger.debug('BecomeInstructorPage initialized', {
    currentStep,
    servicesCount: formData.services.length,
  });

  /**
   * Check user authentication and role
   */
  useEffect(() => {
    const checkAuth = async () => {
      logger.info('Checking user authentication for instructor onboarding');

      const token = localStorage.getItem('access_token');
      if (!token) {
        logger.warn('No access token found, redirecting to login');
        router.push('/login?redirect=/become-instructor');
        return;
      }

      try {
        logger.time('authCheck');
        const response = await fetchWithAuth(API_ENDPOINTS.ME);
        logger.timeEnd('authCheck');

        if (!response.ok) {
          logger.error('Failed to fetch user data', null, {
            status: response.status,
          });
          throw new Error('Failed to fetch user data');
        }

        const userData = await response.json();
        logger.info('User data fetched for onboarding check', {
          userId: userData.id,
          roles: userData.roles,
          isInstructor: hasRole(userData, RoleName.INSTRUCTOR),
        });

        // Get primary role for display
        const primaryRole = userData.roles?.[0] || RoleName.STUDENT;
        setUserRole(primaryRole);
        setAuthCheckStatus(RequestStatus.SUCCESS);
      } catch (error) {
        logger.error('Error checking user authentication', error);
        router.push('/login?redirect=/become-instructor');
      }
    };

    checkAuth();
  }, [router]);

  /**
   * Add a new service to the list
   */
  const addService = () => {
    logger.debug('Attempting to add new service', newService);
    setErrors([]);

    // Validate service
    if (!newService.skill || !newService.hourly_rate) {
      const error = 'Please select a skill and set an hourly rate';
      logger.warn('Service validation failed', { error, newService });
      setErrors([error]);
      return;
    }

    if (formData.services.some((s) => s.skill === newService.skill)) {
      const error = "You've already added this service";
      logger.warn('Duplicate service attempt', { skill: newService.skill });
      setErrors([error]);
      return;
    }

    if (newService.hourly_rate < 0 || newService.hourly_rate > 1000) {
      const error = 'Hourly rate must be between $0 and $1000';
      logger.warn('Invalid hourly rate', { rate: newService.hourly_rate });
      setErrors([error]);
      return;
    }

    // Add service
    const serviceToAdd: InstructorService = {
      id: Date.now(), // Temporary ID for UI
      skill: newService.skill,
      hourly_rate: newService.hourly_rate,
      description: newService.description || null,
    };

    logger.info('Service added successfully', {
      skill: serviceToAdd.skill,
      rate: serviceToAdd.hourly_rate,
    });

    setFormData((prev) => ({
      ...prev,
      services: [...prev.services, serviceToAdd],
    }));

    // Reset form
    setNewService({
      skill: '',
      hourly_rate: 50,
      description: '',
    });
  };

  /**
   * Remove a service from the list
   *
   * @param {number} index - Index of service to remove
   */
  const removeService = (index: number) => {
    const removedService = formData.services[index];
    logger.info('Removing service', {
      index,
      skill: removedService?.skill,
    });

    setFormData((prev) => ({
      ...prev,
      services: prev.services.filter((_, i) => i !== index),
    }));
  };

  /**
   * Toggle area selection
   *
   * @param {string} area - Area to toggle
   */
  const toggleArea = (area: string) => {
    const isSelected = formData.areasOfService.includes(area);
    logger.debug('Toggling area selection', { area, isSelected });

    setFormData((prev) => ({
      ...prev,
      areasOfService: isSelected
        ? prev.areasOfService.filter((a) => a !== area)
        : [...prev.areasOfService, area],
    }));
  };

  /**
   * Update form data field
   *
   * @param {keyof InstructorOnboardingData} field - Field to update
   * @param {string | number} value - New value
   */
  const handleInputChange = (field: keyof InstructorOnboardingData, value: string | number) => {
    logger.debug('Form field updated', { field, value });
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  /**
   * Navigate to next step or submit form
   */
  const handleNext = async () => {
    logger.info('Next button clicked', { currentStep });
    setErrors([]);

    if (currentStep < 2) {
      // Validate step 1
      if (formData.services.length === 0) {
        const error = 'Please add at least one service with pricing';
        logger.warn('Step 1 validation failed', { error });
        setErrors([error]);
        return;
      }

      logger.info('Moving to step 2');
      setCurrentStep((prev) => prev + 1);
    } else {
      // Validate step 2
      const validationErrors = [];

      if (!formData.bio || formData.bio.trim().length < 10) {
        validationErrors.push('Please provide a bio (at least 10 characters)');
      }
      if (formData.bio.trim().length > 1000) {
        validationErrors.push('Bio must be less than 1000 characters');
      }
      if (formData.areasOfService.length === 0) {
        validationErrors.push('Please select at least one area of service');
      }
      if (formData.yearsExperience < 0 || formData.yearsExperience > 50) {
        validationErrors.push('Years of experience must be between 0 and 50');
      }

      if (validationErrors.length > 0) {
        logger.warn('Step 2 validation failed', { errors: validationErrors });
        setErrors(validationErrors);
        return;
      }

      // Submit form
      logger.info('Submitting instructor profile', {
        servicesCount: formData.services.length,
        areasCount: formData.areasOfService.length,
        bioLength: formData.bio.length,
      });

      setRequestStatus(RequestStatus.LOADING);

      try {
        logger.time('profileCreation');

        // Prepare data for API
        const profileData = {
          services: formData.services.map(({ skill, hourly_rate, description }) => ({
            skill,
            hourly_rate,
            description: description || null,
          })),
          years_experience: formData.yearsExperience,
          bio: formData.bio.trim(),
          areas_of_service: formData.areasOfService,
        };

        const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(profileData),
        });

        logger.timeEnd('profileCreation');

        if (!response.ok) {
          const error = await response.json();
          logger.error('Failed to create instructor profile', null, {
            status: response.status,
            error: error.detail,
          });
          throw new Error(error.detail || 'Failed to create instructor profile');
        }

        logger.info('Instructor profile created successfully');
        setRequestStatus(RequestStatus.SUCCESS);
        setShowSuccess(true);

        // Redirect after showing success
        setTimeout(() => {
          logger.info('Redirecting to instructor dashboard');
          router.push('/dashboard/instructor');
        }, 2000);
      } catch (error) {
        const errorMessage = getErrorMessage(error);
        logger.error('Error creating instructor profile', error, { errorMessage });
        setErrors([errorMessage]);
        setRequestStatus(RequestStatus.ERROR);
      }
    }
  };

  /**
   * Navigate to previous step
   */
  const handlePrevious = () => {
    logger.info('Previous button clicked', { currentStep });
    setCurrentStep((prev) => prev - 1);
    setErrors([]);
  };

  const isLoading = requestStatus === RequestStatus.LOADING;
  const isCheckingAuth = authCheckStatus === RequestStatus.LOADING;

  // Loading state while checking auth
  if (isCheckingAuth) {
    logger.debug('Rendering auth check loading state');
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div
          className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"
          role="status"
          aria-label="Checking authentication"
        ></div>
      </div>
    );
  }

  // Already an instructor
  if (userRole === RoleName.INSTRUCTOR) {
    logger.debug('User is already an instructor');
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-800 dark:text-white mb-4">
            You're already an instructor!
          </h1>
          <button
            onClick={() => {
              logger.info('Navigating to instructor dashboard from already-instructor page');
              router.push('/dashboard/instructor');
            }}
            className="bg-indigo-500 text-white px-6 py-2 rounded-lg hover:bg-indigo-600 transition-colors"
          >
            Go to Dashboard
          </button>
        </div>
      </div>
    );
  }

  // Success state
  if (showSuccess) {
    logger.debug('Rendering success state');
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="bg-white dark:bg-gray-800 p-8 rounded-lg shadow-lg text-center max-w-md">
          <div className="w-16 h-16 bg-green-100 dark:bg-green-900/20 rounded-full flex items-center justify-center mx-auto mb-4">
            <Check className="h-8 w-8 text-green-600 dark:text-green-400" aria-hidden="true" />
          </div>
          <h2 className="text-2xl font-bold text-gray-800 dark:text-white mb-2">
            Congratulations!
          </h2>
          <p className="text-gray-600 dark:text-gray-400 mb-4">
            You're now an instructor! Redirecting to your dashboard...
          </p>
          <div
            className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto"
            role="status"
            aria-label="Loading"
          ></div>
        </div>
      </div>
    );
  }

  logger.debug('Rendering onboarding form', { currentStep });

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <h1 className="text-3xl font-bold text-center mb-8 dark:text-white">Become an Instructor</h1>

      {/* Progress Bar */}
      <div
        className="mb-8"
        role="progressbar"
        aria-valuenow={currentStep}
        aria-valuemin={1}
        aria-valuemax={2}
      >
        <div className="flex justify-between mb-2">
          <span className="text-sm font-medium text-gray-600 dark:text-gray-400">
            Step {currentStep} of 2
          </span>
          <span className="text-sm font-medium text-gray-600 dark:text-gray-400">
            {currentStep === 1 ? 'Services & Experience' : 'Profile Details'}
          </span>
        </div>
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
          <div
            className="bg-indigo-500 h-2 rounded-full transition-all duration-300"
            style={{ width: `${(currentStep / 2) * 100}%` }}
          ></div>
        </div>
      </div>

      {/* Error Display */}
      {errors.length > 0 && (
        <div
          className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg"
          role="alert"
        >
          <div className="flex">
            <AlertCircle className="h-5 w-5 text-red-400 mr-2 flex-shrink-0" aria-hidden="true" />
            <div>
              <h3 className="text-sm font-medium text-red-800 dark:text-red-300">
                Please fix the following:
              </h3>
              <ul className="mt-1 list-disc list-inside text-sm text-red-700 dark:text-red-400">
                {errors.map((error, index) => (
                  <li key={index}>{error}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Step 1: Services and Experience */}
      {currentStep === 1 && (
        <div className="space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Services & Pricing
            </label>

            {/* Add Service Form */}
            <div className="border rounded-lg p-4 mb-4 bg-gray-50 dark:bg-gray-800 dark:border-gray-700">
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label
                      htmlFor="skill"
                      className="block text-xs text-gray-600 dark:text-gray-400 mb-1"
                    >
                      Select Skill
                    </label>
                    <select
                      id="skill"
                      value={newService.skill}
                      onChange={(e) => setNewService({ ...newService, skill: e.target.value })}
                      className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                      disabled={isLoading}
                    >
                      <option value="">Choose a skill...</option>
                      {SKILLS_OPTIONS.filter(
                        (skill) => !formData.services.some((s) => s.skill === skill)
                      ).map((skill) => (
                        <option key={skill} value={skill}>
                          {skill}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label
                      htmlFor="hourly_rate"
                      className="block text-xs text-gray-600 dark:text-gray-400 mb-1"
                    >
                      Hourly Rate ($)
                    </label>
                    <input
                      id="hourly_rate"
                      type="number"
                      min="0"
                      max="1000"
                      value={newService.hourly_rate}
                      onChange={(e) =>
                        setNewService({ ...newService, hourly_rate: parseInt(e.target.value) || 0 })
                      }
                      className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                      disabled={isLoading}
                    />
                  </div>
                </div>

                <div>
                  <label
                    htmlFor="description"
                    className="block text-xs text-gray-600 dark:text-gray-400 mb-1"
                  >
                    Description (optional)
                  </label>
                  <input
                    id="description"
                    type="text"
                    placeholder="Brief description of this service..."
                    value={newService.description}
                    onChange={(e) => setNewService({ ...newService, description: e.target.value })}
                    className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                    disabled={isLoading}
                  />
                </div>

                <button
                  type="button"
                  onClick={addService}
                  className="w-full px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  disabled={isLoading}
                >
                  Add Service
                </button>
              </div>
            </div>

            {/* Services List */}
            {formData.services.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  Your Services:
                </h3>
                {formData.services.map((service, index) => (
                  <div
                    key={index}
                    className="flex justify-between items-center p-3 bg-white dark:bg-gray-700 border dark:border-gray-600 rounded-lg"
                  >
                    <div>
                      <span className="font-medium dark:text-white">{service.skill}</span>
                      <span className="text-gray-600 dark:text-gray-400 ml-2">
                        ${service.hourly_rate}/hr
                      </span>
                      {service.description && (
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          {service.description}
                        </p>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => removeService(index)}
                      className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
                      aria-label={`Remove ${service.skill} service`}
                      disabled={isLoading}
                    >
                      <X className="h-5 w-5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <label
              htmlFor="yearsExperience"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2"
            >
              Years of Experience
            </label>
            <input
              id="yearsExperience"
              type="number"
              min="0"
              max="50"
              value={formData.yearsExperience}
              onChange={(e) => handleInputChange('yearsExperience', parseInt(e.target.value) || 0)}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              disabled={isLoading}
            />
          </div>
        </div>
      )}

      {/* Step 2: Profile Details */}
      {currentStep === 2 && (
        <div className="space-y-6">
          <div>
            <label
              htmlFor="bio"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2"
            >
              Bio
            </label>
            <textarea
              id="bio"
              value={formData.bio}
              onChange={(e) => handleInputChange('bio', e.target.value)}
              rows={4}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              placeholder="Tell us about your teaching experience and approach..."
              disabled={isLoading}
              aria-describedby="bio-hint"
            />
            <p id="bio-hint" className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {formData.bio.length}/1000 characters (minimum 10)
            </p>
          </div>

          <div>
            <fieldset>
              <legend className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Areas of Service (Select all that apply)
              </legend>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {NYC_AREAS.map((area) => (
                  <label
                    key={area}
                    className="flex items-center space-x-2 p-2 border rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 dark:border-gray-600"
                  >
                    <input
                      type="checkbox"
                      checked={formData.areasOfService.includes(area)}
                      onChange={() => toggleArea(area)}
                      className="h-4 w-4 text-indigo-500 rounded border-gray-300 dark:border-gray-600"
                      disabled={isLoading}
                    />
                    <span className="text-sm text-gray-700 dark:text-gray-300">{area}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          </div>
        </div>
      )}

      {/* Navigation Buttons */}
      <div className="flex justify-between mt-8">
        {currentStep > 1 && (
          <button
            onClick={handlePrevious}
            className="flex items-center gap-2 px-6 py-2 border rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors dark:border-gray-600 dark:text-gray-300"
            disabled={isLoading}
          >
            <ChevronLeft className="h-5 w-5" />
            Previous
          </button>
        )}
        <button
          onClick={handleNext}
          disabled={isLoading}
          className={`flex items-center gap-2 px-6 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
            currentStep === 1 ? 'ml-auto' : ''
          }`}
        >
          {isLoading ? (
            <>
              <svg
                className="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                ></circle>
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                ></path>
              </svg>
              Submitting...
            </>
          ) : (
            <>
              {currentStep === 2 ? 'Submit' : 'Next'}
              {currentStep === 1 && <ChevronRight className="h-5 w-5" />}
            </>
          )}
        </button>
      </div>
    </div>
  );
}
