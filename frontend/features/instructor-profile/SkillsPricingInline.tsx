"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { DollarSign, ChevronDown, Lightbulb } from 'lucide-react';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { logger } from '@/lib/logger';
import { hydrateCatalogNameById, displayServiceName, normalizeLocationTypes } from '@/lib/instructorServices';
import { usePricingConfig } from '@/lib/pricing/usePricingFloors';
import { formatPlatformFeeLabel, resolvePlatformFeeRate, resolveTakeHomePct } from '@/lib/pricing/platformFees';
import { evaluatePriceFloorViolations, formatCents, type FloorViolation } from '@/lib/pricing/priceFloors';
import { useServiceCategories, useAllServicesWithInstructors } from '@/hooks/queries/useServices';
import { useInstructorProfileMe } from '@/hooks/queries/useInstructorProfileMe';
import { usePlatformFees } from '@/hooks/usePlatformConfig';
import type { ApiErrorResponse, CategoryServiceDetail, InstructorProfileResponse, ServiceCategory } from '@/features/shared/api/types';
import type { ServiceLocationType } from '@/types/instructor';

type SelectedService = {
  catalog_service_id: string;
  service_catalog_name?: string | null;
  name?: string | null;
  hourly_rate: string;
  ageGroup: 'kids' | 'adults' | 'both';
  description?: string;
  equipment?: string;
  levels_taught: Array<'beginner' | 'intermediate' | 'advanced'>;
  duration_options: number[];
  location_types: ServiceLocationType[];
};

interface Props {
  className?: string;
  /** Pre-fetched instructor profile to avoid duplicate API calls */
  instructorProfile?: InstructorProfileResponse | null;
}

export default function SkillsPricingInline({ className, instructorProfile }: Props) {
  const [categories, setCategories] = useState<ServiceCategory[]>([]);
  const [servicesByCategory, setServicesByCategory] = useState<Record<string, CategoryServiceDetail[]>>({});
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [selectedServices, setSelectedServices] = useState<SelectedService[]>([]);
  const [svcLoading, setSvcLoading] = useState(false);
  const [svcSaving, setSvcSaving] = useState(false);
  const [error, setError] = useState('');
  // Default to true (assume live) until we confirm otherwise - safer default
  const [isInstructorLive, setIsInstructorLive] = useState(true);
  const [profileLoaded, setProfileLoaded] = useState(false);
  const { config: pricingConfig } = usePricingConfig();
  const { fees } = usePlatformFees();
  const pricingFloors = pricingConfig?.price_floor_cents ?? null;

  // Use React Query hooks for service data (prevents duplicate API calls)
  const { data: categoriesData, isLoading: categoriesLoading } = useServiceCategories();
  const { data: allServicesData, isLoading: allServicesLoading } = useAllServicesWithInstructors();
  // Use React Query hook for instructor profile when prop not provided (prevents duplicate API calls)
  const { data: profileFromHook } = useInstructorProfileMe(!instructorProfile);
  const [skillsFilter, setSkillsFilter] = useState('');
  const [requestedSkill, setRequestedSkill] = useState('');
  const [requestSubmitting, setRequestSubmitting] = useState(false);
  const [requestSuccess, setRequestSuccess] = useState<string | null>(null);
  const profileFeeContext = useMemo(() => {
    const profileData = instructorProfile ?? profileFromHook;
    const record = profileData as Record<string, unknown> | null;
    const currentTierRaw = record?.['current_tier_pct'] ?? record?.['instructor_tier_pct'];
    const currentTierPct =
      typeof currentTierRaw === 'number' && Number.isFinite(currentTierRaw) ? currentTierRaw : null;
    return {
      isFoundingInstructor: Boolean(record?.['is_founding_instructor']),
      currentTierPct,
    };
  }, [instructorProfile, profileFromHook]);
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
        locationTypes: service.location_types?.length
          ? service.location_types
          : (['in_person'] as ServiceLocationType[]),
        floors: pricingFloors,
      });
      if (violations.length > 0) map.set(service.catalog_service_id, violations);
    });
    return map;
  }, [pricingFloors, selectedServices]);

  // Sync loading state with React Query hooks
  useEffect(() => {
    setSvcLoading(categoriesLoading || allServicesLoading);
  }, [categoriesLoading, allServicesLoading]);

  // Process service categories and services data from hooks
  useEffect(() => {
    if (categoriesData) {
      const filtered = categoriesData.filter((c: ServiceCategory) => c.slug !== 'kids');
      setCategories(filtered);
      const initCollapsed: Record<string, boolean> = {};
      for (const c of filtered) initCollapsed[c.slug] = true;
      setCollapsed(initCollapsed);
    }
  }, [categoriesData]);

  useEffect(() => {
    if (allServicesData) {
      const map: Record<string, CategoryServiceDetail[]> = {};
      const categories = allServicesData.categories ?? [];
      for (const c of categories.filter((category) => category.slug !== 'kids')) {
        const services = c.services ?? [];
        const deduped = Array.from(new Map(services.map((svc) => [svc.id, svc])).values());
        map[c.slug] = deduped;
      }
      setServicesByCategory(map);
    }
  }, [allServicesData]);

  // Load instructor profile (prefilled services) - uses prop or React Query hook data
  useEffect(() => {
    // Use prop if provided, otherwise use hook data
    const profileData = instructorProfile ?? profileFromHook;
    if (!profileData) return;

    const me = profileData as Record<string, unknown>;
    logger.debug('SkillsPricingInline: using profile data', {
      source: instructorProfile ? 'prop' : 'hook',
      is_live: me['is_live'],
    });

    // Track if instructor is live (affects whether they can delete last skill)
    const isLive = Boolean(me['is_live']);
    logger.debug('SkillsPricingInline: instructor is_live status', { is_live: me['is_live'], parsed: isLive });
    setIsInstructorLive(isLive);
    setProfileLoaded(true);

    const mapped: SelectedService[] = (me['services'] as unknown[] || [])
      .map((svc: unknown) => {
        const s = svc as Record<string, unknown>;
        const catalogId = String(s['service_catalog_id'] || '');
        const rawLocationTypes = Array.isArray(s['location_types'])
          ? (s['location_types'] as unknown[])
          : [];
        const normalizedLocationTypes = rawLocationTypes.length
          ? normalizeLocationTypes(rawLocationTypes)
          : [];
        const serviceName = displayServiceName(
          {
            service_catalog_id: catalogId,
            service_catalog_name:
              typeof s['service_catalog_name'] === 'string'
                ? (s['service_catalog_name'] as string)
                : (s['name'] as string | undefined) ?? null,
          },
          hydrateCatalogNameById,
        );
        return {
          catalog_service_id: catalogId,
          service_catalog_name:
            typeof s['service_catalog_name'] === 'string'
              ? (s['service_catalog_name'] as string)
              : null,
          name: serviceName,
          hourly_rate: String(s['hourly_rate'] ?? ''),
          ageGroup:
            Array.isArray(s['age_groups']) && (s['age_groups'] as string[]).length === 2
              ? 'both'
              : ((s['age_groups'] as string[]) || []).includes('kids')
              ? 'kids'
              : 'adults',
          description: (s['description'] as string) || '',
          equipment: Array.isArray(s['equipment_required'])
            ? (s['equipment_required'] as string[]).join(', ')
            : '',
          levels_taught:
            Array.isArray(s['levels_taught']) && (s['levels_taught'] as string[]).length
              ? (s['levels_taught'] as Array<'beginner' | 'intermediate' | 'advanced'>)
              : ['beginner', 'intermediate', 'advanced'],
          duration_options:
            Array.isArray(s['duration_options']) && (s['duration_options'] as number[]).length
              ? (s['duration_options'] as number[])
              : [60],
          location_types: normalizedLocationTypes.length ? normalizedLocationTypes : ['in_person'],
        } as SelectedService;
      })
      .filter((svc: SelectedService) => svc.catalog_service_id);

    if (mapped.length) {
      const deduped = Array.from(
        new Map(
          mapped.map((mappedService: SelectedService) => [
            mappedService.catalog_service_id,
            mappedService,
          ]),
        ).values(),
      );
      setSelectedServices(deduped);
    }
  }, [instructorProfile, profileFromHook]);

  const toggleCategory = (slug: string) => {
    setCollapsed((prev) => ({ ...prev, [slug]: !prev[slug] }));
  };

  // Helper to check if we can remove a skill (live instructors must have at least 1)
  // Also blocks deletion if profile hasn't loaded yet (safety guard)
  const canRemoveSkill = useCallback(() => {
    // Block deletion until profile is loaded (we need to know if instructor is live)
    if (!profileLoaded) return false;
    // Non-live instructors can delete all skills
    if (!isInstructorLive) return true;
    // Live instructors must keep at least 1 skill
    return selectedServices.length > 1;
  }, [profileLoaded, isInstructorLive, selectedServices.length]);

  const removeService = useCallback((catalogServiceId: string) => {
    logger.debug('SkillsPricingInline: removeService called', {
      catalogServiceId,
      profileLoaded,
      isInstructorLive,
      selectedServicesCount: selectedServices.length,
      canRemove: canRemoveSkill()
    });
    if (!canRemoveSkill()) {
      if (!profileLoaded) {
        setError('Please wait for profile to load before removing skills.');
      } else {
        setError('Live instructors must have at least one skill. Add another skill before removing this one.');
      }
      return;
    }
    setSelectedServices((prev) => prev.filter((s) => s.catalog_service_id !== catalogServiceId));
  }, [canRemoveSkill, profileLoaded, isInstructorLive, selectedServices.length]);

  const toggleServiceSelection = (svc: CategoryServiceDetail) => {
    setSelectedServices((prev) => {
      const exists = prev.some((s) => s.catalog_service_id === svc.id);
      if (exists) {
        // Block deletion until profile is loaded
        if (!profileLoaded) {
          setError('Please wait for profile to load before removing skills.');
          return prev;
        }
        // Check if we can remove (live instructors must have at least 1)
        if (isInstructorLive && prev.length <= 1) {
          setError('Live instructors must have at least one skill. Add another skill before removing this one.');
          return prev;
        }
        return prev.filter((s) => s.catalog_service_id !== svc.id);
      }
      const label = displayServiceName({ service_catalog_id: svc.id, service_catalog_name: svc.name }, hydrateCatalogNameById);
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
          location_types: ['in_person'],
        },
      ];
    });
  };

  const handleRequestSkill = useCallback(async () => {
    if (!requestedSkill.trim()) return;
    try {
      setRequestSubmitting(true);
      setRequestSuccess(null);
      logger.info('Instructor profile skill request submitted', { requestedSkill });
      await new Promise((resolve) => setTimeout(resolve, 600));
      setRequestSuccess("Thanks! We'll review and consider adding this skill.");
      setRequestedSkill('');
    } catch {
      setRequestSuccess('Something went wrong. Please try again.');
    } finally {
      setRequestSubmitting(false);
    }
  }, [requestedSkill]);

  const initialLoadRef = useRef(true);
  const autoSaveTimeout = useRef<NodeJS.Timeout | null>(null);

  const handleSave = useCallback(async () => {
    try {
      setSvcSaving(true);

      // Safeguard: Don't save if profile hasn't loaded (we don't know if instructor is live)
      if (!profileLoaded) {
        logger.warn('SkillsPricingInline: Skipping save - profile not loaded yet');
        setSvcSaving(false);
        return;
      }

      // Safeguard: Live instructors must have at least one skill with a valid rate
      const servicesWithRates = selectedServices.filter((s) => s.hourly_rate.trim() !== '');
      if (isInstructorLive && servicesWithRates.length === 0) {
        setError('Live instructors must have at least one skill. Please add a skill before saving.');
        setSvcSaving(false);
        return;
      }

      if (pricingFloors && serviceFloorViolations.size > 0) {
        const iterator = serviceFloorViolations.entries().next();
        if (!iterator.done) {
          const [serviceId, violations] = iterator.value;
          const violation = violations?.[0];
          if (violation) {
            setError(
              `Minimum price for a ${violation.modalityLabel} ${violation.duration}-minute private session is $${formatCents(violation.floorCents)} (current $${formatCents(violation.baseCents)}). Please adjust the rate for ${selectedServices.find((s) => s.catalog_service_id === serviceId)?.name || 'this service'}.`
            );
            setSvcSaving(false);
            return;
          }
        }
      }

      const payload = {
        services: selectedServices
          .filter((service) => service.hourly_rate.trim() !== '')
          .map((service) => ({
            service_catalog_id: service.catalog_service_id || undefined,
            hourly_rate: Number(service.hourly_rate),
            age_groups: service.ageGroup === 'both' ? ['kids', 'adults'] : [service.ageGroup],
            ...(service.description?.trim() ? { description: service.description.trim() } : {}),
            duration_options: (service.duration_options?.length ? service.duration_options : [60]).sort((a, b) => a - b),
            levels_taught: service.levels_taught,
            ...(service.equipment
              ?.split(',')
              .map((v) => v.trim())
              .filter(Boolean)?.length
              ? { equipment_required: service.equipment.split(',').map((v) => v.trim()).filter(Boolean) }
              : {}),
            location_types: service.location_types?.length ? service.location_types : ['in_person'],
          })),
      };

      const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const msg = (await res.json().catch(() => ({}))) as ApiErrorResponse;
        throw new Error(msg.detail || msg.message || 'Failed to save');
      }
      setError('');
    } catch (e: unknown) {
      logger.error('Failed to save services', e);
      setError(e instanceof Error ? e.message : 'Failed to save');
    } finally {
      setSvcSaving(false);
    }
  }, [profileLoaded, isInstructorLive, pricingFloors, selectedServices, serviceFloorViolations]);

  useEffect(() => {
    if (initialLoadRef.current) {
      initialLoadRef.current = false;
      return;
    }

    if (autoSaveTimeout.current) {
      clearTimeout(autoSaveTimeout.current);
    }

    autoSaveTimeout.current = setTimeout(() => {
      void handleSave();
    }, 1200);

    return () => {
      if (autoSaveTimeout.current) {
        clearTimeout(autoSaveTimeout.current);
        autoSaveTimeout.current = null;
      }
    };
  }, [selectedServices, handleSave]);

  return (
    <div className={className}>
      {error && (
        <div className="mb-3 rounded-md border border-red-200 bg-red-50 p-2 text-sm text-red-700">{error}</div>
      )}
      {svcLoading ? (
        <div className="p-3 text-sm text-gray-600">Loading…</div>
      ) : (
        <>
          {/* Categories and search (expandable) */}
          <div className="rounded-lg border border-gray-200 bg-white p-4 mb-6">
            <div className="flex items-center gap-3 text-lg font-semibold text-gray-900 mb-2">
              <div className="w-10 h-10 rounded-full bg-purple-100 flex items-center justify-center">
                <svg className="w-5 h-5 text-[#7E22CE]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6v12m6-6H6" /></svg>
              </div>
              <span>Service categories</span>
            </div>
            <p className="text-gray-600 mb-2 text-sm">Select the service categories you teach</p>
            <div className="mb-3">
              <input
                type="text"
                value={skillsFilter}
                onChange={(e) => setSkillsFilter(e.target.value)}
                placeholder="Search skills..."
                className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0]"
              />
            </div>
            {/* Selected chips */}
            {selectedServices.length > 0 && (
              <div className="mb-4 flex flex-wrap gap-2">
                {selectedServices.map((s) => (
                  <span key={`sel-${s.catalog_service_id}`} className="inline-flex items-center gap-2 rounded-full border border-gray-300 bg-white px-3 h-8 text-xs min-w-0">
                    <span className="truncate max-w-[14rem]" title={s.name || s.service_catalog_name || ''}>{s.name || s.service_catalog_name}</span>
                    <button
                      type="button"
                      aria-label={`Remove ${s.name || s.service_catalog_name}`}
                      title={!canRemoveSkill() ? 'Live instructors must have at least one skill' : `Remove ${s.name || s.service_catalog_name}`}
                      className={`ml-auto rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center ${
                        !canRemoveSkill()
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
            {/* Accordions */}
            <div className="space-y-3">
              {categories.map((cat) => (
                <div key={cat.slug} className="rounded-lg overflow-hidden border border-gray-200 bg-white">
                  <button
                    className="w-full px-4 py-3 flex items-center justify-between text-gray-700 hover:bg-gray-50 transition-colors"
                    onClick={() => toggleCategory(cat.slug)}
                    type="button"
                  >
                    <span className="font-bold">{cat.name}</span>
                    <ChevronDown className={`h-4 w-4 text-gray-600 transition-transform ${collapsed[cat.slug] ? '' : 'rotate-180'}`} />
                  </button>
                  {!collapsed[cat.slug] && (
                    <div className="p-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                      {(servicesByCategory[cat.slug] || [])
                        .filter((svc) => (skillsFilter ? (svc.name || '').toLowerCase().includes(skillsFilter.toLowerCase()) : true))
                        .map((svc) => {
                          const isSel = selectedServices.some((s) => s.catalog_service_id === svc.id);
                          return (
                            <button
                              key={svc.id}
                              onClick={() => toggleServiceSelection(svc)}
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
              ))}
            </div>
          </div>

          {/* Your selected skills (detailed cards) */}
          <div className="space-y-4">
            {selectedServices.map((s, index) => (
              <div key={`${s.catalog_service_id || s.name}-${index}`} className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <div className="text-base font-medium text-gray-900">{s.service_catalog_name ?? s.name ?? 'Service'}</div>
                    <div className="flex items-center gap-1 mt-1">
                      <span className="text-xl font-bold text-[#7E22CE]">${s.hourly_rate || '0'}</span>
                      <span className="text-xs text-gray-600">/hour</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeService(s.catalog_service_id)}
                    title={!canRemoveSkill() ? 'Live instructors must have at least one skill' : 'Remove skill'}
                    className={`w-8 h-8 flex items-center justify-center rounded-full bg-white border transition-colors ${
                      !canRemoveSkill()
                        ? 'border-gray-200 text-gray-300 cursor-not-allowed'
                        : 'border-gray-300 text-gray-600 hover:bg-red-50 hover:text-red-600 hover:border-red-300'
                    }`}
                    aria-label="Remove skill"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
                  </button>
                </div>

                <div className="rounded-lg bg-white p-3 border border-gray-200 mb-3">
                  <div className="grid grid-cols-[auto_1fr_auto] items-center gap-2">
                    <span className="text-sm text-gray-600">Hourly Rate:</span>
                    <div className="relative max-w-[220px]">
                      <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                      <input
                        type="number"
                        placeholder="Hourly rate"
                        value={s.hourly_rate}
                        onChange={(e) => setSelectedServices((prev) => prev.map((x, i) => i === index ? { ...x, hourly_rate: e.target.value } : x))}
                        className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500"
                        min="0"
                        step="0.01"
                        required
                      />
                    </div>
                    <span className="text-sm text-gray-600">/hr</span>
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
                            onClick={() => setSelectedServices((prev) => prev.map((x, i) => {
                              if (i !== index) return x;
                              const cur = x.ageGroup;
                              let next: 'kids' | 'adults' | 'both';
                              if (cur === 'both') next = ageType === 'kids' ? 'adults' : 'kids';
                              else if (cur === ageType) next = ageType === 'kids' ? 'adults' : 'kids';
                              else next = 'both';
                              return { ...x, ageGroup: next };
                            }))}
                            className={`flex-1 px-2 py-2 text-sm rounded-md transition-colors ${isSel ? 'bg-purple-100 text-[#7E22CE] border border-purple-300' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
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
                      {(['in_person', 'online'] as const).map((loc) => (
                        <button
                          key={loc}
                          onClick={() => setSelectedServices((prev) => prev.map((x, i) => {
                            if (i !== index) return x;
                            const has = x.location_types.includes(loc);
                            const other = loc === 'in_person' ? 'online' : 'in_person';
                            if (has && x.location_types.length === 1) return { ...x, location_types: [other] };
                            return { ...x, location_types: has ? x.location_types.filter((v) => v !== loc) : [...x.location_types, loc] };
                          }))}
                          className={`flex-1 px-2 py-2 text-sm rounded-md transition-colors ${
                            s.location_types.includes(loc) ? 'bg-purple-100 text-[#7E22CE] border border-purple-300' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                          }`}
                          type="button"
                        >
                          {loc === 'in_person' ? 'In-Person' : 'Online'}
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
                          onClick={() => setSelectedServices((prev) => prev.map((x, i) => i === index ? { ...x, levels_taught: x.levels_taught.includes(lvl) ? x.levels_taught.filter((v) => v !== lvl) : [...x.levels_taught, lvl] } : x))}
                          className={`flex-1 px-2 py-2 text-sm rounded-md transition-colors ${
                            s.levels_taught.includes(lvl) ? 'bg-purple-100 text-[#7E22CE] border border-purple-300' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
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
                          onClick={() => setSelectedServices((prev) => prev.map((x, i) => {
                            if (i !== index) return x;
                            const has = x.duration_options.includes(d);
                            if (has && x.duration_options.length === 1) return x;
                            return { ...x, duration_options: has ? x.duration_options.filter((v) => v !== d) : [...x.duration_options, d] };
                          }))}
                          className={`flex-1 px-2 py-2 text-sm rounded-md transition-colors ${
                            s.duration_options.includes(d) ? 'bg-purple-100 text-[#7E22CE] border border-purple-300' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
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
                      onChange={(e) => setSelectedServices((prev) => prev.map((x, i) => i === index ? { ...x, description: e.target.value } : x))}
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-1 block">Equipment (Optional)</label>
                    <textarea
                      rows={2}
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500 bg-white"
                      placeholder="Yoga mat, tennis racket..."
                      value={s.equipment || ''}
                      onChange={(e) => setSelectedServices((prev) => prev.map((x, i) => i === index ? { ...x, equipment: e.target.value } : x))}
                    />
                  </div>
                </div>
              </div>
            ))}

            {selectedServices.length === 0 && (
              <div className="text-center py-8 text-gray-500">
                <p>No services added yet. Add your first service above!</p>
              </div>
            )}
          </div>

          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-full bg-purple-100 dark:bg-gray-800 text-[#7E22CE]">
                <Lightbulb className="h-5 w-5" aria-hidden="true" />
              </div>
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">Don&apos;t see your skill? We&apos;d love to add it!</p>
                <p className="text-xs text-gray-600 dark:text-gray-300">Tell us what you teach and we&apos;ll consider adding it to the marketplace.</p>
              </div>
            </div>
            <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-center">
              <input
                type="text"
                value={requestedSkill}
                onChange={(e) => {
                  setRequestedSkill(e.target.value);
                  if (requestSuccess) setRequestSuccess(null);
                }}
                placeholder="Request a new skill"
                className="w-full min-w-[220px] rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900/60 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/30 focus:border-[#7E22CE]"
              />
              <button
                type="button"
                onClick={() => { void handleRequestSkill(); }}
                disabled={!requestedSkill.trim() || requestSubmitting}
                className="inline-flex items-center justify-center rounded-lg bg-[#7E22CE] px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-[#6d1fc3] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {requestSubmitting ? 'Sending…' : 'Submit'}
              </button>
            </div>
          </div>
          {requestSuccess && <p className="mt-2 text-xs text-gray-700 dark:text-gray-200">{requestSuccess}</p>}
          {svcSaving && (
            <p className="mt-3 text-xs text-gray-500">Saving changes…</p>
          )}
        </>
      )}
    </div>
  );
}
