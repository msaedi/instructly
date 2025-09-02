'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState, useRef, useCallback } from 'react';
import { User as UserIcon, MapPin, Settings as SettingsIcon, BookOpen, ChevronDown } from 'lucide-react';
import { fetchWithAuth, API_ENDPOINTS, getErrorMessage } from '@/lib/api';
import { logger } from '@/lib/logger';
import UserProfileDropdown from '@/components/UserProfileDropdown';

type Profile = {
  first_name: string;
  last_name: string;
  postal_code: string;
  bio: string;
  areas_of_service: string[];
  years_experience: number;
  min_advance_booking_hours?: number;
  buffer_time_minutes?: number;
};

type ServiceAreaItem = { id: string; neighborhood_id?: string; ntacode?: string | null; name?: string | null; borough?: string | null };
type ServiceAreasResponse = { items: ServiceAreaItem[]; total: number };
type NYCZipCheck = { is_nyc: boolean; borough?: string | null };

function toTitle(s: string): string {
  return s
    .trim()
    .toLowerCase()
    .split(' ')
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(' ');
}

export default function InstructorProfileSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
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
          firstName = userData.first_name || '';
          lastName = userData.last_name || '';
          userZip = userData.zip_code || '';
          logger.debug('Prefill: /auth/me body', { first_name: firstName, last_name: lastName, id: userData.id, zip_code: userZip });
        } else if (data && data.user) {
          // Fallback to instructor payload's embedded user if available
          firstName = data.user.first_name || '';
          lastName = data.user.last_name || '';
          userZip = data.user.zip_code || '';
          logger.debug('Prefill: using instructor.user fallback', { first_name: firstName, last_name: lastName, zip_code: userZip });
        }

        // Get postal code from default address
        let postalCode = '';
        try {
          const addrRes = await fetchWithAuth('/api/addresses/me');
          logger.debug('Prefill: /api/addresses/me status', { status: addrRes.status });
          if (addrRes.ok) {
            const list = await addrRes.json();
            const def = (list.items || []).find((a: any) => a.is_default) || (list.items || [])[0];
            postalCode = def?.postal_code || '';
            logger.debug('Prefill: selected default address', { id: def?.id, postal_code: postalCode });
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
          bio: data.bio || '',
          areas_of_service: Array.isArray(data.areas_of_service)
            ? data.areas_of_service
            : (data.areas_of_service || '').split(',').map((x: string) => x.trim()).filter((x: string) => x.length),
          years_experience: data.years_experience ?? 0,
          min_advance_booking_hours: data.min_advance_booking_hours ?? 2,
          buffer_time_minutes: data.buffer_time_minutes ?? 0,
        });

        // Prefill service areas (neighborhoods)
        try {
          const areasRes = await fetchWithAuth('/api/addresses/service-areas/me');
          logger.debug('Prefill: /api/addresses/service-areas/me status', { status: areasRes.status });
          if (areasRes.ok) {
            const areas: ServiceAreasResponse = await areasRes.json();
            const items = (areas.items || []) as ServiceAreaItem[];
            const ids = items
              .map((a) => a.neighborhood_id || (a as any).id)
              .filter((v: string | undefined): v is string => typeof v === 'string');
            setSelectedNeighborhoods(new Set(ids));
            // Prime name map so selections show even before a borough loads
            setIdToItem((prev) => {
              const next = { ...prev } as Record<string, ServiceAreaItem>;
              for (const a of items) {
                const nid = a.neighborhood_id || (a as any).id;
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
            const def = (list.items || []).find((a: any) => a.is_default) || (list.items || [])[0];
            const zip = def?.postal_code;
            if (zip) {
              const nycRes = await fetch(`${process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000'}${API_ENDPOINTS.NYC_ZIP_CHECK}?zip=${encodeURIComponent(zip)}`);
              logger.debug('Prefill: NYC zip check status', { status: nycRes.status, zip });
              if (nycRes.ok) {
                const nyc: NYCZipCheck = await nycRes.json();
                setIsNYC(!!nyc.is_nyc);
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

  // Auto-hide success toast after a short delay
  useEffect(() => {
    if (success) {
      const t = setTimeout(() => setSuccess(null), 2500);
      return () => clearTimeout(t);
    }
    return;
  }, [success]);

  const canSave = useMemo(() => {
    return profile.bio.trim().length >= 1;
  }, [profile]);


  // Removed selected neighborhoods panel prefetch effect

  // NYC helpers
  const NYC_BOROUGHS = useMemo(() => ['Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island'] as const, []);

  const loadBoroughNeighborhoods = useCallback(async (borough: string): Promise<ServiceAreaItem[]> => {
    if (boroughNeighborhoods[borough]) return boroughNeighborhoods[borough] || [];
    try {
      const url = `${process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000'}/api/addresses/regions/neighborhoods?region_type=nyc&borough=${encodeURIComponent(borough)}&per_page=500`;
      const r = await fetch(url);
      if (r.ok) {
        const data = await r.json();
        const list = (data.items || []) as ServiceAreaItem[];
        setBoroughNeighborhoods((prev) => ({ ...prev, [borough]: list }));
        // Update id->item map for display in the selection panel
        setIdToItem((prev) => {
          const next = { ...prev } as Record<string, ServiceAreaItem>;
          for (const it of list) {
            const nid = it.neighborhood_id || (it as any).id;
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

  const save = async () => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
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

      const payload = {
        bio: profile.bio.trim(),
        areas_of_service: profile.areas_of_service,
        years_experience: Number(profile.years_experience) || 0,
        min_advance_booking_hours: profile.min_advance_booking_hours ?? 2,
        buffer_time_minutes: profile.buffer_time_minutes ?? 0,
      };
      const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        setError(await getErrorMessage(res));
        return;
      }

      // If ZIP changed, update default address postal_code
      try {
        const addrRes = await fetchWithAuth('/api/addresses/me');
        if (addrRes.ok) {
          const list = await addrRes.json();
          const items = (list.items || []) as any[];
          const def = items.find((a) => a.is_default) || items[0];
          if (def) {
            const currentZip = def.postal_code || '';
            const newZip = (profile.postal_code || '').trim();
            if (newZip && newZip !== currentZip) {
              await fetchWithAuth(`/api/addresses/me/${def.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ postal_code: newZip }),
              });
            }
          } else if ((profile.postal_code || '').trim()) {
            // No address exists yet—create one with ZIP only
            await fetchWithAuth('/api/addresses/me', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ postal_code: (profile.postal_code || '').trim(), is_default: true }),
            });
          }
        }
      } catch {}

      // Persist service areas
      try {
        await fetchWithAuth('/api/addresses/service-areas/me', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ neighborhood_ids: Array.from(selectedNeighborhoods) }),
        });
      } catch {}

      setSuccess('Profile saved');
    } catch {
      setError('Failed to save profile');
    } finally {
      setSaving(false);
    }
  };

  const toggleBoroughAll = (borough: string, value: boolean, itemsOverride?: ServiceAreaItem[]) => {
    const items = itemsOverride || boroughNeighborhoods[borough] || [];
    const ids = items.map((i) => i.neighborhood_id || (i as any).id);
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

  // Compute borough selection status for indeterminate styling
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _getBoroughCounts = (_borough: string) => {
    const list = boroughNeighborhoods[_borough] || [];
    const ids = list.map((n) => n.neighborhood_id || (n as any).id).filter(Boolean) as string[];
    let selected = 0;
    if (ids.length) {
      for (const id of ids) if (selectedNeighborhoods.has(id)) selected++;
    } else {
      // Fallback: count by idToItem when list not loaded
      for (const id of selectedNeighborhoods) if (idToItem[id]?.borough === _borough) selected++;
    }
    return { selected, total: ids.length };
  };

  // Avoid early return to prevent hydration mismatches; render a lightweight inline loader instead

  return (
    <div className="min-h-screen">
      {/* Header - matching onboarding pages */}
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full relative">
          <Link href="/" className="inline-block">
            <h1 className="text-3xl font-bold text-purple-700 hover:text-purple-800 transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
          </Link>

          {/* Progress Bar - 4 Steps - Absolutely centered */
          }
          <div className="absolute left-1/2 transform -translate-x-1/2 flex items-center gap-0">
            {/* Walking Stick Figure - profile page variant */}
            <div className="absolute inst-anim-walk-profile" style={{ top: '-12px', left: '-28px' }}>
              <svg width="16" height="20" viewBox="0 0 16 20" fill="none">
                {/* Head */}
                <circle cx="8" cy="4" r="2.5" stroke="#6A0DAD" strokeWidth="1.2" fill="none" />
                {/* Body */}
                <line x1="8" y1="6.5" x2="8" y2="12" stroke="#6A0DAD" strokeWidth="1.2" />
                {/* Left arm */}
                <line x1="8" y1="8" x2="5" y2="10" stroke="#6A0DAD" strokeWidth="1.2" className="inst-anim-leftArm-fast" />
                {/* Right arm */}
                <line x1="8" y1="8" x2="11" y2="10" stroke="#6A0DAD" strokeWidth="1.2" className="inst-anim-rightArm-fast" />
                {/* Left leg */}
                <line x1="8" y1="12" x2="6" y2="17" stroke="#6A0DAD" strokeWidth="1.2" className="inst-anim-leftLeg-fast" />
                {/* Right leg */}
                <line x1="8" y1="12" x2="10" y2="17" stroke="#6A0DAD" strokeWidth="1.2" className="inst-anim-rightLeg-fast" />
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
          <div className="flex items-center gap-3 mb-3">
            <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
              <svg className="w-6 h-6 text-purple-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
            <div>
              <h1 className="text-3xl font-bold text-gray-800">Set up your profile</h1>
              <p className="text-gray-600">Complete your instructor profile to start teaching</p>
            </div>
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
                <div className="flex items-center gap-2 text-lg font-medium text-gray-900"><UserIcon className="w-5 h-5 text-purple-700" />Personal Information</div>
              </div>
            </div>
            <div className="rounded-lg border border-gray-200 p-5 hover:shadow-sm transition-shadow">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="p-2">
                  <label htmlFor="first_name" className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">First Name</label>
                  <input
                    id="first_name"
                    type="text"
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-purple-500"
                    placeholder="John"
                    value={profile.first_name}
                    onChange={(e) => setProfile((p) => ({ ...p, first_name: e.target.value }))}
                  />
                </div>
                <div className="p-2">
                  <label htmlFor="last_name" className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Last Name</label>
                  <input
                    id="last_name"
                    type="text"
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-purple-500"
                    placeholder="Smith"
                    value={profile.last_name}
                    onChange={(e) => setProfile((p) => ({ ...p, last_name: e.target.value }))}
                  />
                </div>
                <div className="p-2">
                  <label htmlFor="postal_code" className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">ZIP Code</label>
                  <input
                    id="postal_code"
                    type="text"
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-purple-500"
                    placeholder="10001"
                    value={profile.postal_code}
                    onChange={(e) => setProfile((p) => ({ ...p, postal_code: e.target.value }))}
                  />
                </div>
              </div>
            </div>
        </div>

        {/* Professional Information Section */}
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <div className="flex items-center gap-2 text-lg font-medium text-gray-900"><BookOpen className="w-5 h-5 text-purple-700" />Professional Details</div>
            </div>
          </div>
          <div className="rounded-lg border border-gray-200 p-5 hover:shadow-sm transition-shadow">
            <div className="p-2">
              <p className="mb-2 text-sm text-gray-600">Share your experience and teaching preferences</p>
              <textarea
                rows={4}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-purple-500"
                placeholder="Tell students about your experience, style, and approach"
                value={profile.bio}
                onChange={(e) => setProfile((p) => ({ ...p, bio: e.target.value }))}
              />
            </div>
          </div>
        </div>

        {/* Service Areas Section */}
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <div className="flex items-center gap-2 text-lg font-medium text-gray-900"><MapPin className="w-5 h-5 text-purple-700" />Service Areas</div>
            </div>
          </div>
          <div className="rounded-lg border border-gray-200 p-5 hover:shadow-sm transition-shadow">
            <p className="mb-3 text-sm text-gray-600">Select the neighborhoods where you teach</p>
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
              <div className="rounded-lg border border-gray-200 bg-white p-3 mb-3">
                <div className="text-sm text-gray-700 mb-2">Results</div>
                <div className="flex flex-wrap gap-2">
                  {NYC_BOROUGHS.flatMap((b) => boroughNeighborhoods[b] || [])
                    .filter((n) => (n.name || '').toLowerCase().includes(globalNeighborhoodFilter.toLowerCase()))
                    .map((n) => {
                      const nid = n.neighborhood_id || (n as any).id;
                      if (!nid) return null;
                      const checked = selectedNeighborhoods.has(nid);
                      return (
                        <button
                          key={`global-${nid}`}
                          type="button"
                          onClick={() => toggleNeighborhood(nid)}
                          aria-pressed={checked}
                          className={`flex items-center justify-between px-3 py-1.5 text-sm rounded-full font-semibold transition focus:outline-none focus:ring-2 focus:ring-purple-500/20 ${
                            checked ? 'bg-[#6A0DAD] text-white border border-[#6A0DAD]' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
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
            {isNYC ? (
            <div className="space-y-3">
              {/* Removed top borough pills row */}
              {/* Per-borough accordions like screenshot */}
              <div className="mt-3 space-y-3">
                {NYC_BOROUGHS.map((borough) => {
                  const isOpen = openBoroughsMain.has(borough);
                  const list = boroughNeighborhoods[borough] || [];
                  return (
                    <div key={`accordion-${borough}`} ref={(el) => { boroughAccordionRefs.current[borough] = el; }} className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
                      <div
                        className="flex items-center justify-between cursor-pointer"
                        onClick={async () => { await toggleMainBoroughOpen(borough); }}
                        aria-expanded={isOpen}
                        role="button"
                        tabIndex={0}
                        onKeyDown={async (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); await toggleMainBoroughOpen(borough); } }}
                      >
                        <div className="flex items-center gap-2 text-gray-800 font-medium">
                          <span className="tracking-wide text-sm">{borough}</span>
                          <ChevronDown className={`h-4 w-4 text-gray-600 transition-transform ${isOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
                        </div>
                        <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                          <button
                            type="button"
                            className="text-sm px-3 py-1 rounded-md bg-purple-100 text-purple-700 hover:bg-purple-200"
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
                            const nid = n.neighborhood_id || (n as any).id;
                            if (!nid) return null;
                            const checked = selectedNeighborhoods.has(nid);
                            const label = toTitle(n.name || String(nid));
                            return (
                              <button
                                key={`${borough}-${nid}`}
                                type="button"
                                onClick={() => toggleNeighborhood(nid)}
                                aria-pressed={checked}
                                className={`flex items-center justify-between w-full min-w-0 px-2 py-1 text-xs rounded-full font-semibold transition focus:outline-none focus:ring-2 focus:ring-purple-500/20 ${
                                  checked ? 'bg-[#6A0DAD] text-white border border-[#6A0DAD]' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
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
          </div>
        </div>

        {/* Experience Settings Section */}
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <div className="flex items-center gap-2 text-lg font-medium text-gray-900"><SettingsIcon className="w-5 h-5 text-purple-700" />Settings</div>
            </div>
          </div>
          <div className="rounded-lg border border-gray-200 p-5 hover:shadow-sm transition-shadow">
            <p className="mb-3 text-sm text-gray-600">Control availability and booking preferences</p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="bg-white rounded-lg p-3 border border-gray-200">
                <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Years of Experience</label>
                <input
                  type="number"
                  min={0}
                  max={50}
                  value={profile.years_experience}
                  onChange={(e) => setProfile((p) => ({ ...p, years_experience: Number(e.target.value || 0) }))}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-center font-medium focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500"
                />
              </div>
              <div className="bg-white rounded-lg p-3 border border-gray-200">
                <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Advance Notice (hours)</label>
                <input
                  type="number"
                  min={0}
                  max={168}
                  value={profile.min_advance_booking_hours ?? 2}
                  onChange={(e) => setProfile((p) => ({ ...p, min_advance_booking_hours: Number(e.target.value || 0) }))}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-center font-medium focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500"
                />
              </div>
              <div className="bg-white rounded-lg p-3 border border-gray-200">
                <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Buffer Time (minutes)</label>
                <input
                  type="number"
                  min={0}
                  max={60}
                  value={profile.buffer_time_minutes ?? 0}
                  onChange={(e) => setProfile((p) => ({ ...p, buffer_time_minutes: Number(e.target.value || 0) }))}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-center font-medium focus:outline-none focus:ring-2 focus:ring-purple-500/20 focus:border-purple-500"
                />
              </div>
            </div>
          </div>
        </div>

      </div>
        {/* Sticky save bar */}
        <div className="fixed bottom-0 left-0 right-0 bg-white/90 backdrop-blur border-t border-gray-200">
          <div className="mx-auto max-w-6xl px-8 lg:px-32 py-3 flex items-center justify-between">
            <div className="text-sm" aria-live="polite">
              {saving ? (
                <span className="text-gray-600">Saving…</span>
              ) : success ? (
                <span className="text-green-700">Saved</span>
              ) : error ? (
                <span className="text-red-700">Save failed</span>
              ) : (
                <span className="text-gray-500">Make changes and save</span>
              )}
            </div>
            <button
              onClick={save}
              disabled={!canSave || saving}
              className="px-5 py-2.5 rounded-lg text-white bg-[#6A0DAD] hover:bg-[#5c0a9a] disabled:opacity-50 shadow-sm"
            >
              {saving ? 'Saving...' : 'Save & Continue'}
            </button>
          </div>
        </div>
        {/* Success toast */}
        {success && (
          <div className="fixed bottom-20 right-6 rounded-lg bg-green-600 text-white px-4 py-2 shadow-lg" role="alert" aria-live="polite">
            {success}
          </div>
        )}
        {/* Animation CSS now global in app/globals.css */}
      </div>
    </div>
  );
}
