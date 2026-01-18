// frontend/components/modals/EditProfileModal.tsx
'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { X, Plus, Trash2, DollarSign, ChevronDown, MapPin, BookOpen } from 'lucide-react';
import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import type { CategoryServiceDetail, ServiceCategory } from '@/features/shared/api/types';
import { useServiceCategories, useAllServicesWithInstructors } from '@/hooks/queries/useServices';
import { useInstructorProfileMe } from '@/hooks/queries/useInstructorProfileMe';
import Modal from '@/components/Modal';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { logger } from '@/lib/logger';
import { useInstructorServiceAreas } from '@/hooks/queries/useInstructorServiceAreas';
import { PlacesAutocompleteInput } from '@/components/forms/PlacesAutocompleteInput';
import { normalizeInstructorServices, hydrateCatalogNameById, displayServiceName } from '@/lib/instructorServices';
import { getServiceAreaBoroughs } from '@/lib/profileServiceAreas';
import { buildProfileUpdateBody } from '@/lib/profileSchemaDebug';
import type { InstructorProfile, ServiceAreaNeighborhood } from '@/types/instructor';
import { SelectedNeighborhoodChips, type SelectedNeighborhood } from '@/features/shared/components/SelectedNeighborhoodChips';
import { usePricingConfig } from '@/lib/pricing/usePricingFloors';
import { formatPlatformFeeLabel, resolvePlatformFeeRate, resolveTakeHomePct } from '@/lib/pricing/platformFees';
import { evaluatePriceFloorViolations, FloorViolation, formatCents } from '@/lib/pricing/priceFloors';
import { usePlatformFees } from '@/hooks/usePlatformConfig';
import type { ApiErrorResponse, components } from '@/features/shared/api/types';

type InstructorProfileResponse = components['schemas']['InstructorProfileResponse'];
type AuthUserResponse = components['schemas']['AuthUserResponse'];
type AddressListResponse = components['schemas']['AddressListResponse'];
type AddressResponse = components['schemas']['AddressResponse'];
type NeighborhoodsListResponse = components['schemas']['NeighborhoodsListResponse'];
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
type AddressItem = AddressResponse;

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
  variant?: 'full' | 'about' | 'areas' | 'services';
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
  /** Services offered by the instructor */
  services: EditableService[];
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
  const [savingAbout, setSavingAbout] = useState(false);
  // Areas saving state removed - handled by neighborhood persistence
  const [profileData, setProfileData] = useState<ProfileFormData>({
    bio: '',
    service_area_boroughs: [] as string[],
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

  // Use React Query hook for service areas (deduplicates API calls)
  const { data: serviceAreasData } = useInstructorServiceAreas(isOpen);
  // Skills and pricing (onboarding-like)
  type AgeGroup = 'kids' | 'adults' | 'both';
  type SelectedService = {
    catalog_service_id: string;
    service_catalog_name?: string | null;
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
  const [servicesByCategory, setServicesByCategory] = useState<Record<string, CategoryServiceDetail[]>>({});
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [selectedServices, setSelectedServices] = useState<SelectedService[]>([]);
  const [svcLoading, setSvcLoading] = useState(false);
  const [svcSaving, setSvcSaving] = useState(false);
  const [skillsFilter, setSkillsFilter] = useState('');

  // Use React Query hooks for service data (prevents duplicate API calls)
  const { data: categoriesData, isLoading: categoriesLoading } = useServiceCategories();
  const { data: allServicesData, isLoading: allServicesLoading } = useAllServicesWithInstructors();
  // Use React Query hook for instructor profile (prevents duplicate API calls when variant is 'services')
  const { data: instructorProfileFromHook } = useInstructorProfileMe(isOpen && variant === 'services');

  const { config: pricingConfig } = usePricingConfig();
  const { fees } = usePlatformFees();
  const pricingFloors = pricingConfig?.price_floor_cents ?? null;
  const profileFeeContext = useMemo(() => {
    const record = (instructorProfile ?? instructorProfileFromHook) as Record<string, unknown> | null;
    const currentTierRaw = record?.['current_tier_pct'];
    const currentTierPct =
      typeof currentTierRaw === 'number' && Number.isFinite(currentTierRaw) ? currentTierRaw : null;
    return {
      isFoundingInstructor: Boolean(record?.['is_founding_instructor']),
      currentTierPct,
    };
  }, [instructorProfile, instructorProfileFromHook]);
  const platformFeeRate = useMemo(
    () =>
      resolvePlatformFeeRate({
        fees,
        isFoundingInstructor: profileFeeContext.isFoundingInstructor,
        currentTierPct: profileFeeContext.currentTierPct,
      }),
    [fees, profileFeeContext]
  );
  const instructorTakeHomePct = useMemo(() => resolveTakeHomePct(platformFeeRate), [platformFeeRate]);
  const platformFeeLabel = useMemo(() => formatPlatformFeeLabel(platformFeeRate), [platformFeeRate]);
  const serviceFloorViolations = useMemo(() => {
    const map = new Map<string, FloorViolation[]>();
    if (!pricingFloors) return map;
    selectedServices.forEach((service) => {
      const violations = evaluatePriceFloorViolations({
        hourlyRate: Number(service.hourly_rate),
        durationOptions: service.duration_options ?? [60],
        locationTypes: service.location_types ?? ['in-person'],
        floors: pricingFloors,
      });
      if (violations.length > 0) {
        map.set(service.catalog_service_id, violations);
      }
    });
    return map;
  }, [pricingFloors, selectedServices]);
  const hasServiceFloorViolations = serviceFloorViolations.size > 0;

  const fetchProfile = useCallback(async () => {
    try {
      let data: InstructorProfileResponse;

      // Use pre-fetched profile or hook data if available (avoids duplicate API call)
      const profileOverride = instructorProfile
        ? (instructorProfile as unknown as InstructorProfileResponse)
        : null;
      if (profileOverride) {
        logger.info('Using pre-fetched instructor profile for editing');
        data = profileOverride;
      } else if (instructorProfileFromHook) {
        logger.info('Using React Query hook data for editing');
        data = instructorProfileFromHook as unknown as InstructorProfileResponse;
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
      } catch {}

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
      } catch {}

      const normalizedServices = await normalizeInstructorServices(data.services ?? []);

      setProfileData({
        bio: data.bio || '',
        service_area_boroughs: boroughSelection,
        years_experience: data.years_experience || 0,
        services: normalizedServices,
        first_name: firstName,
        last_name: lastName,
        postal_code: postalCode,
      });

      logger.debug('Profile data loaded', {
        servicesCount: Array.isArray(data['services']) ? data['services'].length : 0,
        boroughCount: boroughSelection.length,
      });
    } catch (err) {
      logger.error('Failed to load instructor profile', err);
      setError('Failed to load profile');
    }
  }, [instructorProfile, instructorProfileFromHook]);

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

  // Sync loading state with React Query hooks
  useEffect(() => {
    if (isOpen && variant === 'services') {
      setSvcLoading(categoriesLoading || allServicesLoading);
    }
  }, [isOpen, variant, categoriesLoading, allServicesLoading]);

  // Process service categories from hook data
  useEffect(() => {
    if (!(isOpen && variant === 'services')) return;
    if (categoriesData) {
      const filtered: ServiceCategory[] = categoriesData
        .filter((c) => c.slug !== 'kids')
        .map((c) => ({
          id: c.id,
          slug: c.slug,
          name: c.name,
          subtitle: c.subtitle ?? '',
          description: c.description ?? '',
          display_order: c.display_order,
          icon_name: c.icon_name ?? '',
        }));
      setCategories(filtered);
      const initialCollapsed: Record<string, boolean> = {};
      for (const c of filtered) initialCollapsed[c.slug] = true;
      setCollapsed(initialCollapsed);
    }
  }, [isOpen, variant, categoriesData]);

  // Process all services from hook data
  useEffect(() => {
    if (!(isOpen && variant === 'services')) return;
    if (allServicesData) {
      const map: Record<string, CategoryServiceDetail[]> = {};
      const categories = allServicesData.categories ?? [];
      for (const c of categories.filter((cat) => cat.slug !== 'kids')) {
        map[c.slug] = c.services ?? [];
      }
      setServicesByCategory(map);
    }
  }, [isOpen, variant, allServicesData]);

  // Load instructor profile for prefilling services (uses React Query hook - prevents duplicate API calls)
  useEffect(() => {
    if (!(isOpen && variant === 'services')) return;
    if (!instructorProfileFromHook) return;

    // Transform hook data to match SelectedService format
    const me = instructorProfileFromHook as unknown as Record<string, unknown>;
    const mapped: SelectedService[] = ((me['services'] as unknown[]) || []).map((svc: unknown) => {
      const s = svc as Record<string, unknown>;
      const catalogId = String(s['service_catalog_id'] || '');
      const serviceName = displayServiceName(
        {
          service_catalog_id: catalogId,
          service_catalog_name: typeof s['service_catalog_name'] === 'string' ? s['service_catalog_name'] : (s['name'] as string | undefined) ?? null,
        },
        hydrateCatalogNameById
      );
      return {
        catalog_service_id: catalogId,
        service_catalog_name: typeof s['service_catalog_name'] === 'string' ? s['service_catalog_name'] : null,
        name: serviceName,
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
            ? s['levels_taught'] as Array<'beginner' | 'intermediate' | 'advanced'>
            : ['beginner', 'intermediate', 'advanced'],
        duration_options: Array.isArray(s['duration_options']) && s['duration_options'].length ? s['duration_options'] as number[] : [60],
        location_types: Array.isArray(s['location_types']) && s['location_types'].length ? s['location_types'] as Array<'in-person' | 'online'> : ['in-person'],
      };
    });
    if (mapped.length) setSelectedServices(mapped);
  }, [isOpen, variant, instructorProfileFromHook]);

  const loadBoroughNeighborhoods = useCallback(async (borough: string): Promise<ServiceAreaItem[]> => {
    if (boroughNeighborhoods[borough]) return boroughNeighborhoods[borough] || [];
    try {
      const url = `${process.env['NEXT_PUBLIC_API_BASE'] || 'http://localhost:8000'}/api/v1/addresses/regions/neighborhoods?region_type=nyc&borough=${encodeURIComponent(borough)}&per_page=500`;
      const r = await fetch(url);
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

  const addTeachingPlace = () => {
    const trimmed = preferredAddress.trim();
    if (!trimmed) return;
    let didAdd = false;
    setTeachingPlaces((prev) => {
      if (prev.length >= 2) return prev;
      const exists = prev.some((place) => place.address.toLowerCase() === trimmed.toLowerCase());
      if (exists) return prev;
      didAdd = true;
      return [...prev, { address: trimmed }];
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
    setPublicPlaces((prev) =>
      prev.map((place, idx) => {
        if (idx !== index) return place;
        const nextLabel = label.trim();
        if (!nextLabel) {
          const { label: _omit, ...rest } = place;
          return rest;
        }
        return { ...place, label: nextLabel };
      })
    );
  };

  const addPublicPlace = () => {
    const trimmed = neutralLocationInput.trim();
    if (!trimmed) return;
    let didAdd = false;
    setPublicPlaces((prev) => {
      if (prev.length >= 2) return prev;
      const exists = prev.some((place) => place.address.toLowerCase() === trimmed.toLowerCase());
      if (exists) return prev;
      didAdd = true;
      const parts = trimmed.split(',').map((part) => part.trim()).filter(Boolean);
      const autoLabel = parts.length > 0 ? parts[0] : trimmed;
      const entry: PreferredPublicSpaceInput = { address: trimmed };
      if (autoLabel) {
        entry.label = autoLabel;
      }
      return [...prev, entry];
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
        onSuccess();
        onClose();
        return;
      }

      await fetchWithAuth('/api/v1/addresses/service-areas/me', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ neighborhood_ids: neighborhoodIds }),
      });

      await fetchWithAuth('/instructors/me', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          preferred_teaching_locations: teachingPayload,
          preferred_public_spaces: publicPayload,
        }),
      });

      onSuccess();
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save service areas';
      setError(message);
    } finally {
      setSavingAreas(false);
    }
  }, [onClose, onSave, onSuccess, publicPlaces, selectedNeighborhoodList, teachingPlaces]);

  const handleServicesSave = useCallback(async () => {
    try {
      setSvcSaving(true);
      if (pricingFloors && hasServiceFloorViolations) {
        const iterator = serviceFloorViolations.entries().next();
        if (!iterator.done) {
          const [serviceId, violations] = iterator.value;
          const violation = violations[0];
          if (!violation) {
            setSvcSaving(false);
            return;
          }
          const serviceName = selectedServices.find((svc) => svc.catalog_service_id === serviceId)?.name || 'this service';
          setError(
            `Minimum price for a ${violation.modalityLabel} ${violation.duration}-minute private session is $${formatCents(violation.floorCents)} (current $${formatCents(violation.baseCents)}). Please adjust the rate for ${serviceName}.`
          );
          setSvcSaving(false);
          return;
        }
      }
      const payload: ProfileServiceUpdatePayload = {
        services: selectedServices
          .filter((service) => service.hourly_rate.trim() !== '')
          .map((service) => ({
            service_catalog_id: service.catalog_service_id,
            hourly_rate: Number(service.hourly_rate),
            age_groups: service.ageGroup === 'both' ? ['kids', 'adults'] : [service.ageGroup],
            ...(service.description?.trim() ? { description: service.description.trim() } : {}),
            duration_options: (service.duration_options?.length ? service.duration_options : [60]).sort((a, b) => a - b),
            levels_taught: service.levels_taught,
            ...(service.equipment
              ?.split(',')
              .map((value) => value.trim())
              .filter(Boolean)?.length
              ? {
                  equipment_required: service.equipment
                    .split(',')
                    .map((value) => value.trim())
                    .filter(Boolean),
                }
              : {}),
            location_types: service.location_types?.length ? service.location_types : ['in-person'],
          })),
      };

      const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

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
  }, [
    selectedServices,
    onClose,
    onSuccess,
    pricingFloors,
    hasServiceFloorViolations,
    serviceFloorViolations,
  ]);

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

    logger.info('Submitting profile updates', {
      servicesCount: profileData.services.length,
      boroughCount: profileData.service_area_boroughs.length,
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
      } catch {}

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
        services: profileData.services,
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
    const nextValue =
      field === 'hourly_rate' && typeof value === 'number' && Number.isNaN(value)
        ? 0
        : value;
    updatedServices[index] = { ...serviceToUpdate, [field]: nextValue };
    setProfileData({ ...profileData, services: updatedServices });
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

  const canSubmit = profileData.services.length > 0 && profileData.service_area_boroughs.length > 0;

  const isAboutOnly = variant === 'about';
  const isAreasOnly = isAreasVariant;
  const isServicesOnly = variant === 'services';
  const isStickyVariant = isAreasVariant || isServicesOnly;

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
      } catch {}

      // Persist bio and years of experience along with existing services/areas
      const payload = buildProfileUpdateBody(profileData, {
        bio: profileData.bio,
        years_experience: profileData.years_experience,
        services: profileData.services,
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
      <form className={isStickyVariant ? 'flex min-h-full flex-col' : 'divide-y divide-gray-200'}>
        {isStickyVariant && (
          <div className="sticky top-0 z-30 border-b border-gray-200 bg-white px-6 py-4">
            <div className="flex items-center justify-between">
              <div>
                <Dialog.Title className="text-lg font-semibold text-gray-900">
                  {isAreasVariant ? 'Service Areas' : 'Skills & Pricing'}
                </Dialog.Title>
                <VisuallyHidden>
                  <Dialog.Description>
                    {isAreasVariant
                      ? 'Manage your selected neighborhoods along with preferred teaching and public locations.'
                      : 'Manage your skills, services, and pricing details.'}
                  </Dialog.Description>
                </VisuallyHidden>
              </div>
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="inline-flex h-8 w-8 items-center justify-center rounded-full text-gray-500 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-300"
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
                onChange={(e) => {
                  const parsed = parseInt(e.target.value, 10);
                  setProfileData({
                    ...profileData,
                    years_experience: Number.isNaN(parsed) ? 0 : parsed,
                  });
                }}
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
          <div className={isAreasOnly ? 'px-6 py-6 pb-24' : 'px-6 py-6'}>
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
                  <div className="rounded-lg border border-gray-200 bg-white p-3 mb-3">
                    <div className="text-sm text-gray-700 mb-2">Results</div>
                    <div className="flex flex-wrap gap-2">
                      {globalNeighborhoodMatches
                        .slice(0, 200)
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
                        .filter(Boolean)}
                      {globalNeighborhoodMatches.length === 0 && (
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
                  <p className="text-xs text-gray-600 mb-2 md:max-w-[28rem]">
                    Add a studio, gym, or home address if you teach from a fixed
                    <br />
                    location.
                  </p>
                <div className="grid grid-cols-1 gap-3 items-start md:grid-cols-2">
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
                          onClick={addTeachingPlace}
                          aria-label="Add address"
                          disabled={teachingPlaces.length >= 2}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-[#7E22CE] rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 focus:outline-none no-hover-shadow disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
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
                            className="absolute -top-5 left-2 w-[calc(100%-0.75rem)] border-0 bg-transparent px-0 py-0 text-xs font-medium text-[#7E22CE] focus:outline-none focus:ring-0"
                          />
                          <div className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm">
                            <span className="truncate min-w-0" title={place.address}>{place.address}</span>
                            <button
                              type="button"
                              aria-label={`Remove ${place.address}`}
                              className="ml-auto inline-flex h-6 w-6 items-center justify-center rounded-full text-[#7E22CE] hover:bg-purple-50"
                              onClick={() => removeTeachingPlace(index)}
                            >
                              &times;
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Preferred Public Spaces */}
                <div className="mt-6">
                  <p className="text-gray-600 mt-1 mb-2">Preferred Public Spaces</p>
                  <p className="text-xs text-gray-600 mb-2 md:max-w-[28rem]">
                    Suggest public spaces where you’re comfortable teaching
                    <br />
                    (e.g., library, park, coffee shop).
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
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-[#7E22CE] rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 focus:outline-none no-hover-shadow disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
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
                            className="absolute -top-5 left-2 w-[calc(100%-0.75rem)] border-0 bg-transparent px-0 py-0 text-xs font-medium text-[#7E22CE] focus:outline-none focus:ring-0"
                          />
                          <div className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm">
                            <span className="truncate min-w-0" title={place.address}>{place.address}</span>
                            <button
                              type="button"
                              aria-label={`Remove ${place.address}`}
                              className="ml-auto inline-flex h-6 w-6 items-center justify-center rounded-full text-[#7E22CE] hover:bg-purple-50"
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
                <h3 className="text-lg font-medium text-gray-900 mb-1">Service Areas</h3>
                <p className="text-xs text-gray-600 mb-4 md:max-w-[28rem]">
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
                    {selectedServices.map((s) => {
                      const label = displayServiceName(
                        {
                          service_catalog_id: s.catalog_service_id,
                          service_catalog_name: s.service_catalog_name ?? s.name,
                        },
                        hydrateCatalogNameById,
                      );

                      if (
                        process.env.NODE_ENV !== 'production' &&
                        !s.service_catalog_name &&
                        !hydrateCatalogNameById(s.catalog_service_id)
                      ) {
                        logger.warn('[service-name] missing catalog name (edit modal chip)', {
                          serviceCatalogId: s.catalog_service_id,
                        });
                      }

                      return (
                        <span
                          key={`sel-${s.catalog_service_id}`}
                          className="inline-flex items-center gap-2 rounded-full border border-gray-300 bg-white px-3 h-8 text-xs min-w-0"
                        >
                          <span className="truncate max-w-[14rem]" title={label}>{label}</span>
                          <button
                            type="button"
                            aria-label={`Remove ${label}`}
                            className="ml-auto text-[#7E22CE] rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 no-hover-shadow shrink-0"
                            onClick={() => setSelectedServices((prev) => prev.filter((x) => x.catalog_service_id !== s.catalog_service_id))}
                          >
                            &times;
                          </button>
                        </span>
                      );
                    })}
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
                                if (exists) {
                                  setSelectedServices((prev) => prev.filter((s) => s.catalog_service_id !== svc.id));
                                } else {
                                  setSelectedServices((prev) => {
                                    const label = displayServiceName(
                                      { service_catalog_id: svc.id, service_catalog_name: svc.name },
                                      hydrateCatalogNameById,
                                    );
                                    return [
                                      ...prev,
                                      {
                                        catalog_service_id: svc.id,
                                        service_catalog_name: svc.name,
                                        name: label,
                                        hourly_rate: '',
                                        ageGroup: 'adults',
                                        description: '',
                                        equipment: '',
                                        levels_taught: ['beginner', 'intermediate', 'advanced'],
                                        duration_options: [60],
                                        location_types: ['in-person'],
                                      },
                                    ];
                                  });
                                }
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
                                    if (exists) {
                                      setSelectedServices((prev) => prev.filter((s) => s.catalog_service_id !== svc.id));
                                    } else {
                                      setSelectedServices((prev) => {
                                        const label = displayServiceName(
                                          { service_catalog_id: svc.id, service_catalog_name: svc.name },
                                          hydrateCatalogNameById,
                                        );
                                        return [
                                          ...prev,
                                          {
                                            catalog_service_id: svc.id,
                                            service_catalog_name: svc.name,
                                            name: label,
                                            hourly_rate: '',
                                            ageGroup: 'adults',
                                            description: '',
                                            equipment: '',
                                            levels_taught: ['beginner', 'intermediate', 'advanced'],
                                            duration_options: [60],
                                            location_types: ['in-person'],
                                          },
                                        ];
                                      });
                                    }
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
                      {selectedServices.map((s) => {
                        const violations = serviceFloorViolations.get(s.catalog_service_id) ?? [];
                        const label = displayServiceName(
                          {
                            service_catalog_id: s.catalog_service_id,
                            service_catalog_name: s.service_catalog_name ?? s.name,
                          },
                          hydrateCatalogNameById,
                        );

                        if (
                          process.env.NODE_ENV !== 'production' &&
                          !s.service_catalog_name &&
                          !hydrateCatalogNameById(s.catalog_service_id)
                        ) {
                          logger.warn('[service-name] missing catalog name (edit modal summary)', {
                            serviceCatalogId: s.catalog_service_id,
                          });
                        }

                        return (
                          <div key={s.catalog_service_id} className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                          <div className="flex items-start justify-between mb-3">
                            <div>
                              <div className="text-base font-medium text-gray-900">{label}</div>
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
                                You&apos;ll earn{' '}
                                <span className="font-semibold text-[#7E22CE]">
                                  ${(Number(s.hourly_rate) * instructorTakeHomePct).toFixed(2)}
                                </span>{' '}
                                after the {platformFeeLabel} platform fee
                              </div>
                            )}
                            {violations.length > 0 && (
                              <div className="mt-2 space-y-1 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                                {violations.map((violation, index) => (
                                  <div key={`${violation.modalityLabel}-${violation.duration}-${index}`}>
                                    Minimum for {violation.modalityLabel} {violation.duration}-minute private session is ${formatCents(violation.floorCents)} (current ${formatCents(violation.baseCents)}).
                                  </div>
                                ))}
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
                        );
                      })}
                    </div>
                  )}
                </div>

              </>
            )}
          </div>
        )}
        </div>
        {isStickyVariant && (
          <div className="sticky bottom-0 z-30 border-t border-gray-200 bg-white px-6 py-4">
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  logger.debug('Edit profile cancelled');
                  onClose();
                }}
                className="px-4 py-2.5 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-400 transition-all duration-150 font-medium"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={isAreasVariant ? () => { void handleAreasSave(); } : () => { void handleServicesSave(); }}
                disabled={isAreasVariant ? savingAreas : (svcSaving || hasServiceFloorViolations)}
                className="px-4 py-2.5 bg-[#7E22CE] text-white rounded-lg hover:bg-[#7E22CE] disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-150 font-medium focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#7E22CE]"
              >
                {(isAreasVariant ? savingAreas : svcSaving) ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        )}
      </form>
    </Modal>
  );
}
