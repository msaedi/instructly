// frontend/components/modals/EditProfileModal.tsx
'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { X, Plus, Trash2, DollarSign, ChevronDown, MapPin, BookOpen } from 'lucide-react';
import { publicApi } from '@/features/shared/api/client';
import type { CatalogService, ServiceCategory } from '@/features/shared/api/client';
import Modal from '@/components/Modal';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { logger } from '@/lib/logger';
import { PlacesAutocompleteInput } from '@/components/forms/PlacesAutocompleteInput';
import { normalizeInstructorServices, hydrateCatalogNameById } from '@/lib/instructorServices';
type EditableService = {
  service_catalog_id?: string;
  service_catalog_name?: string | null;
  name?: string | null;
  skill?: string;
  hourly_rate?: number;
  description?: string | null;
  requirements?: string | null;
  age_groups?: string[] | null;
  levels_taught?: string[] | null;
  equipment_required?: string[] | null;
  location_types?: string[] | null;
  duration_options?: number[] | null;
};

// Simple address type for profile editing
interface AddressItem {
  id: string;
  postal_code?: string;
  is_default?: boolean;
}

interface ServiceUpdateItem {
  service_catalog_id: string;
  hourly_rate: number;
  age_groups: string[];
  description?: string;
  duration_options: number[];
  levels_taught: string[];
  equipment_required?: string[];
  location_types: string[];
}

interface ProfileServiceUpdatePayload {
  services: ServiceUpdateItem[];
}

interface ApiErrorResponse {
  detail?: string;
  message?: string;
}

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
  /** Which variant of the modal to show */
  variant?: 'full' | 'about' | 'areas' | 'services';
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
  services: EditableService[];
  /** First name (from account) */
  first_name: string;
  /** Last name (from account) */
  last_name: string;
  /** ZIP/postal code (default address) */
  postal_code: string;
}

export default function EditProfileModal({ isOpen, onClose, onSuccess, variant = 'full' }: EditProfileModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [savingAbout, setSavingAbout] = useState(false);
  // Areas saving state removed - handled by neighborhood persistence
  const [profileData, setProfileData] = useState<ProfileFormData>({
    bio: '',
    areas_of_service: [] as string[],
    years_experience: 0,
    services: [] as EditableService[],
    first_name: '',
    last_name: '',
    postal_code: '',
  });
  const [newService, setNewService] = useState<EditableService>({
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

  // Neighborhood-based service areas (NYC style) - used in areas-only modal variant
  type ServiceAreaItem = { neighborhood_id?: string; id?: string; name?: string | null; borough?: string | null };
  const NYC_BOROUGHS = useMemo(() => ['Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island'] as const, []);
  const [boroughNeighborhoods, setBoroughNeighborhoods] = useState<Record<string, ServiceAreaItem[]>>({});
  const [selectedNeighborhoods, setSelectedNeighborhoods] = useState<Set<string>>(new Set());
  const [, setIdToItem] = useState<Record<string, ServiceAreaItem>>({});
  const [openBoroughs, setOpenBoroughs] = useState<Set<string>>(new Set());
  const [globalNeighborhoodFilter, setGlobalNeighborhoodFilter] = useState('');
  // Preferred locations (teaching address and public spaces) — UI-only like onboarding
  const [preferredAddress, setPreferredAddress] = useState('');
  const [preferredLocations, setPreferredLocations] = useState<string[]>([]);
  const [preferredLocationTitles, setPreferredLocationTitles] = useState<Record<string, string>>({});
  const [neutralLocationInput, setNeutralLocationInput] = useState('');
  const [neutralPlaces, setNeutralPlaces] = useState<string[]>([]);
  // Services & Pricing (onboarding-like)
  type AgeGroup = 'kids' | 'adults' | 'both';
  type SelectedService = {
    catalog_service_id: string;
    name: string;
    hourly_rate: string;
    ageGroup: AgeGroup;
    description?: string;
    equipment?: string;
    levels_taught: Array<'beginner' | 'intermediate' | 'advanced'>;
    duration_options: number[];
    location_types: Array<'in-person' | 'online'>;
  };
  const [categories, setCategories] = useState<ServiceCategory[]>([]);
  const [servicesByCategory, setServicesByCategory] = useState<Record<string, CatalogService[]>>({});
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [selectedServices, setSelectedServices] = useState<SelectedService[]>([]);
  const [svcLoading, setSvcLoading] = useState(false);
  const [svcSaving, setSvcSaving] = useState(false);
  const [skillsFilter, setSkillsFilter] = useState('');

  useEffect(() => {
    if (isOpen) {
      logger.debug('Edit profile modal opened');
      setError(''); // Clear any previous errors when modal opens
      void fetchProfile();
      // Prefill selected neighborhoods from backend when opening areas-only variant
      void (async () => {
        try {
          const areasRes = await fetchWithAuth('/api/addresses/service-areas/me');
          if (areasRes.ok) {
            const json = await areasRes.json();
            const items = (json.items || []) as ServiceAreaItem[];
            const ids = items
              .map((a) => a.neighborhood_id || a.id)
              .filter((v): v is string => typeof v === 'string');
            setSelectedNeighborhoods(new Set(ids));
            setIdToItem((prev) => {
              const next = { ...prev } as Record<string, ServiceAreaItem>;
              for (const a of items) {
                const nid = a.neighborhood_id || a.id;
                if (nid) next[nid] = a;
              }
              return next;
            });
          }
        } catch {}
      })();
    }
  }, [isOpen]);

  // Load services for services-only modal
  useEffect(() => {
    const load = async () => {
      if (!(isOpen && variant === 'services')) return;
      try {
        setSvcLoading(true);
        const [cats, all] = await Promise.all([
          publicApi.getServiceCategories(),
          publicApi.getAllServicesWithInstructors(),
        ]);
        if (cats.status === 200 && cats.data) {
          const filtered = cats.data.filter((c) => c.slug !== 'kids');
          setCategories(filtered);
          const initialCollapsed: Record<string, boolean> = {};
          for (const c of filtered) initialCollapsed[c.slug] = true;
          setCollapsed(initialCollapsed);
        }
        if (all.status === 200 && all.data) {
          const map: Record<string, CatalogService[]> = {};
          for (const c of all.data.categories.filter((c: { slug: string; services: unknown[] }) => c.slug !== 'kids')) {
            map[c.slug] = c.services;
          }
          setServicesByCategory(map);
        }
        // Prefill from profile
        try {
          const meRes = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);
          if (meRes.ok) {
            const me = await meRes.json();
            const mapped: SelectedService[] = (me.services || []).map((svc: unknown) => {
              const s = svc as Record<string, unknown>;
              return {
                catalog_service_id: s['service_catalog_id'] as string,
                name: (s['name'] as string) || '',
                hourly_rate: String(s['hourly_rate'] ?? ''),
                ageGroup:
                  Array.isArray(s['age_groups']) && s['age_groups'].length === 2
                    ? 'both'
                    : ((s['age_groups'] as string[]) || []).includes('kids')
                    ? 'kids'
                    : 'adults',
                description: (s['description'] as string) || '',
                equipment: Array.isArray(s['equipment_required']) ? (s['equipment_required'] as string[]).join(', ') : '',
                levels_taught:
                  Array.isArray(s['levels_taught']) && s['levels_taught'].length
                    ? s['levels_taught'] as string[]
                    : ['beginner', 'intermediate', 'advanced'],
                duration_options: Array.isArray(s['duration_options']) && s['duration_options'].length ? s['duration_options'] as number[] : [60],
                location_types: Array.isArray(s['location_types']) && s['location_types'].length ? s['location_types'] as string[] : ['in-person'],
              };
            });
            if (mapped.length) setSelectedServices(mapped);
          }
        } catch {}
      } catch {
        setError('Failed to load services');
      } finally {
        setSvcLoading(false);
      }
    };
    void load();
  }, [isOpen, variant]);

  const loadBoroughNeighborhoods = useCallback(async (borough: string): Promise<ServiceAreaItem[]> => {
    if (boroughNeighborhoods[borough]) return boroughNeighborhoods[borough] || [];
    try {
      const url = `${process.env['NEXT_PUBLIC_API_BASE'] || 'http://localhost:8000'}/api/addresses/regions/neighborhoods?region_type=nyc&borough=${encodeURIComponent(borough)}&per_page=500`;
      const r = await fetch(url);
      if (r.ok) {
        const data = await r.json();
        const list = (data.items || []) as ServiceAreaItem[];
        setBoroughNeighborhoods((prev) => ({ ...prev, [borough]: list }));
        setIdToItem((prev) => {
          const next = { ...prev } as Record<string, ServiceAreaItem>;
          for (const it of list) {
            const nid = it.neighborhood_id || it.id;
            if (nid) next[nid] = it;
          }
          return next;
        });
        return list;
      }
    } catch {}
    return boroughNeighborhoods[borough] || [];
  }, [boroughNeighborhoods]);

  // Prefetch borough lists when filtering globally
  useEffect(() => {
    if (globalNeighborhoodFilter.trim().length > 0) {
      NYC_BOROUGHS.forEach((b) => {
        void loadBoroughNeighborhoods(b);
      });
    }
  }, [globalNeighborhoodFilter, NYC_BOROUGHS, loadBoroughNeighborhoods]);

  const toggleNeighborhood = (id: string) => {
    setSelectedNeighborhoods((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleBoroughAll = (borough: string, value: boolean, itemsOverride?: ServiceAreaItem[]) => {
    const items = itemsOverride || boroughNeighborhoods[borough] || [];
    const ids = items.map((i) => i.neighborhood_id || i.id).filter((id): id is string => typeof id === 'string');
    setSelectedNeighborhoods((prev) => {
      const next = new Set(prev);
      if (value) ids.forEach((id) => next.add(id));
      else ids.forEach((id) => next.delete(id));
      return next;
    });
  };

  const toggleBoroughOpen = async (borough: string) => {
    setOpenBoroughs((prev) => {
      const next = new Set(prev);
      if (next.has(borough)) next.delete(borough);
      else next.add(borough);
      return next;
    });
    await loadBoroughNeighborhoods(borough);
  };

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

      // Fetch user names
      let firstName = '';
      let lastName = '';
      try {
        const me = await fetchWithAuth(API_ENDPOINTS.ME);
        if (me.ok) {
          const u = await me.json();
          firstName = u.first_name || '';
          lastName = u.last_name || '';
        }
      } catch {}

      // Fetch default address postal code
      let postalCode = '';
      try {
        const addrRes = await fetchWithAuth('/api/addresses/me');
        if (addrRes.ok) {
          const list = await addrRes.json();
          const items = list.items || [];
          const def = items.find((a: AddressItem) => a.is_default) || (items.length > 0 ? items[0] : null);
          postalCode = def?.postal_code || '';
        }
      } catch {}

      const normalizedServices = await normalizeInstructorServices(data.services);

      setProfileData({
        bio: data.bio || '',
        areas_of_service: areasOfService || [],
        years_experience: data.years_experience || 0,
        services: normalizedServices,
        first_name: firstName,
        last_name: lastName,
        postal_code: postalCode,
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
      // Update user first/last names
      try {
        await fetchWithAuth(API_ENDPOINTS.ME, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            first_name: profileData.first_name?.trim() || '',
            last_name: profileData.last_name?.trim() || '',
          }),
        });
      } catch {}

      // Update default address postal code
      try {
        const addrRes = await fetchWithAuth('/api/addresses/me');
        if (addrRes.ok) {
          const list = await addrRes.json();
          const items = (list.items || []) as AddressItem[];
          const def = items.find((a) => a.is_default) || (items.length > 0 ? items[0] : null);
          const newZip = (profileData.postal_code || '').trim();
          if (def && def.id) {
            if (newZip && newZip !== (def.postal_code || '')) {
              await fetchWithAuth(`/api/addresses/me/${def.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ postal_code: newZip }),
              });
            }
          } else if (newZip) {
            await fetchWithAuth('/api/addresses/me', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ postal_code: newZip, is_default: true }),
            });
          }
        }
      } catch {}

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
    } catch (err: unknown) {
      logger.error('Failed to update profile', err);
      setError(err instanceof Error ? err.message : 'Failed to update profile');
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
      services: [...profileData.services, newService as EditableService],
    });

    // Reset the form
    setNewService({ skill: '', hourly_rate: 50, description: '' });
  };

  /**
   * Remove a service from the profile
   */
  const removeService = (index: number) => {
    const serviceToRemove = profileData.services[index];
    if (!serviceToRemove) return;
    logger.info('Removing service', { index, skill: serviceToRemove.skill });

    setProfileData({
      ...profileData,
      services: profileData.services.filter((_, i) => i !== index),
    });
  };

  /**
   * Update a specific field of a service
   */
  const updateService = (index: number, field: keyof EditableService, value: string | number) => {
    logger.debug('Updating service', { index, field, value });

    const updatedServices = [...profileData.services];
    const serviceToUpdate = updatedServices[index];
    if (!serviceToUpdate) return;
    updatedServices[index] = { ...serviceToUpdate, [field]: value };
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

  const isAboutOnly = variant === 'about';
  const isAreasOnly = variant === 'areas';
  const isServicesOnly = variant === 'services';

  const handleSaveBioExperience = async () => {
    try {
      setSavingAbout(true);
      setError('');
      // First, update personal info (names and ZIP)
      try {
        await fetchWithAuth(API_ENDPOINTS.ME, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            first_name: profileData.first_name?.trim() || '',
            last_name: profileData.last_name?.trim() || '',
          }),
        });
      } catch {}

      try {
        const addrRes = await fetchWithAuth('/api/addresses/me');
        if (addrRes.ok) {
          const list = await addrRes.json();
          const items = (list.items || []) as AddressItem[];
          const def = items.find((a) => a.is_default) || (items.length > 0 ? items[0] : null);
          const newZip = (profileData.postal_code || '').trim();
          if (def && def.id) {
            if (newZip && newZip !== (def.postal_code || '')) {
              await fetchWithAuth(`/api/addresses/me/${def.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ postal_code: newZip }),
              });
            }
          } else if (newZip) {
            await fetchWithAuth('/api/addresses/me', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ postal_code: newZip, is_default: true }),
            });
          }
        }
      } catch {}

      // Persist bio and years of experience along with existing services/areas
      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bio: profileData.bio,
          years_experience: profileData.years_experience,
          services: profileData.services,
          areas_of_service: profileData.areas_of_service,
        }),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({} as Record<string, unknown>));
        throw new Error(typeof errorData.detail === 'string' ? errorData.detail : 'Failed to update profile');
      }
      onSuccess();
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to save changes');
    } finally {
      setSavingAbout(false);
    }
  };

  // Areas-only save handler removed - functionality integrated into neighborhood persistence

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      showCloseButton={true}
      size="lg"
      noPadding
      footer={
        isAboutOnly || isAreasOnly || isServicesOnly ? null : (
          <div className="flex gap-3 justify-end px-6 py-4">
            <button
              type="button"
              onClick={() => {
                logger.debug('Edit profile cancelled');
                onClose();
              }}
              className="px-4 py-2.5 text-gray-700 bg-white border border-gray-300 rounded-lg
                       hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2
                       focus:ring-gray-400 transition-all duration-150 font-medium"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={loading || !canSubmit}
              className="px-4 py-2.5 bg-[#7E22CE] text-white rounded-lg hover:bg-[#7E22CE]
                       disabled:opacity-50 disabled:cursor-not-allowed transition-all
                       duration-150 font-medium focus:outline-none focus:ring-2
                       focus:ring-offset-2 focus:ring-[#7E22CE] flex items-center gap-2"
            >
              {loading ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                  <span>Saving...</span>
                </>
              ) : (
                <span>Save Changes</span>
              )}
            </button>
          </div>
        )
      }
    >
      <form className="divide-y divide-gray-200">
        {/* Personal Information Section */}
        {!isAreasOnly && !isServicesOnly && (
        <div className="px-6 py-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Personal Information</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label htmlFor="first_name" className="block text-sm font-medium text-gray-700 mb-2">FIRST NAME</label>
              <input
                id="first_name"
                type="text"
                value={profileData.first_name}
                onChange={(e) => setProfileData({ ...profileData, first_name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500"
                placeholder="First name"
              />
            </div>
            <div>
              <label htmlFor="last_name" className="block text-sm font-medium text-gray-700 mb-2">LAST NAME</label>
              <input
                id="last_name"
                type="text"
                value={profileData.last_name}
                onChange={(e) => setProfileData({ ...profileData, last_name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500"
                placeholder="Last name"
              />
            </div>
            <div>
              <label htmlFor="postal_code" className="block text-sm font-medium text-gray-700 mb-2">ZIP CODE</label>
              <input
                id="postal_code"
                type="text"
                inputMode="numeric"
                pattern="\\d{5}"
                maxLength={5}
                value={profileData.postal_code}
                onChange={(e) => setProfileData({ ...profileData, postal_code: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500"
                placeholder="10001"
              />
            </div>
          </div>
          {/* No section-level Save button for Personal Information in about-only mode */}
        </div>
        )}
        {/* Error message */}
        {error && (
          <div className="px-6 py-4">
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex items-center gap-2">
              <X className="w-4 h-4 text-red-600 flex-shrink-0" aria-hidden="true" />
              <p className="text-sm text-red-700">{error}</p>
            </div>
          </div>
        )}

        {/* Bio Section */}
        {!isAreasOnly && !isServicesOnly && (
        <div className="px-6 py-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">About You</h3>
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
                         focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500"
                rows={4}
                minLength={10}
                maxLength={1000}
                required
                placeholder="Tell students about your teaching style, experience, and what makes you unique..."
              />
              <p className="mt-1 text-xs text-gray-500">{profileData.bio.length}/1000 characters</p>
            </div>

            <div>
              <label htmlFor="experience" className="block text-sm font-medium text-gray-700 mb-2">
                Years of Experience
              </label>
              <input
                id="experience"
                type="number"
                inputMode="numeric"
                step={1}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none
                         focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500 no-spinner"
                value={profileData.years_experience}
                onChange={(e) =>
                  setProfileData({ ...profileData, years_experience: parseInt(e.target.value) })
                }
                min="0"
                onKeyDown={(e) => {
                  if (['e', 'E', '.', '-', '+'].includes(e.key)) {
                    e.preventDefault();
                  }
                }}
                required
              />
            </div>
          </div>
          {isAboutOnly && (
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                onClick={handleSaveBioExperience}
                disabled={savingAbout}
                className="px-4 py-2.5 bg-[#7E22CE] text-white rounded-lg hover:bg-[#7E22CE]
                         disabled:opacity-50 disabled:cursor-not-allowed transition-all
                         duration-150 font-medium focus:outline-none focus:ring-2
                         focus:ring-offset-2 focus:ring-[#7E22CE]"
              >
                {savingAbout ? 'Saving…' : 'Save'}
              </button>
            </div>
          )}
        </div>
        )}

        {/* Areas of Service Section */}
        {!isAboutOnly && !isServicesOnly && (
          <div className="px-6 py-6">
            {isAreasOnly ? (
              <>
                <div className="flex items-start gap-3 mb-3">
                  <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                    <MapPin className="w-6 h-6 text-[#7E22CE]" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900">Service Areas</h3>
                    <p className="text-xs text-gray-600 mt-0.5">Select the neighborhoods where you teach</p>
                  </div>
                </div>
                {/* Global neighborhood search (no wrapper label) */}
                <div className="mb-3">
                  <input
                    type="text"
                    value={globalNeighborhoodFilter}
                    onChange={(e) => setGlobalNeighborhoodFilter(e.target.value)}
                    placeholder="Search neighborhoods..."
                    className="w-full rounded-md border border-gray-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0]"
                  />
                </div>
                {globalNeighborhoodFilter.trim().length > 0 && (
                  <div className="rounded-lg border border-gray-200 bg-white p-3 mb-3">
                    <div className="text-sm text-gray-700 mb-2">Results</div>
                    <div className="flex flex-wrap gap-2">
                      {NYC_BOROUGHS.flatMap((b) => boroughNeighborhoods[b] || [])
                        .filter((n) => (n.name || '').toLowerCase().includes(globalNeighborhoodFilter.toLowerCase()))
                        .map((n) => {
                          const nid = n.neighborhood_id || n.id;
                          if (!nid) return null;
                          const checked = selectedNeighborhoods.has(nid);
                          return (
                            <button
                              key={`global-${nid}`}
                              type="button"
                              onClick={() => toggleNeighborhood(nid)}
                              aria-pressed={checked}
                              className={`flex items-center justify-between px-3 py-1.5 text-sm rounded-full font-semibold transition focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 ${
                                checked ? 'bg-[#7E22CE] text-white border border-[#7E22CE]' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                              }`}
                            >
                              <span className="truncate text-left">{n.name || nid}</span>
                              <span className="ml-2">{checked ? '✓' : '+'}</span>
                            </button>
                          );
                        })
                        .filter(Boolean)
                        .slice(0, 200)}
                      {NYC_BOROUGHS.flatMap((b) => boroughNeighborhoods[b] || [])
                        .filter((n) => (n.name || '').toLowerCase().includes(globalNeighborhoodFilter.toLowerCase())).length === 0 && (
                          <div className="text-sm text-gray-500">No matches found</div>
                      )}
                    </div>
                  </div>
                )}
                {/* Per-borough accordions */}
                <div className="mt-3 space-y-3">
                  {NYC_BOROUGHS.map((borough) => {
                    const isOpen = openBoroughs.has(borough);
                    const list = boroughNeighborhoods[borough] || [];
                    return (
                      <div key={`accordion-${borough}`} className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
                        <div
                          className="flex items-center justify-between cursor-pointer"
                          onClick={async () => { await toggleBoroughOpen(borough); }}
                          aria-expanded={isOpen}
                          role="button"
                          tabIndex={0}
                          onKeyDown={async (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); await toggleBoroughOpen(borough); } }}
                        >
                          <div className="flex items-center gap-2 text-gray-800 font-medium">
                            <span className="tracking-wide text-sm">{borough}</span>
                            <ChevronDown className={`h-4 w-4 text-gray-600 transition-transform ${isOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
                          </div>
                          <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                            <button
                              type="button"
                              className="text-sm px-3 py-1 rounded-md bg-purple-100 text-[#7E22CE] hover:bg-purple-200"
                              onClick={async (e) => {
                                e.stopPropagation();
                                const listNow = boroughNeighborhoods[borough] || (await loadBoroughNeighborhoods(borough));
                                toggleBoroughAll(borough, true, listNow);
                              }}
                            >
                              Select all
                            </button>
                            <button
                              type="button"
                              className="text-sm px-3 py-1 rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50"
                              onClick={async (e) => {
                                e.stopPropagation();
                                const listNow = boroughNeighborhoods[borough] || (await loadBoroughNeighborhoods(borough));
                                toggleBoroughAll(borough, false, listNow);
                              }}
                            >
                              Clear all
                            </button>
                          </div>
                        </div>
                        {isOpen && (
                          <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 max-h-80 overflow-y-auto overflow-x-hidden scrollbar-hide">
                            {(list || []).map((n) => {
                              const nid = n.neighborhood_id || n.id;
                              if (!nid) return null;
                              const checked = selectedNeighborhoods.has(nid);
                              const label = String(n.name || nid)
                                .trim()
                                .toLowerCase()
                                .split(' ')
                                .filter(Boolean)
                                .map((w) => w.length > 0 ? w[0]!.toUpperCase() + w.slice(1) : '')
                                .join(' ');
                              return (
                                <button
                                  key={`${borough}-${nid}`}
                                  type="button"
                                  onClick={() => toggleNeighborhood(nid)}
                                  aria-pressed={checked}
                                  className={`flex items-center justify-between w-full min-w-0 px-2 py-1 text-xs rounded-full font-semibold transition focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 ${
                                    checked ? 'bg-[#7E22CE] text-white border border-[#7E22CE]' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                  }`}
                                >
                                  <span className="truncate text-left">{label}</span>
                                  <span className="ml-2">{checked ? '✓' : '+'}</span>
                                </button>
                              );
                            })}
                            {list.length === 0 && (
                              <div className="col-span-full text-sm text-gray-500">Loading…</div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
                {/* Preferred Teaching Location */}
                <div className="mt-6">
                  <p className="text-gray-600 mt-1 mb-2">Preferred Teaching Location</p>
                  <p className="text-xs text-gray-600 mb-2">Add a studio, gym, or home address if you teach from a fixed location.</p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-start">
                    <div className="flex items-center gap-2">
                      <div className="relative flex-1">
                        <PlacesAutocompleteInput
                          value={preferredAddress}
                          onValueChange={setPreferredAddress}
                          placeholder="Type address..."
                          inputClassName="h-10 border border-gray-300 pl-3 pr-12 text-sm leading-10 focus:border-purple-500"
                        />
                        <button
                          type="button"
                          onClick={() => {
                            const v = preferredAddress.trim();
                            if (!v) return;
                            if (preferredLocations.length >= 2) return;
                            if (!preferredLocations.includes(v)) setPreferredLocations((prev) => [...prev, v]);
                            setPreferredAddress('');
                          }}
                          aria-label="Add address"
                          disabled={preferredLocations.length >= 2}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-[#7E22CE] rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 focus:outline-none no-hover-shadow disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                        >
                          <span className="text-base leading-none">+</span>
                        </button>
                      </div>
                    </div>
                    <div className="min-h-10 flex flex-nowrap items-end gap-4 w-full">
                      {preferredLocations.map((loc) => (
                        <div key={loc} className="relative w-1/2 min-w-0">
                          <input
                            type="text"
                            placeholder="..."
                            value={preferredLocationTitles[loc] || ''}
                            onChange={(e) => setPreferredLocationTitles((prev) => ({ ...prev, [loc]: e.target.value }))}
                            className="absolute -top-5 left-1 text-xs text-[#7E22CE] bg-gray-100 px-1 py-0.5 rounded border-transparent ring-0 shadow-none outline-none focus:outline-none focus-visible:outline-none focus:ring-0 focus-visible:ring-0 focus:border-transparent focus-visible:border-transparent cursor-text"
                            style={{ outline: 'none', outlineOffset: 0, boxShadow: 'none' }}
                          />
                          <span className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 h-10 text-sm w-full min-w-0">
                            <span className="truncate min-w-0" title={loc}>{loc}</span>
                            <button
                              type="button"
                              aria-label={`Remove ${loc}`}
                              className="ml-auto text-[#7E22CE] rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 no-hover-shadow shrink-0"
                              onClick={() => setPreferredLocations((prev) => prev.filter((x) => x !== loc))}
                            >
                              &times;
                            </button>
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Preferred Public Spaces */}
                <div className="mt-6">
                  <p className="text-gray-600 mt-1 mb-2">Preferred Public Spaces</p>
                  <p className="text-xs text-gray-600 mb-2">Suggest public spaces where you’re comfortable teaching (e.g., library, park, coffee shop).</p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-start">
                    <div className="flex items-center gap-2">
                      <div className="relative flex-1">
                        <PlacesAutocompleteInput
                          value={neutralLocationInput}
                          onValueChange={setNeutralLocationInput}
                          placeholder="Type location..."
                          inputClassName="h-10 border border-gray-300 pl-3 pr-12 text-sm leading-10 focus:border-purple-500"
                        />
                        <button
                          type="button"
                          onClick={() => {
                            const v = neutralLocationInput.trim();
                            if (!v) return;
                            if (neutralPlaces.length >= 2) return;
                            if (!neutralPlaces.includes(v)) setNeutralPlaces((prev) => [...prev, v]);
                            setNeutralLocationInput('');
                          }}
                          aria-label="Add public space"
                          disabled={neutralPlaces.length >= 2}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-[#7E22CE] rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 focus:outline-none no-hover-shadow disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                        >
                          <span className="text-base leading-none">+</span>
                        </button>
                      </div>
                    </div>
                    <div className="min-h-10 flex flex-nowrap items-end gap-4 w-full">
                      {neutralPlaces.map((place) => (
                        <div key={place} className="relative w-1/2 min-w-0">
                          <span className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 h-10 text-sm w-full min-w-0">
                            <span className="truncate min-w-0" title={place}>{place}</span>
                            <button
                              type="button"
                              aria-label={`Remove ${place}`}
                              className="ml-auto text-[#7E22CE] rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 no-hover-shadow shrink-0"
                              onClick={() => setNeutralPlaces((prev) => prev.filter((x) => x !== place))}
                            >
                              &times;
                            </button>
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="mt-4 flex justify-end">
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        // Persist selected neighborhoods
                        await fetchWithAuth('/api/addresses/service-areas/me', {
                          method: 'PUT',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ neighborhood_ids: Array.from(selectedNeighborhoods) }),
                        });
                        onSuccess();
                        onClose();
                      } catch {
                        setError('Failed to save service areas');
                      }
                    }}
                    className="px-4 py-2.5 bg-[#7E22CE] text-white rounded-lg hover:bg-[#7E22CE] transition-all font-medium focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#7E22CE]"
                  >
                    Save
                  </button>
                </div>
              </>
            ) : (
              <>
                <h3 className="text-lg font-medium text-gray-900 mb-1">Service Areas</h3>
                <p className="text-xs text-gray-600 mb-4">
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
                        className="rounded text-purple-600 focus:ring-[#D4B5F0]"
                      />
                      <span className="text-sm">{area}</span>
                    </label>
                  ))}
                </div>
                {profileData.areas_of_service.length === 0 && (
                  <p className="mt-3 text-sm text-red-600">Please select at least one area of service</p>
                )}
              </>
            )}
          </div>
        )}

        {/* Services Section */}
        {!isAboutOnly && !isAreasOnly && variant !== 'services' && (
          <div className="px-6 py-6">
            <h3 className="text-lg font-medium text-gray-900 mb-2">
              Services & Rates {profileData.services.length > 0 && (
                <span className="text-sm text-gray-500 font-normal">
                  ({profileData.services.length} service{profileData.services.length !== 1 ? 's' : ''})
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
                             focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500"
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
                               focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500"
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
                           focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500"
                  rows={2}
                  placeholder="Brief description of this service..."
                />
              </div>
              <button
                type="button"
                onClick={addService}
                className="w-full px-3 py-2 bg-[#7E22CE] text-white text-sm rounded-lg
                         hover:bg-[#5c0a9a] transition-colors focus:outline-none focus:ring-2
                         focus:ring-offset-2 focus:ring-[#7E22CE] flex items-center justify-center gap-2"
              >
                <Plus className="w-4 h-4" />
                Add Service
              </button>
            </div>

            {/* Existing services list */}
            <div className="space-y-3">
              {profileData.services.map((service, index) => {
                const hydrated = hydrateCatalogNameById(service.service_catalog_id || '');
                const displayName =
                  service.service_catalog_name ??
                  hydrated ??
                  (service.skill && service.skill.trim().length > 0 ? service.skill : service.name) ??
                  (service.service_catalog_id ? `Service ${service.service_catalog_id}` : 'Service');

                if (!service.service_catalog_name && !hydrated && process.env.NODE_ENV !== 'production') {
                  logger.warn('Service chip missing catalog name (modal)', {
                    serviceCatalogId: service.service_catalog_id,
                  });
                }

                return (
                <div key={index} className="p-4 border border-gray-200 rounded-lg bg-white">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-3">
                    <div>
                      <span className="text-sm font-medium text-gray-900">{displayName}</span>
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
                                   focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500
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
                             focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500 mb-3"
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
              );
              })}
            </div>

            {profileData.services.length === 0 && (
              <div className="text-center py-8 text-gray-500">
                <p>No services added yet. Add your first service above!</p>
              </div>
            )}
          </div>
        )}

        {variant === 'services' && (
        <div className="px-6 py-6">
          <div className="flex items-center gap-3 text-lg font-semibold text-gray-900 mb-2">
            <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
              <BookOpen className="w-6 h-6 text-[#7E22CE]" />
            </div>
            <span>Service categories</span>
          </div>
            {svcLoading ? (
              <div className="p-3 text-sm text-gray-600">Loading…</div>
            ) : (
              <>
              <div className="mt-2 space-y-4">
                <p className="text-gray-600 mt-1 mb-2">Select the service categories you teach</p>
                {/* Global skills search */}
                <div className="mb-3">
                  <input
                    type="text"
                    value={skillsFilter}
                    onChange={(e) => setSkillsFilter(e.target.value)}
                    placeholder="Search skills..."
                    className="w-full rounded-md border border-gray-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0]"
                  />
                </div>
                {selectedServices.length > 0 && (
                  <div className="mb-3 flex flex-wrap gap-2">
                    {selectedServices.map((s) => (
                      <span
                        key={`sel-${s.catalog_service_id}`}
                        className="inline-flex items-center gap-2 rounded-full border border-gray-300 bg-white px-3 h-8 text-xs min-w-0"
                      >
                        <span className="truncate max-w-[14rem]" title={s.name}>{s.name}</span>
                        <button
                          type="button"
                          aria-label={`Remove ${s.name}`}
                          className="ml-auto text-[#7E22CE] rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 no-hover-shadow shrink-0"
                          onClick={() => setSelectedServices((prev) => prev.filter((x) => x.catalog_service_id !== s.catalog_service_id))}
                        >
                          &times;
                        </button>
                      </span>
                    ))}
                  </div>
                )}
                {skillsFilter.trim().length > 0 && (
                  <div className="mb-3">
                    <div className="text-sm text-gray-700 mb-2">Results</div>
                    <div className="flex flex-wrap gap-2">
                      {Object.values(servicesByCategory)
                        .flat()
                        .filter((svc) => (svc.name || '').toLowerCase().includes(skillsFilter.toLowerCase()))
                        .map((svc) => {
                          const isSel = selectedServices.some((s) => s.catalog_service_id === svc.id);
                          return (
                            <button
                              key={`global-${svc.id}`}
                              onClick={() => {
                                const exists = selectedServices.some((s) => s.catalog_service_id === svc.id);
                                if (exists) setSelectedServices((prev) => prev.filter((s) => s.catalog_service_id !== svc.id));
                                else setSelectedServices((prev) => ([...prev, { catalog_service_id: svc.id, name: svc.name, hourly_rate: '', ageGroup: 'adults', description: '', equipment: '', levels_taught: ['beginner','intermediate','advanced'], duration_options: [60], location_types: ['in-person'] }]));
                              }}
                              className={`px-3 py-1.5 text-sm rounded-full font-semibold transition focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 whitespace-nowrap ${
                                isSel ? 'bg-[#7E22CE] text-white border border-[#7E22CE] hover:bg-[#7E22CE]' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                              }`}
                              type="button"
                            >
                              {svc.name} {isSel ? '✓' : '+'}
                            </button>
                          );
                        })
                        .slice(0, 200)}
                      {Object.values(servicesByCategory)
                        .flat()
                        .filter((svc) => (svc.name || '').toLowerCase().includes(skillsFilter.toLowerCase())).length === 0 && (
                          <div className="text-sm text-gray-500">No matches found</div>
                      )}
                    </div>
                  </div>
                )}
                  {categories.map((cat) => {
                    const isCollapsed = collapsed[cat.slug] === true;
                    return (
                      <div key={cat.slug} className="rounded-lg overflow-hidden border border-gray-200 bg-white">
                        <button
                          className="w-full px-4 py-3 flex items-center justify-between text-gray-700 hover:bg-gray-50 transition-colors"
                          onClick={() => setCollapsed((prev) => ({ ...prev, [cat.slug]: !isCollapsed }))}
                          type="button"
                        >
                          <span className="font-bold">{cat.name}</span>
                          <svg className={`h-4 w-4 text-gray-600 transition-transform ${isCollapsed ? '' : 'rotate-180'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                          </svg>
                        </button>
                        {!isCollapsed && (
                        <div className="p-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                            {(servicesByCategory[cat.slug] || []).map((svc) => {
                              const isSel = selectedServices.some((s) => s.catalog_service_id === svc.id);
                              return (
                                <button
                                  key={svc.id}
                                  onClick={() => {
                                    const exists = selectedServices.some((s) => s.catalog_service_id === svc.id);
                                    if (exists) setSelectedServices((prev) => prev.filter((s) => s.catalog_service_id !== svc.id));
                                    else setSelectedServices((prev) => ([...prev, { catalog_service_id: svc.id, name: svc.name, hourly_rate: '', ageGroup: 'adults', description: '', equipment: '', levels_taught: ['beginner','intermediate','advanced'], duration_options: [60], location_types: ['in-person'] }]));
                                  }}
                                  className={`px-3 py-2 text-sm rounded-full font-semibold transition focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 whitespace-nowrap ${
                                    isSel ? 'bg-purple-100 text-[#7E22CE] border border-purple-300' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                  }`}
                                  type="button"
                                >
                                  {svc.name} {isSel ? '✓' : '+'}
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                <div className="mt-6 bg-white rounded-lg p-4 border border-gray-200">
                  <h4 className="text-sm font-medium text-gray-900 mb-3">Your selected skills</h4>
                  {selectedServices.length === 0 ? (
                    <p className="text-gray-500 text-sm">You can add skills now or later.</p>
                  ) : (
                    <div className="grid gap-4">
                      {selectedServices.map((s) => (
                        <div key={s.catalog_service_id} className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                          <div className="flex items-start justify-between mb-3">
                            <div>
                              <div className="text-base font-medium text-gray-900">{s.name}</div>
                              <div className="flex items-center gap-3 mt-1">
                                <div className="flex items-center gap-1">
                                  <span className="text-xl font-bold text-[#7E22CE]">${s.hourly_rate || '0'}</span>
                                  <span className="text-xs text-gray-600">/hour</span>
                                </div>
                              </div>
                            </div>
                            <button
                              aria-label="Remove skill"
                              title="Remove skill"
                              className="w-8 h-8 flex items-center justify-center rounded-full bg-white border border-gray-300 text-gray-600 hover:bg-red-50 hover:text-red-600 hover:border-red-300 transition-colors"
                              onClick={() => setSelectedServices((prev) => prev.filter((x) => x.catalog_service_id !== s.catalog_service_id))}
                              type="button"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </button>
                          </div>
                          <div className="mb-3 bg-white rounded-lg p-3 border border-gray-200">
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-medium text-gray-700">Hourly Rate:</span>
                              <div className="flex items-center gap-1">
                                <span className="text-gray-500">$</span>
                                <input
                                  type="number"
                                  min={1}
                                  step="1"
                                  inputMode="decimal"
                                  className="w-24 rounded-md border border-gray-300 px-2 py-1.5 text-center font-medium focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500"
                                  placeholder="75"
                                  value={s.hourly_rate}
                                  onChange={(e) => setSelectedServices((prev) => prev.map((x) => x.catalog_service_id === s.catalog_service_id ? { ...x, hourly_rate: e.target.value } : x))}
                                />
                                <span className="text-gray-500">/hr</span>
                              </div>
                            </div>
                            {s.hourly_rate && Number(s.hourly_rate) > 0 && (
                              <div className="mt-2 text-xs text-gray-600">
                                You&apos;ll earn <span className="font-semibold text-[#7E22CE]">${(Number(s.hourly_rate) * 0.85).toFixed(2)}</span> after the 15% platform fee
                              </div>
                            )}
                          </div>

                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                            <div className="bg-white rounded-lg p-3 border border-gray-200">
                              <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Age Group</label>
                              <div className="flex gap-1">
                                {(['kids', 'adults'] as const).map((ageType) => {
                                  const isSel = s.ageGroup === 'both' ? true : s.ageGroup === ageType;
                                  return (
                                    <button
                                      key={ageType}
                                      onClick={() => setSelectedServices((prev) => prev.map((x) => {
                                        if (x.catalog_service_id !== s.catalog_service_id) return x;
                                        const cur = x.ageGroup;
                                        let next: AgeGroup;
                                        if (cur === 'both') next = ageType === 'kids' ? 'adults' : 'kids';
                                        else if (cur === ageType) next = ageType === 'kids' ? 'adults' : 'kids';
                                        else next = 'both';
                                        return { ...x, ageGroup: next };
                                      }))}
                                      className={`flex-1 px-2 py-2 text-sm rounded-md transition-colors ${
                                        isSel ? 'bg-purple-100 text-[#7E22CE] border border-purple-300' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                      }`}
                                      type="button"
                                    >
                                      {ageType === 'kids' ? 'Kids' : 'Adults'}
                                    </button>
                                  );
                                })}
                              </div>
                            </div>
                            <div className="bg-white rounded-lg p-3 border border-gray-200">
                              <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Location Type</label>
                              <div className="flex gap-1">
                                {(['in-person', 'online'] as const).map((loc) => (
                                  <button
                                    key={loc}
                                    onClick={() => setSelectedServices((prev) => prev.map((x) => {
                                      if (x.catalog_service_id !== s.catalog_service_id) return x;
                                      const has = x.location_types.includes(loc);
                                      const other = loc === 'in-person' ? 'online' : 'in-person';
                                      if (has && x.location_types.length === 1) return { ...x, location_types: [other] };
                                      return { ...x, location_types: has ? x.location_types.filter((v) => v !== loc) : [...x.location_types, loc] };
                                    }))}
                                    className={`flex-1 px-2 py-2 text-sm rounded-md transition-colors ${
                                      s.location_types.includes(loc)
                                        ? 'bg-purple-100 text-[#7E22CE] border border-purple-300'
                                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                    }`}
                                    type="button"
                                  >
                                    {loc === 'in-person' ? 'In-Person' : 'Online'}
                                  </button>
                                ))}
                              </div>
                            </div>
                          </div>

                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                            <div className="bg-white rounded-lg p-3 border border-gray-200">
                              <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Skill Levels</label>
                              <div className="flex gap-1">
                                {(['beginner', 'intermediate', 'advanced'] as const).map((lvl) => (
                                  <button
                                    key={lvl}
                                    onClick={() => setSelectedServices((prev) => prev.map((x) => x.catalog_service_id === s.catalog_service_id ? { ...x, levels_taught: x.levels_taught.includes(lvl) ? x.levels_taught.filter((v) => v !== lvl) : [...x.levels_taught, lvl] } : x))}
                                    className={`flex-1 px-2 py-2 text-sm rounded-md transition-colors ${
                                      s.levels_taught.includes(lvl)
                                        ? 'bg-purple-100 text-[#7E22CE] border border-purple-300'
                                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                    }`}
                                    type="button"
                                  >
                                    {lvl === 'beginner' ? 'Beginner' : lvl === 'intermediate' ? 'Intermediate' : 'Advanced'}
                                  </button>
                                ))}
                              </div>
                            </div>
                            <div className="bg-white rounded-lg p-3 border border-gray-200">
                              <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Session Duration</label>
                              <div className="flex gap-1">
                                {[30, 45, 60, 90].map((d) => (
                                  <button
                                    key={d}
                                    onClick={() => setSelectedServices((prev) => prev.map((x) => {
                                      if (x.catalog_service_id !== s.catalog_service_id) return x;
                                      const has = x.duration_options.includes(d);
                                      if (has && x.duration_options.length === 1) return x;
                                      return { ...x, duration_options: has ? x.duration_options.filter((v) => v !== d) : [...x.duration_options, d] };
                                    }))}
                                    className={`flex-1 px-2 py-2 text-sm rounded-md transition-colors ${
                                      s.duration_options.includes(d)
                                        ? 'bg-purple-100 text-[#7E22CE] border border-purple-300'
                                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                    }`}
                                    type="button"
                                  >
                                    {d}m
                                  </button>
                                ))}
                              </div>
                            </div>
                          </div>

                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <div>
                              <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-1 block">Description (Optional)</label>
                              <textarea
                                rows={2}
                                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500 bg-white"
                                placeholder="Brief description of your teaching style..."
                                value={s.description || ''}
                                onChange={(e) => setSelectedServices((prev) => prev.map((x) => x.catalog_service_id === s.catalog_service_id ? { ...x, description: e.target.value } : x))}
                              />
                            </div>
                            <div>
                              <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-1 block">Equipment (Optional)</label>
                              <textarea
                                rows={2}
                                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500 bg-white"
                                placeholder="Yoga mat, tennis racket..."
                                value={s.equipment || ''}
                                onChange={(e) => setSelectedServices((prev) => prev.map((x) => x.catalog_service_id === s.catalog_service_id ? { ...x, equipment: e.target.value } : x))}
                              />
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="mt-4 flex justify-end">
                  <button type="button" onClick={async () => {
                    try {
                      setSvcSaving(true);
                      const payload: ProfileServiceUpdatePayload = {
                        services: selectedServices
                          .filter((s) => s.hourly_rate.trim() !== '')
                          .map((s) => ({
                            service_catalog_id: s.catalog_service_id,
                            hourly_rate: Number(s.hourly_rate),
                            age_groups: s.ageGroup === 'both' ? ['kids','adults'] : [s.ageGroup],
                            ...(s.description?.trim() ? { description: s.description.trim() } : {}),
                            duration_options: (s.duration_options?.length ? s.duration_options : [60]).sort((a,b)=>a-b),
                            levels_taught: s.levels_taught,
                            ...(s.equipment?.split(',').map((x)=>x.trim()).filter(Boolean)?.length ? { equipment_required: s.equipment.split(',').map((x)=>x.trim()).filter(Boolean) } : {}),
                            location_types: s.location_types?.length ? s.location_types : ['in-person'],
                          })),
                      };
                      const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, { method: 'PUT', headers: { 'Content-Type':'application/json' }, body: JSON.stringify(payload) });
                      if (!res.ok) {
                        const msg = await res.json().catch((): ApiErrorResponse => ({}));
                        throw new Error(msg.detail || 'Failed to save');
                      }
                      onSuccess();
                      onClose();
                    } catch (e: unknown) {
                      setError(e instanceof Error ? e.message : 'Failed to save');
                    } finally {
                      setSvcSaving(false);
                    }
                  }} disabled={svcSaving} className="px-4 py-2.5 bg-[#7E22CE] text-white rounded-lg hover:bg-[#7E22CE] disabled:opacity-50">{svcSaving ? 'Saving…' : 'Save'}</button>
                </div>
              </>
            )}
          </div>
        )}
      </form>
    </Modal>
  );
}
