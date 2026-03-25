'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState, useRef, useCallback, forwardRef, useImperativeHandle } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Tag } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { User as UserIcon, ChevronDown, Camera } from 'lucide-react';
import { SectionHeroCard } from '@/components/dashboard/SectionHeroCard';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { withApiBase } from '@/lib/apiBase';
import { extractApiErrorCode, extractApiErrorMessage } from '@/lib/apiErrors';
import { fetchWithSessionRefresh } from '@/lib/auth/sessionRefresh';
import { logger } from '@/lib/logger';
import { useInstructorProfileMe } from '@/hooks/queries/useInstructorProfileMe';
import { useSession } from '@/src/api/hooks/useSession';
import { queryKeys } from '@/src/api/queryKeys';
import { useUserAddresses, useInvalidateUserAddresses } from '@/hooks/queries/useUserAddresses';
import { usePhoneVerificationFlow } from '@/features/shared/hooks/usePhoneVerificationFlow';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { ProfilePictureUpload } from '@/components/user/ProfilePictureUpload';
import { formatProblemMessages } from '@/lib/httpErrors';
import type {
  AddressListResponse,
  ApiErrorResponse,
  NeighborhoodsListResponse,
  InstructorProfileResponse,
} from '@/features/shared/api/types';
import {
  debugProfilePayload,
  type InstructorUpdatePayload,
  type PreferredPublicSpacePayload,
  type PreferredTeachingLocationPayload,
} from '@/lib/profileSchemaDebug';
import { getServiceAreaBoroughs } from '@/lib/profileServiceAreas';
import type { ProfileFormState, ServiceAreaItem, ServiceAreasResponse, NYCZipCheck } from './types';
import type { ServiceAreaNeighborhood } from '@/types/instructor';
import { submitServiceAreasOnce } from '@/app/(auth)/instructor/profile/serviceAreaSubmit';
import SkillsPricingInline, { type EnabledFormats } from '@/features/instructor-profile/SkillsPricingInline';
import { PersonalInfoCard } from '@/app/(auth)/instructor/onboarding/account-setup/components/PersonalInfoCard';
import { BioCard } from '@/app/(auth)/instructor/onboarding/account-setup/components/BioCard';
import { ServiceAreasCard } from '@/app/(auth)/instructor/onboarding/account-setup/components/ServiceAreasCard';
import { PreferredLocationsCard } from '@/app/(auth)/instructor/onboarding/account-setup/components/PreferredLocationsCard';

function getYearsExperienceValue(profile: ProfileFormState): number {
  return Number(profile.years_experience);
}

function buildInstructorProfilePayload(profile: ProfileFormState): InstructorUpdatePayload {
  return {
    bio: profile.bio.trim(),
    years_experience: getYearsExperienceValue(profile),
  };
}

function profileRequiresPreferredTeachingLocation(
  profile: InstructorProfileResponse | null,
): boolean {
  if (!Array.isArray(profile?.services)) {
    return false;
  }

  return profile.services.some((service) => {
    const serviceRecord = service as Record<string, unknown>;
    const formatPrices = Array.isArray(serviceRecord['format_prices'])
      ? (serviceRecord['format_prices'] as Array<Record<string, unknown>>)
      : [];

    return formatPrices.some((formatPrice) => formatPrice['format'] === 'instructor_location');
  });
}

function hasNonEmptyLocation(locations: string[]): boolean {
  return locations.some((location) => location.trim().length > 0);
}

type InstructorAddressPayload = {
  street_line1: string;
  street_line2?: string;
  locality: string;
  administrative_area: string;
  postal_code: string;
  country_code: string;
  is_default: boolean;
  place_id?: string;
  latitude?: number;
  longitude?: number;
};

function buildInstructorAddressPayload(profile: ProfileFormState): InstructorAddressPayload | null {
  const streetLine1 = profile.street_line1?.trim();
  const locality = profile.locality?.trim();
  const administrativeArea = profile.administrative_area?.trim();
  const postalCode = profile.postal_code?.trim();

  if (!streetLine1 || !locality || !administrativeArea || !postalCode) {
    return null;
  }

  const payload: InstructorAddressPayload = {
    street_line1: streetLine1,
    locality,
    administrative_area: administrativeArea,
    postal_code: postalCode,
    country_code: profile.country_code?.trim() || 'US',
    is_default: true,
  };

  const streetLine2 = profile.street_line2?.trim();
  if (streetLine2) payload.street_line2 = streetLine2;
  const placeId = profile.place_id?.trim();
  if (placeId) payload.place_id = placeId;
  if (typeof profile.latitude === 'number') payload.latitude = profile.latitude;
  if (typeof profile.longitude === 'number') payload.longitude = profile.longitude;

  return payload;
}

function toTitle(s: string): string {
  return s
    .trim()
    .toLowerCase()
    .split(' ')
    .filter(Boolean)
    .map((w) => {
      const firstChar = w.charAt(0);
      return firstChar ? firstChar.toUpperCase() + w.slice(1) : w;
    })
    .join(' ');
}

type InstructorProfileFormProps = {
  context?: 'dashboard' | 'onboarding';
  embedded?: boolean;
  showPersonalInfo?: boolean;
  onStepStatusChange?: (status: 'done' | 'failed') => void;
};

export type InstructorProfileFormHandle = {
  save: (options?: { redirectTo?: string }) => Promise<void>;
};

const InstructorProfileForm = forwardRef<InstructorProfileFormHandle, InstructorProfileFormProps>(function InstructorProfileForm(
  { context = 'dashboard', embedded: embeddedProp, showPersonalInfo = true, onStepStatusChange }: InstructorProfileFormProps,
  ref
) {
  const isOnboarding = context === 'onboarding';
  const embedded = isOnboarding ? false : Boolean(embeddedProp);
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastNameError, setLastNameError] = useState<string | null>(null);
  // Success toast handled via Sonner; no local success banner state
  const [profile, setProfile] = useState<ProfileFormState>({
    first_name: '',
    last_name: '',
    postal_code: '',
    bio: '',
    service_area_summary: null,
    service_area_boroughs: [],
    years_experience: 0
  });
  const [instructorMeta, setInstructorMeta] = useState<InstructorProfileResponse | null>(null);
  const handleProfileChange = useCallback((updates: Partial<ProfileFormState>) => {
    if ('last_name' in updates) {
      setLastNameError(null);
    }
    setProfile((prev) => ({ ...prev, ...updates }));
  }, []);
  const [isNYC, setIsNYC] = useState<boolean>(true); // default to true for now
  const [selectedNeighborhoods, setSelectedNeighborhoods] = useState<Set<string>>(new Set());
  const [boroughNeighborhoods, setBoroughNeighborhoods] = useState<Record<string, ServiceAreaItem[]>>({});
  const [openBoroughsMain, setOpenBoroughsMain] = useState<Set<string>>(new Set());
  const [globalNeighborhoodFilter, setGlobalNeighborhoodFilter] = useState<string>('');
  const [idToItem, setIdToItem] = useState<Record<string, ServiceAreaItem>>({});
  // Removed selected neighborhoods pills panel state
  const boroughAccordionRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [preferredAddress, setPreferredAddress] = useState<string>('');
  const [preferredLocations, setPreferredLocations] = useState<string[]>([]);
  const [neutralLocations, setNeutralLocations] = useState<string>('');
  const [neutralPlaces, setNeutralPlaces] = useState<string[]>([]);
  const [preferredLocationTitles, setPreferredLocationTitles] = useState<Record<string, string>>({});
  const [bioTouched, setBioTouched] = useState<boolean>(false);
  // Track which lesson formats are enabled across all services (driven by SkillsPricingInline).
  // Default to true so sections show until SkillsPricingInline reports the actual state.
  const [enabledFormats, setEnabledFormats] = useState<EnabledFormats>({
    student_location: true,
    instructor_location: true,
    online: true,
  });
  const inFlightServiceAreasRef = useRef(false);
  const redirectingRef = useRef(false);
  // Fetch guard to prevent duplicate API calls in React Strict Mode
  const hasFetchedPrefillRef = useRef(false);
  // Track initial locations loaded from API to avoid sending unchanged empty arrays
  const initialPreferredLocationsRef = useRef<string[]>([]);
  const initialNeutralPlacesRef = useRef<string[]>([]);

  // Use React Query hook for instructor profile - leverages cache from dashboard
  const { data: instructorProfileFromHook, isLoading: isProfileLoading } = useInstructorProfileMe(true);
  // Use React Query hooks for user session and addresses (prevents duplicate API calls)
  const { data: userDataFromHook, isLoading: isUserLoading } = useSession();
  const { data: addressesDataFromHook, isLoading: isAddressesLoading } = useUserAddresses();
  const invalidateUserAddresses = useInvalidateUserAddresses();
  const queryClient = useQueryClient();
  const phoneVerificationFlow = usePhoneVerificationFlow({
    initialPhoneNumber: userDataFromHook?.phone ?? '',
    onVerified: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.me });
    },
  });
  const [savingServiceAreas, setSavingServiceAreas] = useState(false);
  const [hasProfilePicture, setHasProfilePicture] = useState<boolean>(false);
  const shouldDefaultExpand = isOnboarding;
  const [openPersonal, setOpenPersonal] = useState(shouldDefaultExpand);
  const [openDetails, setOpenDetails] = useState(shouldDefaultExpand);
  const [openServiceAreas, setOpenServiceAreas] = useState(shouldDefaultExpand);
  const [openPreferredLocations, setOpenPreferredLocations] = useState(shouldDefaultExpand);
  const [openSkills, setOpenSkills] = useState(false);
  const shouldRenderPersonalInfo = isOnboarding || showPersonalInfo;
  const requiresPreferredTeachingLocation = useMemo(
    () => profileRequiresPreferredTeachingLocation(instructorMeta),
    [instructorMeta]
  );

  // Derive profile picture status from instructor profile hook (avoids duplicate API call)
  useEffect(() => {
    if (!instructorProfileFromHook) return;
    const hasPic =
      Boolean(instructorProfileFromHook.has_profile_picture) ||
      Number.isFinite(instructorProfileFromHook.profile_picture_version);
    setHasProfilePicture(hasPic);
  }, [instructorProfileFromHook]);

  // Onboarding progress UI removed
  // Derived completion flag (reserved for future server-driven rendering)
  // const isStep1Complete = useMemo(() => {
  //   const hasProfilePic = Boolean(userId);
  //   const personalInfoFilled = Boolean(profile.first_name?.trim()) && Boolean(profile.last_name?.trim()) && Boolean(profile.postal_code?.trim());
  //   const bioOk = (profile.bio?.trim()?.length || 0) >= 400;
  //   const hasServiceArea = selectedNeighborhoods.size > 0;
  //   return hasProfilePic && personalInfoFilled && bioOk && hasServiceArea;
  // }, [userId, profile.first_name, profile.last_name, profile.postal_code, profile.bio, selectedNeighborhoods.size]);

  // Process instructor profile data when available from React Query hooks
  useEffect(() => {
    // Wait for all hooks to load from React Query
    if (isProfileLoading || isUserLoading || isAddressesLoading) return;

    // Wait for hook data to be available (prevents loading with empty data)
    // On dashboard, the cache should already be populated from the parent's fetch
    if (!instructorProfileFromHook) {
      // No data yet - keep waiting (the hook will populate from cache or fetch)
      return;
    }

    // Skip if already processed (prevents duplicate processing in React Strict Mode)
    if (hasFetchedPrefillRef.current) {
      setLoading(false);
      return;
    }
    hasFetchedPrefillRef.current = true;

    const load = async () => {
      try {
        setLoading(true);
        // Use data from React Query hook instead of fetching
        const data = instructorProfileFromHook as unknown as InstructorProfileResponse;
        setInstructorMeta(data);
        // Derive initial enabled formats from saved services
        if (data?.services) {
          const initial: EnabledFormats = { student_location: false, instructor_location: false, online: false };
          for (const svc of data.services) {
            for (const fp of svc.format_prices ?? []) {
              if (fp.format === 'student_location') initial.student_location = true;
              if (fp.format === 'instructor_location') initial.instructor_location = true;
              if (fp.format === 'online') initial.online = true;
            }
          }
          setEnabledFormats(initial);
        }
        const record = (data ?? {}) as Record<string, unknown>;
        logger.debug('Prefill: /instructors/me from cache', { keys: Object.keys(record || {}) });

        // Get user info for name fields from React Query hook (no API call needed)
        let firstName = '';
        let lastName = '';
        let userZip = '';
        if (userDataFromHook) {
          firstName = userDataFromHook.first_name || '';
          lastName = userDataFromHook.last_name || '';
          userZip = userDataFromHook.zip_code || '';
          logger.debug('Prefill: /auth/me from cache', { first_name: firstName, last_name: lastName, id: userDataFromHook.id, zip_code: userZip });
        } else if (record['user']) {
          // Fallback to instructor payload's embedded user if available
          const userObj = record['user'] as Record<string, unknown>;
          firstName = (userObj['first_name'] as string) || '';
          lastName = (userObj['last_name'] as string) || '';
          userZip = (userObj['zip_code'] as string) || '';
          logger.debug('Prefill: using instructor.user fallback', { first_name: firstName, last_name: lastName, zip_code: userZip });
        }

        // Get postal code from default address using React Query hook data (no API call needed)
        let postalCode = '';
        if (addressesDataFromHook?.items) {
          const items = addressesDataFromHook.items;
          const def = items.find((a) => a.is_default) ?? items[0];
          postalCode = def?.postal_code ?? '';
          logger.debug('Prefill: /addresses/me from cache', { id: def?.id, postal_code: postalCode });
        }
        // if no default address zip, fallback to user zip from /auth/me
        if (!postalCode && userZip) {
          postalCode = userZip;
          logger.debug('Prefill: using user.zip_code fallback for postal_code', { postal_code: postalCode });
        }

        const neighborhoodsRaw = Array.isArray(data?.['service_area_neighborhoods'])
          ? (data['service_area_neighborhoods'] as ServiceAreaItem[])
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
        const boroughsFromApi = Array.isArray(data?.['service_area_boroughs'])
          ? (data['service_area_boroughs'] as string[]).filter((value) => typeof value === 'string' && value.trim().length > 0)
          : [];

        setProfile({
          first_name: firstName,
          last_name: lastName,
          postal_code: postalCode,
          bio: (data['bio'] as string) || '',
          service_area_summary: (data['service_area_summary'] as string | null | undefined) ?? null,
          service_area_boroughs:
            boroughsFromApi.length > 0
              ? boroughsFromApi
              : getServiceAreaBoroughs({
                  service_area_boroughs: boroughsFromApi,
                  service_area_neighborhoods: neighborhoods,
                }),
          service_area_neighborhoods: neighborhoods,
          years_experience: (data['years_experience'] as number) ?? 0,
        });

        const teachingFromApi = Array.isArray(data?.['preferred_teaching_locations'])
          ? (data['preferred_teaching_locations'] as Array<Record<string, unknown>>)
          : [];
        const teachingTitles: Record<string, string> = {};
        const teachingAddresses: string[] = [];
        const seenTeaching = new Set<string>();
        for (const item of teachingFromApi) {
          const rawAddress = typeof item?.['address'] === 'string' ? item['address'].trim() : '';
          if (!rawAddress) continue;
          const key = rawAddress.toLowerCase();
          if (seenTeaching.has(key)) continue;
          seenTeaching.add(key);
          teachingAddresses.push(rawAddress);
          const labelValue = typeof item?.['label'] === 'string' ? item['label'].trim() : '';
          teachingTitles[rawAddress] = labelValue;
          if (teachingAddresses.length === 2) break;
        }
        setPreferredLocations(teachingAddresses);
        initialPreferredLocationsRef.current = [...teachingAddresses];
        setPreferredLocationTitles(teachingTitles);

        const publicFromApi = Array.isArray(data?.['preferred_public_spaces'])
          ? (data['preferred_public_spaces'] as Array<Record<string, unknown>>)
          : [];
        const publicAddresses: string[] = [];
        const seenPublic = new Set<string>();
        for (const item of publicFromApi) {
          const rawAddress = typeof item?.['address'] === 'string' ? item['address'].trim() : '';
          if (!rawAddress) continue;
          const key = rawAddress.toLowerCase();
          if (seenPublic.has(key)) continue;
          seenPublic.add(key);
          publicAddresses.push(rawAddress);
          if (publicAddresses.length === 2) break;
        }
        setNeutralPlaces(publicAddresses);
        initialNeutralPlacesRef.current = [...publicAddresses];

        // Prefill service areas (neighborhoods)
        try {
          const areasRes = await fetchWithAuth('/api/v1/addresses/service-areas/me');
          logger.debug('Prefill: /api/v1/addresses/service-areas/me status', { status: areasRes.status });
          if (areasRes.ok) {
            const areas: ServiceAreasResponse = await areasRes.json();
            const items = (areas.items || []) as ServiceAreaItem[];
            const ids = items
              .map((a) => a['neighborhood_id'] || (a as Record<string, unknown>)['id'] as string)
              .filter((v: string | undefined): v is string => typeof v === 'string');
            setSelectedNeighborhoods(new Set(ids));
            // Prime name map so selections show even before a borough loads
            setIdToItem((prev) => {
              const next = { ...prev } as Record<string, ServiceAreaItem>;
              for (const a of items) {
                const nid = a['neighborhood_id'] || (a as Record<string, unknown>)['id'] as string;
                if (nid) next[nid] = a;
              }
              return next;
            });
          }
        } catch (err) {
          logger.warn('Failed to prefill service areas', err);
        }

        // Detect NYC from default address postal code using hook data
        try {
          if (addressesDataFromHook?.items) {
            const items = addressesDataFromHook.items;
            const def = items.find((a) => a.is_default) ?? items[0];
            const zip = def?.postal_code;
            if (zip) {
              const nycRes = await fetchWithSessionRefresh(withApiBase(`${API_ENDPOINTS.NYC_ZIP_CHECK}?zip=${encodeURIComponent(zip)}`), {
                credentials: 'include',
              });
              logger.debug('Prefill: NYC zip check status', { status: nycRes.status, zip });
              if (nycRes.ok) {
                const nyc: NYCZipCheck = await nycRes.json();
                setIsNYC(!!nyc['is_nyc']);
                logger.debug('Prefill: NYC zip check body', nyc);
              }
            }
          }
        } catch (err) {
          logger.warn('Failed to check NYC zip', err);
        }
      } catch (e) {
        logger.error('Failed to load profile', e);
        setError('Failed to load profile');
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [instructorProfileFromHook, isProfileLoading, userDataFromHook, isUserLoading, addressesDataFromHook, isAddressesLoading]);

  useEffect(() => {
    if (!isOnboarding || !instructorMeta || redirectingRef.current) return;
    const isLive = Boolean(instructorMeta.is_live || instructorMeta.onboarding_completed_at);
    if (isLive) {
      redirectingRef.current = true;
      toast.success('Your profile is already live. Redirecting to your dashboard...');
      router.replace('/instructor/dashboard');
    }
  }, [instructorMeta, isOnboarding, router]);

  // Success toast is triggered directly in save(); no banner state

  const bioTooShort = profile.bio.trim().length < 400;

  const [isGeneratingBio, setIsGeneratingBio] = useState(false);

  const handleGenerateBio = useCallback(async () => {
    setIsGeneratingBio(true);
    try {
      const response = await fetchWithAuth('/api/v1/instructors/me/generate-bio', {
        method: 'POST',
      });
      if (!response.ok) {
        const errorData = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(errorData?.detail ?? 'Failed to generate bio');
      }
      const data = (await response.json()) as { bio: string };
      setProfile((prev) => ({ ...prev, bio: data.bio }));
      setBioTouched(true);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to generate bio. Please try again.');
    } finally {
      setIsGeneratingBio(false);
    }
  }, [setBioTouched]);


  // Removed selected neighborhoods panel prefetch effect

  // NYC helpers
  const NYC_BOROUGHS = useMemo(() => ['Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island'] as const, []);

  const loadBoroughNeighborhoods = useCallback(async (borough: string): Promise<ServiceAreaItem[]> => {
    if (boroughNeighborhoods[borough]) return boroughNeighborhoods[borough] || [];
    try {
      const url = withApiBase(`/api/v1/addresses/regions/neighborhoods?region_type=nyc&borough=${encodeURIComponent(borough)}&per_page=500`);
      const r = await fetchWithSessionRefresh(url, { credentials: 'include' });
      if (r.ok) {
        const data = (await r.json()) as NeighborhoodsListResponse;
        const list = (data.items ?? []).flatMap((raw) => {
          const record = raw as Record<string, unknown>;
          const neighborhoodId =
            typeof record['neighborhood_id'] === 'string'
              ? (record['neighborhood_id'] as string)
              : typeof record['id'] === 'string'
              ? (record['id'] as string)
              : '';
          if (!neighborhoodId) return [];
          return [
            {
              neighborhood_id: neighborhoodId,
              ntacode:
                typeof record['ntacode'] === 'string'
                  ? (record['ntacode'] as string)
                  : typeof record['code'] === 'string'
                  ? (record['code'] as string)
                  : null,
              name: typeof record['name'] === 'string' ? (record['name'] as string) : null,
              borough: record['borough'] ?? null,
            } as ServiceAreaItem,
          ];
        });
        setBoroughNeighborhoods((prev) => ({ ...prev, [borough]: list }));
        setIdToItem((prev) => {
          const next = { ...prev } as Record<string, ServiceAreaItem>;
          for (const it of list) {
            if (it.neighborhood_id) next[it.neighborhood_id] = it;
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

  // When using global neighborhood search, ensure borough lists are prefetched
  useEffect(() => {
    if (globalNeighborhoodFilter.trim().length > 0) {
      NYC_BOROUGHS.forEach((b) => {
        void loadBoroughNeighborhoods(b);
      });
    }
  }, [globalNeighborhoodFilter, NYC_BOROUGHS, loadBoroughNeighborhoods]);

  // Removed selected neighborhoods panel accordion handlers

  // Toggle main borough accordion with scroll-position preservation
  const toggleMainBoroughOpen = async (b: string) => {
    const el = boroughAccordionRefs.current[b];
    const prevTop = el?.getBoundingClientRect().top ?? 0;
    setOpenBoroughsMain((prev) => {
      const next = new Set(prev);
      if (next.has(b)) next.delete(b);
      else next.add(b);
      return next;
    });
    await loadBoroughNeighborhoods(b);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const newTop = boroughAccordionRefs.current[b]?.getBoundingClientRect().top ?? prevTop;
        const delta = newTop - prevTop;
        if (delta !== 0) {
          window.scrollBy({ top: delta, left: 0, behavior: 'auto' });
        }
      });
    });
  };

  const save = async (options?: { redirectTo?: string }) => {
    const redirectTo = options?.redirectTo;
    try {
      setSaving(true);
      setError(null);
      setLastNameError(null);

      // Client-side bio length validation (backend enforces min=10, max=1000)
      const bioTrimmed = profile.bio.trim();
      if (bioTrimmed.length < 10) {
        setError('Bio must be at least 10 characters.');
        toast.error('Bio must be at least 10 characters.');
        onStepStatusChange?.('failed');
        return;
      }
      if (bioTrimmed.length > 1000) {
        setError('Bio must be 1,000 characters or fewer.');
        toast.error('Bio must be 1,000 characters or fewer.');
        onStepStatusChange?.('failed');
        return;
      }

      const yearsExperience = getYearsExperienceValue(profile);
      if (!Number.isFinite(yearsExperience) || yearsExperience < 1) {
        const message = 'Years of experience is required (minimum 1)';
        setError(message);
        toast.error(message);
        onStepStatusChange?.('failed');
        return;
      }

      // Update user info if changed
      if (profile.first_name || profile.last_name) {
        const nameResponse = await fetchWithAuth(API_ENDPOINTS.ME, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            first_name: profile.first_name.trim(),
            last_name: profile.last_name.trim(),
          }),
        });
        if (!nameResponse.ok) {
          const errorData = (await nameResponse.json()) as ApiErrorResponse;
          const message = extractApiErrorMessage(errorData, 'Failed to update account details');
          if (extractApiErrorCode(errorData) === 'last_name_locked') {
            setLastNameError(message);
            toast.error('Last name must match your verified government ID. Contact support if you need to update it.');
            return;
          }
          throw new Error(message);
        }
      }

      const payload = buildInstructorProfilePayload(profile);

      const teachingPayload: PreferredTeachingLocationPayload[] = [];
      const seenTeaching = new Set<string>();
      for (const raw of preferredLocations) {
        const trimmed = raw.trim();
        if (!trimmed) continue;
        const key = trimmed.toLowerCase();
        if (seenTeaching.has(key)) continue;
        seenTeaching.add(key);
        const labelSource = preferredLocationTitles[trimmed] ?? preferredLocationTitles[raw] ?? '';
        const label = labelSource?.trim?.() || '';
        const entry: PreferredTeachingLocationPayload = { address: trimmed };
        if (label.length > 0) {
          entry.label = label;
        }
        teachingPayload.push(entry);
        if (teachingPayload.length === 2) break;
      }

      const publicPayload: PreferredPublicSpacePayload[] = [];
      const seenPublic = new Set<string>();
      for (const raw of neutralPlaces) {
        const trimmed = raw.trim();
        if (!trimmed) continue;
        const key = trimmed.toLowerCase();
        if (seenPublic.has(key)) continue;
        seenPublic.add(key);
        publicPayload.push({ address: trimmed });
        if (publicPayload.length === 2) break;
      }

      const teachingChanged =
        JSON.stringify(preferredLocations.map(l => l.trim().toLowerCase()).sort()) !==
        JSON.stringify(initialPreferredLocationsRef.current.map(l => l.trim().toLowerCase()).sort());
      const publicChanged =
        JSON.stringify(neutralPlaces.map(l => l.trim().toLowerCase()).sort()) !==
        JSON.stringify(initialNeutralPlacesRef.current.map(l => l.trim().toLowerCase()).sort());

      if (teachingChanged) {
        payload.preferred_teaching_locations = teachingPayload;
      }
      if (publicChanged) {
        payload.preferred_public_spaces = publicPayload;
      }

      debugProfilePayload('InstructorUpdate', payload);
      const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let message = `Request failed (${res.status})`;
        try {
          const body = (await res.json()) as ApiErrorResponse;
          const messages = formatProblemMessages(body);
          if (messages.length > 0) {
            message = messages.join('; ');
          }
        } catch (parseError) {
          logger.warn('Failed to parse instructor profile error response', parseError);
        }
        setError(message);
        toast.error(message);
        return;
      }

      const deriveErrorMessage = async (resp: Response, fallback: string) => {
        try {
          const body = (await resp.clone().json()) as ApiErrorResponse;
          const messages = formatProblemMessages(body);
          if (messages.length > 0) {
            return messages.join('; ');
          }
        } catch (parseError) {
          logger.warn('Failed to parse address error response', parseError instanceof Error ? parseError : undefined);
        }
        return fallback;
      };

      const addressPayload = buildInstructorAddressPayload(profile);
      if (addressPayload) {
        debugProfilePayload('AddressCreate', addressPayload);
      }

      try {
        const addrRes = await fetchWithAuth('/api/v1/addresses/me');
        if (addrRes.ok) {
          const list = (await addrRes.json()) as AddressListResponse;
          const items = (list.items || []) as Record<string, unknown>[];
          const def = items.find((a) => a['is_default']) || items[0];
          if (def) {
            const currentZip = def['postal_code'] || '';
            const newZip = (profile.postal_code || '').trim();
            if (newZip && newZip !== currentZip) {
              const patchRes = await fetchWithAuth(`/api/v1/addresses/me/${def['id']}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ postal_code: newZip }),
              });
              if (!patchRes.ok) {
                const message = await deriveErrorMessage(patchRes, `Request failed (${patchRes.status})`);
                setError(message);
                toast.error(message);
                return;
              }
            }
          } else if (addressPayload) {
            const createRes = await fetchWithAuth('/api/v1/addresses/me', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(addressPayload),
            });
            if (!createRes.ok) {
              const message = await deriveErrorMessage(createRes, `Request failed (${createRes.status})`);
              setError(message);
              toast.error(message);
              return;
            }
          }
        } else if (addrRes.status === 404) {
          if (addressPayload) {
            const createRes = await fetchWithAuth('/api/v1/addresses/me', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(addressPayload),
            });
            if (!createRes.ok) {
              const message = await deriveErrorMessage(createRes, `Request failed (${createRes.status})`);
              setError(message);
              toast.error(message);
              return;
            }
          }
        } else {
          const message = await deriveErrorMessage(addrRes, `Request failed (${addrRes.status})`);
          setError(message);
          toast.error(message);
          return;
        }
      } catch (addressError) {
        logger.warn('Failed to sync address during profile save', addressError instanceof Error ? addressError : undefined);
      }

      // Invalidate addresses cache after any address operations
      void invalidateUserAddresses();

      // Persist service areas (StrictMode-safe guard)
      if (!inFlightServiceAreasRef.current) {
        const serviceAreasPayload = { neighborhood_ids: Array.from(selectedNeighborhoods) };
        debugProfilePayload('ServiceAreasPayload', serviceAreasPayload);
        try {
          await submitServiceAreasOnce({
            fetcher: fetchWithAuth,
            payload: serviceAreasPayload,
            inFlightRef: inFlightServiceAreasRef,
            setSaving: setSavingServiceAreas,
          });
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to save service areas';
          logger.warn('Failed to submit service areas during profile save', err);
          setError(message);
          toast.error(message);
          return;
        }
      }

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.instructors.me }),
        queryClient.invalidateQueries({ queryKey: queryKeys.auth.me }),
        queryClient.invalidateQueries({ queryKey: ['instructor', 'service-areas'] }),
      ]);

      if (teachingChanged) {
        initialPreferredLocationsRef.current = [...preferredLocations];
      }
      if (publicChanged) {
        initialNeutralPlacesRef.current = [...neutralPlaces];
      }

      toast.success('Profile saved', {
        style: {
          background: '#6b21a8',
          color: '#ffffff',
          padding: '6px 10px',
          borderRadius: '8px',
          width: '230px',
          minWidth: '230px',
          maxWidth: '230px',
          whiteSpace: 'nowrap'
        }
      });

      // Update visual progress indicators
      const ok = (
        (profile.bio?.trim()?.length || 0) >= 400 &&
        Boolean(profile.first_name?.trim()) &&
        Boolean(profile.last_name?.trim()) &&
        Boolean(profile.postal_code?.trim()) &&
        selectedNeighborhoods.size > 0 &&
        (!requiresPreferredTeachingLocation || hasNonEmptyLocation(preferredLocations)) &&
        (hasProfilePicture || false)
      );
      try {
        sessionStorage.setItem('onboarding_step1_complete', ok ? 'true' : 'false');
      } catch (err) {
        logger.warn('Failed to persist onboarding progress', err);
      }
      onStepStatusChange?.(ok ? 'done' : 'failed');

      if (redirectTo) {
        router.push(redirectTo);
      }
    } catch {
      setError('Failed to save profile');
    } finally {
      setSaving(false);
    }
  };

  useImperativeHandle(ref, () => ({
    save: (options) => save(options),
  }));

  const toggleBoroughAll = (borough: string, value: boolean, itemsOverride?: ServiceAreaItem[]) => {
    const items = itemsOverride || boroughNeighborhoods[borough] || [];
    const ids = items.map((i) => i['neighborhood_id'] || (i as Record<string, unknown>)['id'] as string);
    setSelectedNeighborhoods((prev) => {
      const next = new Set(prev);
      if (value) {
        ids.forEach((id) => next.add(id));
      } else {
        ids.forEach((id) => next.delete(id));
      }
      return next;
    });
  };

  const toggleNeighborhood = (id: string) => {
    setSelectedNeighborhoods((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Note: Borough counts helper can be added back if indeterminate styling is needed in the future

  // Avoid early return to prevent hydration mismatches; render a lightweight inline loader instead

  const showDashboardHeader = !embedded && !isOnboarding;
  const showInlineActions = !isOnboarding;
  const containerClass = embedded
    ? 'max-w-none px-0 lg:px-0 py-0'
    : isOnboarding
      ? 'w-full mt-0 sm:mt-6 space-y-4 sm:space-y-6'
      : 'container mx-auto px-8 lg:px-32 py-8 max-w-6xl';
  const rootClass = isOnboarding ? 'w-full' : 'min-h-screen insta-dashboard-page';

  return (
    <div className={rootClass}>
      {/* Header hidden in embedded or onboarding mode */}
      {showDashboardHeader && (
        <header className="px-4 sm:px-6 py-4 insta-dashboard-header">
          <div className="flex items-center justify-between max-w-full relative">
            <Link href="/instructor/dashboard" className="inline-block">
              <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-purple-900 dark:hover:text-purple-300 transition-colors cursor-pointer pl-0 sm:pl-4">iNSTAiNSTRU</h1>
            </Link>
            {/* Onboarding progress removed for standalone page */}

            <div className="pr-4">
              <UserProfileDropdown />
            </div>
          </div>
        </header>
      )}

      <div className={containerClass}>
        {embedded && loading && (
          <div style={{ height: 1 }} />
        )}
        {!embedded && loading && (
          <div className="p-8 text-sm text-gray-500 dark:text-gray-400">Loading…</div>
        )}
        {/* Page Header hidden in embedded mode */}
        {!embedded && !isOnboarding && (
          <>
            {/* Page Header - mobile: no card chrome; desktop: card */}
            <div className="mb-2 sm:mb-8 p-4 sm:p-6 insta-surface-card">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div>
                    <h1 className="text-3xl font-bold text-gray-800 dark:text-gray-200 mb-1 sm:mb-2 whitespace-nowrap">Profile</h1>
                    <p className="text-gray-600 dark:text-gray-400 hidden sm:block">Manage your instructor profile information</p>
                  </div>
                </div>
                {/* Desktop: keep upload in header */}
                <div className="hidden sm:block">
                  <ProfilePictureUpload
                    ariaLabel="Upload profile photo"
                    trigger={
                      <div className="flex flex-col items-center">
                        <div className="w-20 h-20 rounded-full bg-purple-100 flex items-center justify-center hover:bg-purple-200 dark:hover:bg-purple-800/40 focus:outline-none cursor-pointer" title="Upload profile photo">
                          <Camera className="w-6 h-6 text-[#7E22CE]" />
                        </div>
                        <span className="mt-1 text-[10px] text-[#7E22CE]">Upload photo</span>
                      </div>
                    }
                  />
                </div>
              </div>
            </div>
            {/* Mobile: move upload below header */}
            <div className="p-4 pt-0 sm:hidden">
              <div className="flex items-center justify-between gap-3">
                <p className="text-gray-600 dark:text-gray-400 text-base leading-snug flex-1">Manage your instructor profile information</p>
                <ProfilePictureUpload
                  ariaLabel="Upload profile photo"
                  trigger={
                    <div className="w-24 h-24 rounded-full bg-purple-100 flex items-center justify-center hover:bg-purple-200 dark:hover:bg-purple-800/40 focus:outline-none cursor-pointer" title="Upload profile photo">
                      <Camera className="w-6 h-6 text-[#7E22CE]" />
                    </div>
                  }
                />
              </div>
            </div>
      {/* Mobile divider before Personal Information */}
      <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />
          </>
        )}

      {!isOnboarding && (
        <SectionHeroCard
          id={embedded ? 'profile-first-card' : undefined}
          icon={UserIcon}
          title="Instructor profile"
          subtitle="Update your story and teaching services so students know what to expect."
        />
      )}

      {error && (
        <div className="mb-6 rounded-lg bg-red-50 border border-red-200 text-red-700 px-4 py-3">{error}</div>
      )}
      {/* Success toast is shown as a floating element; banner removed for cleaner UI */}

      {/* Mobile: stacked white sections with mobile-only dividers; Desktop: spaced cards */}
      <div className={embedded ? 'mt-0 sm:mt-0 insta-dashboard-accordion-stack--dividers' : 'mt-0 sm:mt-6 insta-dashboard-accordion-stack--dividers'}>
        {shouldRenderPersonalInfo && (
          <>
            <PersonalInfoCard
              context={context}
              profile={profile}
              lastNameError={lastNameError}
              phoneVerificationFlow={isOnboarding ? phoneVerificationFlow : null}
              onProfileChange={handleProfileChange}
              isOpen={openPersonal}
              onToggle={() => setOpenPersonal((v) => !v)}
            />
            <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />
          </>
        )}

        {/* Professional Information Section */}
        <BioCard
          context={context}
          embedded={embedded}
          profile={profile}
          onProfileChange={handleProfileChange}
          bioTouched={bioTouched}
          bioTooShort={bioTooShort}
          setBioTouched={setBioTouched}
          isOpen={openDetails}
          onToggle={() => setOpenDetails((v) => !v)}
          onGenerateBio={handleGenerateBio}
          isGenerating={isGeneratingBio}
          hasServices={(instructorMeta?.services?.length ?? 0) > 0}
          showCharCount
          maxBioChars={1000}
        />
        {!isOnboarding && (
          <>
            {/* Mobile divider before Skills & Pricing */}
            <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />

            {/* Skills & Pricing Section */}
            <div className="p-4 sm:p-6 insta-surface-card">
              <button
                type="button"
                className={`insta-dashboard-accordion-trigger ${openSkills ? 'mb-4' : ''}`}
                onClick={() => setOpenSkills((v) => !v)}
                aria-expanded={openSkills}
              >
                <div className="insta-dashboard-accordion-leading">
                  <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                    <Tag className="w-6 h-6 text-[#7E22CE]" />
                  </div>
                  <div className="flex flex-col text-left">
                    <span className="insta-dashboard-accordion-title">Skills & Pricing</span>
                    <span className="insta-dashboard-accordion-subtitle">Manage the subjects you teach, durations, and rates students see.</span>
                  </div>
                </div>
                <ChevronDown className={`w-5 h-5 text-gray-600 dark:text-gray-400 transition-transform ${openSkills ? 'rotate-180' : ''}`} />
              </button>
              {openSkills && (
                <div className="py-2">
                  <SkillsPricingInline instructorProfile={instructorMeta} onFormatsChange={setEnabledFormats} />
                </div>
              )}
            </div>
          </>
        )}

        {/* Service Areas — only shown when any service has student_location format enabled */}
        {!isOnboarding && enabledFormats.student_location && (
          <>
            {/* Mobile divider before Service Areas */}
            <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />

            {/* Service Areas Section */}
            <ServiceAreasCard
              context={context}
              isOpen={openServiceAreas}
              onToggle={() => setOpenServiceAreas((v) => !v)}
              globalNeighborhoodFilter={globalNeighborhoodFilter}
              onGlobalFilterChange={(value) => setGlobalNeighborhoodFilter(value)}
              nycBoroughs={NYC_BOROUGHS}
              boroughNeighborhoods={boroughNeighborhoods}
              selectedNeighborhoods={selectedNeighborhoods}
              onToggleNeighborhood={toggleNeighborhood}
              openBoroughs={openBoroughsMain}
              onToggleBoroughAccordion={(borough) => toggleMainBoroughOpen(borough)}
              loadBoroughNeighborhoods={loadBoroughNeighborhoods}
              toggleBoroughAll={toggleBoroughAll}
              boroughAccordionRefs={boroughAccordionRefs}
              idToItem={idToItem}
              isNYC={isNYC}
              formatNeighborhoodName={toTitle}
            />
          </>
        )}

        {/* Class Locations — only shown when any service has instructor_location format enabled */}
        {!isOnboarding && enabledFormats.instructor_location && (
          <PreferredLocationsCard
            context={context}
            isOpen={openPreferredLocations}
            onToggle={() => setOpenPreferredLocations((v) => !v)}
            preferredAddress={preferredAddress}
            setPreferredAddress={setPreferredAddress}
            preferredLocations={preferredLocations}
            setPreferredLocations={setPreferredLocations}
            preferredLocationTitles={preferredLocationTitles}
            setPreferredLocationTitles={setPreferredLocationTitles}
            neutralLocations={neutralLocations}
            setNeutralLocations={setNeutralLocations}
            neutralPlaces={neutralPlaces}
            setNeutralPlaces={setNeutralPlaces}
          />
        )}

        {showInlineActions && (
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => { if (!saving && !savingServiceAreas) { void save(); } }}
              disabled={saving || savingServiceAreas}
              className="w-40 whitespace-nowrap px-5 py-2.5 rounded-lg text-white font-semibold bg-[#7E22CE] hover:bg-purple-800 dark:hover:bg-purple-700 disabled:opacity-50 shadow-sm justify-center insta-primary-btn"
            >
              {saving || savingServiceAreas ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        )}
      </div>
        {/* Inline success banner removed; using Sonner toast instead */}
        {/* Animation CSS now global in app/globals.css */}
      </div>
    </div>
  );
});

export default InstructorProfileForm;
