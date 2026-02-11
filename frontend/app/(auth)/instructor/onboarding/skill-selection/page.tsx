'use client';

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { BookOpen, CheckSquare, Lightbulb } from 'lucide-react';
import { useSearchParams } from 'next/navigation';
import { useAuth } from '@/features/shared/hooks/useAuth';
import type {
  ApiErrorResponse,
  CategoryServiceDetail,
  ServiceCategory,
  SubcategoryFilterResponse,
} from '@/features/shared/api/types';
import { logger } from '@/lib/logger';
import { submitSkillRequest } from '@/lib/api/skillRequest';
import { usePricingConfig } from '@/lib/pricing/usePricingFloors';
import { FloorViolation, evaluatePriceFloorViolations, formatCents } from '@/lib/pricing/priceFloors';
import { formatPlatformFeeLabel, resolvePlatformFeeRate, resolveTakeHomePct } from '@/lib/pricing/platformFees';
import { OnboardingProgressHeader } from '@/features/instructor-onboarding/OnboardingProgressHeader';
import { useOnboardingStepStatus } from '@/features/instructor-onboarding/useOnboardingStepStatus';
import { usePlatformFees } from '@/hooks/usePlatformConfig';
import { useAllServicesWithInstructors, useServiceCategories } from '@/hooks/queries/useServices';
import { useCategoriesWithSubcategories, useSubcategoryFilters } from '@/hooks/queries/useTaxonomy';
import { formatFilterLabel } from '@/lib/taxonomy/formatFilterLabel';
import type { ServiceLocationType } from '@/types/instructor';
import { queryKeys } from '@/src/api/queryKeys';
import { ToggleSwitch } from '@/components/ui/ToggleSwitch';
import { toast } from 'sonner';

const ALL_AUDIENCE_GROUPS = ['toddler', 'kids', 'teens', 'adults'] as const;
type AudienceGroup = (typeof ALL_AUDIENCE_GROUPS)[number];

const DEFAULT_SKILL_LEVELS = ['beginner', 'intermediate', 'advanced'] as const;
type SkillLevel = (typeof DEFAULT_SKILL_LEVELS)[number];

type FilterSelections = Record<string, string[]>;

type SelectedService = {
  catalog_service_id: string;
  subcategory_id: string;
  name: string;
  hourly_rate: string; // keep as string for input control
  description?: string;
  equipment?: string; // comma-separated freeform for UI
  filter_selections: FilterSelections;
  eligible_age_groups: AudienceGroup[];
  duration_options: number[];
  offers_travel: boolean;
  offers_at_location: boolean;
  offers_online: boolean;
};

type ServiceCapabilities = Pick<
  SelectedService,
  'offers_travel' | 'offers_at_location' | 'offers_online'
>;

type CategoryServiceGroup = {
  subcategory_id: string;
  subcategory_name: string;
  services: CategoryServiceDetail[];
};

const subcategoryCollapseKey = (categoryId: string, subcategoryId: string): string =>
  `${categoryId}__${subcategoryId}`;

const AUDIENCE_LABELS: Record<AudienceGroup, string> = {
  toddler: 'Toddler',
  kids: 'Kids',
  teens: 'Teens',
  adults: 'Adults',
};

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

const toAudienceGroup = (value: unknown): AudienceGroup | null => {
  if (typeof value !== 'string') {
    return null;
  }
  const normalized = value.trim().toLowerCase();
  if (ALL_AUDIENCE_GROUPS.includes(normalized as AudienceGroup)) {
    return normalized as AudienceGroup;
  }
  return null;
};

const dedupeAudienceGroups = (groups: AudienceGroup[]): AudienceGroup[] => {
  const groupSet = new Set(groups);
  return ALL_AUDIENCE_GROUPS.filter((group) => groupSet.has(group));
};

const normalizeAudienceGroups = (
  value: unknown,
  fallback: AudienceGroup[] = []
): AudienceGroup[] => {
  const fallbackGroups = dedupeAudienceGroups(fallback);
  if (!Array.isArray(value)) {
    return fallbackGroups;
  }

  const normalized = dedupeAudienceGroups(
    value
      .map((entry) => toAudienceGroup(entry))
      .filter((entry): entry is AudienceGroup => entry !== null)
  );

  return normalized.length > 0 ? normalized : fallbackGroups;
};

const normalizeSkillLevels = (
  value: unknown,
  fallback: SkillLevel[] = [...DEFAULT_SKILL_LEVELS]
): SkillLevel[] => {
  if (!Array.isArray(value)) {
    return [...fallback];
  }

  const normalized = value
    .map((entry) => (typeof entry === 'string' ? entry.trim().toLowerCase() : ''))
    .filter((entry): entry is SkillLevel =>
      DEFAULT_SKILL_LEVELS.includes(entry as SkillLevel)
    );

  const unique = DEFAULT_SKILL_LEVELS.filter((level) => normalized.includes(level));
  return unique.length > 0 ? unique : [...fallback];
};

const normalizeSelectionValues = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  const normalized = value
    .map((entry) => (typeof entry === 'string' ? entry.trim() : String(entry).trim()))
    .filter((entry) => entry.length > 0);
  return Array.from(new Set(normalized));
};

const normalizeFilterSelections = (value: unknown): FilterSelections => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }

  const result: FilterSelections = {};
  for (const [key, rawValues] of Object.entries(value as Record<string, unknown>)) {
    const normalized = normalizeSelectionValues(rawValues);
    if (normalized.length > 0) {
      result[key] = normalized;
    }
  }
  return result;
};

const defaultFilterSelections = (eligibleAgeGroups: AudienceGroup[]): FilterSelections => ({
  skill_level: [...DEFAULT_SKILL_LEVELS],
  age_groups:
    eligibleAgeGroups.length > 0 ? [...eligibleAgeGroups] : [...ALL_AUDIENCE_GROUPS],
});

const isNonEmptyString = (value: unknown): value is string =>
  typeof value === 'string' && value.trim().length > 0;

const getErrorMessage = (error: unknown, fallback: string): string => {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }
  return fallback;
};

const arraysEqual = (a: readonly string[], b: readonly string[]): boolean => {
  if (a.length !== b.length) {
    return false;
  }
  return a.every((value, index) => value === b[index]);
};

type RefineFiltersSectionProps = {
  service: SelectedService;
  expanded: boolean;
  onToggleExpanded: (serviceId: string) => void;
  onInitializeMissingFilters: (
    serviceId: string,
    defaults: FilterSelections
  ) => void;
  onSetFilterValues: (
    serviceId: string,
    filterKey: string,
    values: string[]
  ) => void;
};

function RefineFiltersSection({
  service,
  expanded,
  onToggleExpanded,
  onInitializeMissingFilters,
  onSetFilterValues,
}: RefineFiltersSectionProps) {
  const { data: subcategoryFilters = [], isLoading } = useSubcategoryFilters(
    service.subcategory_id
  );

  const additionalFilters = useMemo(
    () =>
      subcategoryFilters.filter((filter) => filter.filter_key !== 'skill_level'),
    [subcategoryFilters]
  );

  useEffect(() => {
    if (!additionalFilters.length) {
      return;
    }

    const defaults: FilterSelections = {};
    for (const filter of additionalFilters) {
      if (service.filter_selections[filter.filter_key]) {
        continue;
      }
      const allValues = (filter.options ?? []).map((option) => option.value);
      if (allValues.length > 0) {
        defaults[filter.filter_key] = allValues;
      }
    }

    if (Object.keys(defaults).length > 0) {
      onInitializeMissingFilters(service.catalog_service_id, defaults);
    }
  }, [
    additionalFilters,
    onInitializeMissingFilters,
    service.catalog_service_id,
    service.filter_selections,
  ]);

  if (!service.subcategory_id || additionalFilters.length === 0) {
    return null;
  }

  return (
    <div className="bg-white rounded-lg p-3 border border-gray-200">
      <div className="w-full flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-gray-900 select-text">
          Refine what you teach (optional)
        </p>
        <button
          type="button"
          onClick={() => onToggleExpanded(service.catalog_service_id)}
          aria-expanded={expanded}
          aria-controls={`refine-filters-${service.catalog_service_id}`}
          aria-label={`Toggle refine filters for ${service.name}`}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-gray-200 text-gray-600 hover:bg-gray-100"
        >
          <svg
            className={`h-4 w-4 transition-transform ${
              expanded ? 'rotate-180' : ''
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
      </div>

      {expanded && (
        <div id={`refine-filters-${service.catalog_service_id}`} className="mt-3 space-y-3">
          {isLoading ? (
            <div className="text-xs text-gray-500">Loading filters…</div>
          ) : (
            additionalFilters.map((filter: SubcategoryFilterResponse) => {
              const selectedValues = service.filter_selections[filter.filter_key] ?? [];
              const options = [...(filter.options ?? [])].sort(
                (a, b) => (a.display_order ?? 0) - (b.display_order ?? 0)
              );

              return (
                <div key={`${service.catalog_service_id}-${filter.filter_key}`}>
                  <p className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2">
                    {filter.filter_display_name}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {options.map((option) => {
                      const isSelected = selectedValues.includes(option.value);
                      return (
                        <button
                          key={option.id}
                          type="button"
                          onClick={() => {
                            let nextValues: string[];
                            if (filter.filter_type === 'single_select') {
                              nextValues = isSelected ? [] : [option.value];
                            } else {
                              const candidate = isSelected
                                ? selectedValues.filter((value) => value !== option.value)
                                : [...selectedValues, option.value];
                              nextValues = normalizeSelectionValues(candidate);
                            }
                            onSetFilterValues(
                              service.catalog_service_id,
                              filter.filter_key,
                              nextValues
                            );
                          }}
                          className={`px-2.5 py-1.5 text-xs rounded-md transition-colors ${
                            isSelected
                              ? 'bg-purple-100 text-[#7E22CE] border border-purple-300'
                              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                          }`}
                        >
                          {formatFilterLabel(option.value, option.display_name)}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

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
    data: allServicesResponse,
    isLoading: servicesLoading,
    error: servicesError,
  } = useAllServicesWithInstructors();
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

  const resolveCapabilitiesFromService = useCallback(
    (service: Record<string, unknown>): ServiceCapabilities => {
      return {
        offers_travel: service['offers_travel'] === true,
        offers_at_location: service['offers_at_location'] === true,
        offers_online: service['offers_online'] === true,
      };
    },
    []
  );

  const defaultCapabilities = useCallback((): ServiceCapabilities => {
    const defaultTravel = hasServiceAreas;
    const defaultAtLocation = hasTeachingLocations;
    return {
      offers_travel: defaultTravel,
      offers_at_location: defaultAtLocation,
      offers_online: !defaultTravel && !defaultAtLocation,
    };
  }, [hasServiceAreas, hasTeachingLocations]);

  const servicesByCategory = useMemo(() => {
    const map: Record<string, CategoryServiceDetail[]> = {};
    const categoryRows = allServicesResponse?.categories ?? [];
    for (const category of categoryRows) {
      map[category.id] = category.services ?? [];
    }
    return map;
  }, [allServicesResponse]);

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

  const floorViolationsByService = useMemo(() => {
    const map = new Map<string, FloorViolation[]>();
    if (!pricingFloors) {
      return map;
    }

    selected.forEach((service) => {
      const locationTypes = locationTypesFromCapabilities(service);
      if (!locationTypes.length) {
        return;
      }

      const violations = evaluatePriceFloorViolations({
        hourlyRate: Number(service.hourly_rate),
        durationOptions: service.duration_options ?? [60],
        locationTypes,
        floors: pricingFloors,
      });

      if (violations.length > 0) {
        map.set(service.catalog_service_id, violations);
      }
    });

    return map;
  }, [pricingFloors, selected]);

  const hasFloorViolations = floorViolationsByService.size > 0;

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
        const capabilities = resolveCapabilitiesFromService(service);
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
          hourly_rate: String(service['hourly_rate'] ?? ''),
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
          offers_travel: hasServiceAreas ? capabilities.offers_travel : false,
          offers_at_location: hasTeachingLocations
            ? capabilities.offers_at_location
            : false,
          offers_online: capabilities.offers_online,
        });

        return accumulator;
      },
      []
    );

    prefilledFromProfileRef.current = true;
    setSelected(mapped);
  }, [
    hasServiceAreas,
    hasTeachingLocations,
    isAuthenticated,
    rawData.profile?.services,
    resolveCapabilitiesFromService,
    serviceCatalogById,
    user,
  ]);

  useEffect(() => {
    if (hasServiceAreas && hasTeachingLocations) {
      return;
    }

    setSelected((previous) => {
      let changed = false;
      const next = previous.map((service) => {
        let updated = service;
        if (!hasServiceAreas && updated.offers_travel) {
          updated = { ...updated, offers_travel: false };
          changed = true;
        }
        if (!hasTeachingLocations && updated.offers_at_location) {
          updated = { ...updated, offers_at_location: false };
          changed = true;
        }
        return updated;
      });

      return changed ? next : previous;
    });
  }, [hasServiceAreas, hasTeachingLocations]);

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
        hourly_rate: '',
        description: '',
        equipment: '',
        filter_selections: defaultFilterSelections(eligibleAgeGroups),
        eligible_age_groups: eligibleAgeGroups,
        duration_options: [60],
        ...defaultCapabilities(),
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

      const hasInvalidCapabilities = selected.some((service) =>
        !hasAnyLocationOption({
          offers_travel: hasServiceAreas ? service.offers_travel : false,
          offers_at_location: hasTeachingLocations ? service.offers_at_location : false,
          offers_online: service.offers_online,
        })
      );

      if (hasInvalidCapabilities) {
        toast.error(
          'Select at least one way to offer this skill (travel, at your studio, or online)'
        );
        setSaving(false);
        return;
      }

      if (pricingFloors && hasFloorViolations) {
        const firstViolation = floorViolationsByService.entries().next();
        if (!firstViolation.done) {
          const [serviceId, violations] = firstViolation.value;
          const violation = violations[0];
          if (!violation) {
            setSaving(false);
            return;
          }

          const serviceName =
            selected.find((service) => service.catalog_service_id === serviceId)?.name ||
            'this service';

          setError(
            `Minimum price for a ${violation.modalityLabel} ${violation.duration}-minute private session is $${formatCents(violation.floorCents)} (current $${formatCents(violation.baseCents)}). Please update the rate for ${serviceName}.`
          );
          setSaving(false);
          return;
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
          await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ services: [] }),
          });
        } catch {
          logger.warn('Failed to clear services, continuing to next step');
        }

        if (typeof window !== 'undefined') {
          sessionStorage.setItem('skillsSkipped', 'true');
        }

        window.location.href = nextUrl;
        return;
      }

      const payload = {
        services: selected
          .filter((service) => service.hourly_rate.trim() !== '')
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
              hourly_rate: Number(service.hourly_rate),
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
              offers_travel: hasServiceAreas ? service.offers_travel : false,
              offers_at_location: hasTeachingLocations
                ? service.offers_at_location
                : false,
              offers_online: service.offers_online,
            };
          }),
      };

      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        try {
          const message = (await response.json()) as ApiErrorResponse;
          logger.warn('Save services failed, moving to verification', { message });
        } catch {
          logger.warn('Save services failed, moving to verification');
        }
        window.location.href = nextUrl;
        return;
      }

      await queryClient.invalidateQueries({ queryKey: queryKeys.instructors.me });
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem('skillsSkipped');
      }
      window.location.href = nextUrl;
    } catch (saveError) {
      logger.error('Save services failed', saveError);
      if (saveError instanceof TypeError) {
        window.location.href = redirectParam || '/instructor/onboarding/verification';
        return;
      }
      const message =
        saveError instanceof Error ? saveError.message : 'Failed to save';
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
    return <div className="p-8">Loading…</div>;
  }

  const showError = Boolean(error) && !isLocationCapabilityError(error ?? '');

  return (
    <div className="min-h-screen">
      <OnboardingProgressHeader activeStep="skill-selection" stepStatus={stepStatus} />

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        <div className="mb-4 sm:mb-6 bg-white border-0 rounded-none p-4 sm:rounded-lg sm:p-6 sm:border sm:border-gray-200">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            What do you teach?
          </h1>
          <p className="text-gray-600">
            Choose your skills and set your rates
          </p>
        </div>
        <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />

        {catalogLoadError && (
          <div className="mt-4 rounded-md bg-red-50 text-red-700 px-4 py-2">
            {catalogLoadError}
          </div>
        )}
        {showError && (
          <div className="mt-4 rounded-md bg-red-50 text-red-700 px-4 py-2">{error}</div>
        )}

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

            <div className="mb-3">
              <input
                type="text"
                value={skillsFilter}
                onChange={(event) => setSkillsFilter(event.target.value)}
                placeholder="Search skills..."
                className="w-full rounded-md border border-gray-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0]"
              />
            </div>

            {selected.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-2">
                {selected.map((service) => (
                  <span
                    key={`selected-${service.catalog_service_id}`}
                    className="inline-flex items-center gap-2 rounded-full border border-gray-300 bg-white px-3 h-8 text-xs min-w-0"
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
                          : 'text-[#7E22CE] hover:bg-purple-50'
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
                <div className="text-sm text-gray-700 mb-2">Results</div>
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
                              ? 'bg-[#7E22CE] text-white border border-[#7E22CE] hover:bg-[#7E22CE]'
                              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
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
                    <div className="text-sm text-gray-500">No matches found</div>
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
                  className="rounded-lg overflow-hidden border border-gray-200 bg-white"
                >
                  <button
                    className="w-full px-4 py-3 flex items-center justify-between text-gray-700 hover:bg-gray-50 transition-colors"
                    onClick={() =>
                      setCollapsed((previous) => ({
                        ...previous,
                        [category.id]: !isCollapsed,
                      }))
                    }
                  >
                    <span className="font-bold">{category.name}</span>
                    <svg
                      className={`h-4 w-4 text-gray-600 transition-transform ${
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
                        <div className="text-sm text-gray-500">
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
                              className="rounded-lg border border-gray-200 bg-white p-2 space-y-2"
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
                                  className="w-full px-1 py-1.5 flex items-center justify-between text-left text-gray-600 hover:bg-gray-50 rounded-md transition-colors"
                                >
                                  <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                                    {group.subcategory_name}
                                  </span>
                                  <svg
                                    className={`h-4 w-4 text-gray-500 transition-transform ${
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
                                            ? 'bg-[#7E22CE] text-white border border-[#7E22CE] hover:bg-[#7E22CE]'
                                            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
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

        <div className="sm:hidden h-px bg-gray-200/80 -mx-4" />

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
              {selected.map((service) => {
                const violations = pricingFloors
                  ? floorViolationsByService.get(service.catalog_service_id) ?? []
                  : [];

                const effectiveOffersTravel = hasServiceAreas
                  ? service.offers_travel
                  : false;
                const effectiveOffersAtLocation = hasTeachingLocations
                  ? service.offers_at_location
                  : false;

                const effectiveCapabilities: ServiceCapabilities = {
                  offers_travel: effectiveOffersTravel,
                  offers_at_location: effectiveOffersAtLocation,
                  offers_online: service.offers_online,
                };

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
                    className="rounded-lg border border-gray-200 bg-gray-50 p-5 hover:shadow-sm transition-shadow"
                  >
                    <div className="flex items-start justify-between mb-4">
                      <div>
                        <div className="text-lg font-medium text-gray-900">{service.name}</div>
                        <div className="flex items-center gap-3 mt-2">
                          <div className="flex items-center gap-1">
                            <span className="text-2xl font-bold text-[#7E22CE]">
                              ${service.hourly_rate || '0'}
                            </span>
                            <span className="text-sm text-gray-600">/hour</span>
                          </div>
                        </div>
                      </div>

                      <button
                        aria-label="Remove skill"
                        title={
                          isInstructorLive && selected.length <= 1
                            ? 'Live instructors must have at least one skill'
                            : 'Remove skill'
                        }
                        className={`w-8 h-8 flex items-center justify-center rounded-full bg-white border transition-colors ${
                          isInstructorLive && selected.length <= 1
                            ? 'border-gray-200 text-gray-300 cursor-not-allowed'
                            : 'border-gray-300 text-gray-600 hover:bg-red-50 hover:text-red-600 hover:border-red-300'
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
                            value={service.hourly_rate}
                            onChange={(event) =>
                              updateSelectedService(
                                service.catalog_service_id,
                                (currentService) => ({
                                  ...currentService,
                                  hourly_rate: event.target.value,
                                })
                              )
                            }
                          />
                          <span className="text-gray-500">/hr</span>
                        </div>
                      </div>

                      {service.hourly_rate && Number(service.hourly_rate) > 0 && (
                        <div className="mt-2 text-xs text-gray-600">
                          You&apos;ll earn{' '}
                          <span className="font-semibold text-[#7E22CE]">
                            ${Number(Number(service.hourly_rate) * instructorTakeHomePct).toFixed(2)}
                          </span>{' '}
                          after the {platformFeeLabel} platform fee
                        </div>
                      )}

                      {violations.length > 0 && (
                        <div className="mt-2 space-y-1 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                          {violations.map((violation, index) => (
                            <div
                              key={`${violation.modalityLabel}-${violation.duration}-${index}`}
                            >
                              Minimum for {violation.modalityLabel} {violation.duration}
                              -minute private session is ${formatCents(violation.floorCents)}
                              {' '}(current ${formatCents(violation.baseCents)}).
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
                      <div className="bg-white rounded-lg p-3 border border-gray-200">
                        <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">
                          Age Groups
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
                                    ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed opacity-70'
                                    : isSelected
                                    ? 'bg-purple-100 text-[#7E22CE] border-purple-300'
                                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200 border-transparent'
                                }`}
                              >
                                {AUDIENCE_LABELS[ageGroup]}
                              </button>
                            );
                          })}
                        </div>
                      </div>

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
                                      <p className="text-sm font-medium text-gray-700">
                                        I travel to students
                                      </p>
                                      <p className="text-xs text-gray-500">
                                        (Within your service areas)
                                      </p>
                                    </div>
                                    <ToggleSwitch
                                      checked={effectiveOffersTravel}
                                      onChange={() =>
                                        updateSelectedService(
                                          service.catalog_service_id,
                                          (currentService) => ({
                                            ...currentService,
                                            offers_travel: !currentService.offers_travel,
                                          })
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
                                      <p className="text-sm font-medium text-gray-700">
                                        Students come to me
                                      </p>
                                      <p className="text-xs text-gray-500">
                                        (At your teaching location)
                                      </p>
                                    </div>
                                    <ToggleSwitch
                                      checked={effectiveOffersAtLocation}
                                      onChange={() =>
                                        updateSelectedService(
                                          service.catalog_service_id,
                                          (currentService) => ({
                                            ...currentService,
                                            offers_at_location:
                                              !currentService.offers_at_location,
                                          })
                                        )
                                      }
                                      disabled={atLocationDisabled}
                                      ariaLabel="Students come to me"
                                      {...(atLocationMessage
                                        ? { title: atLocationMessage }
                                        : {})}
                                    />
                                  </div>
                                  {atLocationMessage && (
                                    <p className="mt-1 text-xs text-gray-500">
                                      {atLocationMessage}
                                    </p>
                                  )}
                                </div>

                                <div className="rounded-md border border-gray-200 p-3">
                                  <div className="flex items-start justify-between gap-3">
                                    <div>
                                      <p className="text-sm font-medium text-gray-700">
                                        Online lessons
                                      </p>
                                      <p className="text-xs text-gray-500">(Video call)</p>
                                    </div>
                                    <ToggleSwitch
                                      checked={service.offers_online}
                                      onChange={() =>
                                        updateSelectedService(
                                          service.catalog_service_id,
                                          (currentService) => ({
                                            ...currentService,
                                            offers_online: !currentService.offers_online,
                                          })
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

                      <div className="bg-white rounded-lg p-3 border border-gray-200">
                        <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">
                          Session Duration
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
                                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                              }`}
                            >
                              {duration}m
                            </button>
                          ))}
                        </div>
                      </div>

                      <div className="bg-white rounded-lg p-3 border border-gray-200">
                        <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-2 block">
                          Skill Level
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
                                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
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
                        <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-1 block">
                          Description (Optional)
                        </label>
                        <textarea
                          rows={2}
                          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500 bg-white"
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
                        <label className="text-xs font-medium text-gray-600 uppercase tracking-wide mb-1 block">
                          Equipment (Optional)
                        </label>
                        <textarea
                          rows={2}
                          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500 bg-white"
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
              onChange={(event) => setRequestText(event.target.value)}
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
          {requestSuccess && <div className="mt-2 text-sm text-gray-900">{requestSuccess}</div>}
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
