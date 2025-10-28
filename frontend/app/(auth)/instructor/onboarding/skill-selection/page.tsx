'use client';

import React, { Suspense, useEffect, useMemo, useState } from 'react';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import Link from 'next/link';
import { BookOpen, CheckSquare, Lightbulb } from 'lucide-react';
import { useSearchParams } from 'next/navigation';
import { publicApi } from '@/features/shared/api/client';
import { useAuth } from '@/features/shared/hooks/useAuth';
import type { CatalogService, ServiceCategory } from '@/features/shared/api/client';
import { logger } from '@/lib/logger';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { usePricingConfig, usePricingFloors } from '@/lib/pricing/usePricingFloors';
import { FloorViolation, evaluatePriceFloorViolations, formatCents } from '@/lib/pricing/priceFloors';

type AgeGroup = 'kids' | 'adults' | 'both';

type SelectedService = {
  catalog_service_id: string;
  name: string;
  hourly_rate: string; // keep as string for input control
  ageGroup: AgeGroup;
  description?: string;
  equipment?: string; // comma-separated freeform for UI
  levels_taught: Array<'beginner' | 'intermediate' | 'advanced'>;
  duration_options: number[];
  location_types: Array<'in-person' | 'online'>;
};

function Step3SkillsPricingInner() {
  const searchParams = useSearchParams();
  const redirectParam = searchParams?.get('redirect') || null;
  const { user, isAuthenticated } = useAuth();
  const [categories, setCategories] = useState<ServiceCategory[]>([]);
  const [servicesByCategory, setServicesByCategory] = useState<Record<string, CatalogService[]>>({});
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedService[]>([]);
  const [requestText, setRequestText] = useState('');
  const [requestSubmitting, setRequestSubmitting] = useState(false);
  const [requestSuccess, setRequestSuccess] = useState<string | null>(null);
  const { floors: pricingFloors } = usePricingFloors();
  const { config: pricingConfig } = usePricingConfig();
  const defaultInstructorTierPct = useMemo(() => {
    const pct = pricingConfig?.instructor_tiers?.[0]?.pct;
    return typeof pct === 'number' ? pct : null;
  }, [pricingConfig]);

  const floorViolationsByService = useMemo(() => {
    const map = new Map<string, FloorViolation[]>();
    if (!pricingFloors) return map;
    selected.forEach((svc) => {
      const violations = evaluatePriceFloorViolations({
        hourlyRate: Number(svc.hourly_rate),
        durationOptions: svc.duration_options ?? [60],
        locationTypes: svc.location_types ?? ['in-person'],
        floors: pricingFloors,
      });
      if (violations.length > 0) {
        map.set(svc.catalog_service_id, violations);
      }
    });
    return map;
  }, [pricingFloors, selected]);

  const hasFloorViolations = floorViolationsByService.size > 0;
  const [skillsFilter, setSkillsFilter] = useState<string>('');

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        const [cats, all] = await Promise.all([
          publicApi.getServiceCategories(),
          publicApi.getAllServicesWithInstructors(),
        ]);

        if (cats.status === 200 && cats.data) {
          const filtered = cats.data.filter((c) => c.slug !== 'kids');
          setCategories(filtered);
          // collapse all by default
          const initialCollapsed: Record<string, boolean> = {};
          for (const c of filtered) initialCollapsed[c.slug] = true;
          setCollapsed(initialCollapsed);
        }
        if (all.status === 200 && all.data) {
          const map: Record<string, CatalogService[]> = {};
          for (const c of all.data.categories.filter((c) => c.slug !== 'kids')) {
            map[c.slug] = c.services;
          }
          setServicesByCategory(map);
        }
        // Catalog loaded; prefill handled in a separate guarded effect below
      } catch (e) {
        logger.error('Failed loading catalog', e);
        setError('Failed to load services');
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  // Evaluate Step 1 completion (profile) and paint state on mount
  useEffect(() => {
    const evaluate = async () => {
      try {
        const [meRes, profRes, areasRes, addrsRes] = await Promise.all([
          fetchWithAuth(API_ENDPOINTS.ME),
          fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE),
          fetchWithAuth('/api/addresses/service-areas/me'),
          fetchWithAuth('/api/addresses/me'),
        ]);
        const me = meRes.ok ? await meRes.json() : {};
        const prof = profRes.ok ? await profRes.json() : {};
        const areas = areasRes.ok ? await areasRes.json() : { items: [] };
        // Resolve a postal/ZIP code from profile, user, or default address
        let defaultZip = '';
        try {
          if (addrsRes && addrsRes.ok) {
            const list = await addrsRes.json();
            const def = (list.items || []).find((a: unknown) => (a as Record<string, unknown>)['is_default']) || (list.items || [])[0];
            defaultZip = String((def as Record<string, unknown>)?.['postal_code'] || '').trim();
          }
        } catch {}
        const zipFromUser = String((me?.zip_code || me?.postal_code || '') as string).trim();
        const zipFromProfile = String((prof?.postal_code || '') as string).trim();
        const resolvedPostal = zipFromProfile || zipFromUser || defaultZip;

        const hasPic = Boolean(me?.has_profile_picture) || Number.isFinite(me?.profile_picture_version);
        const personalInfoFilled = Boolean((me?.first_name || '').trim()) && Boolean((me?.last_name || '').trim()) && Boolean(resolvedPostal);
        const bioOk = (String(prof?.bio || '').trim().length) >= 400;
        const hasServiceArea = Array.isArray(areas?.items) && areas.items.length > 0;
        const ok = hasPic && personalInfoFilled && bioOk && hasServiceArea;
        const circle = document.getElementById('progress-step-1');
        const line = document.getElementById('progress-line-1');
        if (circle && line) {
          const check = circle.querySelector('.icon-check') as HTMLElement | null;
          const cross = circle.querySelector('.icon-cross') as HTMLElement | null;
          if (ok) {
            circle.classList.remove('border-gray-300');
            circle.classList.add('border-[#7E22CE]', 'bg-[#7E22CE]');
            if (check) check.classList.remove('hidden');
            if (cross) cross.classList.add('hidden');
            line.classList.remove('bg-gray-300');
            line.classList.add('bg-[#7E22CE]');
          } else {
            circle.classList.remove('border-gray-300');
            circle.classList.add('border-[#7E22CE]', 'bg-[#7E22CE]');
            if (check) check.classList.add('hidden');
            if (cross) cross.classList.remove('hidden');
            line.classList.remove('bg-[#7E22CE]', 'bg-gray-300');
            line.classList.add('bg-[repeating-linear-gradient(to_right,_#7E22CE_0,_#7E22CE_8px,_transparent_8px,_transparent_16px)]');
          }
        }
      } catch {}
    };
    void evaluate();
  }, []);

  // Guarded prefill: only attempt when authenticated and user has instructor role
  useEffect(() => {
    const shouldPrefill =
      !!isAuthenticated && !!user && Array.isArray(user.roles) && user.roles.some((r: unknown) => String(r).toLowerCase() === 'instructor');
    if (!shouldPrefill) return;

    let cancelled = false;
    const prefill = async () => {
      try {
        const meRes = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);
        if (!meRes.ok) return; // silently ignore 401/403/404
        const me = await meRes.json();
        const mapped: SelectedService[] = (me.services || []).map((svc: unknown) => {
          if (typeof svc !== 'object' || svc === null) return null;
          const service = svc as Record<string, unknown>;
          return {
            catalog_service_id: String(service['service_catalog_id'] || ''),
            name: String(service['name'] || ''),
            hourly_rate: String(service['hourly_rate'] ?? ''),
            ageGroup:
              Array.isArray(service['age_groups']) && service['age_groups'].length === 2
                ? 'both' as AgeGroup
                : Array.isArray(service['age_groups']) && service['age_groups'].includes('kids')
                ? 'kids' as AgeGroup
                : 'adults' as AgeGroup,
            description: String(service['description'] || ''),
            equipment: Array.isArray(service['equipment_required']) ? service['equipment_required'].join(', ') : '',
            levels_taught:
              Array.isArray(service['levels_taught']) && service['levels_taught'].length
                ? service['levels_taught'] as string[]
                : ['beginner', 'intermediate', 'advanced'],
            duration_options: Array.isArray(service['duration_options']) && service['duration_options'].length ? service['duration_options'] as number[] : [60],
            location_types:
              Array.isArray(service['location_types']) && service['location_types'].length
                ? service['location_types'] as string[]
                : ['in-person'],
          };
        }).filter(Boolean) as SelectedService[];
        if (!cancelled && mapped.length) setSelected(mapped);
      } catch {
        // Swallow network errors to keep onboarding clean
      }
    };

    void prefill();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, user]);

  useEffect(() => {
    if (selected.length === 0) return;
    if (!servicesByCategory || Object.keys(servicesByCategory).length === 0) return;

    const lookup = new Map<string, string>();
    Object.values(servicesByCategory).forEach((services) => {
      services.forEach((svc) => {
        if (!lookup.has(svc.id)) {
          lookup.set(svc.id, svc.name);
        }
      });
    });

    setSelected((prev) => {
      let mutated = false;
      const next = prev.map((svc) => {
        if (svc.name && svc.name.trim().length > 0) {
          return svc;
        }
        const resolvedName = lookup.get(svc.catalog_service_id);
        if (resolvedName && resolvedName.trim().length > 0) {
          mutated = true;
          return { ...svc, name: resolvedName };
        }
        if (!svc.name || svc.name.trim().length === 0) {
          mutated = true;
          return { ...svc, name: 'Unknown Service' };
        }
        return svc;
      });
      return mutated ? next : prev;
    });
  }, [servicesByCategory, selected.length]);

  const toggleService = (svc: CatalogService) => {
    const isSelected = selected.some((s) => s.catalog_service_id === svc.id);

    if (isSelected) {
      // Deselect the service
      setSelected((prev) => prev.filter((s) => s.catalog_service_id !== svc.id));
    } else {
      // Add the service
      setSelected((prev) => [
        ...prev,
        {
          catalog_service_id: svc.id,
          name: svc.name,
          hourly_rate: '',
          ageGroup: 'adults',
          description: '',
          equipment: '',
          levels_taught: ['beginner', 'intermediate', 'advanced'],
          duration_options: [60],
          location_types: ['in-person'],
        },
      ]);
    }
  };

  const removeService = (id: string) => {
    setSelected((prev) => prev.filter((s) => s.catalog_service_id !== id));
  };

  const save = async () => {
    try {
      setSaving(true);
      setError(null);
      if (pricingFloors && hasFloorViolations) {
        const iterator = floorViolationsByService.entries().next();
        if (!iterator.done) {
          const [serviceId, violations] = iterator.value;
          const violation = violations[0];
          if (!violation) {
            setSaving(false);
            return;
          }
          const serviceName = selected.find((svc) => svc.catalog_service_id === serviceId)?.name || 'this service';
          setError(
            `Minimum price for a ${violation.modalityLabel} ${violation.duration}-minute private session is $${formatCents(violation.floorCents)} (current $${formatCents(violation.baseCents)}). Please update the rate for ${serviceName}.`
          );
          setSaving(false);
          return;
        }
      }
      const nextUrl = redirectParam || '/instructor/onboarding/verification';
      // If no skills selected, skip saving and go to verification step
      if (selected.length === 0) {
        // Store a flag that skills were skipped
        if (typeof window !== 'undefined') {
          sessionStorage.setItem('skillsSkipped', 'true');
        }
        window.location.href = nextUrl;
        return;
      }
      // PUT /instructors/me with services array
      const payload = {
        services: selected
          .filter((s) => s.hourly_rate.trim() !== '')
          .map((s) => ({
            service_catalog_id: s.catalog_service_id,
            hourly_rate: Number(s.hourly_rate),
            age_groups: s.ageGroup === 'both' ? ['kids', 'adults'] : [s.ageGroup],
            description: s.description && s.description.trim() ? s.description.trim() : undefined,
            duration_options: (s.duration_options && s.duration_options.length ? s.duration_options : [60]).sort((a, b) => a - b),
            levels_taught: s.levels_taught,
            equipment_required:
              s.equipment && s.equipment.trim()
                ? s.equipment
                    .split(',')
                    .map((x) => x.trim())
                    .filter((x) => x.length > 0)
                : undefined,
            location_types: s.location_types && s.location_types.length ? s.location_types : ['in-person'],
          })),
      };
      const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        // If profile not ready yet or any server error, proceed to verification and try later
        try {
          // Best effort to log error but keep user moving forward
          const msg = await res.json();
          logger.warn('Save services failed, moving to verification', { msg });
        } catch {}
        window.location.href = nextUrl;
        return;
      }
      // Clear the skipped flag since skills were saved
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem('skillsSkipped');
      }
      // Navigate to next step
      // Determine completion: at least one selected with required info (price)
      const hasComplete = selected.some((s) => (s.hourly_rate || '').trim().length > 0);
      const circle = document.getElementById('progress-step-2');
      const line = document.getElementById('progress-line-2');
      if (circle && line) {
        if (hasComplete) {
          circle.classList.add('border-[#7E22CE]', 'bg-purple-100');
          circle.setAttribute('data-status', 'done');
          line.classList.remove('bg-gray-300');
          line.classList.add('bg-[#7E22CE]');
          line.setAttribute('data-status', 'filled');
        } else {
          circle.classList.remove('border-[#7E22CE]');
          circle.classList.add('border-gray-300');
          circle.setAttribute('data-status', 'failed');
          line.classList.remove('bg-[#7E22CE]');
          line.classList.add('bg-gray-300');
          line.setAttribute('data-status', 'dashed');
        }
      }

      window.location.href = nextUrl;
    } catch (e) {
      logger.error('Save services failed', e);
      if (e instanceof TypeError) {
        // Likely CORS/network hiccup; continue onboarding and retry later
        window.location.href = redirectParam || '/instructor/onboarding/verification';
        return;
      }
      setError('Failed to save');
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    if (!hasFloorViolations && error && /Minimum price for a/.test(error)) {
      setError(null);
    }
  }, [hasFloorViolations, error]);

  const submitServiceRequest = async () => {
    if (!requestText.trim()) return;
    try {
      setRequestSubmitting(true);
      setRequestSuccess(null);
      // Placeholder client-side submission. In future, wire to backend endpoint.
      // We simulate latency for UX consistency and log for observability.
      logger.info('Service request submitted', { requestText });
      await new Promise((resolve) => setTimeout(resolve, 600));
      setRequestSuccess("Thanks! We'll review and consider adding this skill.");
      setRequestText('');
    } catch {
      setRequestSuccess('Something went wrong. Please try again.');
    } finally {
      setRequestSubmitting(false);
    }
  };

  if (loading) return <div className="p-8">Loading…</div>;

  return (
    <div className="min-h-screen">
      {/* Header - matching other pages */}
      <header className="bg-white backdrop-blur-sm border-b border-gray-200 px-4 sm:px-6 py-4">
        <div className="flex items-center justify-between max-w-full relative">
          <Link href="/instructor/dashboard" className="inline-block">
            <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-0 sm:pl-4">iNSTAiNSTRU</h1>
          </Link>

          {/* Progress Bar - 4 Steps - Absolutely centered */}
          <div className="absolute left-1/2 transform -translate-x-1/2 items-center gap-0 hidden min-[1400px]:flex">
            {/* Walking Stick Figure Animation - positioned on the line between step 1 and 2 */}
            <div className="absolute inst-anim-walk" style={{ top: '-12px', left: '24px' }}>
              <svg width="16" height="20" viewBox="0 0 16 20" fill="none">
                {/* Head */}
                <circle cx="8" cy="4" r="2.5" stroke="#7E22CE" strokeWidth="1.2" fill="none" />
                {/* Body */}
                <line x1="8" y1="6.5" x2="8" y2="12" stroke="#7E22CE" strokeWidth="1.2" />
                {/* Left arm */}
                <line x1="8" y1="8" x2="5" y2="10" stroke="#7E22CE" strokeWidth="1.2" className="inst-anim-leftArm" />
                {/* Right arm */}
                <line x1="8" y1="8" x2="11" y2="10" stroke="#7E22CE" strokeWidth="1.2" className="inst-anim-rightArm" />
                {/* Left leg */}
                <line x1="8" y1="12" x2="6" y2="17" stroke="#7E22CE" strokeWidth="1.2" className="inst-anim-leftLeg" />
                {/* Right leg */}
                <line x1="8" y1="12" x2="10" y2="17" stroke="#7E22CE" strokeWidth="1.2" className="inst-anim-rightLeg" />
              </svg>
            </div>

            {/* Step 1 - Account Setup (dynamic state) */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => window.location.href = '/instructor/profile'}
                  id="progress-step-1"
                  className="w-6 h-6 rounded-full border-2 border-[#7E22CE] bg-[#7E22CE] transition-colors cursor-pointer flex items-center justify-center"
                  title="Step 1: Account Setup"
                >
                  <svg className="icon-check hidden w-3 h-3 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                  </svg>
                  <svg className="icon-cross hidden w-3 h-3 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
                <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">Account Setup</span>
              </div>
              <div id="progress-line-1" className="w-60 h-0.5 bg-gray-300"></div>
            </div>

            {/* Step 2 - Current (Skills) */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => {/* Already on this page */}}
                  id="progress-step-2"
                  className="w-6 h-6 rounded-full border-2 border-purple-300 bg-purple-100 hover:border-[#7E22CE] text-[#7E22CE] transition-colors cursor-pointer"
                  title="Step 2: Skills & Pricing (Current)"
                ></button>
                <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">Add Skills</span>
              </div>
              <div id="progress-line-2" className="w-60 h-0.5 bg-gray-300"></div>
            </div>

            {/* Step 3 - Upcoming */}
            <div className="flex items-center">
              <div className="flex flex-col items-center relative">
                <button
                  onClick={() => window.location.href = '/instructor/onboarding/verification'}
                  className="w-6 h-6 rounded-full border-2 border-gray-300 hover:border-[#7E22CE] text-[#7E22CE] transition-colors cursor-pointer"
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
                  className="w-6 h-6 rounded-full border-2 border-gray-300 hover:border-[#7E22CE] text-[#7E22CE] transition-colors cursor-pointer"
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
        {/* Page Header - mobile sections (white) with dividers; desktop card */}
        <div className="mb-4 sm:mb-6 bg-transparent border-0 rounded-none p-4 sm:bg-white sm:rounded-lg sm:p-6 sm:border sm:border-gray-200">
          <h1 className="text-3xl font-bold text-gray-800 mb-2">What do you teach?</h1>
          <p className="text-gray-600">Choose your skills and set your rates</p>
        </div>
        {/* Divider */}
        <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />

      {error && <div className="mt-4 rounded-md bg-red-50 text-red-700 px-4 py-2">{error}</div>}

      <div className="mt-0 sm:mt-6 bg-white rounded-none border-0 p-4 sm:bg-white sm:rounded-lg sm:border sm:border-gray-200 sm:p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="flex items-center gap-3 text-lg font-semibold text-gray-900">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <BookOpen className="w-6 h-6 text-[#7E22CE]" />
              </div>
              <span>Service categories</span>
            </div>
          </div>
        </div>
        <div className="mt-2 space-y-4">
          <p className="text-gray-600 mt-1 mb-2">Select the service categories you teach</p>
          {/* Global skills search (mirrors service areas search) */}
          <div className="mb-3">
            <input
              type="text"
              value={skillsFilter}
              onChange={(e) => setSkillsFilter(e.target.value)}
              placeholder="Search skills..."
              className="w-full rounded-md border border-gray-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0]"
            />
          </div>
          {selected.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-2">
              {selected.map((s) => (
                <span
                  key={`sel-${s.catalog_service_id}`}
                  className="inline-flex items-center gap-2 rounded-full border border-gray-300 bg-white px-3 h-8 text-xs min-w-0"
                >
                  <span className="truncate max-w-[14rem]" title={s.name}>{s.name}</span>
                  <button
                    type="button"
                    aria-label={`Remove ${s.name}`}
                    className="ml-auto text-[#7E22CE] rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 no-hover-shadow shrink-0"
                    onClick={() => removeService(s.catalog_service_id)}
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
                    const selectedFlag = selected.some((s) => s.catalog_service_id === svc.id);
                    return (
                      <button
                        key={`global-${svc.id}`}
                        type="button"
                        onClick={() => toggleService(svc)}
                        aria-pressed={selectedFlag}
                        className={`inline-flex items-center justify-between px-3 py-1.5 text-sm rounded-full font-semibold focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 transition-colors no-hover-shadow appearance-none overflow-hidden ${
                          selectedFlag
                            ? 'bg-[#7E22CE] text-white border border-[#7E22CE] hover:bg-[#7E22CE]'
                            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                        }`}
                      >
                        <span className="truncate text-left">{svc.name}</span>
                        <span className="ml-2">{selectedFlag ? '✓' : '+'}</span>
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
              >
                <span className="font-bold">{cat.name}</span>
                <svg className={`h-4 w-4 text-gray-600 transition-transform ${isCollapsed ? '' : 'rotate-180'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {!isCollapsed && (
              <div className="p-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                {(servicesByCategory[cat.slug] || []).map((svc) => {
                  const selectedFlag = selected.some((s) => s.catalog_service_id === svc.id);
                  return (
                    <button
                      key={svc.id}
                      onClick={() => toggleService(svc)}
                      className={`inline-flex items-center justify-between px-3 py-1.5 text-sm rounded-full font-semibold focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 transition-colors no-hover-shadow appearance-none overflow-hidden ${
                        selectedFlag
                          ? 'bg-[#7E22CE] text-white border border-[#7E22CE] hover:bg-[#7E22CE]'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      <span className="truncate text-left">{svc.name}</span>
                      <span className="ml-2">{selectedFlag ? '✓' : '+'}</span>
                    </button>
                  );
                })}
              </div>
              )}
            </div>
          );
        })}
        </div>
      </div>
      {/* Divider */}
      <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />

      {/* Global age group selector removed; per-service selection is below */}

      <div className="mt-0 sm:mt-8 bg-white rounded-none p-4 border-0 sm:bg-white sm:rounded-lg sm:p-6 sm:border sm:border-gray-200">
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="flex items-center gap-3 text-lg font-semibold text-gray-900">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <CheckSquare className="w-6 h-6 text-[#7E22CE]" />
              </div>
              <span>Your selected skills</span>
            </div>
          </div>
        </div>
        {selected.length === 0 ? (
          <p className="text-gray-500">You can add skills now or later.</p>
        ) : (
          <div className="grid gap-4">
            {selected.map((s) => {
              const violations = pricingFloors ? floorViolationsByService.get(s.catalog_service_id) ?? [] : [];
              return (
                <div key={s.catalog_service_id} className="rounded-lg border border-gray-200 bg-gray-50 p-5 hover:shadow-sm transition-shadow">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div className="text-lg font-medium text-gray-900">{s.name}</div>
                    <div className="flex items-center gap-3 mt-2">
                      <div className="flex items-center gap-1">
                        <span className="text-2xl font-bold text-[#7E22CE]">${s.hourly_rate || '0'}</span>
                        <span className="text-sm text-gray-600">/hour</span>
                      </div>
                    </div>
                  </div>
                  <button
                    aria-label="Remove skill"
                    title="Remove skill"
                    className="w-8 h-8 flex items-center justify-center rounded-full bg-white border border-gray-300 text-gray-600 hover:bg-red-50 hover:text-red-600 hover:border-red-300 transition-colors"
                    onClick={() => removeService(s.catalog_service_id)}
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
                {/* Price Input Section */}
                <div className="mb-4 bg-white rounded-lg p-3 border border-gray-200">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-gray-700">Hourly Rate:</span>
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
                        onChange={(e) =>
                          setSelected((prev) =>
                            prev.map((x) =>
                              x.catalog_service_id === s.catalog_service_id ? { ...x, hourly_rate: e.target.value } : x
                            )
                          )
                        }
                      />
                      <span className="text-gray-500">/hr</span>
                    </div>
                  </div>
                  {s.hourly_rate && Number(s.hourly_rate) > 0 && defaultInstructorTierPct !== null && (
                    <div className="mt-2 text-xs text-gray-600">
                      You&apos;ll earn{' '}
                      <span className="font-semibold text-[#7E22CE]">
                        ${Number(Number(s.hourly_rate) * (1 - defaultInstructorTierPct)).toFixed(2)}
                      </span>{' '}
                      after the {(defaultInstructorTierPct * 100).toFixed(1).replace(/\.0$/, '')}% platform fee
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
                {/* Settings Grid - 2x2 Layout */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
                  {/* Age Group */}
                  <div className="bg-white rounded-lg p-3 border border-gray-200">
                    <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Age Group</label>
                    <div className="flex gap-1">
                      {(['kids', 'adults'] as const).map((ageType) => {
                        // Check if this age type is selected
                        const isSelected = s.ageGroup === 'both'
                          ? true
                          : s.ageGroup === ageType;

                        return (
                          <button
                            key={ageType}
                            onClick={() => {
                              setSelected((prev) =>
                                prev.map((x) => {
                                  if (x.catalog_service_id !== s.catalog_service_id) return x;

                                  // Toggle logic for age groups - works like checkboxes
                                  const currentAgeGroup = x.ageGroup;
                                  let newAgeGroup: AgeGroup;

                                  if (currentAgeGroup === 'both') {
                                    // Both selected: clicking one deselects it, leaving only the other
                                    newAgeGroup = ageType === 'kids' ? 'adults' : 'kids';
                                  } else if (currentAgeGroup === ageType) {
                                    // Only this one selected: deselect it to select the other
                                    newAgeGroup = ageType === 'kids' ? 'adults' : 'kids';
                                  } else {
                                    // The other one is selected, clicking this one selects both
                                    newAgeGroup = 'both';
                                  }

                                  return { ...x, ageGroup: newAgeGroup };
                                })
                              );
                            }}
                            className={`flex-1 px-2 py-2 text-sm rounded-md transition-colors ${
                              isSelected
                                ? 'bg-purple-100 text-[#7E22CE] border border-purple-300'
                                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                            }`}
                            type="button"
                          >
                            {ageType === 'kids' ? 'Kids' : 'Adults'}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* Location Type */}
                  <div className="bg-white rounded-lg p-3 border border-gray-200">
                    <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Location Type</label>
                    <div className="flex gap-1">
                      {(['in-person', 'online'] as const).map((loc) => (
                        <button
                          key={loc}
                          onClick={() =>
                            setSelected((prev) =>
                              prev.map((x) => {
                                if (x.catalog_service_id !== s.catalog_service_id) return x;

                                const hasLoc = x.location_types.includes(loc);
                                const otherLoc = loc === 'in-person' ? 'online' : 'in-person';

                                // If this is the only location selected, switch to the other one
                                if (hasLoc && x.location_types.length === 1) {
                                  return { ...x, location_types: [otherLoc] };
                                }

                                // Otherwise toggle normally
                                return {
                                  ...x,
                                  location_types: hasLoc
                                    ? x.location_types.filter((v) => v !== loc)
                                    : [...x.location_types, loc],
                                };
                              })
                            )
                          }
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

                  {/* Levels */}
                  <div className="bg-white rounded-lg p-3 border border-gray-200">
                    <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Skill Levels</label>
                    <div className="flex gap-1">
                      {(['beginner', 'intermediate', 'advanced'] as const).map((lvl) => (
                        <button
                          key={lvl}
                          onClick={() =>
                            setSelected((prev) =>
                              prev.map((x) =>
                                x.catalog_service_id === s.catalog_service_id
                                  ? {
                                      ...x,
                                      levels_taught: x.levels_taught.includes(lvl)
                                        ? x.levels_taught.filter((v) => v !== lvl)
                                        : [...x.levels_taught, lvl],
                                    }
                                  : x
                              )
                            )
                          }
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

                  {/* Duration */}
                  <div className="bg-white rounded-lg p-3 border border-gray-200">
                    <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Session Duration</label>
                    <div className="flex gap-1">
                      {[30, 45, 60, 90].map((d) => (
                        <button
                          key={d}
                          onClick={() =>
                            setSelected((prev) =>
                              prev.map((x) => {
                                if (x.catalog_service_id !== s.catalog_service_id) return x;

                                const hasDuration = x.duration_options.includes(d);

                                // If this is the only duration selected, don't allow deselecting it
                                if (hasDuration && x.duration_options.length === 1) {
                                  return x;
                                }

                                // Otherwise toggle normally
                                return {
                                  ...x,
                                  duration_options: hasDuration
                                    ? x.duration_options.filter((v) => v !== d)
                                    : [...x.duration_options, d],
                                };
                              })
                            )
                          }
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

                {/* Optional Details */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-1 block">Description (Optional)</label>
                    <textarea
                      rows={2}
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500 bg-white"
                      placeholder="Brief description of your teaching style..."
                      value={s.description || ''}
                      onChange={(e) =>
                        setSelected((prev) =>
                          prev.map((x) => (x.catalog_service_id === s.catalog_service_id ? { ...x, description: e.target.value } : x))
                        )
                      }
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-1 block">Equipment (Optional)</label>
                    <textarea
                      rows={2}
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500 bg-white"
                      placeholder="Yoga mat, tennis racket..."
                      value={s.equipment || ''}
                      onChange={(e) =>
                        setSelected((prev) =>
                          prev.map((x) => (x.catalog_service_id === s.catalog_service_id ? { ...x, equipment: e.target.value } : x))
                        )
                      }
                    />
                  </div>
                </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Request a new service */}
      <div className="mt-0 sm:mt-8 bg-white rounded-none p-4 border-0 sm:bg-white sm:rounded-lg sm:p-6 sm:border sm:border-gray-200">
        <div className="flex items-start justify-between mb-2">
          <div>
            <div className="flex items-center gap-3 text-lg font-semibold text-gray-900">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <Lightbulb className="w-6 h-6 text-[#7E22CE]" />
              </div>
              <span>Don&apos;t see your skill? We&apos;d love to add it!</span>
            </div>
          </div>
        </div>
        <div className="mt-3 flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            value={requestText}
            onChange={(e) => setRequestText(e.target.value)}
            placeholder="Type your skill here..."
            className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20"
          />
          <button
            onClick={submitServiceRequest}
            disabled={!requestText.trim() || requestSubmitting}
            className="px-4 py-2 rounded-lg text-white bg-[#7E22CE] hover:!bg-[#7E22CE] hover:!text-white disabled:opacity-50 shadow-sm"
          >
            Submit request
          </button>
        </div>
        {requestSuccess && <div className="mt-2 text-sm text-gray-800">{requestSuccess}</div>}
      </div>

      <div className="mt-8 flex items-center justify-end gap-3">
        <button
          type="button"
          onClick={() => {
            const hasComplete = selected.some((s) => (s.hourly_rate || '').trim().length > 0);
            const circle = document.getElementById('progress-step-2');
            const line = document.getElementById('progress-line-2');
            if (circle && line) {
              if (hasComplete) {
                circle.classList.add('border-[#7E22CE]', 'bg-purple-100');
                circle.setAttribute('data-status', 'done');
                line.classList.remove('bg-gray-300');
                line.classList.add('bg-[#7E22CE]');
                line.setAttribute('data-status', 'filled');
              } else {
                circle.classList.remove('border-[#7E22CE]');
                circle.classList.add('border-gray-300');
                circle.setAttribute('data-status', 'failed');
                line.classList.remove('bg-[#7E22CE]');
                line.classList.add('bg-gray-300');
                line.setAttribute('data-status', 'dashed');
              }
            }
            window.location.href = '/instructor/onboarding/verification';
          }}
          className="w-40 px-5 py-2.5 rounded-lg text-[#7E22CE] bg-white border border-purple-200 hover:bg-gray-50 hover:border-purple-300 transition-colors focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 justify-center"
        >
          Skip for now
        </button>
        <button
          onClick={save}
          disabled={saving || hasFloorViolations}
          className="w-56 whitespace-nowrap px-5 py-2.5 rounded-lg text-white bg-[#7E22CE] hover:!bg-[#7E22CE] hover:!text-white disabled:opacity-50 shadow-sm justify-center"
        >
          {saving ? 'Saving...' : 'Save & Continue'}
        </button>
      </div>
      </div>

      {/* Animation CSS moved to global (app/globals.css) */}
    </div>
  );
}

export default function Step3SkillsPricing() {
  return (
    <Suspense fallback={<div className="p-8">Loading…</div>}>
      <Step3SkillsPricingInner />
    </Suspense>
  );
}
