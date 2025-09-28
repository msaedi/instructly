'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState, useRef, useCallback } from 'react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { User as UserIcon, MapPin, Settings as SettingsIcon, BookOpen, ChevronDown, Camera, ExternalLink } from 'lucide-react';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { logger } from '@/lib/logger';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { ProfilePictureUpload } from '@/components/user/ProfilePictureUpload';
import { formatProblemMessages } from '@/lib/httpErrors';
import { PlacesAutocompleteInput } from '@/components/forms/PlacesAutocompleteInput';

type Profile = {
  first_name: string;
  last_name: string;
  postal_code: string;
  bio: string;
  areas_of_service: string[];
  years_experience: number;
  min_advance_booking_hours?: number;
  buffer_time_minutes?: number;
  street_line1?: string;
  street_line2?: string;
  locality?: string;
  administrative_area?: string;
  country_code?: string;
  place_id?: string;
  latitude?: number | null;
  longitude?: number | null;
};

type ServiceAreaItem = { id: string; neighborhood_id?: string; ntacode?: string | null; name?: string | null; borough?: string | null };
type ServiceAreasResponse = { items: ServiceAreaItem[]; total: number };
type NYCZipCheck = { is_nyc: boolean; borough?: string | null };

function buildInstructorProfilePayload(profile: Profile) {
  return {
    bio: profile.bio.trim(),
    areas_of_service: profile.areas_of_service,
    years_experience: Number(profile.years_experience) || 0,
    min_advance_booking_hours: profile.min_advance_booking_hours ?? 2,
    buffer_time_minutes: profile.buffer_time_minutes ?? 0,
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

export default function InstructorProfileSettingsPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Success toast handled via Sonner; no local success banner state
  const [userId, setUserId] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile>({
    first_name: '',
    last_name: '',
    postal_code: '',
    bio: '',
    areas_of_service: [],
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
          try { setUserId(userData?.['id'] ? String(userData['id']) : null); } catch {}
          logger.debug('Prefill: /auth/me body', { first_name: firstName, last_name: lastName, id: userData['id'], zip_code: userZip });
        } else if (data && data.user) {
          // Fallback to instructor payload's embedded user if available
          firstName = data.user['first_name'] || '';
          lastName = data.user['last_name'] || '';
          userZip = data.user['zip_code'] || '';
          try { setUserId(data.user?.['id'] ? String(data.user['id']) : null); } catch {}
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

        setProfile({
          first_name: firstName,
          last_name: lastName,
          postal_code: postalCode,
          bio: data['bio'] || '',
          areas_of_service: Array.isArray(data['areas_of_service'])
            ? data['areas_of_service']
            : (data['areas_of_service'] || '').split(',').map((x: string) => x.trim()).filter((x: string) => x.length),
          years_experience: data['years_experience'] ?? 0,
          min_advance_booking_hours: data['min_advance_booking_hours'] ?? 2,
          buffer_time_minutes: data['buffer_time_minutes'] ?? 0,
        });

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
              const nycRes = await fetch(`${process.env['NEXT_PUBLIC_API_BASE'] || 'http://localhost:8000'}${API_ENDPOINTS.NYC_ZIP_CHECK}?zip=${encodeURIComponent(zip)}`);
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
      const url = `${process.env['NEXT_PUBLIC_API_BASE'] || 'http://localhost:8000'}/api/addresses/regions/neighborhoods?region_type=nyc&borough=${encodeURIComponent(borough)}&per_page=500`;
      const r = await fetch(url);
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

      // Persist service areas
      try {
        await fetchWithAuth('/api/addresses/service-areas/me', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ neighborhood_ids: Array.from(selectedNeighborhoods) }),
        });
      } catch {}

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
      {/* Header - matching onboarding pages */}
      <header className="bg-white backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full relative">
          <Link href="/" className="inline-block">
            <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
          </Link>

          {/* Progress Bar - 4 Steps - Absolutely centered */}
          <div className="absolute left-1/2 transform -translate-x-1/2 items-center gap-0 hidden min-[1400px]:flex">
            {/* Walking Stick Figure - profile page variant */}
            <div className="absolute inst-anim-walk-profile" style={{ top: '-12px', left: '4px' }}>
              <svg width="16" height="20" viewBox="0 0 16 20" fill="none">
                {/* Head */}
                <circle cx="8" cy="4" r="2.5" stroke="#7E22CE" strokeWidth="1.2" fill="none" />
                {/* Body */}
                <line x1="8" y1="6.5" x2="8" y2="12" stroke="#7E22CE" strokeWidth="1.2" />
                {/* Left arm */}
                <line x1="8" y1="8" x2="5" y2="10" stroke="#7E22CE" strokeWidth="1.2" className="inst-anim-leftArm-fast" />
                {/* Right arm */}
                <line x1="8" y1="8" x2="11" y2="10" stroke="#7E22CE" strokeWidth="1.2" className="inst-anim-rightArm-fast" />
                {/* Left leg */}
                <line x1="8" y1="12" x2="6" y2="17" stroke="#7E22CE" strokeWidth="1.2" className="inst-anim-leftLeg-fast" />
                {/* Right leg */}
                <line x1="8" y1="12" x2="10" y2="17" stroke="#7E22CE" strokeWidth="1.2" className="inst-anim-rightLeg-fast" />
              </svg>
            </div>

            {/* Step 1 - Current (Profile) */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => {/* Already on this page */}}
                  className="w-6 h-6 rounded-full border-2 border-purple-300 bg-purple-100 hover:border-purple-400 transition-colors cursor-pointer"
                  title="Step 1: Account Setup (Current)"
                ></button>
                <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">Account Setup</span>
              </div>
              <div className="w-60 h-0.5 bg-gray-300"></div>
            </div>

            {/* Step 2 - Upcoming */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => window.location.href = '/instructor/onboarding/skill-selection'}
                  className="w-6 h-6 rounded-full border-2 border-gray-300 hover:border-gray-400 transition-colors cursor-pointer"
                  title="Step 2: Skills & Pricing"
                ></button>
                <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">Add Skills</span>
              </div>
              <div className="w-60 h-0.5 bg-gray-300"></div>
            </div>

            {/* Step 3 - Upcoming */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => window.location.href = '/instructor/onboarding/verification'}
                  className="w-6 h-6 rounded-full border-2 border-gray-300 hover:border-gray-400 transition-colors cursor-pointer"
                  title="Step 3: Verification"
                ></button>
                <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">Verify Identity</span>
              </div>
              <div className="w-60 h-0.5 bg-gray-300"></div>
            </div>

            {/* Step 4 - Upcoming */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => window.location.href = '/instructor/onboarding/payment-setup'}
                  className="w-6 h-6 rounded-full border-2 border-gray-300 hover:border-gray-400 transition-colors cursor-pointer"
                  title="Step 4: Payment Setup"
                ></button>
                <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">Payment Setup</span>
              </div>
            </div>
          </div>

          <div className="pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        {loading && (
          <div className="p-8 text-sm text-gray-500">Loading…</div>
        )}
        {/* Page Header with subtle purple accent - matching verification page */}
        <div className="bg-white rounded-lg p-6 mb-8 border border-gray-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div>
                <h1 className="text-3xl font-bold text-gray-800 mb-2">Set up your profile</h1>
                <p className="text-gray-600">Complete your instructor profile to start teaching</p>
              </div>
            </div>
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

      {error && (
        <div className="mb-6 rounded-lg bg-red-50 border border-red-200 text-red-700 px-4 py-3">{error}</div>
      )}
      {/* Success toast is shown as a floating element; banner removed for cleaner UI */}

      <div className="mt-6 space-y-6">
        {/* Personal Information Section */}
        <div className="bg-white rounded-lg border border-gray-200 p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="flex items-center gap-3 text-lg font-semibold text-gray-900">
                  <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                    <UserIcon className="w-6 h-6 text-[#7E22CE]" />
                  </div>
                  <span>Personal Information</span>
                </div>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="py-2">
                  <label htmlFor="first_name" className="text-gray-600 mb-2 block">First Name</label>
                  <input
                    id="first_name"
                    type="text"
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-purple-500"
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
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-purple-500"
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
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-purple-500"
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
        </div>

        {/* Professional Information Section */}
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <div className="flex items-center gap-3 text-lg font-semibold text-gray-900">
                <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                  <BookOpen className="w-6 h-6 text-[#7E22CE]" />
                </div>
                <span>Profile Details</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => { if (userId) router.push(`/instructors/${userId}`); }}
                aria-label="View public profile"
                title="View public profile"
                className="inline-flex items-center px-2.5 py-1.5 text-xs rounded-md border border-purple-200 bg-purple-50 text-[#7E22CE] hover:bg-purple-100 transition-colors disabled:opacity-50"
                disabled={!userId}
              >
                <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
                <span className="hidden sm:inline">View public profile</span>
              </button>
            </div>
          </div>
          <div className="py-2">
            <p className="text-gray-600 mt-1 mb-2">Introduce Yourself</p>
            <div className="relative">
              <textarea
                rows={4}
                className={`w-full rounded-md border px-3 py-2 pr-16 pb-6 text-sm focus:outline-none ${bioTouched && bioTooShort ? 'border-red-300 focus:border-red-500' : 'border-gray-300 focus:border-purple-500'}`}
                placeholder="Highlight your experience, favorite teaching methods, and the type of students you enjoy working with."
                value={profile.bio}
                onChange={(e) => setProfile((p) => ({ ...p, bio: e.target.value }))}
                onBlur={() => setBioTouched(true)}
              />
              <div className="pointer-events-none absolute bottom-3 right-3 text-[10px] text-gray-500">
                Minimum 400 characters
              </div>
              {bioTooShort && (
                <div className="mt-1 text-xs text-red-600">Your bio is under 400 characters. You can still save and complete it later.</div>
              )}
            </div>
          </div>
        </div>

        {/* Service Areas Section */}
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <div className="flex items-center gap-3 text-lg font-semibold text-gray-900">
                <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                  <MapPin className="w-6 h-6 text-[#7E22CE]" />
                </div>
                <span>Service Areas</span>
              </div>
            </div>
          </div>
          <p className="text-gray-600 mt-1 mb-2">Select the neighborhoods where you teach</p>
          {/* Global neighborhood search (no card wrapper) */}
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
              {/* Removed top borough pills row */}
              {/* Per-borough accordions like screenshot */}
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
                        onKeyDown={async (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); await toggleMainBoroughOpen(borough); } }}
                      >
                        <div className="flex items-center gap-2 text-gray-800 dark:text-gray-100 font-medium">
                          <span className="tracking-wide text-sm">{borough}</span>
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
                            return (
                              <button
                                key={`${borough}-${nid}`}
                                type="button"
                                onClick={() => toggleNeighborhood(nid)}
                                aria-pressed={checked}
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
            <p className="text-xs text-gray-600 mb-2">Suggest public spaces where you’re comfortable teaching<br />(e.g., library, park, coffee shop).</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-start">
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <PlacesAutocompleteInput
                    value={neutralLocations}
                    onValueChange={setNeutralLocations}
                    placeholder="Type location..."
                    inputClassName="h-10 border border-gray-300 pl-3 pr-12 text-sm leading-10 focus:border-purple-500"
                  />
                  <button
                    type="button"
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
        </div>

        {/* Experience Settings Section */}
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <div className="flex items-center gap-3 text-lg font-semibold text-gray-900">
                <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                  <SettingsIcon className="w-6 h-6 text-[#7E22CE]" />
                </div>
                <span>Booking Preferences</span>
              </div>
            </div>
          </div>
          <p className="text-gray-600 mt-1 mb-3">Control availability and booking preferences</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="bg-white rounded-lg">
                <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Years of Experience</label>
                <input
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
              <div className="bg-white rounded-lg">
                <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Advance Notice (business hours)</label>
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
                <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Buffer Time (minutes)</label>
                <input
                  type="number"
                  min={1}
                  max={300}
                  step={1}
                  inputMode="numeric"
                  value={profile.buffer_time_minutes ?? 0}
                  onKeyDown={(e) => { if ([".", ",", "e", "E", "+", "-"].includes(e.key)) { e.preventDefault(); } }}
                  onChange={(e) => {
                    const n = Math.max(1, Math.min(300, parseInt(e.target.value || '0', 10)));
                    setProfile((p) => ({ ...p, buffer_time_minutes: isNaN(n) ? 1 : n }));
                  }}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-center font-medium focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500 no-spinner"
                />
              </div>
          </div>
        </div>

        {/* Inline actions */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={() => { window.location.href = '/instructor/onboarding/skill-selection'; }}
            className="w-40 px-5 py-2.5 rounded-lg text-[#7E22CE] bg-white border border-purple-200 hover:bg-gray-50 hover:border-purple-300 transition-colors focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 justify-center"
          >
            Skip for now
          </button>
          <button
            onClick={() => { void save({ redirectTo: '/instructor/onboarding/skill-selection' }); }}
            disabled={saving}
            className="w-56 whitespace-nowrap px-5 py-2.5 rounded-lg text-white bg-[#7E22CE] hover:bg-[#7E22CE] disabled:opacity-50 shadow-sm justify-center"
          >
            {saving ? 'Saving...' : 'Save & Continue'}
          </button>
        </div>
      </div>
        {/* Inline success banner removed; using Sonner toast instead */}
        {/* Animation CSS now global in app/globals.css */}
      </div>
    </div>
  );
}
