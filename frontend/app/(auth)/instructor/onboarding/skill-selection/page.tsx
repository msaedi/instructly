'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { BookOpen, CheckSquare, Lightbulb } from 'lucide-react';
import { useSearchParams } from 'next/navigation';
import { publicApi } from '@/features/shared/api/client';
import { useAuth } from '@/features/shared/hooks/useAuth';
import type { ApiErrorResponse, CategoryServiceDetail, ServiceCategory } from '@/features/shared/api/types';
import { logger } from '@/lib/logger';
import { usePricingConfig } from '@/lib/pricing/usePricingFloors';
import { FloorViolation, evaluatePriceFloorViolations, formatCents } from '@/lib/pricing/priceFloors';
import { formatPlatformFeeLabel, resolvePlatformFeeRate, resolveTakeHomePct } from '@/lib/pricing/platformFees';
import { OnboardingProgressHeader } from '@/features/instructor-onboarding/OnboardingProgressHeader';
import { useOnboardingStepStatus } from '@/features/instructor-onboarding/useOnboardingStepStatus';
import { usePlatformFees } from '@/hooks/usePlatformConfig';
import type { ServiceLocationType } from '@/types/instructor';
import { queryKeys } from '@/src/api/queryKeys';
import { ToggleSwitch } from '@/components/ui/ToggleSwitch';
import { toast } from 'sonner';

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
  offers_travel: boolean;
  offers_at_location: boolean;
  offers_online: boolean;
};

type ServiceCapabilities = Pick<
  SelectedService,
  'offers_travel' | 'offers_at_location' | 'offers_online'
>;

const hasAnyLocationOption = (service: ServiceCapabilities) =>
  service.offers_travel || service.offers_at_location || service.offers_online;

const isLocationCapabilityError = (message: string) =>
  message.includes("Cannot enable travel") ||
  message.includes("Cannot enable 'at my location'");

const locationTypesFromCapabilities = (
  service: ServiceCapabilities
): ServiceLocationType[] => {
  const types: ServiceLocationType[] = [];
  if (service.offers_travel || service.offers_at_location) {
    types.push('in_person');
  }
  if (service.offers_online) {
    types.push('online');
  }
  return types;
};

function Step3SkillsPricingInner() {
  const searchParams = useSearchParams();
  const redirectParam = searchParams?.get('redirect') || null;
  const { user, isAuthenticated } = useAuth();
  const [categories, setCategories] = useState<ServiceCategory[]>([]);
  const [servicesByCategory, setServicesByCategory] = useState<Record<string, CategoryServiceDetail[]>>({});
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedService[]>([]);
  const [requestText, setRequestText] = useState('');
  const [requestSubmitting, setRequestSubmitting] = useState(false);
  const [requestSuccess, setRequestSuccess] = useState<string | null>(null);
  // Use unified step status hook for consistent progress display
  const { stepStatus, rawData } = useOnboardingStepStatus();
  const queryClient = useQueryClient();
  // Check if instructor is already live (affects whether they can have 0 skills)
  const isInstructorLive = rawData.profile?.is_live === true;
  // Single pricing config fetch - derive floors from config to avoid duplicate API calls
  const { config: pricingConfig } = usePricingConfig();
  const { fees } = usePlatformFees();
  const pricingFloors = pricingConfig?.price_floor_cents ?? null;
  const isFoundingInstructor = Boolean(rawData.profile?.is_founding_instructor);
  const profileRecord = rawData.profile as Record<string, unknown> | null;
  const serviceAreaNeighborhoods = Array.isArray(profileRecord?.['service_area_neighborhoods'])
    ? (profileRecord?.['service_area_neighborhoods'] as unknown[])
    : [];
  const serviceAreaBoroughs = Array.isArray(profileRecord?.['service_area_boroughs'])
    ? (profileRecord?.['service_area_boroughs'] as unknown[])
    : [];
  const serviceAreaSummary =
    typeof profileRecord?.['service_area_summary'] === 'string'
      ? (profileRecord?.['service_area_summary'] as string)
      : '';
  const hasServiceAreas =
    serviceAreaNeighborhoods.length > 0 ||
    serviceAreaBoroughs.length > 0 ||
    serviceAreaSummary.trim().length > 0;
  const teachingLocations = Array.isArray(profileRecord?.['preferred_teaching_locations'])
    ? (profileRecord?.['preferred_teaching_locations'] as unknown[])
    : [];
  const hasTeachingLocations = teachingLocations.length > 0;
  const currentTierRaw = profileRecord?.['current_tier_pct'] ?? profileRecord?.['instructor_tier_pct'];
  const currentTierPct = typeof currentTierRaw === 'number' ? currentTierRaw : null;
  const platformFeeRate = useMemo(
    () =>
      resolvePlatformFeeRate({
        fees,
        isFoundingInstructor,
        currentTierPct,
      }),
    [currentTierPct, fees, isFoundingInstructor]
  );
  const platformFeeLabel = useMemo(() => formatPlatformFeeLabel(platformFeeRate), [platformFeeRate]);
  const instructorTakeHomePct = useMemo(() => resolveTakeHomePct(platformFeeRate), [platformFeeRate]);

  const resolveCapabilitiesFromService = useCallback((service: Record<string, unknown>): ServiceCapabilities => {
    return {
      offers_travel: service['offers_travel'] === true,
      offers_at_location: service['offers_at_location'] === true,
      offers_online: service['offers_online'] === true,
    };
  }, []);

  const defaultCapabilities = (): ServiceCapabilities => {
    const defaultTravel = hasServiceAreas;
    const defaultAtLocation = hasTeachingLocations;
    return {
      offers_travel: defaultTravel,
      offers_at_location: defaultAtLocation,
      offers_online: !defaultTravel && !defaultAtLocation,
    };
  };

  const floorViolationsByService = useMemo(() => {
    const map = new Map<string, FloorViolation[]>();
    if (!pricingFloors) return map;
    selected.forEach((svc) => {
      const locationTypes = locationTypesFromCapabilities(svc);
      if (!locationTypes.length) return;
      const violations = evaluatePriceFloorViolations({
        hourlyRate: Number(svc.hourly_rate),
        durationOptions: svc.duration_options ?? [60],
        locationTypes,
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
          const map: Record<string, CategoryServiceDetail[]> = {};
          const categories = all.data.categories ?? [];
          for (const c of categories.filter((category) => category.slug !== 'kids')) {
            map[c.slug] = c.services ?? [];
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

  // Prefill from hook's rawData to avoid duplicate fetch
  useEffect(() => {
    const shouldPrefill =
      !!isAuthenticated && !!user && Array.isArray(user.roles) && user.roles.some((r: unknown) => String(r).toLowerCase() === 'instructor');
    if (!shouldPrefill || !rawData.profile?.services) return;

    const mapped: SelectedService[] = (rawData.profile.services || []).map((svc: unknown) => {
      if (typeof svc !== 'object' || svc === null) return null;
      const service = svc as Record<string, unknown>;
      const capabilities = resolveCapabilitiesFromService(service);
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
        offers_travel: hasServiceAreas ? capabilities.offers_travel : false,
        offers_at_location: hasTeachingLocations ? capabilities.offers_at_location : false,
        offers_online: capabilities.offers_online,
      };
    }).filter(Boolean) as SelectedService[];
    if (mapped.length) setSelected(mapped);
  }, [
    hasServiceAreas,
    hasTeachingLocations,
    isAuthenticated,
    rawData.profile?.services,
    resolveCapabilitiesFromService,
    user,
  ]);

  useEffect(() => {
    if (hasServiceAreas && hasTeachingLocations) return;
    setSelected((prev) => {
      let mutated = false;
      const next = prev.map((service) => {
        let updated = service;
        if (!hasServiceAreas && updated.offers_travel) {
          updated = { ...updated, offers_travel: false };
          mutated = true;
        }
        if (!hasTeachingLocations && updated.offers_at_location) {
          updated = { ...updated, offers_at_location: false };
          mutated = true;
        }
        return updated;
      });
      return mutated ? next : prev;
    });
  }, [hasServiceAreas, hasTeachingLocations]);


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

  const toggleService = (svc: CategoryServiceDetail) => {
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
          ...defaultCapabilities(),
        },
      ]);
    }
  };

  const removeService = (id: string) => {
    // Prevent removing the last skill if instructor is already live
    if (isInstructorLive && selected.length <= 1) {
      setError('Live instructors must have at least one skill. Add another skill before removing this one.');
      return;
    }
    setSelected((prev) => prev.filter((s) => s.catalog_service_id !== id));
  };

  const save = async () => {
    try {
      setSaving(true);
      setError(null);
      const hasInvalidCapabilities = selected.some((svc) =>
        !hasAnyLocationOption({
          offers_travel: hasServiceAreas ? svc.offers_travel : false,
          offers_at_location: hasTeachingLocations ? svc.offers_at_location : false,
          offers_online: svc.offers_online,
        })
      );
      if (hasInvalidCapabilities) {
        toast.error('Select at least one way to offer this skill (travel, at your studio, or online)');
        setSaving(false);
        return;
      }
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
      // If no skills selected
      if (selected.length === 0) {
        // Live instructors must have at least one skill
        if (isInstructorLive) {
          setError('Live instructors must have at least one skill.');
          setSaving(false);
          return;
        }
        // During onboarding: persist empty skills array to backend, then navigate
        try {
          await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ services: [] }),
          });
        } catch {
          // Best effort - continue even if clearing fails
          logger.warn('Failed to clear services, continuing to next step');
        }
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
            offers_travel: hasServiceAreas ? s.offers_travel : false,
            offers_at_location: hasTeachingLocations ? s.offers_at_location : false,
            offers_online: s.offers_online,
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
          const msg = (await res.json()) as ApiErrorResponse;
          logger.warn('Save services failed, moving to verification', { msg });
        } catch {}
        window.location.href = nextUrl;
        return;
      }
      await queryClient.invalidateQueries({ queryKey: queryKeys.instructors.me });
      // Clear the skipped flag since skills were saved
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem('skillsSkipped');
      }
      // Navigate to next step
      window.location.href = nextUrl;
    } catch (e) {
      logger.error('Save services failed', e);
      if (e instanceof TypeError) {
        // Likely CORS/network hiccup; continue onboarding and retry later
        window.location.href = redirectParam || '/instructor/onboarding/verification';
        return;
      }
      const message = e instanceof Error ? e.message : 'Failed to save';
      if (!isLocationCapabilityError(message)) {
        setError(message);
      }
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

  const showError = Boolean(error) && !isLocationCapabilityError(error ?? '');

  return (
    <div className="min-h-screen">
      <OnboardingProgressHeader activeStep="skill-selection" stepStatus={stepStatus} />

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        {/* Page Header - mobile sections (white) with dividers; desktop card */}
        <div className="mb-4 sm:mb-6 bg-transparent border-0 rounded-none p-4 sm:bg-white sm:rounded-lg sm:p-6 sm:border sm:border-gray-200">
          <h1 className="text-3xl font-bold text-gray-800 mb-2">What do you teach?</h1>
          <p className="text-gray-600">Choose your skills and set your rates</p>
        </div>
        {/* Divider */}
        <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />

      {showError && <div className="mt-4 rounded-md bg-red-50 text-red-700 px-4 py-2">{error}</div>}

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
                    title={isInstructorLive && selected.length <= 1 ? 'Live instructors must have at least one skill' : `Remove ${s.name}`}
                    className={`ml-auto rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center no-hover-shadow shrink-0 ${
                      isInstructorLive && selected.length <= 1
                        ? 'text-gray-300 cursor-not-allowed'
                        : 'text-[#7E22CE] hover:bg-purple-50'
                    }`}
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
              const effectiveOffersTravel = hasServiceAreas ? s.offers_travel : false;
              const effectiveOffersAtLocation = hasTeachingLocations ? s.offers_at_location : false;
              const effectiveCapabilities: ServiceCapabilities = {
                offers_travel: effectiveOffersTravel,
                offers_at_location: effectiveOffersAtLocation,
                offers_online: s.offers_online,
              };
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
                    title={isInstructorLive && selected.length <= 1 ? 'Live instructors must have at least one skill' : 'Remove skill'}
                    className={`w-8 h-8 flex items-center justify-center rounded-full bg-white border transition-colors ${
                      isInstructorLive && selected.length <= 1
                        ? 'border-gray-200 text-gray-300 cursor-not-allowed'
                        : 'border-gray-300 text-gray-600 hover:bg-red-50 hover:text-red-600 hover:border-red-300'
                    }`}
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
                  {s.hourly_rate && Number(s.hourly_rate) > 0 && (
                    <div className="mt-2 text-xs text-gray-600">
                      You&apos;ll earn{' '}
                      <span className="font-semibold text-[#7E22CE]">
                        ${Number(Number(s.hourly_rate) * instructorTakeHomePct).toFixed(2)}
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
                    <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">
                      How do you offer this skill?
                    </label>
                    <div className="space-y-3">
                      {(() => {
                        const travelDisabled = !hasServiceAreas;
                        const travelMessage = travelDisabled
                          ? 'You need at least one service area to offer travel lessons'
                          : null;
                        const atLocationDisabled = !hasTeachingLocations;
                        const atLocationMessage = atLocationDisabled
                          ? 'You need at least one teaching location to offer studio lessons'
                          : null;

                        return (
                          <>
                            <div
                              className={`rounded-md border border-gray-200 p-3 ${
                                travelDisabled ? 'opacity-60 cursor-not-allowed' : ''
                              }`}
                              title={travelMessage ?? undefined}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div>
                                  <p className="text-sm font-medium text-gray-700">I travel to students</p>
                                  <p className="text-xs text-gray-500">(Within your service areas)</p>
                                </div>
                                <ToggleSwitch
                                  checked={effectiveOffersTravel}
                                  onChange={() =>
                                    setSelected((prev) =>
                                      prev.map((x) =>
                                        x.catalog_service_id === s.catalog_service_id
                                          ? { ...x, offers_travel: !x.offers_travel }
                                          : x
                                      )
                                    )
                                  }
                                  disabled={travelDisabled}
                                  ariaLabel="I travel to students"
                                  {...(travelMessage ? { title: travelMessage } : {})}
                                />
                              </div>
                              {travelMessage && (
                                <p className="mt-1 text-xs text-gray-500">{travelMessage}</p>
                              )}
                            </div>
                            <div
                              className={`rounded-md border border-gray-200 p-3 ${
                                atLocationDisabled ? 'opacity-60 cursor-not-allowed' : ''
                              }`}
                              title={atLocationMessage ?? undefined}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div>
                                  <p className="text-sm font-medium text-gray-700">Students come to me</p>
                                  <p className="text-xs text-gray-500">(At your teaching location)</p>
                                </div>
                                <ToggleSwitch
                                  checked={effectiveOffersAtLocation}
                                  onChange={() =>
                                    setSelected((prev) =>
                                      prev.map((x) =>
                                        x.catalog_service_id === s.catalog_service_id
                                          ? { ...x, offers_at_location: !x.offers_at_location }
                                          : x
                                      )
                                    )
                                  }
                                  disabled={atLocationDisabled}
                                  ariaLabel="Students come to me"
                                  {...(atLocationMessage ? { title: atLocationMessage } : {})}
                                />
                              </div>
                              {atLocationMessage && (
                                <p className="mt-1 text-xs text-gray-500">{atLocationMessage}</p>
                              )}
                            </div>
                            <div className="rounded-md border border-gray-200 p-3">
                              <div className="flex items-start justify-between gap-3">
                                <div>
                                  <p className="text-sm font-medium text-gray-700">Online lessons</p>
                                  <p className="text-xs text-gray-500">(Video call)</p>
                                </div>
                                <ToggleSwitch
                                  checked={s.offers_online}
                                  onChange={() =>
                                    setSelected((prev) =>
                                      prev.map((x) =>
                                        x.catalog_service_id === s.catalog_service_id
                                          ? { ...x, offers_online: !x.offers_online }
                                          : x
                                      )
                                    )
                                  }
                                  ariaLabel="Online lessons"
                                />
                              </div>
                            </div>
                          </>
                        );
                      })()}
                    </div>
                    {!hasAnyLocationOption(effectiveCapabilities) && (
                      <p className="text-xs text-red-600 mt-2">
                        Select at least one location option for this skill.
                      </p>
                    )}
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
