"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { DollarSign, ChevronDown, Lightbulb } from 'lucide-react';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { extractApiErrorMessage } from '@/lib/apiErrors';
import { logger } from '@/lib/logger';
import { submitSkillRequest } from '@/lib/api/skillRequest';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { hydrateCatalogNameById, displayServiceName } from '@/lib/instructorServices';
import { usePricingConfig } from '@/lib/pricing/usePricingFloors';
import { formatPlatformFeeLabel, resolvePlatformFeeRate, resolveTakeHomePct } from '@/lib/pricing/platformFees';
import { evaluatePriceFloorViolations, formatCents, type FloorViolation } from '@/lib/pricing/priceFloors';
import { useServiceCategories, useAllServicesWithInstructors } from '@/hooks/queries/useServices';
import { useInstructorProfileMe } from '@/hooks/queries/useInstructorProfileMe';
import { usePlatformFees } from '@/hooks/usePlatformConfig';
import type { ApiErrorResponse, CategoryServiceDetail, InstructorProfileResponse, ServiceCategory } from '@/features/shared/api/types';
import type { ServiceLocationType } from '@/types/instructor';
import {
  ALL_AUDIENCE_GROUPS,
  AUDIENCE_LABELS,
  DEFAULT_SKILL_LEVELS,
  defaultFilterSelections,
  normalizeAudienceGroups,
  normalizeFilterSelections,
  normalizeSkillLevels,
} from '@/lib/taxonomy/filterHelpers';
import type { AudienceGroup, FilterSelections } from '@/lib/taxonomy/filterHelpers';
import { RefineFiltersSection } from '@/components/taxonomy/RefineFiltersSection';
import { queryKeys } from '@/src/api/queryKeys';
import { ToggleSwitch } from '@/components/ui/ToggleSwitch';
import { toast } from 'sonner';

type SelectedService = {
  catalog_service_id: string;
  subcategory_id: string;
  service_catalog_name?: string | null;
  name?: string | null;
  hourly_rate: string;
  eligible_age_groups: AudienceGroup[];
  filter_selections: FilterSelections;
  description?: string;
  equipment?: string;
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

interface Props {
  className?: string;
  /** Pre-fetched instructor profile to avoid duplicate API calls */
  instructorProfile?: InstructorProfileResponse | null;
}

export default function SkillsPricingInline({ className, instructorProfile }: Props) {
  const { user } = useAuth();
  const [categories, setCategories] = useState<ServiceCategory[]>([]);
  const [servicesByCategory, setServicesByCategory] = useState<Record<string, CategoryServiceDetail[]>>({});
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [refineExpandedByService, setRefineExpandedByService] = useState<Record<string, boolean>>({});
  const [selectedServices, setSelectedServices] = useState<SelectedService[]>([]);
  const queryClient = useQueryClient();
  const [svcLoading, setSvcLoading] = useState(false);
  const [svcSaving, setSvcSaving] = useState(false);
  const [error, setError] = useState('');
  const [priceErrors, setPriceErrors] = useState<Record<string, string>>({});
  // Default to true (assume live) until we confirm otherwise - safer default
  const [isInstructorLive, setIsInstructorLive] = useState(true);
  const [profileLoaded, setProfileLoaded] = useState(false);
  const { config: pricingConfig, isLoading: pricingConfigLoading } = usePricingConfig();
  const { fees } = usePlatformFees();
  const pricingFloors = pricingConfig?.price_floor_cents ?? null;

  // Use React Query hooks for service data (prevents duplicate API calls)
  const { data: categoriesData, isLoading: categoriesLoading } = useServiceCategories();
  const { data: allServicesData, isLoading: allServicesLoading } = useAllServicesWithInstructors();
  // Use React Query hook for instructor profile when prop not provided (prevents duplicate API calls)
  const { data: profileFromHook } = useInstructorProfileMe(!instructorProfile);
  const profileData = instructorProfile ?? profileFromHook;
  const hasServiceAreas = useMemo(() => {
    if (!profileData) return false;
    const neighborhoods = Array.isArray(profileData.service_area_neighborhoods)
      ? profileData.service_area_neighborhoods
      : [];
    const boroughs = Array.isArray(profileData.service_area_boroughs)
      ? profileData.service_area_boroughs
      : [];
    const summary =
      typeof profileData.service_area_summary === 'string'
        ? profileData.service_area_summary
        : '';
    return (
      neighborhoods.length > 0 || boroughs.length > 0 || summary.trim().length > 0
    );
  }, [profileData]);
  const hasTeachingLocations = useMemo(() => {
    if (!profileData) return false;
    const teaching = Array.isArray(profileData.preferred_teaching_locations)
      ? profileData.preferred_teaching_locations
      : [];
    return teaching.length > 0;
  }, [profileData]);

  // Build lookup map from allServicesData for catalog enrichment
  const serviceCatalogById = useMemo(() => {
    const map = new Map<string, { subcategory_id: string; eligible_age_groups: AudienceGroup[] }>();
    if (!allServicesData) return map;
    for (const cat of allServicesData.categories ?? []) {
      for (const svc of cat.services ?? []) {
        const eligible = normalizeAudienceGroups(
          svc.eligible_age_groups,
          ['kids', 'teens', 'adults']
        );
        map.set(svc.id, { subcategory_id: svc.subcategory_id, eligible_age_groups: eligible });
      }
    }
    return map;
  }, [allServicesData]);

  const [skillsFilter, setSkillsFilter] = useState('');
  const [requestedSkill, setRequestedSkill] = useState('');
  const [requestSubmitting, setRequestSubmitting] = useState(false);
  const [requestSuccess, setRequestSuccess] = useState<string | null>(null);
  const initialLoadRef = useRef(true);
  const autoSaveTimeout = useRef<NodeJS.Timeout | null>(null);
  const hasLocalEditsRef = useRef(false);
  const isHydratingRef = useRef(false);
  const isEditingRef = useRef(false);
  const pendingSyncSignatureRef = useRef<string | null>(null);
  const lastLocalSignatureRef = useRef<string>('');
  // FIX 1: Use ref for priceErrors to avoid dependency cycle in handleSave
  // handleSave reads priceErrors but also SETS it, causing infinite re-renders
  const priceErrorsRef = useRef<Record<string, string>>({});
  // FIX 4: Use ref for handleSave to remove it from autosave effect dependencies
  // This prevents the effect from firing twice (once for selectedServices, once for handleSave)
  const handleSaveRef = useRef<((source: 'auto' | 'manual') => Promise<void>) | null>(null);
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

  const serviceFloorViolations = useMemo(() => {
    const map = new Map<string, FloorViolation[]>();
    if (!pricingFloors) {
      logger.debug('SkillsPricingInline: serviceFloorViolations memo - no pricing floors');
      return map;
    }
    selectedServices.forEach((service) => {
      const locationTypes = locationTypesFromCapabilities(service);
      if (!locationTypes.length) {
        logger.debug('SkillsPricingInline: serviceFloorViolations memo - no location types', {
          serviceId: service.catalog_service_id,
        });
        return;
      }
      const hourlyRate = Number(service.hourly_rate);
      const violations = evaluatePriceFloorViolations({
        hourlyRate,
        durationOptions: service.duration_options ?? [60],
        locationTypes,
        floors: pricingFloors,
      });
      logger.debug('SkillsPricingInline: serviceFloorViolations memo - evaluated', {
        serviceId: service.catalog_service_id,
        hourlyRate,
        locationTypes,
        durationOptions: service.duration_options,
        violationsCount: violations.length,
        violations,
      });
      if (violations.length > 0) map.set(service.catalog_service_id, violations);
    });
    return map;
  }, [pricingFloors, selectedServices]);

  const buildPriceFloorErrors = useCallback(() => {
    const next: Record<string, string> = {};
    if (!pricingFloors) return next;
    serviceFloorViolations.forEach((violations, serviceId) => {
      const violation = violations?.[0];
      if (!violation) return;
      const serviceName =
        selectedServices.find((s) => s.catalog_service_id === serviceId)?.name || 'this service';
      next[serviceId] =
        `Minimum price for a ${violation.modalityLabel} ${violation.duration}-minute private session ` +
        `is $${formatCents(violation.floorCents)} (current $${formatCents(violation.baseCents)}). ` +
        `Please adjust the rate for ${serviceName}.`;
    });
    return next;
  }, [pricingFloors, serviceFloorViolations, selectedServices]);

  const serializeServices = useCallback((services: SelectedService[]) => {
    return JSON.stringify(
      services
        .map((service) => ({
          id: service.catalog_service_id,
          hourly_rate: service.hourly_rate.trim(),
          offers_travel: service.offers_travel,
          offers_at_location: service.offers_at_location,
          offers_online: service.offers_online,
          duration_options: [...service.duration_options].sort((a, b) => a - b),
          filter_selections: Object.fromEntries(
            Object.entries(service.filter_selections).map(([k, v]) => [k, [...v].sort()])
          ),
          description: (service.description ?? '').trim(),
          equipment: (service.equipment ?? '').trim(),
        }))
        .sort((a, b) => a.id.localeCompare(b.id))
    );
  }, []);

  const setSelectedServicesWithDirty = useCallback((updater: (prev: SelectedService[]) => SelectedService[]) => {
    hasLocalEditsRef.current = true;
    isEditingRef.current = true;
    pendingSyncSignatureRef.current = null;
    setSelectedServices(updater);
  }, []);

  const setServiceFilterValues = useCallback(
    (serviceId: string, filterKey: string, values: string[]) => {
      setSelectedServicesWithDirty((prev) =>
        prev.map((s) =>
          s.catalog_service_id === serviceId
            ? { ...s, filter_selections: { ...s.filter_selections, [filterKey]: values } }
            : s
        )
      );
    },
    [setSelectedServicesWithDirty]
  );

  const initializeMissingFilters = useCallback(
    (serviceId: string, defaults: FilterSelections) => {
      setSelectedServices((prev) =>
        prev.map((s) => {
          if (s.catalog_service_id !== serviceId) return s;
          const merged = { ...s.filter_selections };
          let changed = false;
          for (const [key, values] of Object.entries(defaults)) {
            if (!merged[key]) {
              merged[key] = values;
              changed = true;
            }
          }
          return changed ? { ...s, filter_selections: merged } : s;
        })
      );
    },
    []
  );

  const toggleRefineExpanded = useCallback(
    (serviceId: string) => {
      setRefineExpandedByService((prev) => ({
        ...prev,
        [serviceId]: !prev[serviceId],
      }));
    },
    []
  );

  // FIX 1 (continued): Sync priceErrors ref when state changes
  useEffect(() => {
    priceErrorsRef.current = priceErrors;
  }, [priceErrors]);

  // Sync loading state with React Query hooks
  useEffect(() => {
    setSvcLoading(categoriesLoading || allServicesLoading);
  }, [categoriesLoading, allServicesLoading]);

  // Process service categories and services data from hooks
  useEffect(() => {
    if (categoriesData) {
      setCategories(categoriesData);
      const initCollapsed: Record<string, boolean> = {};
      for (const c of categoriesData) initCollapsed[c.id] = true;
      setCollapsed(initCollapsed);
    }
  }, [categoriesData]);

  useEffect(() => {
    if (allServicesData) {
      const map: Record<string, CategoryServiceDetail[]> = {};
      const categories = allServicesData.categories ?? [];
      for (const c of categories) {
        const services = c.services ?? [];
        const deduped = Array.from(new Map(services.map((svc) => [svc.id, svc])).values());
        map[c.id] = deduped;
      }
      setServicesByCategory(map);
    }
  }, [allServicesData]);

  // Load instructor profile (prefilled services) - uses prop or React Query hook data
  useEffect(() => {
    // Use prop if provided, otherwise use hook data
    const profileData = instructorProfile ?? profileFromHook;
    if (!profileData) return;

    if (isEditingRef.current) {
      return;
    }

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
        const capabilities = resolveCapabilitiesFromService(s);
        const catalogId = String(s['service_catalog_id'] || '');
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
        const catalogEntry = serviceCatalogById.get(catalogId);
        const eligibleAgeGroups = catalogEntry?.eligible_age_groups ?? ['kids', 'teens', 'adults'];

        // Build filter_selections from API response
        const rawFilterSelections = normalizeFilterSelections(s['filter_selections']);
        // Populate age_groups from top-level API field into filter_selections
        const ageGroupsFromApi = normalizeAudienceGroups(s['age_groups'], eligibleAgeGroups);
        // Populate skill_level — read from filter_selections first, fallback to all levels
        const skillLevels = normalizeSkillLevels(rawFilterSelections['skill_level']);

        const mergedFilters: FilterSelections = {
          ...rawFilterSelections,
          age_groups: ageGroupsFromApi,
          skill_level: skillLevels,
        };

        return {
          catalog_service_id: catalogId,
          subcategory_id: catalogEntry?.subcategory_id ?? '',
          service_catalog_name:
            typeof s['service_catalog_name'] === 'string'
              ? (s['service_catalog_name'] as string)
              : null,
          name: serviceName,
          hourly_rate: String(s['hourly_rate'] ?? ''),
          eligible_age_groups: eligibleAgeGroups,
          filter_selections: mergedFilters,
          description: (s['description'] as string) || '',
          equipment: Array.isArray(s['equipment_required'])
            ? (s['equipment_required'] as string[]).join(', ')
            : '',
          duration_options:
            Array.isArray(s['duration_options']) && (s['duration_options'] as number[]).length
              ? (s['duration_options'] as number[])
              : [60],
          offers_travel: hasServiceAreas ? capabilities.offers_travel : false,
          offers_at_location: hasTeachingLocations ? capabilities.offers_at_location : false,
          offers_online: capabilities.offers_online,
        } satisfies SelectedService;
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
      const incomingSignature = serializeServices(deduped);

      // FIX 6: Check if this is our own save returning
      // If pendingSyncSignatureRef matches, this is our save - clear editing state and accept
      if (pendingSyncSignatureRef.current && incomingSignature === pendingSyncSignatureRef.current) {
        logger.debug('SkillsPricingInline: hydration matches pending save, accepting', {
          matchedSignature: true,
        });
        pendingSyncSignatureRef.current = null;
        hasLocalEditsRef.current = false;
        isEditingRef.current = false; // FIX 6: Clear editing state now that our save is confirmed
        isHydratingRef.current = true;
        setSelectedServices(deduped);
        return;
      }

      // If user has local edits and incoming doesn't match, don't overwrite
      if (hasLocalEditsRef.current || isEditingRef.current) {
        const localSignature = lastLocalSignatureRef.current;
        if (localSignature === incomingSignature) {
          // Incoming matches local - no change needed, just clear flags
          hasLocalEditsRef.current = false;
          isEditingRef.current = false;
          return;
        }
        // Incoming differs from local - don't overwrite user edits
        logger.debug('SkillsPricingInline: hydration blocked - user has local edits', {
          hasLocalEdits: hasLocalEditsRef.current,
          isEditing: isEditingRef.current,
        });
        return;
      }

      isHydratingRef.current = true;
      hasLocalEditsRef.current = false;
      setSelectedServices(deduped);
    }
  }, [
    hasServiceAreas,
    hasTeachingLocations,
    instructorProfile,
    profileFromHook,
    resolveCapabilitiesFromService,
    serializeServices,
    serviceCatalogById,
  ]);

  // FIX 3: Effect #5 - Capability cleanup when service areas/teaching locations removed
  // This is a system-initiated change, not a user edit. Mark as hydrating to prevent
  // autosave effect from treating it as a user change that needs saving.
  useEffect(() => {
    if (hasServiceAreas && hasTeachingLocations) return;
    // Mark as hydrating so autosave effect skips this change
    isHydratingRef.current = true;
    setSelectedServices((prev) => {
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

  // Back-fill subcategory_id, eligible_age_groups, and default filter_selections
  // from catalog when taxonomy data loads after profile hydration.
  useEffect(() => {
    if (serviceCatalogById.size === 0 || selectedServices.length === 0) return;
    let changed = false;
    const next = selectedServices.map((svc) => {
      const entry = serviceCatalogById.get(svc.catalog_service_id);
      if (!entry) return svc;
      let updated = svc;
      if (!updated.subcategory_id && entry.subcategory_id) {
        updated = { ...updated, subcategory_id: entry.subcategory_id };
        changed = true;
      }
      if (updated.eligible_age_groups.length === 0) {
        updated = { ...updated, eligible_age_groups: entry.eligible_age_groups };
        changed = true;
      }
      // Ensure skill_level and age_groups defaults exist in filter_selections
      if (!updated.filter_selections['skill_level'] || !updated.filter_selections['age_groups']) {
        const defaults = defaultFilterSelections(updated.eligible_age_groups);
        const merged = { ...updated.filter_selections };
        if (!merged['skill_level']) merged['skill_level'] = defaults['skill_level'] ?? [...DEFAULT_SKILL_LEVELS];
        if (!merged['age_groups']) merged['age_groups'] = defaults['age_groups'] ?? [...ALL_AUDIENCE_GROUPS];
        updated = { ...updated, filter_selections: merged };
        changed = true;
      }
      return updated;
    });
    if (changed) {
      isHydratingRef.current = true;
      setSelectedServices(next);
    }
  }, [serviceCatalogById, selectedServices]);

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
    setSelectedServicesWithDirty((prev) => prev.filter((s) => s.catalog_service_id !== catalogServiceId));
  }, [canRemoveSkill, profileLoaded, isInstructorLive, selectedServices.length, setSelectedServicesWithDirty]);

  const toggleServiceSelection = (svc: CategoryServiceDetail) => {
    setSelectedServicesWithDirty((prev) => {
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
      const catalogEntry = serviceCatalogById.get(svc.id);
      const eligibleAgeGroups = catalogEntry?.eligible_age_groups ?? ['kids', 'teens', 'adults'] as AudienceGroup[];
      return [
        ...prev,
        {
          catalog_service_id: svc.id,
          subcategory_id: catalogEntry?.subcategory_id ?? '',
          service_catalog_name: svc.name,
          name: label,
          hourly_rate: '',
          eligible_age_groups: eligibleAgeGroups,
          filter_selections: defaultFilterSelections(eligibleAgeGroups),
          description: '',
          equipment: '',
          duration_options: [60],
          ...defaultCapabilities(),
        },
      ];
    });
  };

  const handleRequestSkill = useCallback(async () => {
    if (!requestedSkill.trim()) return;
    try {
      setRequestSubmitting(true);
      setRequestSuccess(null);
      await submitSkillRequest({
        skill_name: requestedSkill.trim(),
        instructor_id: profileData?.id ?? null,
        email: user?.email ?? null,
        first_name: user?.first_name ?? null,
        last_name: user?.last_name ?? null,
        is_founding_instructor: Boolean(profileData?.is_founding_instructor),
        is_live: Boolean(profileData?.is_live),
        source: 'profile_skills_inline',
      });
      setRequestSuccess("Thanks! We'll review and consider adding this skill.");
      setRequestedSkill('');
    } catch {
      setRequestSuccess('Something went wrong. Please try again.');
    } finally {
      setRequestSubmitting(false);
    }
  }, [requestedSkill, profileData, user]);

  const handleSave = useCallback(async (source: 'auto' | 'manual' = 'auto') => {
    try {
      setSvcSaving(true);
      // FIX 2: Don't clear isEditingRef at start - only after successful save
      // This prevents hydration from overwriting user edits during save

      // Safeguard: Don't save if profile hasn't loaded (we don't know if instructor is live)
      if (!profileLoaded) {
        logger.warn('SkillsPricingInline: Skipping save - profile not loaded yet');
        setSvcSaving(false);
        return;
      }

      // FIX 9: Don't save if pricing config is still loading - we need it for floor validation
      if (pricingConfigLoading) {
        logger.warn('SkillsPricingInline: Skipping save - pricing config still loading');
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

      // FIX 8: Add comprehensive logging to debug price floor validation
      logger.debug('SkillsPricingInline: price floor validation check', {
        source,
        hasPricingFloors: Boolean(pricingFloors),
        pricingFloors,
        violationsSize: serviceFloorViolations.size,
        violations: Array.from(serviceFloorViolations.entries()).map(([id, v]) => ({ id, violations: v })),
        services: selectedServices.map((s) => ({
          id: s.catalog_service_id,
          hourly_rate: s.hourly_rate,
          duration_options: s.duration_options,
          offers_travel: s.offers_travel,
          offers_at_location: s.offers_at_location,
          offers_online: s.offers_online,
        })),
      });

      if (pricingFloors && serviceFloorViolations.size > 0) {
        const nextPriceErrors = buildPriceFloorErrors();
        const firstError = Object.values(nextPriceErrors)[0];
        if (firstError) {
          logger.debug('SkillsPricingInline: price floor violation detected, blocking save', {
            source,
            violationCount: serviceFloorViolations.size,
            firstError,
          });
          setPriceErrors(nextPriceErrors);
          // FIX 7: Show toast for ALL saves (not just manual) so user sees feedback
          toast.error(firstError, { id: 'price-floor-error' });
          setSvcSaving(false);
          return;
        }
      }
      // FIX 1: Read from ref to avoid dependency cycle
      const currentPriceErrors = priceErrorsRef.current;
      if (currentPriceErrors && Object.keys(currentPriceErrors).length > 0) {
        setPriceErrors({});
      }

      const hasInvalidCapabilities = selectedServices.some((service) =>
        !hasAnyLocationOption({
          offers_travel: hasServiceAreas ? service.offers_travel : false,
          offers_at_location: hasTeachingLocations ? service.offers_at_location : false,
          offers_online: service.offers_online,
        })
      );
      if (hasInvalidCapabilities) {
        setSvcSaving(false);
        return;
      }

      const payload = {
        services: selectedServices
          .filter((service) => service.hourly_rate.trim() !== '')
          .map((service) => {
            // Build filter_selections for backend (without age_groups — sent separately)
            const { age_groups: _ageGroups, ...restFilters } = service.filter_selections;
            return {
              service_catalog_id: service.catalog_service_id || undefined,
              hourly_rate: Number(service.hourly_rate),
              age_groups: service.filter_selections['age_groups'] ?? [...service.eligible_age_groups],
              filter_selections: restFilters,
              ...(service.description?.trim() ? { description: service.description.trim() } : {}),
              duration_options: (service.duration_options?.length ? service.duration_options : [60]).sort((a, b) => a - b),
              ...(service.equipment
                ?.split(',')
                .map((v) => v.trim())
                .filter(Boolean)?.length
                ? { equipment_required: service.equipment.split(',').map((v) => v.trim()).filter(Boolean) }
                : {}),
              offers_travel: hasServiceAreas ? service.offers_travel : false,
              offers_at_location: hasTeachingLocations ? service.offers_at_location : false,
              offers_online: service.offers_online,
            };
          }),
      };

      const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const msg = (await res.json().catch(() => ({}))) as ApiErrorResponse;
        throw new Error(extractApiErrorMessage(msg, 'Failed to save'));
      }
      // FIX 6: Set pendingSyncSignatureRef BEFORE invalidation, and DON'T clear isEditingRef
      // The hydration effect will clear isEditingRef when it sees our save return
      logger.debug('SkillsPricingInline: save succeeded', {
        source,
        serviceCount: selectedServices.length,
      });
      pendingSyncSignatureRef.current = serializeServices(selectedServices);
      await queryClient.invalidateQueries({ queryKey: queryKeys.instructors.me });
      // DON'T clear isEditingRef here - let hydration effect clear it when signature matches
      // This prevents race condition where hydration runs before we're ready
      setError('');
    } catch (e: unknown) {
      logger.error('Failed to save services', e);
      const message = e instanceof Error ? e.message : 'Failed to save';
      if (isLocationCapabilityError(message)) {
        setError('');
        return;
      }
      setError(message);
    } finally {
      setSvcSaving(false);
    }
  }, [
    buildPriceFloorErrors,
    hasServiceAreas,
    hasTeachingLocations,
    profileLoaded,
    isInstructorLive,
    pricingConfigLoading, // FIX 9: Wait for pricing config before saving
    pricingFloors,
    // FIX 1: priceErrors removed - now read via priceErrorsRef to break dependency cycle
    queryClient,
    selectedServices,
    serviceFloorViolations,
    serializeServices,
  ]);

  // FIX 4 (continued): Keep handleSaveRef in sync with handleSave
  useEffect(() => {
    handleSaveRef.current = handleSave;
  }, [handleSave]);

  // Autosave effect - triggers save 1200ms after user changes
  // FIX 4: Removed handleSave from dependencies - use ref instead
  // This prevents double-firing when handleSave changes due to selectedServices dependency
  useEffect(() => {
    if (initialLoadRef.current) {
      initialLoadRef.current = false;
      if (isHydratingRef.current) {
        isHydratingRef.current = false;
        return;
      }
      // FIX 5: Don't set hasLocalEditsRef on initial mount with empty services
      // Only mark dirty if there are actually services (meaning user added something)
      if (selectedServices.length > 0) {
        hasLocalEditsRef.current = true;
      }
      return;
    }

    if (isHydratingRef.current) {
      isHydratingRef.current = false;
      return;
    }

    hasLocalEditsRef.current = true;

    if (autoSaveTimeout.current) {
      clearTimeout(autoSaveTimeout.current);
    }

    autoSaveTimeout.current = setTimeout(() => {
      // FIX 4: Call via ref to avoid dependency
      void handleSaveRef.current?.('auto');
    }, 1200);

    return () => {
      if (autoSaveTimeout.current) {
        clearTimeout(autoSaveTimeout.current);
        autoSaveTimeout.current = null;
      }
    };
  }, [selectedServices]); // FIX 4: handleSave removed from dependencies

  useEffect(() => {
    lastLocalSignatureRef.current = serializeServices(selectedServices);
  }, [selectedServices, serializeServices]);

  const showError = Boolean(error) && !isLocationCapabilityError(error);

  return (
    <div className={className}>
      {showError && (
        <div className="mb-3 rounded-md border border-red-200 bg-red-50 p-2 text-sm text-red-700">{error}</div>
      )}
      {svcLoading ? (
        <div className="p-3 text-sm text-gray-600">Loading…</div>
      ) : (
        <>
          {/* Categories and search (expandable) */}
          <div className="rounded-lg border border-gray-200 bg-white p-4 mb-6 insta-surface-card">
            <div className="flex items-center gap-3 text-xl sm:text-lg font-bold sm:font-semibold text-gray-900 mb-2">
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
                className="w-full rounded-md border border-gray-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0]"
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
                <div key={cat.id} className="rounded-lg overflow-hidden border border-gray-200 bg-white insta-surface-card">
                  <button
                    className="w-full px-4 py-3 flex items-center justify-between text-gray-700 hover:bg-gray-50 transition-colors"
                    onClick={() => toggleCategory(cat.id)}
                    type="button"
                  >
                    <span className="font-bold">{cat.name}</span>
                    <ChevronDown className={`h-4 w-4 text-gray-600 transition-transform ${collapsed[cat.id] ? '' : 'rotate-180'}`} />
                  </button>
                  {!collapsed[cat.id] && (
                    <div className="p-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                      {(servicesByCategory[cat.id] || [])
                        .filter((svc) => (skillsFilter ? (svc.name || '').toLowerCase().includes(skillsFilter.toLowerCase()) : true))
                        .map((svc) => {
                          const isSel = selectedServices.some((s) => s.catalog_service_id === svc.id);
                          return (
                            <button
                              key={svc.id}
                              onClick={() => toggleServiceSelection(svc)}
                              className={`inline-flex items-center justify-between px-3 py-1.5 text-sm rounded-full font-semibold transition-colors no-hover-shadow appearance-none overflow-hidden focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 ${
                                isSel ? 'bg-[#7E22CE] text-white border border-[#7E22CE] hover:bg-[#7E22CE]' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                              }`}
                              type="button"
                            >
                              <span className="truncate text-left">{svc.name}</span>
                              <span className="ml-2">{isSel ? '✓' : '+'}</span>
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
            {selectedServices.map((s, index) => {
              const effectiveOffersTravel = hasServiceAreas ? s.offers_travel : false;
              const effectiveOffersAtLocation = hasTeachingLocations ? s.offers_at_location : false;
              const priceError = priceErrors[s.catalog_service_id];
              const effectiveCapabilities: ServiceCapabilities = {
                offers_travel: effectiveOffersTravel,
                offers_at_location: effectiveOffersAtLocation,
                offers_online: s.offers_online,
              };

              return (
                <div
                  key={`${s.catalog_service_id || s.name}-${index}`}
                  className="p-4 bg-gray-50 border border-gray-200 rounded-lg insta-surface-card"
                >
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

                <div className="rounded-lg bg-white p-3 border border-gray-200 mb-3 insta-surface-card">
                  <div className="grid grid-cols-[auto_1fr_auto] items-center gap-2">
                    <span className="text-sm text-gray-600">Hourly Rate:</span>
                    <div className="relative max-w-[220px]">
                      <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                      <input
                        type="number"
                        placeholder="Hourly rate"
                        value={s.hourly_rate}
                        onChange={(e) => {
                          const nextValue = e.target.value;
                          setSelectedServicesWithDirty((prev) =>
                            prev.map((x, i) => (i === index ? { ...x, hourly_rate: nextValue } : x))
                          );
                          if (priceError) {
                            setPriceErrors((prev) => {
                              if (!prev[s.catalog_service_id]) return prev;
                              const next = { ...prev };
                              delete next[s.catalog_service_id];
                              return next;
                            });
                          }
                        }}
                        // FIX 2: Removed onBlur that cleared isEditingRef
                        // isEditingRef stays true until save succeeds, protecting against hydration overwrite
                        className={`w-full pl-9 pr-3 py-2 border rounded-lg focus:outline-none focus:ring-2 ${
                          priceError
                            ? 'border-red-500 focus:ring-red-200 focus:border-red-500'
                            : 'border-gray-300 focus:ring-[#D4B5F0] focus:border-purple-500'
                        }`}
                        aria-invalid={priceError ? 'true' : 'false'}
                        min="0"
                        step="0.01"
                        required
                      />
                    </div>
                  </div>
                  {priceError && (
                    <p className="mt-1 text-xs text-red-600">{priceError}</p>
                  )}
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
                  <div className="bg-white rounded-lg p-3 border border-gray-200 insta-surface-card">
                    <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Age Groups</label>
                    <div className="grid grid-cols-2 gap-1">
                      {ALL_AUDIENCE_GROUPS.map((group) => {
                        const selectedAgeGroups = s.filter_selections['age_groups'] ?? [];
                        const isSelected = selectedAgeGroups.includes(group);
                        const isEligible = s.eligible_age_groups.includes(group);
                        return (
                          <button
                            key={group}
                            disabled={!isEligible}
                            onClick={() => {
                              if (!isEligible) return;
                              setSelectedServicesWithDirty((prev) => prev.map((x, i) => {
                                if (i !== index) return x;
                                const current = x.filter_selections['age_groups'] ?? [];
                                const next = isSelected
                                  ? current.filter((g) => g !== group)
                                  : [...current, group];
                                // Min-1 guard: can't deselect last age group
                                if (next.length === 0) return x;
                                return {
                                  ...x,
                                  filter_selections: { ...x.filter_selections, age_groups: next },
                                };
                              }));
                            }}
                            className={`px-2 py-2 text-sm rounded-md transition-colors ${
                              !isEligible
                                ? 'bg-gray-50 text-gray-300 cursor-not-allowed'
                                : isSelected
                                ? 'bg-purple-100 text-[#7E22CE] border border-purple-300'
                                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                            }`}
                            type="button"
                          >
                            {AUDIENCE_LABELS[group]}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <div className="bg-white rounded-lg p-3 border border-gray-200 insta-surface-card">
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
                                    setSelectedServicesWithDirty((prev) =>
                                      prev.map((x, i) =>
                                        i === index ? { ...x, offers_travel: !x.offers_travel } : x
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
                                    setSelectedServicesWithDirty((prev) =>
                                      prev.map((x, i) =>
                                        i === index ? { ...x, offers_at_location: !x.offers_at_location } : x
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
                                    setSelectedServicesWithDirty((prev) =>
                                      prev.map((x, i) =>
                                        i === index ? { ...x, offers_online: !x.offers_online } : x
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
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                  <div className="bg-white rounded-lg p-3 border border-gray-200 insta-surface-card">
                    <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Skill Levels</label>
                    <div className="flex gap-1">
                      {DEFAULT_SKILL_LEVELS.map((lvl) => {
                        const selectedLevels = s.filter_selections['skill_level'] ?? [...DEFAULT_SKILL_LEVELS];
                        const isLvlSelected = selectedLevels.includes(lvl);
                        return (
                          <button
                            key={lvl}
                            onClick={() => setSelectedServicesWithDirty((prev) => prev.map((x, i) => {
                              if (i !== index) return x;
                              const current = x.filter_selections['skill_level'] ?? [...DEFAULT_SKILL_LEVELS];
                              const next = isLvlSelected
                                ? current.filter((v) => v !== lvl)
                                : [...current, lvl];
                              // Min-1 guard: can't deselect last level
                              if (next.length === 0) return x;
                              return {
                                ...x,
                                filter_selections: { ...x.filter_selections, skill_level: next },
                              };
                            }))}
                            className={`flex-1 px-2 py-2 text-sm rounded-md transition-colors ${
                              isLvlSelected ? 'bg-purple-100 text-[#7E22CE] border border-purple-300' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                            }`}
                            type="button"
                          >
                            {lvl === 'beginner' ? 'Beginner' : lvl === 'intermediate' ? 'Intermediate' : 'Advanced'}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <div className="bg-white rounded-lg p-3 border border-gray-200 insta-surface-card">
                    <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">Session Duration</label>
                    <div className="flex gap-1">
                      {[30, 45, 60, 90].map((d) => (
                        <button
                          key={d}
                          onClick={() => setSelectedServicesWithDirty((prev) => prev.map((x, i) => {
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

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                  <div>
                    <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-1 block">Description (Optional)</label>
                    <textarea
                      rows={2}
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500 bg-white"
                      placeholder="Brief description of your teaching style..."
                      value={s.description || ''}
                      onChange={(e) => setSelectedServicesWithDirty((prev) => prev.map((x, i) => i === index ? { ...x, description: e.target.value } : x))}
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-1 block">Equipment (Optional)</label>
                    <textarea
                      rows={2}
                      className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500 bg-white"
                      placeholder="Yoga mat, tennis racket..."
                      value={s.equipment || ''}
                      onChange={(e) => setSelectedServicesWithDirty((prev) => prev.map((x, i) => i === index ? { ...x, equipment: e.target.value } : x))}
                    />
                  </div>
                </div>

                <RefineFiltersSection
                  service={s}
                  expanded={refineExpandedByService[s.catalog_service_id] ?? false}
                  onToggleExpanded={toggleRefineExpanded}
                  onInitializeMissingFilters={initializeMissingFilters}
                  onSetFilterValues={setServiceFilterValues}
                />
              </div>
              );
            })}

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
