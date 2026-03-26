'use client';

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { BookOpen, CheckSquare, Lightbulb } from 'lucide-react';
import { useSearchParams } from 'next/navigation';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { extractApiErrorMessage } from '@/lib/apiErrors';
import type {
  ApiErrorResponse,
  CategoryServiceDetail,
  NeighborhoodsListResponse,
  ServiceCategory,
} from '@/features/shared/api/types';
import type { ServiceAreaItem } from '@/features/instructor-profile/types';
import { logger } from '@/lib/logger';
import { submitSkillRequest } from '@/lib/api/skillRequest';
import { usePricingConfig } from '@/lib/pricing/usePricingFloors';
import {
  evaluateFormatPriceFloorViolations,
  formatCents,
  type FormatFloorViolation,
} from '@/lib/pricing/priceFloors';
import {
  type FormatPriceState,
  type ServiceFormat,
  defaultFormatPrices,
  formatPricesToPayload,
  getFirstFormatPriceValidationError,
  getFormatPriceValidationErrors,
  hasAnyFormatEnabled,
  MAX_HOURLY_RATE_MESSAGE,
  payloadToFormatPriceState,
} from '@/lib/pricing/formatPricing';
import { FormatPricingCards } from '@/components/pricing/FormatPricingCards';
import { formatPlatformFeeLabel, resolvePlatformFeeRate, resolveTakeHomePct } from '@/lib/pricing/platformFees';
import { OnboardingProgressHeader } from '@/features/instructor-onboarding/OnboardingProgressHeader';
import { useOnboardingStepStatus } from '@/features/instructor-onboarding/useOnboardingStepStatus';
import { usePlatformFees } from '@/hooks/usePlatformConfig';
import { useCatalogBrowse, useServiceCategories } from '@/hooks/queries/useServices';
import { useCategoriesWithSubcategories } from '@/hooks/queries/useTaxonomy';
import {
  ALL_AUDIENCE_GROUPS,
  AUDIENCE_LABELS,
  DEFAULT_SKILL_LEVELS,
  arraysEqual,
  defaultFilterSelections,
  isNonEmptyString,
  normalizeAudienceGroups,
  normalizeFilterSelections,
  normalizeSelectionValues,
  normalizeSkillLevels,
} from '@/lib/taxonomy/filterHelpers';
import type { AudienceGroup, FilterSelections } from '@/lib/taxonomy/filterHelpers';
import { RefineFiltersSection } from '@/components/taxonomy/RefineFiltersSection';
import { queryKeys } from '@/src/api/queryKeys';
import { toast } from 'sonner';
import { withApiBase } from '@/lib/apiBase';
import { fetchWithSessionRefresh } from '@/lib/auth/sessionRefresh';
import { useUserAddresses } from '@/hooks/queries/useUserAddresses';
import { ServiceAreasCard } from '@/app/(auth)/instructor/onboarding/account-setup/components/ServiceAreasCard';
import { PreferredLocationsCard } from '@/app/(auth)/instructor/onboarding/account-setup/components/PreferredLocationsCard';

type SelectedService = {
  catalog_service_id: string;
  subcategory_id: string;
  name: string;
  format_prices: FormatPriceState;
  description?: string;
  equipment?: string; // comma-separated freeform for UI
  filter_selections: FilterSelections;
  eligible_age_groups: AudienceGroup[];
  duration_options: number[];
};

type CategoryServiceGroup = {
  subcategory_id: string;
  subcategory_name: string;
  services: CategoryServiceDetail[];
};

const subcategoryCollapseKey = (categoryId: string, subcategoryId: string): string =>
  `${categoryId}__${subcategoryId}`;

function toTitle(s: string): string {
  return s
    .split(/[\s-]+/)
    .map((w) => (w.length > 0 ? w[0]!.toUpperCase() + w.slice(1).toLowerCase() : ''))
    .join(' ');
}

const getErrorMessage = (error: unknown, fallback: string): string => {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }
  return fallback;
};

function Step3SkillsPricingInner() {
  const searchParams = useSearchParams();
  const redirectParam = searchParams?.get('redirect') || null;
  const { user, isAuthenticated } = useAuth();
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [collapsedSubcategories, setCollapsedSubcategories] = useState<Record<string, boolean>>(
    {}
  );
  const [refineExpandedByService, setRefineExpandedByService] = useState<
    Record<string, boolean>
  >({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedService[]>([]);
  const [requestText, setRequestText] = useState('');
  const [requestSubmitting, setRequestSubmitting] = useState(false);
  const [requestSuccess, setRequestSuccess] = useState<string | null>(null);
  const [skillsFilter, setSkillsFilter] = useState<string>('');

  // Use unified step status hook for consistent progress display
  const { stepStatus, rawData } = useOnboardingStepStatus();
  const queryClient = useQueryClient();
  const prefilledFromProfileRef = useRef(false);

  // Check if instructor is already live (affects whether they can have 0 skills)
  const isInstructorLive = rawData.profile?.is_live === true;

  // Single pricing config fetch - derive floors from config to avoid duplicate API calls
  const { config: pricingConfig } = usePricingConfig();
  const { fees } = usePlatformFees();
  const pricingFloors = pricingConfig?.price_floor_cents ?? null;
  const isFoundingInstructor = Boolean(rawData.profile?.is_founding_instructor);

  const {
    data: categories = [],
    isLoading: categoriesLoading,
    error: categoriesError,
  } = useServiceCategories();
  const {
    data: catalogBrowseResponse,
    isLoading: servicesLoading,
    error: servicesError,
  } = useCatalogBrowse();
  const { data: categoriesWithSubcategories = [] } = useCategoriesWithSubcategories();

  const profileRecord = rawData.profile as Record<string, unknown> | null;
  const serviceAreaNeighborhoods = Array.isArray(
    profileRecord?.['service_area_neighborhoods']
  )
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

  const teachingLocations = Array.isArray(
    profileRecord?.['preferred_teaching_locations']
  )
    ? (profileRecord?.['preferred_teaching_locations'] as unknown[])
    : [];
  const hasTeachingLocations = teachingLocations.length > 0;

  const currentTierRaw =
    profileRecord?.['current_tier_pct'] ?? profileRecord?.['instructor_tier_pct'];
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
  const platformFeeLabel = useMemo(
    () => formatPlatformFeeLabel(platformFeeRate),
    [platformFeeRate]
  );
  const instructorTakeHomePct = useMemo(
    () => resolveTakeHomePct(platformFeeRate),
    [platformFeeRate]
  );

  // ── Service Areas state (for ServiceAreasCard) ──
  const [isNYC, setIsNYC] = useState<boolean>(true);
  const [selectedNeighborhoods, setSelectedNeighborhoods] = useState<Set<string>>(new Set());
  const [boroughNeighborhoods, setBoroughNeighborhoods] = useState<Record<string, ServiceAreaItem[]>>({});
  const [openBoroughsMain, setOpenBoroughsMain] = useState<Set<string>>(new Set());
  const [globalNeighborhoodFilter, setGlobalNeighborhoodFilter] = useState<string>('');
  const [idToItem, setIdToItem] = useState<Record<string, ServiceAreaItem>>({});
  const boroughAccordionRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // ── Preferred Locations state (for PreferredLocationsCard) ──
  const [preferredAddress, setPreferredAddress] = useState<string>('');
  const [preferredLocations, setPreferredLocations] = useState<string[]>([]);
  const [preferredLocationTitles, setPreferredLocationTitles] = useState<Record<string, string>>({});
  const [neutralLocations, setNeutralLocations] = useState<string>('');
  const [neutralPlaces, setNeutralPlaces] = useState<string[]>([]);

  const { data: addressesDataFromHook } = useUserAddresses();

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

  useEffect(() => {
    if (globalNeighborhoodFilter.trim().length > 0) {
      NYC_BOROUGHS.forEach((b) => {
        void loadBoroughNeighborhoods(b);
      });
    }
  }, [globalNeighborhoodFilter, NYC_BOROUGHS, loadBoroughNeighborhoods]);

  const toggleMainBoroughOpen = async (b: string) => {
    const el = boroughAccordionRefs.current[b];
    const prevTop = el?.getBoundingClientRect().top ?? 0;
    setOpenBoroughsMain((prev) => {
      const next = new Set(prev);
      if (next.has(b)) {
        next.delete(b);
      } else {
        next.add(b);
      }
      return next;
    });
    await loadBoroughNeighborhoods(b);
    requestAnimationFrame(() => {
      const newTop = boroughAccordionRefs.current[b]?.getBoundingClientRect().top ?? prevTop;
      if (Math.abs(newTop - prevTop) > 5) {
        window.scrollBy({ top: newTop - prevTop, behavior: 'smooth' });
      }
    });
  };

  const toggleBoroughAll = (borough: string, value: boolean, itemsOverride?: ServiceAreaItem[]) => {
    const items = itemsOverride || boroughNeighborhoods[borough] || [];
    setSelectedNeighborhoods((prev) => {
      const next = new Set(prev);
      for (const n of items) {
        const nid = n.neighborhood_id;
        if (!nid) continue;
        if (value) next.add(nid);
        else next.delete(nid);
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

  // Prefill service areas & preferred locations from profile
  const serviceAreasPrefilled = useRef(false);
  useEffect(() => {
    if (serviceAreasPrefilled.current) return;
    if (!isAuthenticated || !rawData.profile) return;
    serviceAreasPrefilled.current = true;

    // Prefill preferred teaching locations
    const teachingFromApi = Array.isArray(rawData.profile?.['preferred_teaching_locations'])
      ? (rawData.profile['preferred_teaching_locations'] as Array<Record<string, unknown>>)
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

    // Prefill preferred public spaces
    const publicFromApi = Array.isArray(rawData.profile?.['preferred_public_spaces'])
      ? (rawData.profile['preferred_public_spaces'] as Array<Record<string, unknown>>)
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
    void (async () => {
      try {
        const areasRes = await fetchWithAuth('/api/v1/addresses/service-areas/me');
        if (areasRes.ok) {
          const areas = await areasRes.json() as { items?: ServiceAreaItem[] };
          const items = (areas.items || []) as ServiceAreaItem[];
          const ids = items
            .map((a) => a['neighborhood_id'] || (a as Record<string, unknown>)['id'] as string)
            .filter((v: string | undefined): v is string => typeof v === 'string');
          setSelectedNeighborhoods(new Set(ids));
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
    })();

    // Detect NYC from default address postal code
    void (async () => {
      try {
        if (addressesDataFromHook?.items) {
          const items = addressesDataFromHook.items;
          const def = items.find((a) => a.is_default) ?? items[0];
          const zip = def?.postal_code;
          if (zip) {
            const nycRes = await fetchWithSessionRefresh(withApiBase(`${API_ENDPOINTS.NYC_ZIP_CHECK}?zip=${encodeURIComponent(zip)}`), {
              credentials: 'include',
            });
            if (nycRes.ok) {
              const nyc = await nycRes.json() as { is_nyc?: boolean };
              setIsNYC(!!nyc['is_nyc']);
            }
          }
        }
      } catch (err) {
        logger.warn('Failed to check NYC zip', err);
      }
    })();
  }, [isAuthenticated, rawData.profile, addressesDataFromHook]);

  // Derive hasServiceAreas / hasTeachingLocations from local state too
  const hasServiceAreasLocal = selectedNeighborhoods.size > 0;
  const hasTeachingLocationsLocal = preferredLocations.length > 0;
  // Combined: true if profile data OR local state has them
  const effectiveHasServiceAreas = hasServiceAreas || hasServiceAreasLocal;
  const effectiveHasTeachingLocations = hasTeachingLocations || hasTeachingLocationsLocal;

  // Whether any selected service uses student_location or instructor_location
  const anyServiceUsesStudentLocation = selected.some(
    (svc) => 'student_location' in svc.format_prices
  );
  const anyServiceUsesInstructorLocation = selected.some(
    (svc) => 'instructor_location' in svc.format_prices
  );

  const servicesByCategory = useMemo(() => {
    const map: Record<string, CategoryServiceDetail[]> = {};
    const categoryRows = catalogBrowseResponse?.categories ?? [];
    for (const category of categoryRows) {
      map[category.id] = (category.services ?? []).map((svc) => ({
        id: svc.id,
        name: svc.name,
        subcategory_id: svc.subcategory_id,
        eligible_age_groups: svc.eligible_age_groups ?? [],
        description: svc.description ?? null,
        display_order: svc.display_order ?? null,
        active_instructors: 0,
        demand_score: 0,
        is_trending: false,
      }));
    }
    return map;
  }, [catalogBrowseResponse]);

  const allCatalogServices = useMemo(
    () => Object.values(servicesByCategory).flat(),
    [servicesByCategory]
  );

  const serviceCatalogById = useMemo(() => {
    const map = new Map<string, CategoryServiceDetail>();
    for (const service of allCatalogServices) {
      map.set(service.id, service);
    }
    return map;
  }, [allCatalogServices]);

  const subcategoryNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const category of categoriesWithSubcategories) {
      for (const subcategory of category.subcategories ?? []) {
        if (isNonEmptyString(subcategory.id) && isNonEmptyString(subcategory.name)) {
          map.set(subcategory.id, subcategory.name);
        }
      }
    }
    return map;
  }, [categoriesWithSubcategories]);

  const subcategoryOrderById = useMemo(() => {
    const map = new Map<string, number>();
    for (const category of categoriesWithSubcategories) {
      (category.subcategories ?? []).forEach((subcategory, index) => {
        if (isNonEmptyString(subcategory.id)) {
          map.set(subcategory.id, index);
        }
      });
    }
    return map;
  }, [categoriesWithSubcategories]);

  const groupedServicesByCategory = useMemo(() => {
    const groupedByCategory: Record<string, CategoryServiceGroup[]> = {};

    for (const category of categories as ServiceCategory[]) {
      const services = servicesByCategory[category.id] ?? [];
      const groups = new Map<string, CategoryServiceGroup>();

      for (const service of services) {
        const subcategoryId = service.subcategory_id || 'uncategorized';
        const fallbackName = subcategoryId === 'uncategorized' ? 'Other' : 'Subcategory';
        const subcategoryName =
          subcategoryNameById.get(subcategoryId) ?? fallbackName;

        const existing = groups.get(subcategoryId);
        if (existing) {
          existing.services.push(service);
        } else {
          groups.set(subcategoryId, {
            subcategory_id: subcategoryId,
            subcategory_name: subcategoryName,
            services: [service],
          });
        }
      }

      groupedByCategory[category.id] = Array.from(groups.values())
        .map((group) => ({
          ...group,
          services: [...group.services].sort((a, b) =>
            (a.display_order ?? Number.MAX_SAFE_INTEGER) -
              (b.display_order ?? Number.MAX_SAFE_INTEGER) ||
            a.name.localeCompare(b.name)
          ),
        }))
        .sort((a, b) => {
          const aOrder = subcategoryOrderById.get(a.subcategory_id) ?? Number.MAX_SAFE_INTEGER;
          const bOrder = subcategoryOrderById.get(b.subcategory_id) ?? Number.MAX_SAFE_INTEGER;
          if (aOrder !== bOrder) {
            return aOrder - bOrder;
          }
          return a.subcategory_name.localeCompare(b.subcategory_name);
        });
    }

    return groupedByCategory;
  }, [categories, servicesByCategory, subcategoryNameById, subcategoryOrderById]);

  const formatViolationsByService = useMemo(() => {
    const map = new Map<string, Map<ServiceFormat, FormatFloorViolation[]>>();
    if (!pricingFloors) {
      return map;
    }

    selected.forEach((service) => {
      const violations = evaluateFormatPriceFloorViolations({
        formatPrices: service.format_prices,
        durationOptions: service.duration_options ?? [60],
        floors: pricingFloors,
      });

      if (violations.size > 0) {
        map.set(service.catalog_service_id, violations);
      }
    });

    return map;
  }, [pricingFloors, selected]);

  const hasFloorViolations = formatViolationsByService.size > 0;
  const maxRateErrorsByService = useMemo(() => {
    const map = new Map<string, Partial<Record<ServiceFormat, string>>>();

    selected.forEach((service) => {
      const formatErrors = getFormatPriceValidationErrors(service.format_prices);
      if (Object.keys(formatErrors).length > 0) {
        map.set(service.catalog_service_id, formatErrors);
      }
    });

    return map;
  }, [selected]);
  const hasRateCapViolations = maxRateErrorsByService.size > 0;

  const catalogLoadError = useMemo(() => {
    if (categoriesError) {
      return getErrorMessage(categoriesError, 'Failed to load service categories');
    }
    if (servicesError) {
      return getErrorMessage(servicesError, 'Failed to load services');
    }
    return null;
  }, [categoriesError, servicesError]);

  const updateSelectedService = useCallback(
    (
      serviceId: string,
      updater: (service: SelectedService) => SelectedService
    ): void => {
      setSelected((previous) =>
        previous.map((service) =>
          service.catalog_service_id === serviceId ? updater(service) : service
        )
      );
    },
    []
  );

  const setServiceFilterValues = useCallback(
    (serviceId: string, filterKey: string, values: string[]) => {
      updateSelectedService(serviceId, (service) => {
        const nextSelections: FilterSelections = {
          ...service.filter_selections,
          [filterKey]: normalizeSelectionValues(values),
        };
        return { ...service, filter_selections: nextSelections };
      });
    },
    [updateSelectedService]
  );

  const initializeMissingFilters = useCallback(
    (serviceId: string, defaults: FilterSelections) => {
      updateSelectedService(serviceId, (service) => {
        let changed = false;
        const nextSelections: FilterSelections = { ...service.filter_selections };

        for (const [key, values] of Object.entries(defaults)) {
          if (nextSelections[key] !== undefined) {
            continue;
          }
          nextSelections[key] = normalizeSelectionValues(values);
          changed = true;
        }

        return changed
          ? { ...service, filter_selections: nextSelections }
          : service;
      });
    },
    [updateSelectedService]
  );

  useEffect(() => {
    if (categories.length === 0) {
      return;
    }

    setCollapsed((previous) => {
      const next: Record<string, boolean> = {};
      for (const category of categories) {
        next[category.id] = previous[category.id] ?? true;
      }

      const prevKeys = Object.keys(previous);
      const nextKeys = Object.keys(next);
      if (
        prevKeys.length === nextKeys.length &&
        nextKeys.every((key) => previous[key] === next[key])
      ) {
        return previous;
      }

      return next;
    });
  }, [categories]);

  useEffect(() => {
    setCollapsedSubcategories((previous) => {
      const next: Record<string, boolean> = {};

      for (const category of categories) {
        const groups = groupedServicesByCategory[category.id] ?? [];
        for (const group of groups) {
          const key = subcategoryCollapseKey(category.id, group.subcategory_id);
          // Keep subcategories collapsed by default for cleaner scanning.
          next[key] = previous[key] ?? true;
        }
      }

      const prevKeys = Object.keys(previous);
      const nextKeys = Object.keys(next);
      if (
        prevKeys.length === nextKeys.length &&
        nextKeys.every((key) => previous[key] === next[key])
      ) {
        return previous;
      }

      return next;
    });
  }, [categories, groupedServicesByCategory]);

  useEffect(() => {
    const shouldPrefill =
      !!isAuthenticated &&
      !!user &&
      Array.isArray(user.roles) &&
      user.roles.some((role: unknown) => String(role).toLowerCase() === 'instructor');

    if (!shouldPrefill || prefilledFromProfileRef.current) {
      return;
    }

    const profileServices = Array.isArray(rawData.profile?.services)
      ? rawData.profile?.services
      : null;

    if (!profileServices) {
      return;
    }

    const mapped = profileServices.reduce<SelectedService[]>(
      (accumulator, serviceRecord: unknown) => {
        if (!serviceRecord || typeof serviceRecord !== 'object') {
          return accumulator;
        }

        const service = serviceRecord as Record<string, unknown>;
        const catalogServiceId = String(service['service_catalog_id'] || '').trim();
        if (!catalogServiceId) {
          return accumulator;
        }

        const catalogEntry = serviceCatalogById.get(catalogServiceId);
        const eligibleAgeGroups = normalizeAudienceGroups(
          catalogEntry?.eligible_age_groups,
          [...ALL_AUDIENCE_GROUPS]
        );

        const rawSelections = normalizeFilterSelections(service['filter_selections']);
        const persistedAgeGroups = normalizeAudienceGroups(
          service['age_groups'],
          normalizeAudienceGroups(rawSelections['age_groups'], eligibleAgeGroups)
        );

        const normalizedSelections: FilterSelections = {
          ...rawSelections,
          skill_level: normalizeSkillLevels(rawSelections['skill_level']),
          age_groups:
            persistedAgeGroups.length > 0
              ? persistedAgeGroups
              : [...eligibleAgeGroups],
        };

        // Resolve format_prices from API response
        const rawFormatPrices = Array.isArray(service['format_prices'])
          ? (service['format_prices'] as Array<Record<string, unknown>>)
          : [];
        const apiFormatPrices = rawFormatPrices.length > 0
          ? payloadToFormatPriceState(
              rawFormatPrices.map((fp) => ({
                format: String(fp['format'] ?? '') as 'student_location' | 'instructor_location' | 'online',
                hourly_rate: Number(fp['hourly_rate'] ?? 0),
              }))
            )
          : defaultFormatPrices(effectiveHasServiceAreas, effectiveHasTeachingLocations);

        accumulator.push({
          catalog_service_id: catalogServiceId,
          subcategory_id:
            (isNonEmptyString(service['subcategory_id'])
              ? String(service['subcategory_id'])
              : catalogEntry?.subcategory_id) ?? '',
          name:
            (isNonEmptyString(service['name'])
              ? String(service['name'])
              : isNonEmptyString(service['service_catalog_name'])
              ? String(service['service_catalog_name'])
              : catalogEntry?.name) ?? 'Unknown Service',
          format_prices: apiFormatPrices,
          description: String(service['description'] || ''),
          equipment: Array.isArray(service['equipment_required'])
            ? service['equipment_required'].join(', ')
            : '',
          filter_selections: normalizedSelections,
          eligible_age_groups: eligibleAgeGroups,
          duration_options:
            Array.isArray(service['duration_options']) && service['duration_options'].length
              ? (service['duration_options'] as number[])
              : [60],
        });

        return accumulator;
      },
      []
    );

    prefilledFromProfileRef.current = true;
    setSelected(mapped);
  }, [
    effectiveHasServiceAreas,
    effectiveHasTeachingLocations,
    isAuthenticated,
    rawData.profile?.services,
    serviceCatalogById,
    user,
  ]);

  // When service areas or teaching locations are removed, disable corresponding formats
  useEffect(() => {
    if (effectiveHasServiceAreas && effectiveHasTeachingLocations) {
      return;
    }

    setSelected((previous) => {
      let changed = false;
      const next = previous.map((service) => {
        let updated = service;
        if (!effectiveHasServiceAreas && 'student_location' in updated.format_prices) {
          const { student_location: _removed, ...rest } = updated.format_prices;
          updated = { ...updated, format_prices: rest };
          changed = true;
        }
        if (!effectiveHasTeachingLocations && 'instructor_location' in updated.format_prices) {
          const { instructor_location: _removed, ...rest } = updated.format_prices;
          updated = { ...updated, format_prices: rest };
          changed = true;
        }
        return updated;
      });

      return changed ? next : previous;
    });
  }, [effectiveHasServiceAreas, effectiveHasTeachingLocations]);

  useEffect(() => {
    if (!selected.length || !serviceCatalogById.size) {
      return;
    }

    setSelected((previous) => {
      let changed = false;
      const next = previous.map((service) => {
        const catalogEntry = serviceCatalogById.get(service.catalog_service_id);
        if (!catalogEntry) {
          return service;
        }

        let updated = service;
        let serviceChanged = false;
        if (!isNonEmptyString(updated.name) && isNonEmptyString(catalogEntry.name)) {
          updated = { ...updated, name: catalogEntry.name };
          serviceChanged = true;
        }

        if (!updated.subcategory_id && isNonEmptyString(catalogEntry.subcategory_id)) {
          updated = { ...updated, subcategory_id: catalogEntry.subcategory_id };
          serviceChanged = true;
        }

        const eligibleAgeGroups = normalizeAudienceGroups(
          catalogEntry.eligible_age_groups,
          [...ALL_AUDIENCE_GROUPS]
        );
        if (!arraysEqual(updated.eligible_age_groups, eligibleAgeGroups)) {
          updated = { ...updated, eligible_age_groups: eligibleAgeGroups };
          serviceChanged = true;
        }

        const currentSelections = { ...updated.filter_selections };
        if (!currentSelections['skill_level']) {
          currentSelections['skill_level'] = [...DEFAULT_SKILL_LEVELS];
          serviceChanged = true;
        }

        if (!currentSelections['age_groups']) {
          currentSelections['age_groups'] = [...eligibleAgeGroups];
          serviceChanged = true;
        }

        if (serviceChanged && currentSelections !== updated.filter_selections) {
          updated = { ...updated, filter_selections: currentSelections };
        }

        if (serviceChanged) {
          changed = true;
        }

        return updated;
      });

      return changed ? next : previous;
    });
  }, [selected.length, serviceCatalogById]);

  const toggleService = (service: CategoryServiceDetail) => {
    const isAlreadySelected = selected.some(
      (selectedService) => selectedService.catalog_service_id === service.id
    );

    if (isAlreadySelected) {
      setSelected((previous) =>
        previous.filter((selectedService) => selectedService.catalog_service_id !== service.id)
      );
      setRefineExpandedByService((previous) => {
        if (previous[service.id] === undefined) {
          return previous;
        }
        const next = { ...previous };
        delete next[service.id];
        return next;
      });
      return;
    }

    const eligibleAgeGroups = normalizeAudienceGroups(
      service.eligible_age_groups,
      [...ALL_AUDIENCE_GROUPS]
    );

    setSelected((previous) => [
      ...previous,
      {
        catalog_service_id: service.id,
        subcategory_id: service.subcategory_id,
        name: service.name,
        format_prices: defaultFormatPrices(effectiveHasServiceAreas, effectiveHasTeachingLocations),
        description: '',
        equipment: '',
        filter_selections: defaultFilterSelections(eligibleAgeGroups),
        eligible_age_groups: eligibleAgeGroups,
        duration_options: [60],
      },
    ]);
  };

  const removeService = (serviceId: string) => {
    if (isInstructorLive && selected.length <= 1) {
      setError(
        'Live instructors must have at least one skill. Add another skill before removing this one.'
      );
      return;
    }

    setSelected((previous) =>
      previous.filter((service) => service.catalog_service_id !== serviceId)
    );
    setRefineExpandedByService((previous) => {
      if (previous[serviceId] === undefined) {
        return previous;
      }
      const next = { ...previous };
      delete next[serviceId];
      return next;
    });
  };

  const save = async () => {
    try {
      setSaving(true);
      setError(null);

      const hasInvalidFormats = selected.some(
        (service) => !hasAnyFormatEnabled(service.format_prices)
      );

      if (hasInvalidFormats) {
        toast.error(
          'Enable at least one lesson format and set a rate for each selected skill'
        );
        setSaving(false);
        return;
      }

      if (hasRateCapViolations) {
        const firstViolation = selected
          .map((service) => getFirstFormatPriceValidationError(service.format_prices))
          .find((message): message is string => Boolean(message));

        if (firstViolation) {
          setError(firstViolation);
          toast.error(firstViolation);
        }
        setSaving(false);
        return;
      }

      if (pricingFloors && hasFloorViolations) {
        const firstViolation = formatViolationsByService.entries().next();
        if (!firstViolation.done) {
          const [serviceId, violationsMap] = firstViolation.value;
          const firstFormat = violationsMap.entries().next();
          if (!firstFormat.done) {
            const [, formatViolations] = firstFormat.value;
            const violation = formatViolations[0];
            if (violation) {
              const serviceName =
                selected.find((service) => service.catalog_service_id === serviceId)?.name ||
                'this service';

              setError(
                `Minimum price for a ${violation.duration}-minute private session is $${formatCents(violation.floorCents)} (current $${formatCents(violation.baseCents)}). Please update the rate for ${serviceName}.`
              );
              setSaving(false);
              return;
            }
          }
        }
      }

      const nextUrl = redirectParam || '/instructor/onboarding/verification';

      if (selected.length === 0) {
        if (isInstructorLive) {
          setError('Live instructors must have at least one skill.');
          setSaving(false);
          return;
        }

        try {
          const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ services: [] }),
          });
          if (!response.ok) {
            const apiError = (await response.json().catch(() => null)) as ApiErrorResponse | null;
            const message = apiError
              ? extractApiErrorMessage(apiError, 'Failed to save skills')
              : 'Failed to save skills';
            setError(message);
            toast.error(message);
            setSaving(false);
            return;
          }
        } catch {
          setError('Failed to save skills');
          toast.error('Failed to save skills');
          setSaving(false);
          return;
        }

        if (typeof window !== 'undefined') {
          sessionStorage.setItem('skillsSkipped', 'true');
        }

        window.location.href = nextUrl;
        return;
      }

      // Save service areas before the profile PUT (backend validates they exist)
      if (anyServiceUsesStudentLocation && selectedNeighborhoods.size > 0) {
        const neighborhoodIds = [...selectedNeighborhoods];
        const areasRes = await fetchWithAuth('/api/v1/addresses/service-areas/me', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ neighborhood_ids: neighborhoodIds }),
        });
        if (!areasRes.ok) {
          setError('Failed to save service areas. Please try again.');
          setSaving(false);
          return;
        }
      }

      const servicesPayload = selected
        .filter((service) => hasAnyFormatEnabled(service.format_prices))
        .map((service) => {
          const normalizedSelections = normalizeFilterSelections(
            service.filter_selections
          );
          const ageGroups = normalizeAudienceGroups(
            normalizedSelections['age_groups'],
            service.eligible_age_groups
          );

          const skillLevelSelections = normalizeSkillLevels(
            normalizedSelections['skill_level']
          );

          const taxonomyFilterSelections: FilterSelections = {
            ...normalizedSelections,
            skill_level: [...skillLevelSelections],
          };
          delete taxonomyFilterSelections['age_groups'];

          for (const key of Object.keys(taxonomyFilterSelections)) {
            if ((taxonomyFilterSelections[key] ?? []).length === 0) {
              delete taxonomyFilterSelections[key];
            }
          }

          return {
            service_catalog_id: service.catalog_service_id,
            format_prices: formatPricesToPayload(service.format_prices),
            age_groups: ageGroups.length > 0 ? ageGroups : undefined,
            description:
              service.description && service.description.trim()
                ? service.description.trim()
                : undefined,
            duration_options: (
              service.duration_options && service.duration_options.length
                ? service.duration_options
                : [60]
            ).sort((a, b) => a - b),
            filter_selections:
              Object.keys(taxonomyFilterSelections).length > 0
                ? taxonomyFilterSelections
                : undefined,
            equipment_required:
              service.equipment && service.equipment.trim()
                ? service.equipment
                    .split(',')
                    .map((entry) => entry.trim())
                    .filter((entry) => entry.length > 0)
                : undefined,
          };
        });

      // Include teaching locations and public spaces in profile payload
      // (backend saves these before validating services)
      const payload: Record<string, unknown> = {
        services: servicesPayload,
      };

      if (anyServiceUsesInstructorLocation && preferredLocations.length > 0) {
        payload['preferred_teaching_locations'] = preferredLocations.map((address) => ({
          address,
          label: preferredLocationTitles[address] || null,
        }));
      }

      if (anyServiceUsesInstructorLocation && neutralPlaces.length > 0) {
        payload['preferred_public_spaces'] = neutralPlaces.map((address) => ({
          address,
          label: null,
        }));
      }

      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const apiError = (await response.json().catch(() => null)) as ApiErrorResponse | null;
        const message = apiError
          ? extractApiErrorMessage(apiError, 'Failed to save skills')
          : 'Failed to save skills';
        logger.warn('Save services failed', { message: apiError });
        setError(message);
        toast.error(message);
        return;
      }

      await queryClient.invalidateQueries({ queryKey: queryKeys.instructors.me });
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem('skillsSkipped');
      }
      window.location.href = nextUrl;
    } catch (saveError) {
      logger.error('Save services failed', saveError);
      const message =
        saveError instanceof Error ? saveError.message : 'Failed to save';
      setError(message);
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    if (!hasFloorViolations && error && /Minimum price for a/.test(error)) {
      setError(null);
    }
  }, [hasFloorViolations, error]);

  useEffect(() => {
    if (!hasRateCapViolations && error === MAX_HOURLY_RATE_MESSAGE) {
      setError(null);
    }
  }, [error, hasRateCapViolations]);

  const submitServiceRequest = async () => {
    if (!requestText.trim()) {
      return;
    }
    try {
      setRequestSubmitting(true);
      setRequestSuccess(null);
      await submitSkillRequest({
        skill_name: requestText.trim(),
        instructor_id: rawData.profile?.id ?? null,
        email: user?.email ?? null,
        first_name: user?.first_name ?? null,
        last_name: user?.last_name ?? null,
        is_founding_instructor: isFoundingInstructor,
        is_live: isInstructorLive,
        source: 'onboarding_skill_selection',
      });
      setRequestSuccess("Thanks! We'll review and consider adding this skill.");
      setRequestText('');
    } catch {
      setRequestSuccess('Something went wrong. Please try again.');
    } finally {
      setRequestSubmitting(false);
    }
  };

  if (categoriesLoading || servicesLoading) {
    return (
      <div className="min-h-screen insta-onboarding-page">
        <OnboardingProgressHeader activeStep="skill-selection" stepStatus={stepStatus} />
        <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
          <div className="insta-surface-card insta-onboarding-header">
            <div className="h-7 w-48 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
            <div className="h-4 w-72 bg-gray-200 dark:bg-gray-700 rounded animate-pulse mt-2" />
          </div>
          <div className="insta-onboarding-divider" />
          {/* Category tab skeleton */}
          <div className="flex gap-2 flex-wrap mb-6">
            {Array.from({ length: 7 }, (_, i) => (
              <div
                key={i}
                className="h-9 rounded-full bg-gray-200 dark:bg-gray-700 animate-pulse"
                style={{ width: `${72 + (i % 3) * 24}px` }}
              />
            ))}
          </div>
          {/* Skill chip skeleton */}
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {Array.from({ length: 12 }, (_, i) => (
              <div
                key={i}
                className="h-9 rounded-full bg-gray-200 dark:bg-gray-700 animate-pulse"
              />
            ))}
          </div>
        </div>
      </div>
    );
  }

  const showError = Boolean(error);

  return (
    <div className="min-h-screen insta-onboarding-page">
      <OnboardingProgressHeader activeStep="skill-selection" stepStatus={stepStatus} />

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        <div className="insta-surface-card insta-onboarding-header">
          <h1 className="insta-onboarding-title">
            What do you teach?
          </h1>
          <p className="insta-onboarding-subtitle">
            Choose your skills and set your rates
          </p>
        </div>
        <div className="insta-onboarding-divider" />

        {catalogLoadError && (
          <div className="mt-4 rounded-md bg-red-50 text-red-700 px-4 py-2">
            {catalogLoadError}
          </div>
        )}
        {showError && (
          <div className="mt-4 rounded-md bg-red-50 text-red-700 px-4 py-2">{error}</div>
        )}

        <div className="insta-surface-card mt-0 sm:mt-6 p-4 sm:p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <div className="flex items-center gap-3 text-lg font-semibold text-gray-900 dark:text-gray-100">
                <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                  <BookOpen className="w-6 h-6 text-[#7E22CE]" />
                </div>
                <span>Service categories</span>
              </div>
            </div>
          </div>

          <div className="mt-2 space-y-4">
            <p className="text-gray-600 dark:text-gray-400 mt-1 mb-2">Select the service categories you teach</p>

            <div className="mb-3">
              <input
                type="text"
                value={skillsFilter}
                onChange={(event) => setSkillsFilter(event.target.value)}
                placeholder="Search skills..."
                className="w-full rounded-md border border-gray-200 dark:border-gray-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0]"
              />
            </div>

            {selected.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-2">
                {selected.map((service) => (
                  <span
                    key={`selected-${service.catalog_service_id}`}
                    className="inline-flex items-center gap-2 rounded-full border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 h-8 text-xs min-w-0"
                  >
                    <span className="truncate max-w-[14rem]" title={service.name}>
                      {service.name}
                    </span>
                    <button
                      type="button"
                      aria-label={`Remove ${service.name}`}
                      title={
                        isInstructorLive && selected.length <= 1
                          ? 'Live instructors must have at least one skill'
                          : `Remove ${service.name}`
                      }
                      className={`ml-auto rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center no-hover-shadow shrink-0 ${
                        isInstructorLive && selected.length <= 1
                          ? 'text-gray-300 cursor-not-allowed'
                          : 'text-[#7E22CE] hover:bg-purple-50 dark:hover:bg-purple-900/30'
                      }`}
                      onClick={() => removeService(service.catalog_service_id)}
                    >
                      &times;
                    </button>
                  </span>
                ))}
              </div>
            )}

            {skillsFilter.trim().length > 0 && (
              <div className="mb-3">
                <div className="text-sm text-gray-700 dark:text-gray-300 mb-2">Results</div>
                <div className="flex flex-wrap gap-2">
                  {allCatalogServices
                    .filter((service) =>
                      service.name.toLowerCase().includes(skillsFilter.toLowerCase())
                    )
                    .slice(0, 200)
                    .map((service) => {
                      const selectedFlag = selected.some(
                        (selectedService) =>
                          selectedService.catalog_service_id === service.id
                      );
                      return (
                        <button
                          key={`global-${service.id}`}
                          type="button"
                          onClick={() => toggleService(service)}
                          aria-pressed={selectedFlag}
                          className={`inline-flex items-center justify-between px-3 py-1.5 text-sm rounded-full font-semibold focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 transition-colors no-hover-shadow appearance-none overflow-hidden ${
                            selectedFlag
                              ? 'bg-[#7E22CE] text-white border border-[#7E22CE] hover:bg-purple-800 dark:hover:bg-purple-700'
                              : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                          }`}
                        >
                          <span className="truncate text-left">{service.name}</span>
                          <span className="ml-2">{selectedFlag ? '✓' : '+'}</span>
                        </button>
                      );
                    })}
                  {allCatalogServices.filter((service) =>
                    service.name.toLowerCase().includes(skillsFilter.toLowerCase())
                  ).length === 0 && (
                    <div className="text-sm text-gray-500 dark:text-gray-400">No matches found</div>
                  )}
                </div>
              </div>
            )}

            {categories.map((category) => {
              const isCollapsed = collapsed[category.id] === true;
              const categoryGroups = groupedServicesByCategory[category.id] ?? [];
              const hideSingleSubcategoryLabel =
                categoryGroups.length === 1 &&
                categoryGroups[0] &&
                categoryGroups[0].subcategory_name.trim().toLowerCase() ===
                  category.name.trim().toLowerCase();

              return (
                <div
                  key={category.id}
                  className="rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800"
                >
                  <button
                    className="w-full px-4 py-3 flex items-center justify-between text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                    onClick={() =>
                      setCollapsed((previous) => ({
                        ...previous,
                        [category.id]: !isCollapsed,
                      }))
                    }
                  >
                    <span className="font-bold">{category.name}</span>
                    <svg
                      className={`h-4 w-4 text-gray-600 dark:text-gray-400 transition-transform ${
                        isCollapsed ? '' : 'rotate-180'
                      }`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M19 9l-7 7-7-7"
                      />
                    </svg>
                  </button>

                  {!isCollapsed && (
                    <div className="p-4 space-y-4">
                      {categoryGroups.length === 0 ? (
                        <div className="text-sm text-gray-500 dark:text-gray-400">
                          No services available in this category yet.
                        </div>
                      ) : (
                        categoryGroups.map((group) => {
                          const collapseKey = subcategoryCollapseKey(
                            category.id,
                            group.subcategory_id
                          );
                          const isSubcategoryCollapsed =
                            collapsedSubcategories[collapseKey] === true;
                          const shouldRenderServices =
                            hideSingleSubcategoryLabel || !isSubcategoryCollapsed;

                          return (
                            <div
                              key={`${category.id}-${group.subcategory_id}`}
                              className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-2 space-y-2"
                            >
                              {!hideSingleSubcategoryLabel && (
                                <button
                                  type="button"
                                  aria-expanded={!isSubcategoryCollapsed}
                                  aria-controls={`subcategory-services-${collapseKey}`}
                                  aria-label={`Toggle subcategory ${group.subcategory_name}`}
                                  onClick={() =>
                                    setCollapsedSubcategories((previous) => ({
                                      ...previous,
                                      [collapseKey]: !(previous[collapseKey] ?? false),
                                    }))
                                  }
                                  className="w-full px-1 py-1.5 flex items-center justify-between text-left text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-md transition-colors"
                                >
                                  <span className="text-xs font-semibold text-gray-500 dark:text-gray-400">
                                    {toTitle(group.subcategory_name)}
                                  </span>
                                  <svg
                                    className={`h-4 w-4 text-gray-500 dark:text-gray-400 transition-transform ${
                                      isSubcategoryCollapsed ? '' : 'rotate-180'
                                    }`}
                                    fill="none"
                                    stroke="currentColor"
                                    viewBox="0 0 24 24"
                                  >
                                    <path
                                      strokeLinecap="round"
                                      strokeLinejoin="round"
                                      strokeWidth="2"
                                      d="M19 9l-7 7-7-7"
                                    />
                                  </svg>
                                </button>
                              )}
                              {shouldRenderServices && (
                                <div
                                  id={`subcategory-services-${collapseKey}`}
                                  className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3"
                                >
                                  {group.services.map((service) => {
                                    const selectedFlag = selected.some(
                                      (selectedService) =>
                                        selectedService.catalog_service_id === service.id
                                    );
                                    return (
                                      <button
                                        key={service.id}
                                        type="button"
                                        aria-label={`${selectedFlag ? 'Remove' : 'Add'} service ${service.name}`}
                                        onClick={() => toggleService(service)}
                                        className={`inline-flex items-center justify-between px-3 py-1.5 text-sm rounded-full font-semibold focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 transition-colors no-hover-shadow appearance-none overflow-hidden ${
                                          selectedFlag
                                            ? 'bg-[#7E22CE] text-white border border-[#7E22CE] hover:bg-purple-800 dark:hover:bg-purple-700'
                                            : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                                        }`}
                                      >
                                        <span className="truncate text-left">{service.name}</span>
                                        <span className="ml-2">
                                          {selectedFlag ? '✓' : '+'}
                                        </span>
                                      </button>
                                    );
                                  })}
                                </div>
                              )}
                            </div>
                          );
                        })
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="insta-onboarding-divider" />

        <div className="insta-surface-card mt-0 sm:mt-8 p-4 sm:p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <div className="flex items-center gap-3 text-lg font-semibold text-gray-900 dark:text-gray-100">
                <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                  <CheckSquare className="w-6 h-6 text-[#7E22CE]" />
                </div>
                <span>Your selected skills</span>
              </div>
            </div>
          </div>

          {selected.length === 0 ? (
            <p className="text-gray-500 dark:text-gray-400">You can add skills now or later.</p>
          ) : (
            <div className="grid gap-4">
              {selected.map((service) => {
                const serviceViolationsMap = pricingFloors
                  ? formatViolationsByService.get(service.catalog_service_id)
                  : undefined;

                // Build per-format error strings for FormatPricingCards
                const formatErrors: Partial<Record<ServiceFormat, string>> = {};
                if (serviceViolationsMap) {
                  for (const [fmt, violations] of serviceViolationsMap) {
                    const first = violations[0];
                    if (first) {
                      formatErrors[fmt] = `Min $${formatCents(first.floorCents)} for ${first.duration}min (current $${formatCents(first.baseCents)})`;
                    }
                  }
                }
                const maxRateErrors = maxRateErrorsByService.get(service.catalog_service_id);
                if (maxRateErrors) {
                  Object.assign(formatErrors, maxRateErrors);
                }

                const selectedAgeGroups = normalizeAudienceGroups(
                  service.filter_selections['age_groups'],
                  service.eligible_age_groups
                );
                const selectedSkillLevels = normalizeSkillLevels(
                  service.filter_selections['skill_level']
                );

                return (
                  <div
                    key={service.catalog_service_id}
                    className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 p-5 hover:shadow-sm transition-shadow"
                  >
                    <div className="flex items-start justify-between mb-4">
                      <div>
                        <div className="text-lg font-medium text-gray-900 dark:text-gray-100">{service.name}</div>
                      </div>

                      <button
                        aria-label="Remove skill"
                        title={
                          isInstructorLive && selected.length <= 1
                            ? 'Live instructors must have at least one skill'
                            : 'Remove skill'
                        }
                        className={`w-8 h-8 flex items-center justify-center rounded-full bg-white dark:bg-gray-800 border transition-colors ${
                          isInstructorLive && selected.length <= 1
                            ? 'border-gray-200 dark:border-gray-700 text-gray-300 cursor-not-allowed'
                            : 'border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-red-50 dark:hover:bg-red-900/30 hover:text-red-600 dark:hover:text-red-400 hover:border-red-300 dark:hover:border-red-500'
                        }`}
                        onClick={() => removeService(service.catalog_service_id)}
                      >
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth="2"
                            d="M6 18L18 6M6 6l12 12"
                          />
                        </svg>
                      </button>
                    </div>

                    <div className="mb-4">
                      <FormatPricingCards
                        formatPrices={service.format_prices}
                        onChange={(next) =>
                          updateSelectedService(
                            service.catalog_service_id,
                            (currentService) => ({
                              ...currentService,
                              format_prices: next,
                            })
                          )
                        }
                        priceFloors={pricingFloors}
                        durationOptions={service.duration_options}
                        takeHomePct={instructorTakeHomePct}
                        platformFeeLabel={platformFeeLabel}
                        {...(Object.keys(formatErrors).length > 0
                          ? { formatErrors }
                          : {})}
                        {...(!effectiveHasServiceAreas
                          ? {
                              studentLocationDisabled: true,
                              studentLocationDisabledReason:
                                'Add service areas below to enable this format',
                            }
                          : {})}
                      />

                      {Object.keys(service.format_prices).length === 0 && (
                        <p className="text-xs text-red-600 mt-2">
                          Enable at least one lesson format for this skill.
                        </p>
                      )}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
                      <div className="bg-white dark:bg-gray-800 rounded-lg p-3 border border-gray-200 dark:border-gray-700">
                        <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2 block">
                          Age groups
                        </label>
                        <div className="grid grid-cols-2 gap-2">
                          {ALL_AUDIENCE_GROUPS.map((ageGroup) => {
                            const isEligible = service.eligible_age_groups.includes(ageGroup);
                            const isSelected = selectedAgeGroups.includes(ageGroup);

                            return (
                              <button
                                key={`${service.catalog_service_id}-age-${ageGroup}`}
                                type="button"
                                disabled={!isEligible}
                                onClick={() => {
                                  if (!isEligible) {
                                    return;
                                  }
                                  const candidate = isSelected
                                    ? selectedAgeGroups.filter((value) => value !== ageGroup)
                                    : [...selectedAgeGroups, ageGroup];

                                  const ordered = ALL_AUDIENCE_GROUPS.filter((value) =>
                                    candidate.includes(value)
                                  );
                                  setServiceFilterValues(
                                    service.catalog_service_id,
                                    'age_groups',
                                    ordered
                                  );
                                }}
                                className={`px-2 py-2 text-sm rounded-md border transition-colors ${
                                  !isEligible
                                    ? 'bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-300 border-gray-200 dark:border-gray-700 cursor-not-allowed opacity-70'
                                    : isSelected
                                    ? 'bg-purple-100 text-[#7E22CE] border-purple-300'
                                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 border-transparent'
                                }`}
                              >
                                {AUDIENCE_LABELS[ageGroup]}
                              </button>
                            );
                          })}
                        </div>
                      </div>

                      <div className="bg-white dark:bg-gray-800 rounded-lg p-3 border border-gray-200 dark:border-gray-700">
                        <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2 block">
                          Session duration
                        </label>
                        <div className="flex gap-1">
                          {[30, 45, 60, 90].map((duration) => (
                            <button
                              key={`${service.catalog_service_id}-duration-${duration}`}
                              type="button"
                              onClick={() =>
                                updateSelectedService(
                                  service.catalog_service_id,
                                  (currentService) => {
                                    const hasDuration = currentService.duration_options.includes(
                                      duration
                                    );
                                    if (
                                      hasDuration &&
                                      currentService.duration_options.length === 1
                                    ) {
                                      return currentService;
                                    }

                                    const nextDurations = hasDuration
                                      ? currentService.duration_options.filter(
                                          (value) => value !== duration
                                        )
                                      : [...currentService.duration_options, duration];

                                    return {
                                      ...currentService,
                                      duration_options: nextDurations,
                                    };
                                  }
                                )
                              }
                              className={`flex-1 px-2 py-2 text-sm rounded-md transition-colors ${
                                service.duration_options.includes(duration)
                                  ? 'bg-purple-100 text-[#7E22CE] border border-purple-300'
                                  : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                              }`}
                            >
                              {duration}m
                            </button>
                          ))}
                        </div>
                      </div>

                      <div className="bg-white dark:bg-gray-800 rounded-lg p-3 border border-gray-200 dark:border-gray-700">
                        <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2 block">
                          Skill level
                        </label>
                        <div className="flex gap-1">
                          {DEFAULT_SKILL_LEVELS.map((level) => {
                            const isSelected = selectedSkillLevels.includes(level);
                            return (
                              <button
                                key={`${service.catalog_service_id}-level-${level}`}
                                type="button"
                                onClick={() => {
                                  if (isSelected && selectedSkillLevels.length === 1) {
                                    return;
                                  }
                                  const candidate = isSelected
                                    ? selectedSkillLevels.filter(
                                        (value) => value !== level
                                      )
                                    : [...selectedSkillLevels, level];
                                  const ordered = DEFAULT_SKILL_LEVELS.filter((value) =>
                                    candidate.includes(value)
                                  );
                                  setServiceFilterValues(
                                    service.catalog_service_id,
                                    'skill_level',
                                    ordered
                                  );
                                }}
                                className={`flex-1 px-2 py-2 text-sm rounded-md transition-colors ${
                                  isSelected
                                    ? 'bg-purple-100 text-[#7E22CE] border border-purple-300'
                                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                                }`}
                              >
                                {level === 'beginner'
                                  ? 'Beginner'
                                  : level === 'intermediate'
                                  ? 'Intermediate'
                                  : 'Advanced'}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    </div>

                    <div className="mb-4">
                      <RefineFiltersSection
                        service={service}
                        expanded={
                          refineExpandedByService[service.catalog_service_id] === true
                        }
                        onToggleExpanded={(serviceId) =>
                          setRefineExpandedByService((previous) => ({
                            ...previous,
                            [serviceId]: !previous[serviceId],
                          }))
                        }
                        onInitializeMissingFilters={initializeMissingFilters}
                        onSetFilterValues={setServiceFilterValues}
                      />
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1 block">
                          Description (optional)
                        </label>
                        <textarea
                          rows={2}
                          className="w-full rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500 bg-white dark:bg-gray-800"
                          placeholder="Brief description of your teaching style..."
                          value={service.description || ''}
                          onChange={(event) =>
                            updateSelectedService(
                              service.catalog_service_id,
                              (currentService) => ({
                                ...currentService,
                                description: event.target.value,
                              })
                            )
                          }
                        />
                      </div>

                      <div>
                        <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1 block">
                          Equipment (optional)
                        </label>
                        <textarea
                          rows={2}
                          className="w-full rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500 bg-white dark:bg-gray-800"
                          placeholder="Yoga mat, tennis racket..."
                          value={service.equipment || ''}
                          onChange={(event) =>
                            updateSelectedService(
                              service.catalog_service_id,
                              (currentService) => ({
                                ...currentService,
                                equipment: event.target.value,
                              })
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

        {/* Service Areas — shown when any service has student_location enabled */}
        {anyServiceUsesStudentLocation && (
          <div className="mt-6">
            <div className="insta-onboarding-divider" />
            <ServiceAreasCard
              context="onboarding"
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
          </div>
        )}

        {/* Preferred Locations — shown when any service has instructor_location enabled */}
        {anyServiceUsesInstructorLocation && (
          <div className="mt-6">
            <div className="insta-onboarding-divider" />
            <PreferredLocationsCard
              context="onboarding"
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
          </div>
        )}

        <div className="insta-surface-card mt-0 sm:mt-8 p-4 sm:p-6">
          <div className="flex items-start justify-between mb-2">
            <div>
              <div className="flex items-center gap-3 text-lg font-semibold text-gray-900 dark:text-gray-100">
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
              onChange={(event) => setRequestText(event.target.value)}
              placeholder="Type your skill here..."
              className="flex-1 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20"
            />
            <button
              onClick={submitServiceRequest}
              disabled={!requestText.trim() || requestSubmitting}
              className="insta-primary-btn px-4 py-2 rounded-lg text-white disabled:opacity-50 shadow-sm"
            >
              Submit request
            </button>
          </div>
          {requestSuccess && <div className="mt-2 text-sm text-gray-900 dark:text-gray-100">{requestSuccess}</div>}
        </div>

        <div className="mt-8 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={() => {
              window.location.href = '/instructor/onboarding/verification';
            }}
            className="insta-secondary-btn w-40 px-5 py-2.5 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 justify-center"
          >
            Skip for now
          </button>
          <button
            onClick={save}
            disabled={saving || hasFloorViolations || hasRateCapViolations}
            className="insta-primary-btn w-56 whitespace-nowrap px-5 py-2.5 rounded-lg text-white disabled:opacity-50 shadow-sm justify-center"
          >
            {saving ? 'Saving...' : 'Save & Continue'}
          </button>
        </div>
      </div>
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
