'use client';

import Link from 'next/link';
import { useEmbedded } from '../_embedded/EmbeddedContext';
import { useEffect, useMemo, useState, useRef, useCallback } from 'react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { User as UserIcon, MapPin, Settings as SettingsIcon, BookOpen, ChevronDown, Camera, Info, ShieldCheck, CreditCard } from 'lucide-react';
import { SectionHeroCard } from '@/components/dashboard/SectionHeroCard';
import * as Tooltip from '@radix-ui/react-tooltip';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { withApiBase } from '@/lib/apiBase';
import { logger } from '@/lib/logger';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { ProfilePictureUpload } from '@/components/user/ProfilePictureUpload';
import { formatProblemMessages } from '@/lib/httpErrors';
import { PlacesAutocompleteInput } from '@/components/forms/PlacesAutocompleteInput';
import {
  debugProfilePayload,
  type InstructorUpdatePayload,
  type PreferredPublicSpacePayload,
  type PreferredTeachingLocationPayload,
} from '@/lib/profileSchemaDebug';
import { getServiceAreaBoroughs } from '@/lib/profileServiceAreas';
import type { ServiceAreaNeighborhood } from '@/types/instructor';
import { submitServiceAreasOnce } from './serviceAreaSubmit';
import SkillsPricingInline from '@/features/instructor-profile/SkillsPricingInline';

type Profile = {
  first_name: string;
  last_name: string;
  postal_code: string;
  bio: string;
  service_area_summary?: string | null;
  service_area_boroughs: string[];
  service_area_neighborhoods?: ServiceAreaNeighborhood[];
  years_experience: number;
  min_advance_booking_hours?: number;
  buffer_time_hours?: number; // store in hours in UI, convert on save
  street_line1?: string;
  street_line2?: string;
  locality?: string;
  administrative_area?: string;
  country_code?: string;
  place_id?: string;
  latitude?: number | null;
  longitude?: number | null;
};

type ServiceAreaItem = {
  id: string;
  neighborhood_id?: string;
  ntacode?: string | null;
  name?: string | null;
  borough?: string | null;
  code?: string | null;
};
type ServiceAreasResponse = { items: ServiceAreaItem[]; total: number };
type NYCZipCheck = { is_nyc: boolean; borough?: string | null };

function buildInstructorProfilePayload(profile: Profile): InstructorUpdatePayload {
  return {
    bio: profile.bio.trim(),
    years_experience: Number(profile.years_experience) || 0,
    min_advance_booking_hours: profile.min_advance_booking_hours ?? 2,
    buffer_time_minutes: Math.round(((profile.buffer_time_hours ?? 0.5) * 60)),
  };
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

function buildInstructorAddressPayload(profile: Profile): InstructorAddressPayload | null {
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

function ProfilePageImpl() {
  const embedded = useEmbedded();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Success toast handled via Sonner; no local success banner state
  const [profile, setProfile] = useState<Profile>({
    first_name: '',
    last_name: '',
    postal_code: '',
    bio: '',
    service_area_summary: null,
    service_area_boroughs: [],
    years_experience: 0
  });
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
  const inFlightServiceAreasRef = useRef(false);
  const [savingServiceAreas, setSavingServiceAreas] = useState(false);
  const [hasProfilePicture, setHasProfilePicture] = useState<boolean>(false);
  const [openIdentity, setOpenIdentity] = useState(false);
  const [openPayments, setOpenPayments] = useState(false);
  const [openPersonal, setOpenPersonal] = useState(false);
  const [openDetails, setOpenDetails] = useState(false);
  const [openServiceAreas, setOpenServiceAreas] = useState(false);
  const [openPreferences, setOpenPreferences] = useState(false);
  const [openSkills, setOpenSkills] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetchWithAuth(API_ENDPOINTS.ME);
        if (res.ok) {
          const me = await res.json();
          const hasPic = Boolean(me?.has_profile_picture) || Number.isFinite(me?.profile_picture_version);
          setHasProfilePicture(hasPic);
        }
      } catch {}
    })();
  }, []);

  // Onboarding progress UI removed
  // Derived completion flag (reserved for future server-driven rendering)
  // const isStep1Complete = useMemo(() => {
  //   const hasProfilePic = Boolean(userId);
  //   const personalInfoFilled = Boolean(profile.first_name?.trim()) && Boolean(profile.last_name?.trim()) && Boolean(profile.postal_code?.trim());
  //   const bioOk = (profile.bio?.trim()?.length || 0) >= 400;
  //   const hasServiceArea = selectedNeighborhoods.size > 0;
  //   return hasProfilePic && personalInfoFilled && bioOk && hasServiceArea;
  // }, [userId, profile.first_name, profile.last_name, profile.postal_code, profile.bio, selectedNeighborhoods.size]);

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);
        logger.debug('Prefill: /instructors/me status', { status: res.status });
        const data = res.ok ? await res.json() : {};
        if (!res.ok) {
          try {
            const errBody = await res.clone().json();
            logger.debug('Prefill: /instructors/me error body', errBody);
          } catch {}
        } else {
          logger.debug('Prefill: /instructors/me body keys', { keys: Object.keys(data || {}) });
        }

        // Get user info for name fields (use /auth/me)
        const userRes = await fetchWithAuth(API_ENDPOINTS.ME);
        logger.debug('Prefill: /auth/me status', { status: userRes.status });
        let firstName = '';
        let lastName = '';
        let userZip = '';
        if (userRes.ok) {
          const userData = await userRes.json();
          firstName = userData['first_name'] || '';
          lastName = userData['last_name'] || '';
          userZip = userData['zip_code'] || '';
          logger.debug('Prefill: /auth/me body', { first_name: firstName, last_name: lastName, id: userData['id'], zip_code: userZip });
        } else if (data && data.user) {
          // Fallback to instructor payload's embedded user if available
          firstName = data.user['first_name'] || '';
          lastName = data.user['last_name'] || '';
          userZip = data.user['zip_code'] || '';
          logger.debug('Prefill: using instructor.user fallback', { first_name: firstName, last_name: lastName, zip_code: userZip });
        }

        // Get postal code from default address
        let postalCode = '';
        try {
          const addrRes = await fetchWithAuth('/api/addresses/me');
          logger.debug('Prefill: /api/addresses/me status', { status: addrRes.status });
          if (addrRes.ok) {
            const list = await addrRes.json();
            const def = (list.items || []).find((a: unknown) => (a as Record<string, unknown>)['is_default']) || (list.items || [])[0];
            postalCode = def?.['postal_code'] || '';
            logger.debug('Prefill: selected default address', { id: def?.['id'], postal_code: postalCode });
          }
        } catch {}
        // if no default address zip, fallback to user zip from /auth/me
        if (!postalCode && userZip) {
          postalCode = userZip;
          logger.debug('Prefill: using user.zip_code fallback for postal_code', { postal_code: postalCode });
        }

        const neighborhoodsRaw = Array.isArray(data?.['service_area_neighborhoods'])
          ? (data['service_area_neighborhoods'] as ServiceAreaItem[])
          : [];
        const neighborhoods = neighborhoodsRaw.reduce<ServiceAreaNeighborhood[]>((acc, item) => {
          const neighborhoodId = item.neighborhood_id || item.id;
          if (!neighborhoodId) {
            return acc;
          }
          acc.push({
            neighborhood_id: neighborhoodId,
            ntacode: item.ntacode ?? item.code ?? null,
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
          bio: data['bio'] || '',
          service_area_summary: (data['service_area_summary'] as string | null | undefined) ?? null,
          service_area_boroughs:
            boroughsFromApi.length > 0
              ? boroughsFromApi
              : getServiceAreaBoroughs({
                  service_area_boroughs: boroughsFromApi,
                  service_area_neighborhoods: neighborhoods,
                }),
          service_area_neighborhoods: neighborhoods,
          years_experience: data['years_experience'] ?? 0,
          min_advance_booking_hours: data['min_advance_booking_hours'] ?? 2,
          buffer_time_hours: Math.max(0.5, Math.min(24, Number(((data['buffer_time_minutes'] ?? 0) / 60) || 0.5))),
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

        // Prefill service areas (neighborhoods)
        try {
          const areasRes = await fetchWithAuth('/api/addresses/service-areas/me');
          logger.debug('Prefill: /api/addresses/service-areas/me status', { status: areasRes.status });
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
        } catch {}

        // Detect NYC from default address postal code if available
        try {
          const addrRes = await fetchWithAuth('/api/addresses/me');
          if (addrRes.ok) {
            const list = await addrRes.json();
            const def = (list.items || []).find((a: unknown) => (a as Record<string, unknown>)['is_default']) || (list.items || [])[0];
            const zip = def?.['postal_code'];
            if (zip) {
              const nycRes = await fetch(withApiBase(`${API_ENDPOINTS.NYC_ZIP_CHECK}?zip=${encodeURIComponent(zip)}`), {
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
        } catch {}
      } catch (e) {
        logger.error('Failed to load profile', e);
        setError('Failed to load profile');
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  // Success toast is triggered directly in save(); no banner state

  const bioTooShort = profile.bio.trim().length < 400;


  // Removed selected neighborhoods panel prefetch effect

  // NYC helpers
  const NYC_BOROUGHS = useMemo(() => ['Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island'] as const, []);

  const loadBoroughNeighborhoods = useCallback(async (borough: string): Promise<ServiceAreaItem[]> => {
    if (boroughNeighborhoods[borough]) return boroughNeighborhoods[borough] || [];
    try {
      const url = withApiBase(`/api/addresses/regions/neighborhoods?region_type=nyc&borough=${encodeURIComponent(borough)}&per_page=500`);
      const r = await fetch(url, { credentials: 'include' });
      if (r.ok) {
        const data = await r.json();
        const list = (data.items || []) as ServiceAreaItem[];
        setBoroughNeighborhoods((prev) => ({ ...prev, [borough]: list }));
        // Update id->item map for display in the selection panel
        setIdToItem((prev) => {
          const next = { ...prev } as Record<string, ServiceAreaItem>;
          for (const it of list) {
            const nid = it['neighborhood_id'] || (it as Record<string, unknown>)['id'] as string;
            if (nid) next[nid] = it;
          }
          return next;
        });
        return list;
      }
    } catch {}
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
      // Update user info if changed
      if (profile.first_name || profile.last_name) {
        await fetchWithAuth(API_ENDPOINTS.ME, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            first_name: profile.first_name.trim(),
            last_name: profile.last_name.trim(),
          }),
        });
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

      payload.preferred_teaching_locations = teachingPayload;
      payload.preferred_public_spaces = publicPayload;

      debugProfilePayload('InstructorUpdate', payload);
      const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let message = `Request failed (${res.status})`;
        try {
          const body = await res.json();
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
          const body = await resp.clone().json();
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
        const addrRes = await fetchWithAuth('/api/addresses/me');
        if (addrRes.ok) {
          const list = await addrRes.json();
          const items = (list.items || []) as Record<string, unknown>[];
          const def = items.find((a) => a['is_default']) || items[0];
          if (def) {
            const currentZip = def['postal_code'] || '';
            const newZip = (profile.postal_code || '').trim();
            if (newZip && newZip !== currentZip) {
              const patchRes = await fetchWithAuth(`/api/addresses/me/${def['id']}`, {
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
            const createRes = await fetchWithAuth('/api/addresses/me', {
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
            const createRes = await fetchWithAuth('/api/addresses/me', {
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
        } catch {
          // Swallow here; page already reports via toast earlier
        }
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
      const stepCircle = document.getElementById('progress-step-1');
      const stepLine = document.getElementById('progress-line-1');
      if (stepCircle && stepLine) {
        const ok = (
          (profile.bio?.trim()?.length || 0) >= 400 &&
          Boolean(profile.first_name?.trim()) &&
          Boolean(profile.last_name?.trim()) &&
          Boolean(profile.postal_code?.trim()) &&
          selectedNeighborhoods.size > 0 &&
          (hasProfilePicture || false)
        );
        try { sessionStorage.setItem('onboarding_step1_complete', ok ? 'true' : 'false'); } catch {}
        if (ok) {
          stepCircle.classList.remove('border-gray-300', 'bg-purple-100');
          stepCircle.classList.add('bg-[#7E22CE]', 'border-[#7E22CE]');
          stepCircle.setAttribute('data-status', 'done');
          // show check, hide cross
          const check = stepCircle.querySelector('.icon-check') as HTMLElement | null;
          const cross = stepCircle.querySelector('.icon-cross') as HTMLElement | null;
          if (check) check.classList.remove('hidden');
          if (cross) cross.classList.add('hidden');
          stepLine.classList.remove('bg-gray-300');
          stepLine.classList.add('bg-[#7E22CE]');
          stepLine.setAttribute('data-status', 'filled');
        } else {
          stepCircle.classList.remove('border-gray-300', 'bg-purple-100');
          stepCircle.classList.add('border-[#7E22CE]', 'bg-[#7E22CE]');
          stepCircle.setAttribute('data-status', 'failed');
          const check = stepCircle.querySelector('.icon-check') as HTMLElement | null;
          const cross = stepCircle.querySelector('.icon-cross') as HTMLElement | null;
          if (check) check.classList.add('hidden');
          if (cross) cross.classList.remove('hidden');
          stepLine.classList.remove('bg-[#7E22CE]', 'bg-gray-300');
          stepLine.classList.add('bg-[repeating-linear-gradient(to_right,_#7E22CE_0,_#7E22CE_8px,_transparent_8px,_transparent_16px)]');
        }
      }

      if (redirectTo) {
        router.push(redirectTo);
      }
    } catch {
      setError('Failed to save profile');
    } finally {
      setSaving(false);
    }
  };

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

  return (
    <div className="min-h-screen">
      {/* Header hidden in embedded mode */}
      {!embedded && (
        <header className="bg-white backdrop-blur-sm border-b border-gray-200 px-4 sm:px-6 py-4">
          <div className="flex items-center justify-between max-w-full relative">
            <Link href="/instructor/dashboard" className="inline-block">
              <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-0 sm:pl-4">iNSTAiNSTRU</h1>
            </Link>
            {/* Onboarding progress removed for standalone page */}

            <div className="pr-4">
              <UserProfileDropdown />
            </div>
          </div>
        </header>
      )}

      <div className={embedded ? 'max-w-none px-0 lg:px-0 py-0' : 'container mx-auto px-8 lg:px-32 py-8 max-w-6xl'}>
        {embedded && loading && (
          <div style={{ height: 1 }} />
        )}
        {!embedded && loading && (
          <div className="p-8 text-sm text-gray-500">Loading…</div>
        )}
        {/* Page Header hidden in embedded mode */}
        {!embedded && (
          <>
            {/* Page Header - mobile: no card chrome; desktop: card */}
            <div className="mb-2 sm:mb-8 bg-transparent border-0 rounded-none p-4 sm:bg-white sm:rounded-lg sm:p-6 sm:border sm:border-gray-200">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div>
                    <h1 className="text-3xl font-bold text-gray-800 mb-1 sm:mb-2 whitespace-nowrap">Profile</h1>
                    <p className="text-gray-600 hidden sm:block">Manage your instructor profile information</p>
                  </div>
                </div>
                {/* Desktop: keep upload in header */}
                <div className="hidden sm:block">
                  <ProfilePictureUpload
                    ariaLabel="Upload profile photo"
                    trigger={
                      <div className="flex flex-col items-center">
                        <div className="w-20 h-20 rounded-full bg-purple-100 flex items-center justify-center hover:bg-purple-200 focus:outline-none cursor-pointer" title="Upload profile photo">
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
                <p className="text-gray-600 text-base leading-snug flex-1">Manage your instructor profile information</p>
                <ProfilePictureUpload
                  ariaLabel="Upload profile photo"
                  trigger={
                    <div className="w-24 h-24 rounded-full bg-purple-100 flex items-center justify-center hover:bg-purple-200 focus:outline-none cursor-pointer" title="Upload profile photo">
                      <Camera className="w-6 h-6 text-[#7E22CE]" />
                    </div>
                  }
                />
              </div>
            </div>
      {/* Mobile divider before Personal Information */}
      {!embedded && <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />}
          </>
        )}

      <SectionHeroCard
        id={embedded ? 'profile-first-card' : undefined}
        icon={UserIcon}
        title="Instructor profile"
        subtitle="Update your story, teaching services, and booking preferences so students know what to expect."
      />

      {error && (
        <div className="mb-6 rounded-lg bg-red-50 border border-red-200 text-red-700 px-4 py-3">{error}</div>
      )}
      {/* Success toast is shown as a floating element; banner removed for cleaner UI */}

      {/* Mobile: stacked white sections with mobile-only dividers; Desktop: spaced cards */}
      <div className={embedded ? 'mt-0 sm:mt-0 sm:space-y-6' : 'mt-0 sm:mt-6 sm:space-y-6'}>
        {/* Personal Information Section */}
        <div className="bg-white sm:bg-white rounded-none border-0 p-4 sm:rounded-lg sm:border sm:border-gray-200 sm:p-6">
            <button
              type="button"
              className="w-full flex items-center justify-between mb-4 text-left"
              onClick={() => setOpenPersonal((v) => !v)}
              aria-expanded={openPersonal}
            >
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <UserIcon className="w-6 h-6 text-[#7E22CE]" />
              </div>
              <div className="flex flex-col text-left">
                <span className="text-xl sm:text-lg font-bold sm:font-semibold text-gray-900">Personal Information</span>
                <span className="text-sm text-gray-500">Basic details that appear on your profile and booking receipts.</span>
              </div>
            </div>
              <ChevronDown className={`w-5 h-5 text-gray-600 transition-transform ${openPersonal ? 'rotate-180' : ''}`} />
            </button>
            {openPersonal && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="py-2">
                  <label htmlFor="first_name" className="text-gray-600 mb-2 block">First Name</label>
                  <input
                    id="first_name"
                    type="text"
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-purple-500 bg-white autofill-fix"
                    placeholder="John"
                    value={profile.first_name}
                    onChange={(e) => setProfile((p) => ({ ...p, first_name: e.target.value }))}
                  />
                </div>
                <div className="py-2">
                  <label htmlFor="last_name" className="text-gray-600 mb-2 block">Last Name</label>
                  <input
                    id="last_name"
                    type="text"
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-purple-500 bg-white autofill-fix"
                    placeholder="Smith"
                    value={profile.last_name}
                    onChange={(e) => setProfile((p) => ({ ...p, last_name: e.target.value }))}
                  />
                </div>
                <div className="py-2">
                  <label htmlFor="postal_code" className="text-gray-600 mb-2 block">ZIP Code</label>
                  <input
                    id="postal_code"
                    type="text"
                    inputMode="numeric"
                    maxLength={5}
                    pattern="\\d{5}"
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-purple-500 bg-white autofill-fix"
                    placeholder="10001"
                    value={profile.postal_code}
                    onChange={(e) => {
                      const digits = e.target.value.replace(/\D/g, '').slice(0, 5);
                      setProfile((p) => ({ ...p, postal_code: digits }));
                    }}
                    onKeyDown={(e) => {
                      const allowed = ['Backspace','Delete','Tab','ArrowLeft','ArrowRight','Home','End'];
                      if (!/[0-9]/.test(e.key) && !allowed.includes(e.key)) e.preventDefault();
                    }}
                  />
                </div>
            </div>
            )}
        </div>
        {/* Mobile divider before Profile Details */}
        <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />

        {/* Professional Information Section */}
        <div className="bg-white sm:bg-white rounded-none border-0 p-4 sm:rounded-lg sm:border sm:border-gray-200 sm:p-6">
          <button
            type="button"
            className="w-full flex items-center justify-between mb-4 text-left"
            onClick={() => setOpenDetails((v) => !v)}
            aria-expanded={openDetails}
          >
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <BookOpen className="w-6 h-6 text-[#7E22CE]" />
              </div>
              <div className="flex flex-col text-left">
                <span className="text-xl sm:text-lg font-bold sm:font-semibold text-gray-900">Profile Details</span>
                <span className="text-sm text-gray-500">Tell students about your experience, style, and teaching approach.</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <ChevronDown className={`w-5 h-5 text-gray-600 transition-transform ${openDetails ? 'rotate-180' : ''}`} />
            </div>
          </button>
          {openDetails && (
          <div className="py-2">
            {embedded && (
              <div className="mb-4">
                <ProfilePictureUpload
                  size={101}
                  ariaLabel="Upload profile photo"
                  trigger={
                    <div
                      className="w-[101px] h-[101px] rounded-full bg-purple-100 flex items-center justify-center hover:bg-purple-200 cursor-pointer transition-transform duration-150 ease-in-out hover:scale-[1.02]"
                      title="Upload profile photo"
                    >
                      <Camera className="w-7 h-7 text-[#7E22CE]" />
                    </div>
                  }
                />
              </div>
            )}
            <div className="mb-2">
              <p className="text-gray-600 mt-1">Introduce Yourself</p>
            </div>
            <div>
              <div className="relative">
                <textarea
                rows={4}
                className={`w-full rounded-md border px-3 py-2 pr-16 pb-8 text-sm focus:outline-none ${bioTouched && bioTooShort ? 'border-red-300 focus:border-red-500' : 'border-gray-300 focus:border-purple-500'}`}
                placeholder="Highlight your experience, favorite teaching methods, and the type of students you enjoy working with."
                value={profile.bio}
                onChange={(e) => setProfile((p) => ({ ...p, bio: e.target.value }))}
                onBlur={() => setBioTouched(true)}
              />
                <div className="pointer-events-none absolute bottom-2 right-3 text-[10px] text-gray-500 z-10 bg-white/80 px-1">
                  Minimum 400 characters
                </div>
              </div>
              {bioTooShort && (
                <div className="mt-1 text-xs text-red-600">Your bio is under 400 characters. You can still save and complete it later.</div>
              )}
              {/* Years of experience (duplicate access here for convenience) */}
              <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label htmlFor="details_years_experience" className="block text-sm text-gray-600 mb-1">Years of Experience</label>
                  <input
                    id="details_years_experience"
                    type="number"
                    min={1}
                    max={70}
                    step={1}
                    inputMode="numeric"
                    value={profile.years_experience}
                    onKeyDown={(e) => { if ([".", ",", "e", "E", "+", "-"].includes(e.key)) { e.preventDefault(); } }}
                    onChange={(e) => {
                      const n = Math.max(1, Math.min(70, parseInt(e.target.value || '0', 10)));
                      setProfile((p) => ({ ...p, years_experience: isNaN(n) ? 1 : n }));
                    }}
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-center font-medium focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500 no-spinner"
                  />
                </div>
              </div>
              <div className="mt-3 flex justify-end">
                <button
                  type="button"
                  onClick={() => {
                    const base = (profile.bio || '').trim();
                    const prefix = base.length > 0 ? base : 'I am a dedicated instructor who helps students learn efficiently and enjoy the process.';
                    const pool = [
                      'I focus on building strong fundamentals and lasting confidence.',
                      'Each lesson is tailored to your goals, pace, and learning style.',
                      'We combine technique drills with practical applications you can use right away.',
                      'I provide clear takeaways, measurable milestones, and simple practice plans.',
                      'My approach balances encouragement with constructive, actionable feedback.',
                      'You will know what to improve next and how to practice effectively between sessions.',
                      'I bring real-world examples, curated resources, and step‑by‑step guidance.',
                      'Consistency matters—together we set realistic targets and celebrate progress.',
                      'Whether you are a beginner or leveling up, I will meet you where you are.',
                      'My goal is to make learning engaging, stress‑free, and genuinely rewarding.'
                    ];
                    let assembled = prefix.endsWith('.') ? prefix : `${prefix}.`;
                    for (const sentence of pool) {
                      if (assembled.length >= 400) break;
                      assembled += ` ${sentence}`;
                    }
                    // If still short, repeat from the pool until we reach the floor, but cap length for readability
                    let i = 0;
                    while (assembled.length < 400 && i < pool.length * 2) {
                      assembled += ` ${pool[i % pool.length]}`;
                      i += 1;
                    }
                    // Soft cap to avoid overly long bios
                    const next = assembled.slice(0, 560);
                    setProfile((p) => ({ ...p, bio: next }));
                    setBioTouched(true);
                  }}
                  className="inline-flex items-center justify-center px-3 py-1.5 rounded-md text-sm sm:text-xs bg-[#7E22CE] text-white shadow-sm hover:bg-[#7E22CE]"
                >
                  Rewrite with AI
                </button>
              </div>
            </div>
          </div>
          )}
        </div>
        {/* Mobile divider before Service Areas */}
        <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />

        {/* Service Areas Section */}
        <div className="bg-white sm:bg-white rounded-none border-0 p-4 sm:rounded-lg sm:border sm:border-gray-200 sm:p-6">
          <button
            type="button"
            className="w-full flex items-center justify-between mb-4 text-left"
            onClick={() => setOpenServiceAreas((v) => !v)}
            aria-expanded={openServiceAreas}
          >
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <MapPin className="w-6 h-6 text-[#7E22CE]" />
              </div>
              <div className="flex flex-col text-left">
                <span className="text-xl sm:text-lg font-bold sm:font-semibold text-gray-900">Service Areas</span>
                <span className="text-sm text-gray-500">Select the neighborhoods where you’re available for lessons.</span>
              </div>
            </div>
            <ChevronDown className={`w-5 h-5 text-gray-600 transition-transform ${openServiceAreas ? 'rotate-180' : ''}`} />
          </button>
          {openServiceAreas && (
            <>
              <p className="text-gray-600 mt-1 mb-2">Select the neighborhoods where you teach</p>
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
                <div className="mb-3">
                  <div className="text-sm text-gray-700 mb-2">Results</div>
                  <div className="flex flex-wrap gap-2">
                    {NYC_BOROUGHS.flatMap((b) => boroughNeighborhoods[b] || [])
                      .filter((n) => (n['name'] || '').toLowerCase().includes(globalNeighborhoodFilter.toLowerCase()))
                      .map((n) => {
                        const nid = n['neighborhood_id'] || (n as Record<string, unknown>)['id'] as string;
                        if (!nid) return null;
                        const checked = selectedNeighborhoods.has(nid);
                        return (
                          <button
                            key={`global-${nid}`}
                            type="button"
                            onClick={() => toggleNeighborhood(nid)}
                            aria-pressed={checked}
                            className={`inline-flex items-center justify-between px-3 py-1.5 text-sm rounded-full font-semibold focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 transition-colors no-hover-shadow appearance-none overflow-hidden ${
                              checked ? 'bg-[#7E22CE] text-white border border-[#7E22CE] hover:bg-[#7E22CE]' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                            }`}
                          >
                            <span className="truncate text-left">{n['name'] || nid}</span>
                            <span className="ml-2">{checked ? '✓' : '+'}</span>
                          </button>
                        );
                      })
                      .filter(Boolean)
                      .slice(0, 200)}
                    {NYC_BOROUGHS.flatMap((b) => boroughNeighborhoods[b] || [])
                      .filter((n) => (n['name'] || '').toLowerCase().includes(globalNeighborhoodFilter.toLowerCase())).length === 0 && (
                        <div className="text-sm text-gray-500">No matches found</div>
                    )}
                  </div>
                </div>
              )}
              {selectedNeighborhoods.size > 0 && (
                <div className="mb-3 flex flex-wrap gap-2">
                  {Array.from(selectedNeighborhoods).map((nid) => {
                    const name = toTitle(idToItem[nid]?.['name'] || String(nid));
                    return (
                      <span key={`sel-${nid}`} className="inline-flex items-center gap-2 rounded-full border border-gray-300 bg-white px-3 h-8 text-xs min-w-0">
                        <span className="truncate max-w-[14rem]" title={name}>{name}</span>
                        <button
                          type="button"
                          aria-label={`Remove ${name}`}
                          className="ml-auto text-[#7E22CE] rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 no-hover-shadow shrink-0"
                          onClick={() => toggleNeighborhood(nid)}
                        >
                          &times;
                        </button>
                      </span>
                    );
                  })}
                </div>
              )}
              {isNYC ? (
                <div className="space-y-3">
                  <div className="mt-3 space-y-3">
                    {NYC_BOROUGHS.map((borough) => {
                      const isOpen = openBoroughsMain.has(borough);
                      const list = boroughNeighborhoods[borough] || [];
                      return (
                        <div
                          key={`accordion-${borough}`}
                          ref={(el) => { boroughAccordionRefs.current[borough] = el; }}
                          className="rounded-xl bg-white shadow-sm overflow-hidden"
                        >
                          <div
                            className="flex items-center justify-between cursor-pointer w-full pl-4 pr-3 md:pl-5 py-2 hover:bg-gray-50 dark:hover:bg-gray-800 transition-all"
                            onClick={async () => { await toggleMainBoroughOpen(borough); }}
                            aria-expanded={isOpen}
                            role="button"
                            tabIndex={0}
                            data-testid={`service-area-borough-${borough.toLowerCase().replace(/\s+/g, '-')}`}
                            onKeyDown={async (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); await toggleMainBoroughOpen(borough); } }}
                          >
                            <div className="flex items-center gap-2 text-gray-800 dark:text-gray-100 font-medium">
                              <span className="tracking-wide text-xs sm:text-sm whitespace-nowrap">{borough}</span>
                              <ChevronDown
                                className={`h-4 w-4 text-gray-600 dark:text-gray-300 transition-transform ${isOpen ? 'rotate-180' : ''}`}
                                aria-hidden="true"
                              />
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
                            <div className="px-3 pb-3 mt-3 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 max-h-80 overflow-y-auto overflow-x-hidden scrollbar-hide">
                              {(list || []).map((n) => {
                                const nid = n['neighborhood_id'] || (n as Record<string, unknown>)['id'] as string;
                                if (!nid) return null;
                                const checked = selectedNeighborhoods.has(nid);
                                const label = toTitle(n['name'] || String(nid));
                                const regionCode = String(n.code || n.ntacode || idToItem[nid]?.ntacode || nid);
                                return (
                                  <button
                                    key={`${borough}-${nid}`}
                                    type="button"
                                    onClick={() => toggleNeighborhood(nid)}
                                    aria-pressed={checked}
                                    data-testid={`service-area-chip-${regionCode}`}
                                    data-state={checked ? 'selected' : 'idle'}
                                    className={`inline-flex items-center justify-between w-full min-w-0 px-2 py-1 text-xs rounded-full font-semibold focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 transition-colors no-hover-shadow appearance-none overflow-hidden ${
                                      checked ? 'bg-[#7E22CE] text-white border border-[#7E22CE] hover:bg-[#7E22CE]' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
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
                </div>
              ) : (
                <div className="mt-2 rounded-lg border border-dashed border-gray-300 p-4 text-sm text-gray-600">
                  Your city is not yet supported for granular neighborhoods. We’ll add it soon.
                </div>
              )}
            </>
          )}
          {/* Preferred Teaching Location */}
          {openServiceAreas && (
          <div className="mt-6">
            <p className="text-gray-600 mt-1 mb-2">Preferred Teaching Location</p>
            <p className="text-xs text-gray-600 mb-2">Add a studio, gym, or home address if you teach from a fixed location.</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-start mt-3 sm:mt-0">
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <PlacesAutocompleteInput
                    data-testid="ptl-input"
                    value={preferredAddress}
                    onValueChange={setPreferredAddress}
                    placeholder="Type address..."
                    inputClassName="h-10 border border-gray-300 pl-3 pr-12 text-sm leading-10 focus:border-purple-500"
                  />
                  <button
                    type="button"
                    data-testid="ptl-add"
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
              <div className="min-h-10 flex flex-wrap items-start gap-4 w-full mt-4 sm:mt-0">
                {preferredLocations.map((loc, index) => (
                  <div key={loc} className="relative w-1/2 min-w-0 pt-4 sm:pt-0">
                    <input
                      type="text"
                      placeholder="..."
                      data-testid={`ptl-chip-label-${index}`}
                      value={preferredLocationTitles[loc] || ''}
                      onChange={(e) => setPreferredLocationTitles((prev) => ({ ...prev, [loc]: e.target.value }))}
                      className="absolute -top-2 sm:-top-5 left-1 text-xs text-[#7E22CE] bg-gray-100 px-1 py-0.5 rounded border-transparent ring-0 shadow-none outline-none focus:outline-none focus-visible:outline-none focus:ring-0 focus-visible:ring-0 focus:border-transparent focus-visible:border-transparent cursor-text"
                      style={{ outline: 'none', outlineOffset: 0, boxShadow: 'none' }}
                    />
                    <span
                      data-testid={`ptl-chip-${index}`}
                      className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 h-10 text-sm w-full min-w-0"
                    >
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
          )}

          {/* Preferred Public Spaces */}
          {openServiceAreas && (
          <div className="mt-6">
            <p className="text-gray-600 mt-1 mb-2">Preferred Public Spaces</p>
            <p className="text-xs text-gray-600 mb-2">Suggest public spaces where you’re comfortable teaching<br />(e.g., library, park, coffee shop).</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-start">
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <PlacesAutocompleteInput
                    data-testid="pps-input"
                    value={neutralLocations}
                    onValueChange={setNeutralLocations}
                    placeholder="Type location..."
                    inputClassName="h-10 border border-gray-300 pl-3 pr-12 text-sm leading-10 focus:border-purple-500"
                  />
                  <button
                    type="button"
                    data-testid="pps-add"
                    onClick={() => {
                      const v = neutralLocations.trim();
                      if (!v) return;
                      if (neutralPlaces.length >= 2) return;
                      if (!neutralPlaces.includes(v)) setNeutralPlaces((prev) => [...prev, v]);
                      setNeutralLocations('');
                    }}
                    aria-label="Add public space"
                    disabled={neutralPlaces.length >= 2}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#7E22CE] rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 focus:outline-none no-hover-shadow disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                  >
                    <span className="text-base leading-none">+</span>
                  </button>
                </div>
              </div>
              <div className="min-h-10 flex flex-col sm:flex-row items-start gap-4 w-full">
                {neutralPlaces.map((place, index) => (
                  <div key={place} className="relative w-1/2 min-w-0">
                    <span
                      data-testid={`pps-chip-${index}`}
                      className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 h-10 text-sm w-full min-w-0"
                    >
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
          )}
        </div>
        {/* Mobile divider before Skills & Pricing */}
        <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />

        {/* Skills & Pricing Section */}
        <div className="bg-white sm:bg-white rounded-none border-0 p-4 sm:rounded-lg sm:border sm:border-gray-200 sm:p-6">
          <button
            type="button"
            className="w-full flex items-center justify-between mb-4 text-left"
            onClick={() => setOpenSkills((v) => !v)}
            aria-expanded={openSkills}
          >
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <BookOpen className="w-6 h-6 text-[#7E22CE]" />
              </div>
              <div className="flex flex-col text-left">
                <span className="text-xl sm:text-lg font-bold sm:font-semibold text-gray-900">Skills & Pricing</span>
                <span className="text-sm text-gray-500">Manage the subjects you teach, durations, and rates students see.</span>
              </div>
            </div>
            <ChevronDown className={`w-5 h-5 text-gray-600 transition-transform ${openSkills ? 'rotate-180' : ''}`} />
          </button>
          {openSkills && (
            <div className="py-2">
              <SkillsPricingInline />
            </div>
          )}
        </div>

        {/* Mobile divider before Booking Preferences */}
        <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />

        {/* Experience Settings Section */}
        <div className="bg-white sm:bg-white rounded-none border-0 p-4 sm:rounded-lg sm:border sm:border-gray-200 sm:p-6">
          <button
            type="button"
            className="w-full flex items-center justify-between mb-4 text-left"
            onClick={() => setOpenPreferences((v) => !v)}
            aria-expanded={openPreferences}
          >
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <SettingsIcon className="w-6 h-6 text-[#7E22CE]" />
              </div>
              <div className="flex flex-col text-left">
                <span className="text-xl sm:text-lg font-bold sm:font-semibold text-gray-900">Booking Preferences</span>
                <span className="text-sm text-gray-500">Fine-tune lead time, buffers, and other scheduling requirements.</span>
              </div>
            </div>
            <ChevronDown className={`w-5 h-5 text-gray-600 transition-transform ${openPreferences ? 'rotate-180' : ''}`} />
          </button>
          {openPreferences && (
          <>
          <p className="text-gray-600 mt-1 mb-3">Control availability and booking preferences</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="bg-white rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-gray-600 uppercase tracking-wide">Advance Notice (business hours)</label>
                  <Tooltip.Provider delayDuration={150} skipDelayDuration={0}>
                    <Tooltip.Root>
                      <Tooltip.Trigger asChild>
                        <span tabIndex={0} className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-purple-50 text-[#7E22CE] focus:outline-none">
                          <Info className="w-3.5 h-3.5" aria-hidden="true" />
                        </span>
                      </Tooltip.Trigger>
                      <Tooltip.Content side="top" sideOffset={6} className="rounded-md bg-white border border-gray-200 px-2 py-1 text-xs text-gray-900 shadow-sm select-none max-w-xs">
                        The minimum time required between booking and the start of a lesson. For example, if set to 2 hours, students can’t book a session that starts in less than 2 hours from now.
                        <Tooltip.Arrow className="fill-gray-200" />
                      </Tooltip.Content>
                    </Tooltip.Root>
                  </Tooltip.Provider>
                </div>
                <input
                  type="number"
                  min={1}
                  max={24}
                  step={1}
                  inputMode="numeric"
                  value={profile.min_advance_booking_hours ?? 2}
                  onKeyDown={(e) => { if ([".", ",", "e", "E", "+", "-"].includes(e.key)) { e.preventDefault(); } }}
                  onChange={(e) => {
                    const n = Math.max(1, Math.min(24, parseInt(e.target.value || '0', 10)));
                    setProfile((p) => ({ ...p, min_advance_booking_hours: isNaN(n) ? 1 : n }));
                  }}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-center font-medium focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500 no-spinner"
                />
              </div>
              <div className="bg-white rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-medium text-gray-600 uppercase tracking-wide">Buffer Time (hours)</label>
                  <Tooltip.Provider delayDuration={150} skipDelayDuration={0}>
                    <Tooltip.Root>
                      <Tooltip.Trigger asChild>
                        <span tabIndex={0} className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-purple-50 text-[#7E22CE] focus:outline-none">
                          <Info className="w-3.5 h-3.5" aria-hidden="true" />
                        </span>
                      </Tooltip.Trigger>
                      <Tooltip.Content side="top" sideOffset={6} className="rounded-md bg-white border border-gray-200 px-2 py-1 text-xs text-gray-900 shadow-sm select-none max-w-xs">
                        The minimum gap between two sessions. For example, if set to 15 minutes, and someone books 9:00–10:00, the next session will be bookable starting at 10:15.
                        <Tooltip.Arrow className="fill-gray-200" />
                      </Tooltip.Content>
                    </Tooltip.Root>
                  </Tooltip.Provider>
                </div>
                <input
                  type="number"
                  min={0.5}
                  max={24}
                  step={0.5}
                  inputMode="decimal"
                  value={profile.buffer_time_hours ?? 0.5}
                  onChange={(e) => {
                    const raw = parseFloat(e.target.value || '0.5');
                    const n = Math.max(0.5, Math.min(24, isNaN(raw) ? 0.5 : raw));
                    setProfile((p) => ({ ...p, buffer_time_hours: n }));
                  }}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-center font-medium focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500"
                />
              </div>
          </div>
          </>
          )}
        </div>
        {embedded && (
          <>
            <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />
            <div className="bg-white sm:bg-white rounded-none border-0 p-4 sm:rounded-lg sm:border sm:border-gray-200 sm:p-6">
              <button
                type="button"
                className="w-full flex items-center justify-between mb-4 text-left"
                onClick={() => setOpenIdentity((v) => !v)}
                aria-expanded={openIdentity}
              >
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                    <ShieldCheck className="w-6 h-6 text-[#7E22CE]" />
                  </div>
                  <div className="flex flex-col text-left">
                    <span className="text-xl sm:text-lg font-bold sm:font-semibold text-gray-900">Verify identity</span>
                    <span className="text-sm text-gray-500">Secure your account with a fast Stripe identity check.</span>
                  </div>
                </div>
                <ChevronDown className={`w-5 h-5 text-gray-600 transition-transform ${openIdentity ? 'rotate-180' : ''}`} />
              </button>
              {openIdentity && (
                <div className="space-y-4">
                  <p className="text-sm text-gray-600">
                    Complete a quick identity check so students can trust who they are booking. We use a secure Stripe flow to verify your government ID.
                  </p>
                  <button
                    type="button"
                    className="inline-flex items-center justify-center h-10 px-4 rounded-lg bg-[#7E22CE] text-sm font-medium text-white transition-colors hover:bg-[#6b1cb9]"
                    onClick={() => router.push('/instructor/onboarding/verification')}
                  >
                    Start verification
                  </button>
                </div>
              )}
            </div>
            <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />
            <div className="bg-white sm:bg-white rounded-none border-0 p-4 sm:rounded-lg sm:border sm:border-gray-200 sm:p-6">
              <button
                type="button"
                className="w-full flex items-center justify-between mb-4 text-left"
                onClick={() => setOpenPayments((v) => !v)}
                aria-expanded={openPayments}
              >
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                    <CreditCard className="w-6 h-6 text-[#7E22CE]" />
                  </div>
                  <div className="flex flex-col text-left">
                    <span className="text-xl sm:text-lg font-bold sm:font-semibold text-gray-900">Payment setup</span>
                    <span className="text-sm text-gray-500">Link Stripe payouts so completed lessons are paid automatically.</span>
                  </div>
                </div>
                <ChevronDown className={`w-5 h-5 text-gray-600 transition-transform ${openPayments ? 'rotate-180' : ''}`} />
              </button>
              {openPayments && (
                <div className="space-y-4">
                  <p className="text-sm text-gray-600">
                    Connect Stripe payouts so you can receive earnings without delay. Confirm your tax information and bank details to enable transfers.
                  </p>
                  <button
                    type="button"
                    className="inline-flex items-center justify-center h-10 px-4 rounded-lg border border-purple-200 bg-white text-sm font-medium text-[#7E22CE] transition-colors hover:bg-purple-50"
                    onClick={() => router.push('/instructor/onboarding/payment-setup')}
                  >
                    Open payment setup
                  </button>
                </div>
              )}
            </div>
          </>
        )}

        {/* Inline actions - standalone save */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={() => { if (!saving && !savingServiceAreas) { void save(); } }}
            disabled={saving || savingServiceAreas}
            className="w-40 whitespace-nowrap px-5 py-2.5 rounded-lg text-white bg-[#7E22CE] hover:bg-[#7E22CE] disabled:opacity-50 shadow-sm justify-center"
          >
            {saving || savingServiceAreas ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
        {/* Inline success banner removed; using Sonner toast instead */}
        {/* Animation CSS now global in app/globals.css */}
      </div>
    </div>
  );
}

export default function InstructorProfileSettingsPage() {
  return <ProfilePageImpl />;
}
