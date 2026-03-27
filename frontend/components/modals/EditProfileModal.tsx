// frontend/components/modals/EditProfileModal.tsx
'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { X, ChevronDown, MapPin } from 'lucide-react';
import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import Modal from '@/components/Modal';
import { fetchWithAuth, API_ENDPOINTS, getErrorMessage } from '@/lib/api';
import { fetchWithSessionRefresh } from '@/lib/auth/sessionRefresh';
import { logger } from '@/lib/logger';
import { useInstructorServiceAreas } from '@/hooks/queries/useInstructorServiceAreas';
import { PlacesAutocompleteInput } from '@/components/forms/PlacesAutocompleteInput';
import { getServiceAreaBoroughs } from '@/lib/profileServiceAreas';
import { buildProfileUpdateBody } from '@/lib/profileSchemaDebug';
import {
  hasNonEmptyTeachingLocation,
  servicesUseInstructorLocation,
  TEACHING_ADDRESS_REQUIRED_MESSAGE,
} from '@/lib/teachingLocations';
import type { InstructorProfile, ServiceAreaNeighborhood } from '@/types/instructor';
import { SelectedNeighborhoodChips, type SelectedNeighborhood } from '@/features/shared/components/SelectedNeighborhoodChips';
import type { ApiErrorResponse, components } from '@/features/shared/api/types';
import { extractApiErrorCode, extractApiErrorMessage } from '@/lib/apiErrors';
import { toast } from 'sonner';
import { queryKeys } from '@/src/api/queryKeys';
import {
  addPreferredPlace,
  getGlobalNeighborhoodMatchesWithIds,
  updateOptionalPlaceLabel,
} from './EditProfileModal.helpers';

type InstructorProfileResponse = components['schemas']['InstructorProfileResponse'];
type AuthUserResponse = components['schemas']['AuthUserWithPermissionsResponse'];
type AddressListResponse = components['schemas']['AddressListResponse'];
type AddressResponse = components['schemas']['AddressResponse'];
type NeighborhoodsListResponse = components['schemas']['NeighborhoodsListResponse'];
// Simple address type for profile editing
type AddressItem = AddressResponse;

type PreferredTeachingLocationInput = {
  address: string;
  label?: string;
};

type PreferredPublicSpaceInput = {
  address: string;
  label?: string;
};

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
  variant?: 'full' | 'about' | 'areas';
  /** Prefilled neighborhoods provided by parent */
  selectedServiceAreas?: SelectedNeighborhood[];
  /** Prefilled preferred teaching locations */
  preferredTeaching?: PreferredTeachingLocationInput[];
  /** Prefilled preferred public spaces */
  preferredPublic?: PreferredPublicSpaceInput[];
  /** Pre-fetched instructor profile to avoid duplicate API calls */
  instructorProfile?: InstructorProfileResponse | InstructorProfile | null;
  /** Callback when areas variant saves */
  onSave?: (payload: {
    neighborhoods: SelectedNeighborhood[];
    preferredTeaching: PreferredTeachingLocationInput[];
    preferredPublic: PreferredPublicSpaceInput[];
  }) => Promise<void> | void;
}

/**
 * Profile data structure for the form
 */
interface ProfileFormData {
  /** Instructor bio/description */
  bio: string;
  /** Derived borough labels served */
  service_area_boroughs: string[];
  /** Years of teaching experience */
  years_experience: number;
  /** First name (from account) */
  first_name: string;
  /** Last name (from account) */
  last_name: string;
  /** ZIP/postal code (default address) */
  postal_code: string;
}

export default function EditProfileModal({
  isOpen,
  onClose,
  onSuccess,
  variant = 'full',
  selectedServiceAreas = [],
  preferredTeaching = [],
  preferredPublic = [],
  onSave,
  instructorProfile,
}: EditProfileModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [lastNameError, setLastNameError] = useState('');
  const [savingAbout, setSavingAbout] = useState(false);
  // Areas saving state removed - handled by neighborhood persistence
  const [profileData, setProfileData] = useState<ProfileFormData>({
    bio: '',
    service_area_boroughs: [] as string[],
    years_experience: 1,
    first_name: '',
    last_name: '',
    postal_code: '',
  });
  const queryClient = useQueryClient();

  const updateAccountNames = useCallback(async (): Promise<boolean> => {
    const response = await fetchWithAuth(API_ENDPOINTS.ME, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        first_name: profileData.first_name?.trim() || '',
        last_name: profileData.last_name?.trim() || '',
      }),
    });
    if (response.ok) {
      setLastNameError('');
      return true;
    }

    const errorData = (await response.json()) as ApiErrorResponse;
    const message = extractApiErrorMessage(errorData, 'Failed to update profile');
    if (extractApiErrorCode(errorData) === 'last_name_locked') {
      setLastNameError(message);
      toast.error('Last name must match your verified government ID. Contact support if you need to update it.');
      return false;
    }

    throw new Error(message);
  }, [profileData.first_name, profileData.last_name]);

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
  type ServiceAreaItem = {
    neighborhood_id?: string;
    id?: string;
    name?: string | null;
    borough?: string | null;
    ntacode?: string | null;
    code?: string | null;
  };
  const NYC_BOROUGHS = useMemo(() => ['Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island'] as const, []);
  const [boroughNeighborhoods, setBoroughNeighborhoods] = useState<Record<string, ServiceAreaItem[]>>({});
  const [selectedNeighborhoods, setSelectedNeighborhoods] = useState<Set<string>>(new Set());
  const [idToItem, setIdToItem] = useState<Record<string, ServiceAreaItem>>({});
  const [openBoroughs, setOpenBoroughs] = useState<Set<string>>(new Set());
  const [globalNeighborhoodFilter, setGlobalNeighborhoodFilter] = useState('');
  const globalNeighborhoodMatches = useMemo(() => {
    const query = globalNeighborhoodFilter.trim().toLowerCase();
    if (!query) return [];
    const seen = new Set<string>();
    const matches = NYC_BOROUGHS.flatMap((b) => boroughNeighborhoods[b] || [])
      .filter((n) => (n.name || '').toLowerCase().includes(query));
    const results: ServiceAreaItem[] = [];
    for (const match of matches) {
      const nid = match.neighborhood_id || match.id;
      if (!nid || seen.has(nid)) continue;
      seen.add(nid);
      results.push(match);
    }
    return results;
  }, [NYC_BOROUGHS, boroughNeighborhoods, globalNeighborhoodFilter]);
  // Preferred locations (teaching address and public spaces) — UI-only like onboarding
  const [preferredAddress, setPreferredAddress] = useState('');
  const [teachingPlaces, setTeachingPlaces] = useState<PreferredTeachingLocationInput[]>([]);
  const [neutralLocationInput, setNeutralLocationInput] = useState('');
  const [publicPlaces, setPublicPlaces] = useState<PreferredPublicSpaceInput[]>([]);
  const [savingAreas, setSavingAreas] = useState(false);
  const areasPrefillAppliedRef = useRef(false);
  const serviceAreasPrefillAppliedRef = useRef(false);
  const isAreasVariant = variant === 'areas';
  const [requiresTeachingAddress, setRequiresTeachingAddress] = useState(false);
  const teachingAddressError = requiresTeachingAddress &&
    !hasNonEmptyTeachingLocation(teachingPlaces.map((place) => place.address))
    ? TEACHING_ADDRESS_REQUIRED_MESSAGE
    : '';

  // Use React Query hook for service areas (deduplicates API calls)
  const { data: serviceAreasData } = useInstructorServiceAreas(isOpen);
  const fetchProfile = useCallback(async () => {
    try {
      let data: InstructorProfileResponse;

      // Use pre-fetched profile if available (avoids duplicate API call)
      const profileOverride = instructorProfile
        ? (instructorProfile as unknown as InstructorProfileResponse)
        : null;
      if (profileOverride) {
        logger.info('Using pre-fetched instructor profile for editing');
        data = profileOverride;
      } else {
        logger.info('Fetching instructor profile for editing');
        const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);

        if (!response.ok) {
          throw new Error('Failed to fetch profile');
        }

        data = (await response.json()) as InstructorProfileResponse;
      }

      const neighborhoodsRaw = Array.isArray(data.service_area_neighborhoods)
        ? data.service_area_neighborhoods
        : [];
      const neighborhoods = neighborhoodsRaw.reduce<ServiceAreaNeighborhood[]>((acc, item) => {
        const neighborhoodId = item.neighborhood_id;
        if (!neighborhoodId) {
          return acc;
        }
        acc.push({
          neighborhood_id: neighborhoodId,
          ntacode: item.ntacode ?? null,
          name: item.name ?? null,
          borough: item.borough ?? null,
        });
        return acc;
      }, []);

      const serviceAreaSource = {
        service_area_summary: data.service_area_summary ?? null,
        service_area_boroughs: data.service_area_boroughs ?? [],
        service_area_neighborhoods: neighborhoods,
      };
      const boroughSelection = getServiceAreaBoroughs(serviceAreaSource);

      // Fetch user names
      let firstName = '';
      let lastName = '';
      try {
        const me = await fetchWithAuth(API_ENDPOINTS.ME);
        if (me.ok) {
          const u = (await me.json()) as AuthUserResponse;
          firstName = u.first_name || '';
          lastName = u.last_name || '';
        }
      } catch (err) {
        logger.warn('Failed to fetch user profile data', err);
      }

      // Fetch default address postal code
      let postalCode = '';
      try {
        const addrRes = await fetchWithAuth('/api/v1/addresses/me');
        if (addrRes.ok) {
          const list = (await addrRes.json()) as AddressListResponse;
          const items = list.items || [];
          const def = items.find((a: AddressItem) => a.is_default) || (items.length > 0 ? items[0] : null);
          postalCode = def?.postal_code || '';
        }
      } catch (err) {
        logger.warn('Failed to fetch default address', err);
      }

      setProfileData({
        bio: data.bio || '',
        service_area_boroughs: boroughSelection,
        years_experience: data.years_experience || 1,
        first_name: firstName,
        last_name: lastName,
        postal_code: postalCode,
      });
      setRequiresTeachingAddress(servicesUseInstructorLocation(data.services));

      logger.debug('Profile data loaded', {
        boroughCount: boroughSelection.length,
      });
    } catch (err) {
      logger.error('Failed to load instructor profile', err);
      setError('Failed to load profile');
    }
  }, [instructorProfile]);

  useEffect(() => {
    if (isOpen) {
      logger.debug('Edit profile modal opened');
      setError(''); // Clear any previous errors when modal opens
      void fetchProfile();
      // Reset prefill flags when modal opens
      serviceAreasPrefillAppliedRef.current = false;
    }
  }, [fetchProfile, isOpen]);

  // Prefill selected neighborhoods from hook data (replaces direct fetch)
  useEffect(() => {
    if (!isOpen || !serviceAreasData || serviceAreasPrefillAppliedRef.current) return;
    serviceAreasPrefillAppliedRef.current = true;

    const items = (serviceAreasData.items || []) as ServiceAreaItem[];
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
  }, [isOpen, serviceAreasData]);

  useEffect(() => {
    if (!isOpen || !isAreasVariant) {
      areasPrefillAppliedRef.current = false;
      return;
    }

    if (areasPrefillAppliedRef.current) {
      return;
    }
    areasPrefillAppliedRef.current = true;

    if (Array.isArray(selectedServiceAreas)) {
      const nextIds = selectedServiceAreas
        .map((item) => item?.neighborhood_id)
        .filter((id): id is string => typeof id === 'string' && id.length > 0);
      setSelectedNeighborhoods(new Set(nextIds));
      if (selectedServiceAreas.length > 0) {
        setIdToItem((prev) => {
          const next = { ...prev } as Record<string, ServiceAreaItem>;
          for (const item of selectedServiceAreas) {
            if (!item?.neighborhood_id) continue;
            next[item.neighborhood_id] = {
              neighborhood_id: item.neighborhood_id,
              id: item.neighborhood_id,
              name: item.name,
            };
          }
          return next;
        });
      }
    }

    const normalizeTeaching = (input?: PreferredTeachingLocationInput[]): PreferredTeachingLocationInput[] => {
      if (!Array.isArray(input)) return [];
      const seen = new Set<string>();
      const result: PreferredTeachingLocationInput[] = [];
      for (const item of input) {
        const address = typeof item?.address === 'string' ? item.address.trim() : '';
        if (!address) continue;
        const key = address.toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        const label = typeof item?.label === 'string' ? item.label.trim() : '';
        result.push(label ? { address, label } : { address });
        if (result.length === 2) break;
      }
      return result;
    };

    const normalizePublic = (input?: PreferredPublicSpaceInput[]): PreferredPublicSpaceInput[] => {
      if (!Array.isArray(input)) return [];
      const seen = new Set<string>();
      const result: PreferredPublicSpaceInput[] = [];
      for (const item of input) {
        const address = typeof item?.address === 'string' ? item.address.trim() : '';
        if (!address) continue;
        const key = address.toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        const label = typeof item?.label === 'string' ? item.label.trim() : '';
        result.push(label ? { address, label } : { address });
        if (result.length === 2) break;
      }
      return result;
    };

    setTeachingPlaces(normalizeTeaching(preferredTeaching));
    setPublicPlaces(normalizePublic(preferredPublic));
  }, [isAreasVariant, isOpen, preferredPublic, preferredTeaching, selectedServiceAreas, areasPrefillAppliedRef]);



  const loadBoroughNeighborhoods = useCallback(async (borough: string): Promise<ServiceAreaItem[]> => {
    if (boroughNeighborhoods[borough]) return boroughNeighborhoods[borough] || [];
    try {
      const url = `${process.env['NEXT_PUBLIC_API_BASE'] || 'http://localhost:8000'}/api/v1/addresses/regions/neighborhoods?region_type=nyc&borough=${encodeURIComponent(borough)}&per_page=500`;
      const r = await fetchWithSessionRefresh(url);
      if (r.ok) {
        const data = (await r.json()) as NeighborhoodsListResponse;
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
    } catch (err) {
      logger.warn('Failed to load borough neighborhoods', { borough, err });
    }
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

  const addTeachingPlace = () => {
    let didAdd = false;
    setTeachingPlaces((prev) => {
      const next = addPreferredPlace(prev, preferredAddress, (trimmed) => ({ address: trimmed }));
      didAdd = next.didAdd;
      return next.next;
    });
    if (didAdd) {
      setPreferredAddress('');
    }
  };

  const updateTeachingLabel = (index: number, label: string) => {
    setTeachingPlaces((prev) =>
      prev.map((place, idx) => (idx === index ? { ...place, label } : place))
    );
  };

  const removeTeachingPlace = (index: number) => {
    setTeachingPlaces((prev) => prev.filter((_, idx) => idx !== index));
  };

  const updatePublicLabel = (index: number, label: string) => {
    setPublicPlaces((prev) => updateOptionalPlaceLabel(prev, index, label));
  };

  const addPublicPlace = () => {
    let didAdd = false;
    setPublicPlaces((prev) => {
      const next = addPreferredPlace(prev, neutralLocationInput, (trimmed) => {
        const parts = trimmed.split(',').map((part) => part.trim()).filter(Boolean);
        const autoLabel = parts.length > 0 ? parts[0] : trimmed;
        const entry: PreferredPublicSpaceInput = { address: trimmed };
        if (autoLabel) {
          entry.label = autoLabel;
        }
        return entry;
      });
      didAdd = next.didAdd;
      return next.next;
    });
    if (didAdd) {
      setNeutralLocationInput('');
    }
  };

  const removePublicPlace = (index: number) => {
    setPublicPlaces((prev) => prev.filter((_, idx) => idx !== index));
  };

  const selectedNeighborhoodList = useMemo<SelectedNeighborhood[]>(() => {
    return Array.from(selectedNeighborhoods).map((id) => {
      const item = idToItem[id];
      const rawName = typeof item?.name === 'string' ? item.name.trim() : '';
      const normalizedName = rawName.length > 0 ? rawName : id;
      return { neighborhood_id: id, name: normalizedName };
    });
  }, [idToItem, selectedNeighborhoods]);

  const handleAreasSave = useCallback(async () => {
    if (teachingAddressError) {
      setError(teachingAddressError);
      return;
    }

    const neighborhoodIds = selectedNeighborhoodList.map((item) => item.neighborhood_id);
    const teachingPayload = teachingPlaces.slice(0, 2).map((place) => {
      const address = place.address.trim();
      const label = place.label?.trim();
      return label ? { address, label } : { address };
    });
    const publicPayload = publicPlaces.slice(0, 2).map((place) => {
      const address = place.address.trim();
      const label = place.label?.trim();
      return label ? { address, label } : { address };
    });

    setSavingAreas(true);
    setError('');
    try {
      if (onSave) {
        await onSave({
          neighborhoods: selectedNeighborhoodList,
          preferredTeaching: teachingPayload,
          preferredPublic: publicPayload,
        });
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: queryKeys.instructors.me }),
          queryClient.invalidateQueries({ queryKey: ['instructor', 'service-areas'] }),
        ]);
        onSuccess();
        onClose();
        return;
      }

      const serviceAreasRes = await fetchWithAuth('/api/v1/addresses/service-areas/me', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ neighborhood_ids: neighborhoodIds }),
      });
      if (serviceAreasRes.ok === false) {
        const message = await getErrorMessage(serviceAreasRes);
        throw new Error(typeof message === 'string' ? message : 'Failed to save service areas');
      }

      const preferredPlacesRes = await fetchWithAuth('/instructors/me', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          preferred_teaching_locations: teachingPayload,
          preferred_public_spaces: publicPayload,
        }),
      });
      if (preferredPlacesRes.ok === false) {
        const message = await getErrorMessage(preferredPlacesRes);
        throw new Error(typeof message === 'string' ? message : 'Failed to save service areas');
      }

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.instructors.me }),
        queryClient.invalidateQueries({ queryKey: ['instructor', 'service-areas'] }),
      ]);
      onSuccess();
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save service areas';
      setError(message);
      toast.error(message);
    } finally {
      setSavingAreas(false);
    }
  }, [onClose, onSave, onSuccess, publicPlaces, queryClient, selectedNeighborhoodList, teachingAddressError, teachingPlaces]);

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
   * Handle profile update submission
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setLastNameError('');

    logger.info('Submitting profile updates', {
      boroughCount: profileData.service_area_boroughs.length,
    });

    try {
      // Update user first/last names
      try {
        const updatedNames = await updateAccountNames();
        if (!updatedNames) {
          return;
        }
      } catch (err) {
        logger.warn('Failed to update user name', err);
        throw err;
      }

      // Update default address postal code
      try {
        const addrRes = await fetchWithAuth('/api/v1/addresses/me');
        if (addrRes.ok) {
          const list = (await addrRes.json()) as AddressListResponse;
          const items = (list.items || []) as AddressItem[];
          const def = items.find((a) => a.is_default) || (items.length > 0 ? items[0] : null);
          const newZip = (profileData.postal_code || '').trim();
          if (def && def.id) {
            if (newZip && newZip !== (def.postal_code || '')) {
              await fetchWithAuth(`/api/v1/addresses/me/${def.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ postal_code: newZip }),
              });
            }
          } else if (newZip) {
            await fetchWithAuth('/api/v1/addresses/me', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ postal_code: newZip, is_default: true }),
            });
          }
        }
      } catch (err) {
        logger.warn('Failed to update postal code', err);
      }

      // Ensure at least one service area (temporary guard while modal transitions)
      if (profileData.service_area_boroughs.length === 0) {
        logger.warn('Profile update attempted without service area boroughs');
        setError('Please select at least one service area');
        setLoading(false);
        return;
      }

      const payload = buildProfileUpdateBody(profileData, {
        bio: profileData.bio,
        years_experience: profileData.years_experience,
      });

      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorData = (await response.json()) as ApiErrorResponse;
        throw new Error(extractApiErrorMessage(errorData, 'Failed to update profile'));
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
   * Toggle area of service selection
   */
  const toggleArea = (area: string) => {
    logger.debug('Toggling service area borough', { area });

    setProfileData({
      ...profileData,
      service_area_boroughs: profileData.service_area_boroughs.includes(area)
        ? profileData.service_area_boroughs.filter((a) => a !== area)
        : [...profileData.service_area_boroughs, area],
    });
  };

  if (!isOpen) return null;

  const canSubmit = profileData.service_area_boroughs.length > 0;

  const isAboutOnly = variant === 'about';
  const isAreasOnly = isAreasVariant;
  const isStickyVariant = isAreasVariant;

  const handleSaveBioExperience = async () => {
    try {
      setSavingAbout(true);
      setError('');
      setLastNameError('');
      // First, update personal info (names and ZIP)
      try {
        const updatedNames = await updateAccountNames();
        if (!updatedNames) {
          return;
        }
      } catch (err) {
        logger.warn('Failed to update user name in about section', err);
        throw err;
      }

      try {
        const addrRes = await fetchWithAuth('/api/v1/addresses/me');
        if (addrRes.ok) {
          const list = (await addrRes.json()) as AddressListResponse;
          const items = (list.items || []) as AddressItem[];
          const def = items.find((a) => a.is_default) || (items.length > 0 ? items[0] : null);
          const newZip = (profileData.postal_code || '').trim();
          if (def && def.id) {
            if (newZip && newZip !== (def.postal_code || '')) {
              await fetchWithAuth(`/api/v1/addresses/me/${def.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ postal_code: newZip }),
              });
            }
          } else if (newZip) {
            await fetchWithAuth('/api/v1/addresses/me', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ postal_code: newZip, is_default: true }),
            });
          }
        }
      } catch (err) {
        logger.warn('Failed to update postal code in about section', err);
      }

      // Persist bio and years of experience along with existing services/areas
      const payload = buildProfileUpdateBody(profileData, {
        bio: profileData.bio,
        years_experience: profileData.years_experience,
      });

      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const errorData = (await response.json().catch(() => ({}))) as ApiErrorResponse;
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
      showCloseButton={!isStickyVariant}
      size="lg"
      noPadding
      footer={
        isAboutOnly || isAreasOnly ? null : (
          <div className="flex gap-3 justify-end px-6 py-4">
            <button
              type="button"
              onClick={() => {
                logger.debug('Edit profile cancelled');
                onClose();
              }}
              className="px-4 py-2.5 text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg
                       hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2
                       focus:ring-gray-400 transition-all duration-150 font-medium"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={loading || !canSubmit}
              className="px-4 py-2.5 bg-(--color-brand-dark) text-white rounded-lg hover:bg-purple-800 dark:hover:bg-purple-700
                       disabled:opacity-50 disabled:cursor-not-allowed transition-all
                       duration-150 font-medium focus:outline-none focus:ring-2
                       focus:ring-offset-2 focus:ring-(--color-brand-dark) flex items-center gap-2"
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
      <form className={isStickyVariant ? 'flex min-h-full flex-col' : 'divide-y divide-gray-200 dark:divide-gray-700'}>
        {isStickyVariant && (
          <div className="sticky top-0 z-30 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-6 py-4">
            <div className="flex items-center justify-between">
              <div>
                <Dialog.Title className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  Service Areas
                </Dialog.Title>
                <VisuallyHidden>
                  <Dialog.Description>
                    Manage your selected neighborhoods along with preferred teaching and public locations.
                  </Dialog.Description>
                </VisuallyHidden>
              </div>
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="inline-flex h-8 w-8 items-center justify-center rounded-full text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-300 dark:focus:ring-gray-400"
                  aria-label="Close"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </Dialog.Close>
            </div>
          </div>
        )}
        <div className={isStickyVariant ? 'flex-1 overflow-y-auto' : ''}>
        {/* Personal Information Section */}
        {!isAreasOnly && (
        <div className="px-6 py-6">
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">Personal Information</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label htmlFor="first_name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">FIRST NAME</label>
              <input
                id="first_name"
                type="text"
                value={profileData.first_name}
                onChange={(e) => setProfileData({ ...profileData, first_name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500"
                placeholder="First name"
              />
            </div>
            <div>
              <label htmlFor="last_name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">LAST NAME</label>
              <input
                id="last_name"
                type="text"
                value={profileData.last_name}
                onChange={(e) => {
                  setProfileData({ ...profileData, last_name: e.target.value });
                  setLastNameError('');
                }}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500"
                placeholder="Last name"
              />
              {lastNameError && (
                <p className="mt-2 text-sm text-red-600 dark:text-red-400" role="alert">
                  {lastNameError}
                </p>
              )}
            </div>
            <div>
              <label htmlFor="postal_code" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">ZIP CODE</label>
              <input
                id="postal_code"
                type="text"
                inputMode="numeric"
                pattern="\\d{5}"
                maxLength={5}
                value={profileData.postal_code}
                onChange={(e) => setProfileData({ ...profileData, postal_code: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500"
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
        {!isAreasOnly && (
        <div className="px-6 py-6">
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">About You</h3>
          <div className="space-y-4">
            <div>
              <label htmlFor="bio" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Bio <span className="text-red-500">*</span>
              </label>
              <textarea
                id="bio"
                value={profileData.bio}
                onChange={(e) => setProfileData({ ...profileData, bio: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg focus:outline-none
                         focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500"
                rows={4}
                minLength={10}
                maxLength={1000}
                required
                placeholder="Tell students about your teaching style, experience, and what makes you unique..."
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{profileData.bio.length}/1000 characters</p>
            </div>

            <div>
              <label htmlFor="experience" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Years of Experience
              </label>
              <input
                id="experience"
                type="number"
                inputMode="numeric"
                step={1}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg focus:outline-none
                         focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500 no-spinner"
                value={profileData.years_experience}
                onChange={(e) => {
                  const parsed = parseInt(e.target.value, 10);
                  setProfileData({
                    ...profileData,
                    years_experience: Number.isNaN(parsed) ? 0 : Math.min(50, Math.max(1, parsed)),
                  });
                }}
                min="1"
                max="50"
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
                className="px-4 py-2.5 bg-(--color-brand-dark) text-white rounded-lg hover:bg-purple-800 dark:hover:bg-purple-700
                         disabled:opacity-50 disabled:cursor-not-allowed transition-all
                         duration-150 font-medium focus:outline-none focus:ring-2
                         focus:ring-offset-2 focus:ring-(--color-brand-dark)"
              >
                {savingAbout ? 'Saving…' : 'Save'}
              </button>
            </div>
          )}
        </div>
        )}

        {/* Areas of Service Section */}
        {!isAboutOnly && (
          <div className={isAreasOnly ? 'px-6 py-6 pb-24' : 'px-6 py-6'}>
            {isAreasOnly ? (
              <>
                <div className="flex items-start gap-3 mb-3">
                  <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                    <MapPin className="w-6 h-6 text-(--color-brand-dark)" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Service Areas</h3>
                    <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">Select the neighborhoods where you teach</p>
                  </div>
                </div>
                {/* Global neighborhood search (no wrapper label) */}
                <div className="mb-3">
                  <input
                    type="text"
                    value={globalNeighborhoodFilter}
                    onChange={(e) => setGlobalNeighborhoodFilter(e.target.value)}
                    placeholder="Search neighborhoods..."
                    className="w-full rounded-md border border-gray-200 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0]"
                  />
                </div>
                {selectedNeighborhoodList.length > 0 && (
                  <div className="mb-4">
                    <SelectedNeighborhoodChips
                      selected={selectedNeighborhoodList}
                      onRemove={(id) => {
                        setSelectedNeighborhoods((prev) => {
                          const next = new Set(prev);
                          next.delete(id);
                          return next;
                        });
                      }}
                    />
                  </div>
                )}
                {globalNeighborhoodFilter.trim().length > 0 && (
                  <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-3 mb-3">
                    <div className="text-sm text-gray-700 dark:text-gray-300 mb-2">Results</div>
                    <div className="flex flex-wrap gap-2">
                      {getGlobalNeighborhoodMatchesWithIds(globalNeighborhoodMatches)
                        .slice(0, 200)
                        .map(({ match: n, id: nid }, index) => {
                          const checked = selectedNeighborhoods.has(nid);
                          return (
                            <button
                              key={`global-${nid}-${index}`}
                              type="button"
                              onClick={() => toggleNeighborhood(nid)}
                              aria-pressed={checked}
                              className={`flex items-center justify-between px-3 py-1.5 text-sm rounded-full font-semibold transition focus:outline-none focus:ring-2 focus:ring-(--color-brand-dark)/20 ${
                                checked ? 'bg-(--color-brand-dark) text-white border border-(--color-brand-dark)' : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                              }`}
                            >
                              <span className="truncate text-left">{n.name || nid}</span>
                              <span className="ml-2">{checked ? '✓' : '+'}</span>
                            </button>
                          );
                        })
                        .filter(Boolean)}
                      {globalNeighborhoodMatches.length === 0 && (
                        <div className="text-sm text-gray-500 dark:text-gray-400">No matches found</div>
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
                      <div key={`accordion-${borough}`} className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-3 shadow-sm">
                        <div
                          className="flex items-center justify-between cursor-pointer"
                          onClick={async () => { await toggleBoroughOpen(borough); }}
                          aria-expanded={isOpen}
                          aria-label={`${borough} neighborhoods`}
                          role="button"
                          tabIndex={0}
                          onKeyDown={async (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); await toggleBoroughOpen(borough); } }}
                        >
                          <div className="flex items-center gap-2 text-gray-800 dark:text-gray-200 font-medium">
                            <span className="tracking-wide text-sm">{borough}</span>
                            <ChevronDown className={`h-4 w-4 text-gray-600 dark:text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
                          </div>
                          <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                            <button
                              type="button"
                              className="text-sm px-3 py-1 rounded-md bg-purple-100 text-(--color-brand-dark) hover:bg-purple-200 dark:hover:bg-purple-800/40"
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
                              className="text-sm px-3 py-1 rounded-md border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
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
                                  className={`flex items-center justify-between w-full min-w-0 px-2 py-1 text-xs rounded-full font-semibold transition focus:outline-none focus:ring-2 focus:ring-(--color-brand-dark)/20 ${
                                    checked ? 'bg-(--color-brand-dark) text-white border border-(--color-brand-dark)' : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                                  }`}
                                >
                                  <span className="truncate text-left">{label}</span>
                                  <span className="ml-2">{checked ? '✓' : '+'}</span>
                                </button>
                              );
                            })}
                            {list.length === 0 && (
                              <div className="col-span-full text-sm text-gray-500 dark:text-gray-400">Loading…</div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
                {/* Teaching Location */}
                <div className="mt-6">
                  <p className="text-gray-600 dark:text-gray-400 mt-1 mb-2">
                    {requiresTeachingAddress ? 'Where You Teach' : 'Where You Teach (Optional)'}
                  </p>
                  <p className="text-xs text-gray-600 dark:text-gray-400 mb-2 md:max-w-[28rem]">
                    Have a studio, gym, or home address where you can host lessons? Add it here.
                  </p>
                  <div className="grid grid-cols-1 gap-3 items-start md:grid-cols-2">
                    <div className="flex items-center gap-2">
                      <div className="relative flex-1">
                        <PlacesAutocompleteInput
                          value={preferredAddress}
                          onValueChange={setPreferredAddress}
                          placeholder="Type address..."
                          inputClassName={`h-10 border pl-3 pr-12 text-sm leading-10 focus:border-purple-500 ${
                            teachingAddressError
                              ? 'border-red-400 focus:border-red-500'
                              : 'border-gray-300'
                          }`}
                        />
                        <button
                          type="button"
                          onClick={addTeachingPlace}
                          aria-label="Add address"
                          disabled={teachingPlaces.length >= 2}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-(--color-brand-dark) rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 dark:hover:bg-purple-900/30 focus:outline-none no-hover-shadow disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                        >
                          <span className="text-base leading-none">+</span>
                        </button>
                      </div>
                    </div>
                    <div className="min-h-10 flex w-full flex-nowrap items-end gap-4">
                      {teachingPlaces.map((place, index) => (
                        <div key={`${place.address}-${index}`} className="relative w-1/2 min-w-0">
                          <input
                            type="text"
                            value={place.label ?? ''}
                            onChange={(e) => updateTeachingLabel(index, e.target.value)}
                            placeholder="..."
                            className="absolute -top-5 left-2 w-[calc(100%-0.75rem)] border-0 bg-transparent px-0 py-0 text-xs font-medium text-(--color-brand-dark) focus:outline-none focus:ring-0"
                          />
                          <div className="flex items-center gap-2 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm">
                            <span className="truncate min-w-0" title={place.address}>{place.address}</span>
                            <button
                              type="button"
                              aria-label={`Remove ${place.address}`}
                              className="ml-auto inline-flex h-6 w-6 items-center justify-center rounded-full text-(--color-brand-dark) hover:bg-purple-50 dark:hover:bg-purple-900/30"
                              onClick={() => removeTeachingPlace(index)}
                            >
                              &times;
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                  {teachingAddressError ? (
                    <p
                      className="mt-2 text-sm text-red-600 dark:text-red-400"
                      role="alert"
                    >
                      {teachingAddressError}
                    </p>
                  ) : null}
                </div>

                {/* Preferred Public Spaces */}
                <div className="mt-6">
                  <p className="text-gray-600 dark:text-gray-400 mt-1 mb-2">Preferred Public Spaces (Optional)</p>
                  <p className="text-xs text-gray-600 dark:text-gray-400 mb-2 md:max-w-[28rem]">
                    Know public spaces that work well for your lessons (library, coffee shop, court, park)? Add them here.
                  </p>
                <div className="grid grid-cols-1 gap-3 items-start md:grid-cols-2">
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
                          onClick={addPublicPlace}
                          aria-label="Add public space"
                          disabled={publicPlaces.length >= 2}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-(--color-brand-dark) rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 dark:hover:bg-purple-900/30 focus:outline-none no-hover-shadow disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                        >
                          <span className="text-base leading-none">+</span>
                        </button>
                      </div>
                    </div>
                    <div className="min-h-10 flex w-full flex-nowrap items-end gap-4">
                      {publicPlaces.map((place, index) => (
                        <div key={`${place.address}-${index}`} className="relative w-1/2 min-w-0">
                          <input
                            type="text"
                            value={place.label ?? ''}
                            onChange={(e) => updatePublicLabel(index, e.target.value)}
                            placeholder="Name this spot"
                            className="absolute -top-5 left-2 w-[calc(100%-0.75rem)] border-0 bg-transparent px-0 py-0 text-xs font-medium text-(--color-brand-dark) focus:outline-none focus:ring-0"
                          />
                          <div className="flex items-center gap-2 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm">
                            <span className="truncate min-w-0" title={place.address}>{place.address}</span>
                            <button
                              type="button"
                              aria-label={`Remove ${place.address}`}
                              className="ml-auto inline-flex h-6 w-6 items-center justify-center rounded-full text-(--color-brand-dark) hover:bg-purple-50 dark:hover:bg-purple-900/30"
                              onClick={() => removePublicPlace(index)}
                            >
                              &times;
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <>
                <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-1">Service Areas</h3>
                <p className="text-xs text-gray-600 dark:text-gray-400 mb-4 md:max-w-[28rem]">
                  Select all NYC areas where you provide services <span className="text-red-500">*</span>
                </p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  {nycAreas.map((area) => (
                    <label
                      key={area}
                      className="flex items-center space-x-2 cursor-pointer p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700"
                    >
                      <input
                        type="checkbox"
                        checked={profileData.service_area_boroughs.includes(area)}
                        onChange={() => toggleArea(area)}
                        className="rounded text-purple-600 focus:ring-[#D4B5F0]"
                      />
                      <span className="text-sm">{area}</span>
                    </label>
                  ))}
                </div>
                {profileData.service_area_boroughs.length === 0 && (
                  <p className="mt-3 text-sm text-red-600">Please select at least one area of service</p>
                )}
              </>
            )}
          </div>
        )}

        </div>
        {isStickyVariant && (
          <div className="sticky bottom-0 z-30 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-6 py-4">
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  logger.debug('Edit profile cancelled');
                  onClose();
                }}
                className="px-4 py-2.5 text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-400 transition-all duration-150 font-medium"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => { void handleAreasSave(); }}
                disabled={savingAreas}
                className="px-4 py-2.5 bg-(--color-brand-dark) text-white rounded-lg hover:bg-purple-800 dark:hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-150 font-medium focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-(--color-brand-dark)"
              >
                {savingAreas ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        )}
      </form>
    </Modal>
  );
}
