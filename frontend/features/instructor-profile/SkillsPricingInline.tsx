"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ChevronDown, Lightbulb } from 'lucide-react';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { extractApiErrorMessage } from '@/lib/apiErrors';
import { logger } from '@/lib/logger';
import { submitSkillRequest } from '@/lib/api/skillRequest';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { hydrateCatalogNameById, displayServiceName } from '@/lib/instructorServices';
import { usePricingConfig } from '@/lib/pricing/usePricingFloors';
import { formatPlatformFeeLabel, resolvePlatformFeeRate, resolveTakeHomePct } from '@/lib/pricing/platformFees';
import { evaluateFormatPriceFloorViolations, formatCents, type FormatFloorViolation } from '@/lib/pricing/priceFloors';
import {
  defaultFormatPrices,
  formatPricesToPayload,
  getEmptyRateOffenders,
  getFirstFormatPriceValidationError,
  hasAnyFormatEnabled,
  getFormatPriceValidationErrors,
  payloadToFormatPriceState,
  type FormatPriceState,
  type ServiceFormat,
} from '@/lib/pricing/formatPricing';
import { FormatPricingCards } from '@/components/pricing/FormatPricingCards';
import { useServiceCategories, useAllServicesWithInstructors } from '@/hooks/queries/useServices';
import { useInstructorProfileMe } from '@/hooks/queries/useInstructorProfileMe';
import { usePlatformFees } from '@/hooks/usePlatformConfig';
import type { ApiErrorResponse, CategoryServiceDetail, InstructorProfileResponse, ServiceCategory } from '@/features/shared/api/types';
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
import { toast } from 'sonner';
import {
  applyPendingHydrationAcceptance,
  backfillSelectedServicesFromCatalog,
  getPendingHydrationAcceptance,
  type SelectedService,
} from './SkillsPricingInline.helpers';

/** Set of format keys that are currently enabled across all services. */
export type EnabledFormats = { student_location: boolean; instructor_location: boolean; online: boolean };

interface Props {
  className?: string;
  /** Pre-fetched instructor profile to avoid duplicate API calls */
  instructorProfile?: InstructorProfileResponse | null;
  /** Callback fired whenever the set of enabled formats changes across all services. */
  onFormatsChange?: ((formats: EnabledFormats) => void) | undefined;
}

export default function SkillsPricingInline({ className, instructorProfile, onFormatsChange }: Props) {
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
  const [priceErrors, setPriceErrors] = useState<Record<string, Partial<Record<ServiceFormat, string>>>>({});
  const [emptyRateErrors, setEmptyRateErrors] = useState<
    Record<string, Partial<Record<ServiceFormat, boolean>>>
  >({});
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
  const priceErrorsRef = useRef<Record<string, Partial<Record<ServiceFormat, string>>>>({});
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

  const serviceFloorViolations = useMemo(() => {
    const map = new Map<string, Map<ServiceFormat, FormatFloorViolation[]>>();
    if (!pricingFloors) {
      logger.debug('SkillsPricingInline: serviceFloorViolations memo - no pricing floors');
      return map;
    }
    selectedServices.forEach((service) => {
      if (!hasAnyFormatEnabled(service.format_prices)) {
        logger.debug('SkillsPricingInline: serviceFloorViolations memo - no formats enabled', {
          serviceId: service.catalog_service_id,
        });
        return;
      }
      const violations = evaluateFormatPriceFloorViolations({
        formatPrices: service.format_prices,
        durationOptions: service.duration_options,
        floors: pricingFloors,
      });
      logger.debug('SkillsPricingInline: serviceFloorViolations memo - evaluated', {
        serviceId: service.catalog_service_id,
        formatPrices: service.format_prices,
        durationOptions: service.duration_options,
        violationsSize: violations.size,
      });
      if (violations.size > 0) map.set(service.catalog_service_id, violations);
    });
    return map;
  }, [pricingFloors, selectedServices]);

  const buildPriceFloorErrors = useCallback(() => {
    const next: Record<string, Partial<Record<ServiceFormat, string>>> = {};
    serviceFloorViolations.forEach((formatMap, serviceId) => {
      const perFormat: Partial<Record<ServiceFormat, string>> = {};
      formatMap.forEach((violations, format) => {
        const violation = violations[0];
        if (violation) {
          perFormat[format] =
            `Min price for ${violation.duration}-min session is $${formatCents(violation.floorCents)} ` +
            `(current $${formatCents(violation.baseCents)})`;
        }
      });
      if (Object.keys(perFormat).length > 0) {
        next[serviceId] = perFormat;
      }
    });
    return next;
  }, [serviceFloorViolations]);

  const serializeServices = useCallback((services: SelectedService[]) => {
    return JSON.stringify(
      services
        .map((service) => ({
          id: service.catalog_service_id,
          format_prices: service.format_prices,
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

  const clearEmptyRateErrorsForState = useCallback(
    (serviceId: string, formatPrices: FormatPriceState) => {
      setEmptyRateErrors((previous) => {
        const serviceErrors = previous[serviceId];
        if (!serviceErrors) {
          return previous;
        }

        let changed = false;
        const nextServiceErrors: Partial<Record<ServiceFormat, boolean>> = { ...serviceErrors };

        for (const format of Object.keys(serviceErrors) as ServiceFormat[]) {
          const rate = formatPrices[format];
          if (rate === undefined || rate.trim().length > 0) {
            delete nextServiceErrors[format];
            changed = true;
          }
        }

        if (!changed) {
          return previous;
        }

        const next = { ...previous };
        if (Object.keys(nextServiceErrors).length === 0) {
          delete next[serviceId];
        } else {
          next[serviceId] = nextServiceErrors;
        }

        return next;
      });
    },
    [],
  );

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

  // Report enabled formats to parent whenever selectedServices change
  const onFormatsChangeRef = useRef(onFormatsChange);
  onFormatsChangeRef.current = onFormatsChange;

  useEffect(() => {
    const cb = onFormatsChangeRef.current;
    if (!cb) return;
    const enabled: EnabledFormats = { student_location: false, instructor_location: false, online: false };
    for (const svc of selectedServices) {
      if ('student_location' in svc.format_prices) enabled.student_location = true;
      if ('instructor_location' in svc.format_prices) enabled.instructor_location = true;
      if ('online' in svc.format_prices) enabled.online = true;
    }
    cb(enabled);
  }, [selectedServices]);

  const initializeMissingFilters = useCallback(
    (serviceId: string, defaults: FilterSelections) => {
      setSelectedServices((prev) =>
        prev.map((s) => {
          if (s.catalog_service_id !== serviceId) return s;
          return {
            ...s,
            filter_selections: {
              ...defaults,
              ...s.filter_selections,
            },
          };
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

        // Convert API format_prices array to FormatPriceState
        const apiFormatPrices = Array.isArray(s['format_prices'])
          ? (s['format_prices'] as Parameters<typeof payloadToFormatPriceState>[0])
          : [];
        const rawFormatPrices = apiFormatPrices.length > 0
          ? payloadToFormatPriceState(apiFormatPrices)
          : defaultFormatPrices(hasServiceAreas, hasTeachingLocations);

        return {
          catalog_service_id: catalogId,
          subcategory_id: catalogEntry?.subcategory_id ?? '',
          service_catalog_name:
            typeof s['service_catalog_name'] === 'string'
              ? (s['service_catalog_name'] as string)
              : null,
          name: serviceName,
          format_prices: rawFormatPrices,
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

      const pendingHydrationAcceptance = getPendingHydrationAcceptance({
        pendingSyncSignature: pendingSyncSignatureRef.current,
        incomingSignature,
        nextSelectedServices: deduped,
      });

      // FIX 6: Check if this is our own save returning
      // If pendingSyncSignatureRef matches, this is our save - clear editing state and accept
      if (applyPendingHydrationAcceptance({ pendingHydrationAcceptance, pendingSyncSignatureRef, hasLocalEditsRef, isEditingRef, isHydratingRef, setSelectedServices })) return;

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
    serializeServices,
    serviceCatalogById,
  ]);

  // Back-fill subcategory_id, eligible_age_groups, and default filter_selections
  // from catalog when taxonomy data loads after profile hydration.
  useEffect(() => {
    if (serviceCatalogById.size === 0 || selectedServices.length === 0) return;
    const taxonomyBackfill = backfillSelectedServicesFromCatalog(selectedServices, serviceCatalogById);
    if (taxonomyBackfill.changed) {
      isHydratingRef.current = true;
      setSelectedServices(taxonomyBackfill.nextSelectedServices);
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
    setEmptyRateErrors((prev) => {
      if (!prev[catalogServiceId]) return prev;
      const next = { ...prev };
      delete next[catalogServiceId];
      return next;
    });
    setSelectedServicesWithDirty((prev) => prev.filter((s) => s.catalog_service_id !== catalogServiceId));
  }, [canRemoveSkill, profileLoaded, isInstructorLive, selectedServices.length, setSelectedServicesWithDirty]);

  const toggleServiceSelection = (svc: CategoryServiceDetail) => {
    const exists = selectedServices.some((s) => s.catalog_service_id === svc.id);
    if (exists) {
      setEmptyRateErrors((currentErrors) => {
        if (!currentErrors[svc.id]) return currentErrors;
        const nextErrors = { ...currentErrors };
        delete nextErrors[svc.id];
        return nextErrors;
      });
    }

    setSelectedServicesWithDirty((prev) => {
      const serviceExists = prev.some((s) => s.catalog_service_id === svc.id);
      if (serviceExists) {
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
      const eligibleAgeGroups = normalizeAudienceGroups(
        svc.eligible_age_groups ?? catalogEntry?.eligible_age_groups,
        ['kids', 'teens', 'adults']
      );
      return [
        ...prev,
        {
          catalog_service_id: svc.id,
          subcategory_id: catalogEntry?.subcategory_id ?? '',
          service_catalog_name: svc.name,
          name: label,
          format_prices: defaultFormatPrices(hasServiceAreas, hasTeachingLocations),
          eligible_age_groups: eligibleAgeGroups,
          filter_selections: defaultFilterSelections(eligibleAgeGroups),
          description: '',
          equipment: '',
          duration_options: [60],
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

      const emptyRateOffenders = getEmptyRateOffenders(selectedServices);
      if (emptyRateOffenders.length > 0) {
        const nextEmptyRateErrors: Record<string, Partial<Record<ServiceFormat, boolean>>> = {};
        emptyRateOffenders.forEach(({ serviceId, format }) => {
          if (!nextEmptyRateErrors[serviceId]) {
            nextEmptyRateErrors[serviceId] = {};
          }
          nextEmptyRateErrors[serviceId][format] = true;
        });
        setEmptyRateErrors(nextEmptyRateErrors);
        setSvcSaving(false);
        return;
      }

      setEmptyRateErrors({});

      // Safeguard: Live instructors must have at least one skill with a valid rate
      const servicesWithRates = selectedServices.filter((s) => hasAnyFormatEnabled(s.format_prices));
      if (isInstructorLive && servicesWithRates.length === 0) {
        setError('Live instructors must have at least one skill. Please add a skill before saving.');
        setSvcSaving(false);
        return;
      }

      const maxRateErrors: Record<string, Partial<Record<ServiceFormat, string>>> = {};
      for (const service of selectedServices) {
        const serviceErrors = getFormatPriceValidationErrors(service.format_prices);
        if (Object.keys(serviceErrors).length > 0) {
          maxRateErrors[service.catalog_service_id] = serviceErrors;
        }
      }

      if (Object.keys(maxRateErrors).length > 0) {
        const firstError = selectedServices
          .map((service) => getFirstFormatPriceValidationError(service.format_prices))
          .find((message): message is string => Boolean(message))!;
        setPriceErrors(maxRateErrors);
        toast.error(firstError, { id: 'max-rate-error' });
        setSvcSaving(false);
        return;
      }

      // FIX 8: Add comprehensive logging to debug price floor validation
      logger.debug('SkillsPricingInline: price floor validation check', {
        source,
        hasPricingFloors: Boolean(pricingFloors),
        pricingFloors,
        violationsSize: serviceFloorViolations.size,
        services: selectedServices.map((s) => ({
          id: s.catalog_service_id,
          format_prices: s.format_prices,
          duration_options: s.duration_options,
        })),
      });

      if (pricingFloors && serviceFloorViolations.size > 0) {
        const nextPriceErrors = buildPriceFloorErrors();
        if (Object.keys(nextPriceErrors).length > 0) {
          // Build a top-level toast message from the first violation
          const firstServiceErrors = Object.values(nextPriceErrors)[0];
          const firstMsg = firstServiceErrors ? Object.values(firstServiceErrors)[0] : undefined;
          logger.debug('SkillsPricingInline: price floor violation detected, blocking save', {
            source,
            violationCount: serviceFloorViolations.size,
            firstMsg,
          });
          setPriceErrors(nextPriceErrors);
          // FIX 7: Show toast for ALL saves (not just manual) so user sees feedback
          if (firstMsg) {
            toast.error(firstMsg, { id: 'price-floor-error' });
          }
          setSvcSaving(false);
          return;
        }
      }
      // FIX 1: Read from ref to avoid dependency cycle
      const currentPriceErrors = priceErrorsRef.current;
      if (currentPriceErrors && Object.keys(currentPriceErrors).length > 0) {
        setPriceErrors({});
      }

      const payload = {
        services: selectedServices
          .filter((service) => hasAnyFormatEnabled(service.format_prices))
          .map((service) => {
                // Build filter_selections for backend (without age_groups — sent separately)
                const { age_groups: _ageGroups, ...restFilters } = service.filter_selections;
                return {
                  service_catalog_id: service.catalog_service_id,
                  format_prices: formatPricesToPayload(service.format_prices),
                  age_groups: service.filter_selections['age_groups'] ?? [...service.eligible_age_groups],
                  filter_selections: restFilters,
                  ...(service.description?.trim() ? { description: service.description.trim() } : {}),
                  duration_options: [...service.duration_options].sort((a, b) => a - b),
                  ...(service.equipment
                    ?.split(',')
                    .map((v) => v.trim())
                .filter(Boolean)?.length
                ? { equipment_required: service.equipment.split(',').map((v) => v.trim()).filter(Boolean) }
                : {}),
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
      setError(message);
    } finally {
      setSvcSaving(false);
    }
  }, [
    buildPriceFloorErrors,
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
      }
      return;
    }

    if (isHydratingRef.current) {
      isHydratingRef.current = false;
      return;
    }

    hasLocalEditsRef.current = true;

    autoSaveTimeout.current = setTimeout(() => {
      // FIX 4: Call via ref to avoid dependency
      void handleSaveRef.current?.('auto');
    }, 1200);

    return () => {
      clearTimeout(autoSaveTimeout.current ?? undefined);
      autoSaveTimeout.current = null;
    };
  }, [selectedServices]); // FIX 4: handleSave removed from dependencies

  useEffect(() => {
    lastLocalSignatureRef.current = serializeServices(selectedServices);
  }, [selectedServices, serializeServices]);

  const showError = Boolean(error);

  return (
    <div className={className}>
      {showError && (
        <div className="mb-3 rounded-md border border-red-200 bg-red-50 p-2 text-sm text-red-700">{error}</div>
      )}
      {svcLoading ? (
        <div className="p-3 text-sm text-gray-600 dark:text-gray-400">Loading…</div>
      ) : (
        <>
          {/* Categories and search (expandable) */}
          <div className="p-4 mb-6 rounded-lg insta-surface-card">
            <div className="flex items-center gap-3 text-xl sm:text-lg font-bold sm:font-semibold text-gray-900 dark:text-gray-100 mb-2">
              <div className="w-10 h-10 rounded-full bg-purple-100 flex items-center justify-center">
                <svg className="w-5 h-5 text-(--color-brand)" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6v12m6-6H6" /></svg>
              </div>
              <span>Service categories</span>
            </div>
            <p className="text-gray-600 dark:text-gray-400 mb-2 text-sm">Select the service categories you teach</p>
            <div className="mb-3">
              <input
                type="text"
                value={skillsFilter}
                onChange={(e) => setSkillsFilter(e.target.value)}
                placeholder="Search skills..."
                className="w-full rounded-md border border-gray-200 dark:border-gray-700 px-3 py-2 focus:outline-none"
              />
            </div>
            {/* Selected chips */}
            {selectedServices.length > 0 && (
              <div className="mb-4 flex flex-wrap gap-2">
                {selectedServices.map((s) => (
                  <span key={`sel-${s.catalog_service_id}`} className="inline-flex items-center gap-2 rounded-full border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 h-8 text-xs min-w-0">
                    <span className="truncate max-w-[14rem]" title={s.name || s.service_catalog_name || ''}>{s.name || s.service_catalog_name}</span>
                    <button
                      type="button"
                      aria-label={`Remove ${s.name || s.service_catalog_name}`}
                      title={!canRemoveSkill() ? 'Live instructors must have at least one skill' : `Remove ${s.name || s.service_catalog_name}`}
                      className={`ml-auto rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center ${
                        !canRemoveSkill()
                          ? 'text-gray-300 cursor-not-allowed'
                          : 'text-(--color-brand) hover:bg-purple-50 dark:hover:bg-purple-900/30'
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
                <div key={cat.id} className="rounded-lg overflow-hidden insta-surface-card">
                  <button
                    className="w-full px-4 py-3 flex items-center justify-between text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                    onClick={() => toggleCategory(cat.id)}
                    type="button"
                  >
                    <span className="font-bold">{cat.name}</span>
                    <ChevronDown className={`h-4 w-4 text-gray-600 dark:text-gray-400 transition-transform ${collapsed[cat.id] ? '' : 'rotate-180'}`} />
                  </button>
                  {!collapsed[cat.id] && (
                    <div className="p-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                      {(servicesByCategory[cat.id] || [])
                        .filter((svc) => (skillsFilter ? svc.name.toLowerCase().includes(skillsFilter.toLowerCase()) : true))
                        .map((svc) => {
                          const isSel = selectedServices.some((s) => s.catalog_service_id === svc.id);
                          return (
                            <button
                              key={svc.id}
                              onClick={() => toggleServiceSelection(svc)}
                              className={`inline-flex items-center justify-between px-3 py-1.5 text-sm rounded-full font-semibold transition-colors no-hover-shadow appearance-none overflow-hidden focus:outline-none ${
                                isSel ? 'bg-(--color-brand) text-white border border-(--color-brand) hover:bg-purple-800 dark:hover:bg-purple-700' : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                              }`}
                              type="button"
                            >
                              <span className="truncate text-left">{svc.name}</span>
                              <span className="ml-2">{isSel ? '\u2713' : '+'}</span>
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
              const formatErrors = priceErrors[s.catalog_service_id];

              return (
                <div
                  key={`${s.catalog_service_id}-${index}`}
                  className="p-4 rounded-lg insta-surface-card"
                >
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <div className="text-base font-medium text-gray-900 dark:text-gray-100">{s.service_catalog_name ?? s.name ?? 'Service'}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeService(s.catalog_service_id)}
                    title={!canRemoveSkill() ? 'Live instructors must have at least one skill' : 'Remove skill'}
                    className={`w-8 h-8 flex items-center justify-center rounded-full bg-white dark:bg-gray-800 border transition-colors ${
                      !canRemoveSkill()
                        ? 'border-gray-200 dark:border-gray-700 text-gray-300 cursor-not-allowed'
                        : 'border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-red-50 dark:hover:bg-red-900/30 hover:text-red-600 dark:hover:text-red-400 hover:border-red-300 dark:hover:border-red-500'
                    }`}
                    aria-label="Remove skill"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
                  </button>
                </div>

                <div className="mb-3">
                  <FormatPricingCards
                    formatPrices={s.format_prices}
                    onChange={(next) => {
                      clearEmptyRateErrorsForState(s.catalog_service_id, next);
                      setSelectedServicesWithDirty((prev) =>
                        prev.map((x, i) => (i === index ? { ...x, format_prices: next } : x))
                      );
                      if (formatErrors) {
                        setPriceErrors((prev) => {
                          if (!prev[s.catalog_service_id]) return prev;
                          const updated = { ...prev };
                          delete updated[s.catalog_service_id];
                          return updated;
                        });
                      }
                    }}
                    priceFloors={pricingFloors}
                    durationOptions={s.duration_options}
                    takeHomePct={instructorTakeHomePct}
                    platformFeeLabel={platformFeeLabel}
                    formatErrors={formatErrors}
                    emptyRateErrors={emptyRateErrors[s.catalog_service_id]}
                    studentLocationDisabled={!hasServiceAreas}
                    studentLocationDisabledReason={
                      !hasServiceAreas
                        ? 'You need at least one service area to offer travel lessons'
                        : undefined
                    }
                  />
                </div>

                <div className="rounded-lg p-3 insta-surface-card mb-3">
                    <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2 block">Age groups</label>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-1">
                      {ALL_AUDIENCE_GROUPS.map((group) => {
                        const selectedAgeGroups = s.filter_selections['age_groups']!;
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
                              const current = x.filter_selections['age_groups']!;
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
                              ? 'bg-gray-50 dark:bg-gray-900 text-gray-300 cursor-not-allowed'
                              : isSelected
                              ? 'bg-purple-100 text-(--color-brand) border border-purple-300'
                              : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                          }`}
                          type="button"
                        >
                          {AUDIENCE_LABELS[group]}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                  <div className="rounded-lg p-3 insta-surface-card">
                    <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2 block">Skill level</label>
                    <div className="flex gap-1">
                      {DEFAULT_SKILL_LEVELS.map((lvl) => {
                        const selectedLevels = s.filter_selections['skill_level']!;
                        const isLvlSelected = selectedLevels.includes(lvl);
                        return (
                          <button
                            key={lvl}
                            onClick={() => setSelectedServicesWithDirty((prev) => prev.map((x, i) => {
                              if (i !== index) return x;
                              const current = x.filter_selections['skill_level']!;
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
                              isLvlSelected ? 'bg-purple-100 text-(--color-brand) border border-purple-300' : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                            }`}
                            type="button"
                          >
                            {lvl === 'beginner' ? 'Beginner' : lvl === 'intermediate' ? 'Intermediate' : 'Advanced'}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <div className="rounded-lg p-3 insta-surface-card">
                    <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2 block">Session duration</label>
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
                            s.duration_options.includes(d) ? 'bg-purple-100 text-(--color-brand) border border-purple-300' : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
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
                    <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1 block">Description (optional)</label>
                    <textarea
                      rows={2}
                      className="w-full rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-2 text-sm focus:outline-none bg-white dark:bg-gray-800"
                      placeholder="Brief description of your teaching style..."
                      value={s.description || ''}
                      onChange={(e) => setSelectedServicesWithDirty((prev) => prev.map((x, i) => i === index ? { ...x, description: e.target.value } : x))}
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1 block">Equipment (optional)</label>
                    <textarea
                      rows={2}
                      className="w-full rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-2 text-sm focus:outline-none bg-white dark:bg-gray-800"
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
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                <p>No services added yet. Add your first service above!</p>
              </div>
            )}
          </div>

          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-full bg-purple-100 dark:bg-gray-800 text-(--color-brand)">
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
                className="w-full min-w-[220px] rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900/60 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => { void handleRequestSkill(); }}
                disabled={!requestedSkill.trim() || requestSubmitting}
                className="inline-flex items-center justify-center rounded-lg bg-(--color-brand) px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-[#6d1fc3] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {requestSubmitting ? 'Sending\u2026' : 'Submit'}
              </button>
            </div>
          </div>
          {requestSuccess && <p className="mt-2 text-xs text-gray-700 dark:text-gray-200">{requestSuccess}</p>}
          {svcSaving && (
            <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">Saving changes\u2026</p>
          )}
        </>
      )}
    </div>
  );
}
