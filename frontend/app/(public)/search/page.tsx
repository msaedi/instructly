// frontend/app/(public)/search/page.tsx
'use client';

import { useEffect, useState, Suspense, useCallback, useRef, useMemo, useSyncExternalStore } from 'react';
import { createPortal } from 'react-dom';
import { useSearchParams, useRouter, usePathname } from 'next/navigation';
import Link from 'next/link';
import InstructorCard from '@/components/InstructorCard';
import dynamic from 'next/dynamic';
const InstructorCoverageMap = dynamic(() => import('@/components/maps/InstructorCoverageMap'), { ssr: false });
import { Instructor } from '@/types/api';
import { useBackgroundConfig } from '@/lib/config/backgroundProvider';
import { getString, getNumber, getArray, getBoolean, isRecord, isFeatureCollection } from '@/lib/typesafe';
import TimeSelectionModal from '@/features/student/booking/components/TimeSelectionModal';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { recordSearch } from '@/lib/searchTracking';
import { withApiBase } from '@/lib/apiBase';
import { fetchWithSessionRefresh } from '@/lib/auth/sessionRefresh';
import { SearchType } from '@/types/enums';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useInstructorSearchInfinite } from '@/hooks/queries/useInstructorSearch';
import { useInstructorCoverage } from '@/hooks/queries/useInstructorCoverage';
import { usePublicAvailability, type InstructorAvailabilitySummary } from '@/hooks/queries/usePublicAvailability';
import { useAllServicesWithInstructors } from '@/hooks/queries/useServices';
import { useCategoriesWithSubcategories, useSubcategoryFilters } from '@/hooks/queries/useTaxonomy';
import { AlertTriangle, ChevronDown } from 'lucide-react';
import { FilterBar } from '@/components/search/FilterBar';
import {
  type ContentFilterSelections,
  DEFAULT_FILTERS,
  UNIVERSAL_SKILL_LEVEL_OPTIONS,
  type FilterState,
  type SkillLevelOption,
} from '@/components/search/filterTypes';
import { CURRENT_AUDIENCE, type AudienceMode } from '@/lib/audience';
import { logger } from '@/lib/logger';
import {
  buildContentFiltersParam,
  buildSkillLevelParam,
  getDynamicContentFiltersFromSearchMeta,
  getDynamicContentFiltersFromTaxonomy,
  getSkillLevelOptionsFromTaxonomy,
  normalizeLookupKey,
  parseContentFiltersParam,
  parseSkillLevelParam,
  resolveSubcategoryContext,
  sanitizeContentFiltersForDefinitions,
  sanitizeContentFiltersForSubcategory,
  type SubcategoryResolutionLookup,
} from './filterContext';

const IS_TAXONOMY_DEBUG_ENABLED = process.env.NODE_ENV !== 'production';

type SortOption = 'recommended' | 'price_asc' | 'price_desc' | 'rating';
const SORT_OPTIONS: Array<{ value: SortOption; triggerLabel: string; menuLabel: string }> = [
  { value: 'recommended', triggerLabel: 'Recommended', menuLabel: 'Recommended' },
  { value: 'price_asc', triggerLabel: 'Price: Low', menuLabel: 'Price: Low to High' },
  { value: 'price_desc', triggerLabel: 'Price: High', menuLabel: 'Price: High to Low' },
  { value: 'rating', triggerLabel: 'Top Rated', menuLabel: 'Highest Rated' },
];

type AggregatedSearchData = {
  instructors: Instructor[];
  totalResults: number;
  nlSearchMeta: Record<string, unknown> | null;
};

function RateLimitBanner({ rateLimit }: { rateLimit: { seconds: number } | null }) {
  if (!rateLimit) return null;
  return (
    <div
      data-testid="rate-limit-banner"
      role="alert"
      className="mb-4 rounded-md bg-yellow-50 border border-yellow-200 text-yellow-900 px-3 py-2 text-sm"
    >
      Our hamsters are sprinting. Give them {rateLimit.seconds}s.
    </div>
  );
}


const getServiceDisplayName = (service: Instructor['services'][number]): string => {
  const candidates: Array<unknown> = [
    (service as { service_catalog_name?: unknown }).service_catalog_name,
    (service as { name?: unknown }).name,
    (service as { title?: unknown }).title,
  ];

  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim().length > 0) {
      return candidate.trim();
    }
  }

  return '';
};

// Note: normalizeProfileServices and mergeInstructorServices removed
// - Backend now returns all embedded data in NL search response
// - No need to hydrate or merge services from individual profile fetches

const dedupeAndOrderServices = (
  services: Instructor['services'],
  highlightCatalogId?: string | null
): Instructor['services'] => {
  if (!Array.isArray(services) || services.length === 0) {
    return [];
  }

  const seenKeys = new Map<string, Instructor['services'][number]>();
  const orderedKeys: string[] = [];

  services.forEach((service) => {
    if (!service) return;
    const catalogKey = (service.service_catalog_id || '').trim().toLowerCase();
    const nameKey = getServiceDisplayName(service).trim().toLowerCase();
    const idKey = (service.id || '').trim().toLowerCase();

    const key = catalogKey || nameKey || idKey;
    if (!key) return;

    if (!seenKeys.has(key)) {
      seenKeys.set(key, { ...service });
      orderedKeys.push(key);
    } else {
      const existing = seenKeys.get(key)!;
      if (!existing.service_catalog_name && service.service_catalog_name) {
        existing.service_catalog_name = service.service_catalog_name;
      }
      if (!existing.description && service.description) {
        existing.description = service.description;
      }
      if (
        (!existing.duration_options || existing.duration_options.length === 0) &&
        Array.isArray(service.duration_options) &&
        service.duration_options.length > 0
      ) {
        existing.duration_options = [...service.duration_options];
      }
      if (typeof existing.is_active !== 'boolean' && typeof service.is_active === 'boolean') {
        existing.is_active = service.is_active;
      }
      if (!existing.service_catalog_id && service.service_catalog_id) {
        existing.service_catalog_id = service.service_catalog_id;
      }
      if (!existing.id && service.id) {
        existing.id = service.id;
      }
    }
  });

  const highlightKey = highlightCatalogId ? highlightCatalogId.trim().toLowerCase() : null;
  if (highlightKey) {
    for (let i = 0; i < orderedKeys.length; i += 1) {
      const key = orderedKeys[i];
      if (!key) continue;
      const service = seenKeys.get(key);
      if (!service) continue;
      const catalogKey = (service.service_catalog_id || '').trim().toLowerCase();
      if (catalogKey === highlightKey) {
        if (i > 0) {
          orderedKeys.splice(i, 1);
          orderedKeys.unshift(key);
        }
        break;
      }
    }
  }

  return orderedKeys
    .map((key) => (key ? seenKeys.get(key) : undefined))
    .filter((svc): svc is Instructor['services'][number] => Boolean(svc));
};

const normalizeTeachingLocations = (
  locations: readonly unknown[]
): Array<{ approx_lat: number; approx_lng: number; neighborhood?: string }> => {
  return locations
    .map((loc) => {
      if (!isRecord(loc)) return null;
      const approxLat = getNumber(loc, 'approx_lat', Number.NaN);
      const approxLng = getNumber(loc, 'approx_lng', Number.NaN);
      if (!Number.isFinite(approxLat) || !Number.isFinite(approxLng)) return null;
      const neighborhood = getString(loc, 'neighborhood', '').trim();
      return {
        approx_lat: approxLat,
        approx_lng: approxLng,
        ...(neighborhood ? { neighborhood } : {}),
      };
    })
    .filter(
      (loc): loc is { approx_lat: number; approx_lng: number; neighborhood?: string } =>
        loc !== null
    );
};

const getOptionalBoolean = (record: Record<string, unknown>, key: string): boolean | undefined => {
  const value = record[key];
  return typeof value === 'boolean' ? value : undefined;
};

const normalizeStringSelections = (value: unknown): string[] =>
  Array.isArray(value)
    ? value
        .filter((item): item is string => typeof item === 'string')
        .map((item) => item.trim().toLowerCase())
        .filter(Boolean)
    : [];

const getFilterSelectionValues = (
  service: Instructor['services'][number] | null | undefined,
  key: string
): string[] => {
  if (!service || typeof service !== 'object') return [];
  const rawSelections = (service as { filter_selections?: unknown }).filter_selections;
  if (!rawSelections || typeof rawSelections !== 'object') return [];
  const value = (rawSelections as Record<string, unknown>)[key];
  return normalizeStringSelections(value);
};

const parseAudienceMode = (value: string | null): AudienceMode => {
  if (!value) return CURRENT_AUDIENCE;
  const normalized = value.trim().toLowerCase();
  if (
    normalized === 'toddler' ||
    normalized === 'kids' ||
    normalized === 'teens' ||
    normalized === 'adults'
  ) {
    return normalized;
  }
  return CURRENT_AUDIENCE;
};

type NormalizedSearchResult = {
  instructors: Instructor[];
  totalResults: number;
  hasMore: boolean;
  meta: Record<string, unknown> | null;
};

type NormalizeSearchInput =
  | {
      mode: 'nl';
      results: unknown[];
      meta?: unknown;
    }
  | {
      mode: 'catalog';
      results: unknown[];
      total: number;
      hasNext: boolean;
      serviceCatalogId?: string | null;
    };

const normalizeSearchResults = (input: NormalizeSearchInput): NormalizedSearchResult => {
  if (input.mode === 'nl') {
    const instructors = input.results
      .map((result: unknown) => {
        if (!isRecord(result)) {
          return null;
        }

        // Extract instructor-level data
        const instructorId = getString(result, 'instructor_id', '');
        const relevanceScore = getNumber(result, 'relevance_score', 0);

        // Extract embedded instructor info
        const instructorInfo = isRecord(result['instructor']) ? result['instructor'] : {};
        const firstName = getString(instructorInfo, 'first_name', 'Instructor');
        const lastInitial = getString(instructorInfo, 'last_initial', '');
        const bioSnippet = getString(instructorInfo, 'bio_snippet', '');
        const profilePictureUrl = getString(instructorInfo, 'profile_picture_url', '');
        const verified = Boolean(instructorInfo['verified']);
        const isFoundingInstructor = Boolean(instructorInfo['is_founding_instructor']);
        const yearsExperience = getNumber(instructorInfo, 'years_experience', 0);

        // Extract embedded rating info
        const ratingInfo = isRecord(result['rating']) ? result['rating'] : {};
        const avgRating = getNumber(ratingInfo, 'average', 0);
        const reviewCount = getNumber(ratingInfo, 'count', 0);

        // Extract coverage areas
        const coverageAreas = getArray(result, 'coverage_areas').filter(
          (v): v is string => typeof v === 'string'
        );

        const teachingLocations = getArray(instructorInfo, 'teaching_locations')
          .map((loc) => {
            if (!isRecord(loc)) return null;
            const approxLat = getNumber(loc, 'approx_lat', Number.NaN);
            const approxLng = getNumber(loc, 'approx_lng', Number.NaN);
            if (!Number.isFinite(approxLat) || !Number.isFinite(approxLng)) return null;
            const neighborhood = getString(loc, 'neighborhood', '').trim();
            return {
              approx_lat: approxLat,
              approx_lng: approxLng,
              ...(neighborhood ? { neighborhood } : {}),
            };
          })
          .filter(
            (loc): loc is { approx_lat: number; approx_lng: number; neighborhood?: string } =>
              loc !== null
          );

        // Optional debug distance from searched location (populated when location was resolved)
        const distanceMiRaw = getNumber(result, 'distance_mi', Number.NaN);
        const distanceMi = Number.isFinite(distanceMiRaw) ? distanceMiRaw : null;
        const distanceKmRaw = getNumber(result, 'distance_km', Number.NaN);
        const distanceKm = Number.isFinite(distanceKmRaw) ? distanceKmRaw : null;

        // Extract best matching service
        const bestMatch = isRecord(result['best_match']) ? result['best_match'] : {};
        const bestServiceId = getString(bestMatch, 'service_id', '');
        const bestServiceCatalogId = getString(bestMatch, 'service_catalog_id', '');
        const bestServiceName = getString(bestMatch, 'name', '');
        const bestServiceDescription = getString(bestMatch, 'description', '');
        const bestPricePerHour = getNumber(bestMatch, 'price_per_hour', 0);
        const bestOffersTravel = getOptionalBoolean(bestMatch, 'offers_travel');
        const bestOffersAtLocation = getOptionalBoolean(bestMatch, 'offers_at_location');
        const bestOffersOnline = getOptionalBoolean(bestMatch, 'offers_online');

        // Build services array from best_match + other_matches
        const services: Instructor['services'] = [];

        // Add best match as first service
        services.push({
          id: bestServiceId,
          service_catalog_id: bestServiceCatalogId,
          service_catalog_name: bestServiceName,
          hourly_rate: bestPricePerHour,
          description: bestServiceDescription,
          duration_options: [60],
          is_active: true,
          ...(bestOffersTravel !== undefined ? { offers_travel: bestOffersTravel } : {}),
          ...(bestOffersAtLocation !== undefined ? { offers_at_location: bestOffersAtLocation } : {}),
          ...(bestOffersOnline !== undefined ? { offers_online: bestOffersOnline } : {}),
        });

        // Add other matches
        const otherMatches = getArray(result, 'other_matches');
        for (const match of otherMatches) {
          if (!isRecord(match)) continue;
          const matchOffersTravel = getOptionalBoolean(match, 'offers_travel');
          const matchOffersAtLocation = getOptionalBoolean(match, 'offers_at_location');
          const matchOffersOnline = getOptionalBoolean(match, 'offers_online');
          services.push({
            id: getString(match, 'service_id', ''),
            service_catalog_id: getString(match, 'service_catalog_id', ''),
            service_catalog_name: getString(match, 'name', ''),
            hourly_rate: getNumber(match, 'price_per_hour', 0),
            description: getString(match, 'description', ''),
            duration_options: [60],
            is_active: true,
            ...(matchOffersTravel !== undefined ? { offers_travel: matchOffersTravel } : {}),
            ...(matchOffersAtLocation !== undefined ? { offers_at_location: matchOffersAtLocation } : {}),
            ...(matchOffersOnline !== undefined ? { offers_online: matchOffersOnline } : {}),
          });
        }

        const mapped = {
          id: instructorId,
          user_id: instructorId,
          bio: bioSnippet,
          profile_picture_url: profilePictureUrl,
          service_area_summary: coverageAreas.join(', '),
          service_area_boroughs: coverageAreas,
          service_area_neighborhoods: [] as Array<{
            neighborhood_id: string;
            ntacode: string | null;
            name: string | null;
            borough: string | null;
          }>,
          years_experience: yearsExperience,
          teaching_locations: teachingLocations,
          user: {
            first_name: firstName,
            last_initial: lastInitial,
          },
          is_founding_instructor: isFoundingInstructor,
          is_live: true,
          services,
          verified,
          rating: avgRating || undefined,
          total_reviews: reviewCount,
          distance_mi: distanceMi,
          distance_km: distanceKm,
          _matchedServiceContext: {
            skill_level: [] as string[],
            age_groups: [] as string[],
          },
          relevance_score: relevanceScore,
          _matchedServiceCatalogId: bestServiceCatalogId || null,
        } as Instructor & { relevance_score: number; _matchedServiceCatalogId?: string | null };

        return mapped;
      })
      .filter(
        (
          item:
            | (Instructor & { relevance_score: number; _matchedServiceCatalogId?: string | null })
            | null
        ): item is Instructor & { relevance_score: number; _matchedServiceCatalogId?: string | null } =>
          item !== null
      );

    const meta = isRecord(input.meta) ? input.meta : null;
    const totalResults = meta ? getNumber(meta, 'total_results', instructors.length) : instructors.length;
    return { instructors, totalResults, hasMore: false, meta };
  }

  const casted = input.results as unknown as Instructor[];
  const instructors = casted.map((item) => {
    const matchId = input.serviceCatalogId || null;
    const teachingLocationsRaw = getArray(item, 'teaching_locations');
    const preferredLocationsRaw = getArray(item, 'preferred_teaching_locations');
    const teachingLocations = normalizeTeachingLocations(
      teachingLocationsRaw.length ? teachingLocationsRaw : preferredLocationsRaw
    );
    const highlightedService = Array.isArray(item.services)
      ? item.services.find(
          (svc) =>
            (svc.service_catalog_id || '').trim().toLowerCase() ===
              (matchId || '').trim().toLowerCase()
        ) || item.services[0]
      : undefined;
    const skillLevels = getFilterSelectionValues(highlightedService, 'skill_level');
    const fallbackLevels = normalizeStringSelections(highlightedService?.levels_taught);
    const ageGroups = getFilterSelectionValues(highlightedService, 'age_groups');
    const fallbackAgeGroups = normalizeStringSelections(highlightedService?.age_groups);
    return {
      ...item,
      ...(teachingLocations.length ? { teaching_locations: teachingLocations } : {}),
      _matchedServiceCatalogId: matchId,
      _matchedServiceContext: {
        skill_level: skillLevels.length ? skillLevels : fallbackLevels,
        age_groups: ageGroups.length ? ageGroups : fallbackAgeGroups,
      },
    };
  });

  return {
    instructors,
    totalResults: input.total,
    hasMore: input.hasNext,
    meta: null,
  };
};

// Note: Instructor profile hydration removed - backend now returns all embedded data
// in NL search response (instructor info, ratings, coverage areas, services)

// GeoJSON feature interface for coverage areas
interface GeoJSONFeature {
  type: 'Feature';
  properties?: {
    instructors?: string[];
  };
  geometry?: {
    type: string;
    coordinates: unknown;
  } | null;
}

type MapFeatureCollection = {
  type: 'FeatureCollection';
  features: GeoJSONFeature[];
};

const getInstructorMinRate = (instructor: Instructor): number | null => {
  const services = Array.isArray(instructor.services) ? instructor.services : [];
  const rates = services
    .map((service) => service.hourly_rate)
    .filter((rate): rate is number => Number.isFinite(rate));
  if (rates.length === 0) return null;
  return Math.min(...rates);
};

const compareNullableNumbers = (a: number | null, b: number | null, direction: 'asc' | 'desc') => {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return direction === 'asc' ? a - b : b - a;
};

// Helper to build query with filters appended
const buildQueryWithFilters = (baseQuery: string, filters: FilterState): string => {
  let query = baseQuery.trim();

  // Remove existing filter keywords to avoid duplication
  const filterPatterns = [
    /\b(today|tomorrow|this week|next week)\b/gi,
    /\b(morning|afternoon|evening)\b/gi,
    /\b(online|in-person|in person|virtual)\b/gi,
    /\bunder \$?\d+\b/gi,
    /\babove \$?\d+\b/gi,
    /\$\d+\s*-\s*\$?\d+/gi,
  ];
  for (const pattern of filterPatterns) {
    query = query.replace(pattern, '').trim();
  }
  // Clean up extra spaces
  query = query.replace(/\s+/g, ' ').trim();

  // Append date filter
  if (filters.date) {
    const date = new Date(filters.date);
    if (!Number.isNaN(date.getTime())) {
      const monthName = date.toLocaleDateString('en-US', { month: 'long' });
      const day = date.getDate();
      query = `${query} on ${monthName} ${day}`;
    }
  }

  // Append time filters
  if (filters.timeOfDay.length > 0) {
    for (const time of filters.timeOfDay) {
      query = `${query} ${time}`;
    }
  }

  // Append location filter
  if (filters.location === 'online') {
    query = `${query} online`;
  } else if (filters.location === 'travels' || filters.location === 'studio') {
    query = `${query} in-person`;
  }

  // Append price filters
  if (filters.priceMin !== null && filters.priceMax !== null) {
    query = `${query} $${filters.priceMin}-$${filters.priceMax}`;
  } else if (filters.priceMax !== null) {
    query = `${query} under $${filters.priceMax}`;
  } else if (filters.priceMin !== null) {
    query = `${query} above $${filters.priceMin}`;
  }

  return query.trim();
};

const TIME_OF_DAY_RANGES: Record<'morning' | 'afternoon' | 'evening', [number, number]> = {
  morning: [6 * 60, 12 * 60],
  afternoon: [12 * 60, 17 * 60],
  evening: [17 * 60, 21 * 60],
};

const parseTimeToMinutes = (value?: string | null): number | null => {
  if (!value) return null;
  const [hoursRaw, minutesRaw] = value.split(':');
  const hours = Number.parseInt(hoursRaw ?? '', 10);
  const minutes = Number.parseInt(minutesRaw ?? '', 10);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return null;
  return hours * 60 + minutes;
};

const slotOverlapsRanges = (
  slot: { start_time: string; end_time: string },
  ranges: Array<[number, number]>
): boolean => {
  const start = parseTimeToMinutes(slot.start_time);
  const end = parseTimeToMinutes(slot.end_time);
  if (start === null || end === null) return false;
  const normalizedEnd = end <= start ? 24 * 60 : end;
  return ranges.some(([rangeStart, rangeEnd]) => start < rangeEnd && normalizedEnd > rangeStart);
};

const availabilityMatchesFilters = (
  availability: InstructorAvailabilitySummary | undefined,
  filters: FilterState
): boolean => {
  const hasDateFilter = Boolean(filters.date);
  const hasTimeFilter = filters.timeOfDay.length > 0;
  if (!hasDateFilter && !hasTimeFilter) return true;
  if (!availability) return true;

  const ranges = hasTimeFilter
    ? filters.timeOfDay.map((rangeKey) => TIME_OF_DAY_RANGES[rangeKey])
    : [];

  if (filters.date) {
    const day = availability.availabilityByDate?.[filters.date];
    if (!day || day.is_blackout) return false;
    if (!day.available_slots || day.available_slots.length === 0) return false;
    if (ranges.length === 0) return true;
    return day.available_slots.some((slot) => slotOverlapsRanges(slot, ranges));
  }

  const days = Object.values(availability.availabilityByDate || {});
  if (days.length === 0) return false;
  return days.some(
    (day) =>
      !day.is_blackout &&
      Array.isArray(day.available_slots) &&
      day.available_slots.some((slot) => slotOverlapsRanges(slot, ranges))
  );
};

function SearchPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { setActivity } = useBackgroundConfig();
  const { isAuthenticated } = useAuth();
  const headerRef = useRef<HTMLDivElement | null>(null);
  const lastSearchParamsRef = useRef<string>('');
  const [stackedViewportHeight, setStackedViewportHeight] = useState<number | null>(null);
  const [isStacked, setIsStacked] = useState<boolean>(false);
  const isAuthenticatedRef = useRef(isAuthenticated);
  useEffect(() => {
    isAuthenticatedRef.current = isAuthenticated;
  }, [isAuthenticated]);
  const [serviceSlug] = useState<string>('');
  const [showTimeSelection, setShowTimeSelection] = useState(false);
  const [timeSelectionContext, setTimeSelectionContext] = useState<Record<string, unknown> | null>(null);

  const observerRef = useRef<IntersectionObserver | null>(null);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const [hoveredInstructorId, setHoveredInstructorId] = useState<string | null>(null);
  const [focusedInstructorId, setFocusedInstructorId] = useState<string | null>(null);
  const [showScrollIndicator, setShowScrollIndicator] = useState(true);
  const [mapBounds, setMapBounds] = useState<unknown>(null);
  const [showSearchAreaButton, setShowSearchAreaButton] = useState(false);
  const [mapFilterIds, setMapFilterIds] = useState<string[] | null>(null);

  const boundsContains = useCallback((bounds: unknown, lat: number, lng: number): boolean => {
    if (!bounds || typeof bounds !== 'object') return false;

    const b = bounds as {
      _southWest?: { lat: number; lng: number };
      _northEast?: { lat: number; lng: number };
    };

    if (!b._southWest || !b._northEast) return false;

    return (
      lat >= b._southWest.lat &&
      lat <= b._northEast.lat &&
      lng >= b._southWest.lng &&
      lng <= b._northEast.lng
    );
  }, []);

  const featureHasPointInBounds = useCallback(
    (feature: GeoJSONFeature, bounds: unknown): boolean => {
      if (!feature.geometry || feature.geometry.type !== 'MultiPolygon') return false;
      const coordinates = feature.geometry.coordinates;
      if (!Array.isArray(coordinates)) return false;

      for (const polygon of coordinates) {
        if (!Array.isArray(polygon)) continue;
        for (const ring of polygon) {
          if (!Array.isArray(ring)) continue;
          for (const coord of ring) {
            if (!Array.isArray(coord) || coord.length < 2) continue;
            const lng = coord[0];
            const lat = coord[1];
            if (typeof lat !== 'number' || typeof lng !== 'number') continue;
            if (boundsContains(bounds, lat, lng)) return true;
          }
        }
      }

      return false;
    },
    [boundsContains]
  );


  const sortParam = (searchParams.get('sort') || 'recommended') as SortOption;
  const [sortOption, setSortOption] = useState<SortOption>(sortParam);
  const [showSortDropdown, setShowSortDropdown] = useState(false);
  const sortDropdownRef = useRef<HTMLDivElement>(null);
  const sortTriggerRef = useRef<HTMLButtonElement | null>(null);
  const sortMenuRef = useRef<HTMLDivElement | null>(null);
  const sortDropdownRafRef = useRef<number | null>(null);
  const sortOptionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [sortPosition, setSortPosition] = useState<{ top: number; left: number } | null>(null);
  const [activeSortIndex, setActiveSortIndex] = useState(-1);
  const isClient = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false
  );
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [liveAnnouncement, setLiveAnnouncement] = useState('');
  const selectedSortIndex = SORT_OPTIONS.findIndex((option) => option.value === sortOption);
  const sortListboxId = 'search-sort-listbox';
  const currentSortTriggerLabel =
    SORT_OPTIONS.find((option) => option.value === sortOption)?.triggerLabel ?? 'Recommended';

  const closeSortDropdown = useCallback((restoreFocus = false) => {
    setShowSortDropdown(false);
    setActiveSortIndex(-1);
    if (restoreFocus) {
      if (sortDropdownRafRef.current !== null) {
        cancelAnimationFrame(sortDropdownRafRef.current);
      }
      sortDropdownRafRef.current = requestAnimationFrame(() => {
        sortTriggerRef.current?.focus();
      });
    }
  }, []);

  useEffect(() => {
    return () => {
      if (sortDropdownRafRef.current !== null) {
        cancelAnimationFrame(sortDropdownRafRef.current);
      }
    };
  }, []);

  const openSortDropdown = useCallback(
    (preferredIndex?: number) => {
      if (sortTriggerRef.current) {
        const rect = sortTriggerRef.current.getBoundingClientRect();
        setSortPosition({
          top: rect.bottom + 8,
          left: rect.left,
        });
      }

      const fallbackIndex = selectedSortIndex >= 0 ? selectedSortIndex : 0;
      const nextIndex =
        typeof preferredIndex === 'number'
          ? Math.max(0, Math.min(preferredIndex, SORT_OPTIONS.length - 1))
          : fallbackIndex;

      setActiveSortIndex(nextIndex);
      setShowSortDropdown(true);
    },
    [selectedSortIndex]
  );

  const handleSortChange = useCallback((nextSort: SortOption) => {
    const params = new URLSearchParams(searchParams.toString());
    if (nextSort && nextSort !== 'recommended') {
      params.set('sort', nextSort);
    } else {
      params.delete('sort');
    }
    setSortOption(nextSort);
    const queryString = params.toString();
    router.push(queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
  }, [searchParams, pathname, router]);

  useEffect(() => {
    setSortOption(sortParam);
  }, [sortParam]);

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      const inButton = sortDropdownRef.current?.contains(target);
      const inMenu = sortMenuRef.current?.contains(target);
      if (!inButton && !inMenu) {
        closeSortDropdown();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [closeSortDropdown]);

  useEffect(() => {
    if (!showSortDropdown) return;

    const fallbackIndex = selectedSortIndex >= 0 ? selectedSortIndex : 0;
    const focusIndex = activeSortIndex >= 0 ? activeSortIndex : fallbackIndex;

    const rafId = requestAnimationFrame(() => {
      sortOptionRefs.current[focusIndex]?.focus();
    });

    return () => {
      cancelAnimationFrame(rafId);
    };
  }, [activeSortIndex, selectedSortIndex, showSortDropdown]);

  const selectSortOptionAtIndex = useCallback((index: number) => {
    const option = SORT_OPTIONS[index];
    if (!option) return;

    handleSortChange(option.value);
    closeSortDropdown(true);
  }, [closeSortDropdown, handleSortChange]);

  const handleSortToggle = useCallback(() => {
    if (showSortDropdown) {
      closeSortDropdown(true);
      return;
    }
    openSortDropdown();
  }, [closeSortDropdown, openSortDropdown, showSortDropdown]);

  const handleSortTriggerKeyDown = useCallback((event: React.KeyboardEvent<HTMLButtonElement>) => {
    const lastIndex = SORT_OPTIONS.length - 1;

    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (showSortDropdown) {
        closeSortDropdown(true);
      } else {
        openSortDropdown();
      }
      return;
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (showSortDropdown) {
        setActiveSortIndex((prev) => {
          const next = prev < 0 ? 0 : Math.min(prev + 1, lastIndex);
          return next;
        });
      } else {
        const start = selectedSortIndex >= 0 ? selectedSortIndex : -1;
        openSortDropdown(Math.min(start + 1, lastIndex));
      }
      return;
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (showSortDropdown) {
        setActiveSortIndex((prev) => {
          const next = prev < 0 ? lastIndex : Math.max(prev - 1, 0);
          return next;
        });
      } else {
        const start = selectedSortIndex >= 0 ? selectedSortIndex : SORT_OPTIONS.length;
        openSortDropdown(Math.max(start - 1, 0));
      }
      return;
    }

    if (event.key === 'Escape' && showSortDropdown) {
      event.preventDefault();
      closeSortDropdown(true);
    }
  }, [closeSortDropdown, openSortDropdown, selectedSortIndex, showSortDropdown]);

  const handleSortListboxKeyDown = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
    const lastIndex = SORT_OPTIONS.length - 1;

    if (event.key === 'Escape') {
      event.preventDefault();
      closeSortDropdown(true);
      return;
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveSortIndex((prev) => {
        if (prev < 0) return 0;
        return Math.min(prev + 1, lastIndex);
      });
      return;
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveSortIndex((prev) => {
        if (prev < 0) return lastIndex;
        return Math.max(prev - 1, 0);
      });
      return;
    }

    if (event.key === 'Home') {
      event.preventDefault();
      setActiveSortIndex(0);
      return;
    }

    if (event.key === 'End') {
      event.preventDefault();
      setActiveSortIndex(lastIndex);
      return;
    }

    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      const indexToSelect = activeSortIndex >= 0
        ? activeSortIndex
        : selectedSortIndex >= 0
          ? selectedSortIndex
          : 0;
      selectSortOptionAtIndex(indexToSelect);
    }
  }, [activeSortIndex, closeSortDropdown, selectedSortIndex, selectSortOptionAtIndex]);

  const searchParamsString = searchParams.toString();
  const query = searchParams.get('q') || '';
  const category = searchParams.get('category') || '';
  const serviceCatalogId = searchParams.get('service_catalog_id') || '';
  const serviceParam = searchParams.get('service') || '';
  const serviceNameFromUrl = searchParams.get('service_name') || '';
  const explicitSubcategoryId = searchParams.get('subcategory_id') || '';
  const subcategoryParam = searchParams.get('subcategory') || '';
  const activeAudience = parseAudienceMode(
    searchParams.get('audience') || searchParams.get('age_group')
  );
  const fromSource = searchParams.get('from') || '';
  const parsedSkillLevelFromUrl = useMemo(() => {
    const params = new URLSearchParams(searchParamsString);
    return parseSkillLevelParam(params.get('skill_level'));
  }, [searchParamsString]);
  const parsedContentFiltersFromUrl = useMemo(() => {
    const params = new URLSearchParams(searchParamsString);
    return parseContentFiltersParam(params.get('content_filters'));
  }, [searchParamsString]);

  const { data: categoriesWithSubcategories } = useCategoriesWithSubcategories();
  const { data: allServicesWithInstructors } = useAllServicesWithInstructors();

  const subcategoryLookup = useMemo<SubcategoryResolutionLookup>(() => {
    const subcategoryIds = new Set<string>();
    const subcategoryIdsByLower = new Map<string, string>();
    const subcategoryByName = new Map<string, string>();
    const serviceByCatalogId = new Map<string, string>();
    const serviceBySlug = new Map<string, string>();
    const serviceByName = new Map<string, string>();

    for (const categoryItem of categoriesWithSubcategories ?? []) {
      for (const subcategory of categoryItem.subcategories ?? []) {
        if (!subcategory?.id) continue;
        const subcategoryId = subcategory.id.trim();
        if (!subcategoryId) continue;
        subcategoryIds.add(subcategoryId);
        subcategoryIdsByLower.set(subcategoryId.toLowerCase(), subcategoryId);
        if (subcategory.name) {
          subcategoryByName.set(normalizeLookupKey(subcategory.name), subcategoryId);
        }
      }
    }

    for (const categoryItem of allServicesWithInstructors?.categories ?? []) {
      for (const service of categoryItem.services ?? []) {
        const subcategoryId = service.subcategory_id?.trim();
        if (!subcategoryId) continue;
        if (service.id) {
          serviceByCatalogId.set(service.id.trim().toLowerCase(), subcategoryId);
        }
        if (service.slug) {
          serviceBySlug.set(normalizeLookupKey(service.slug), subcategoryId);
        }
        if (service.name) {
          serviceByName.set(normalizeLookupKey(service.name), subcategoryId);
        }
      }
    }

    return {
      subcategoryIds,
      subcategoryIdsByLower,
      subcategoryByName,
      serviceByCatalogId,
      serviceBySlug,
      serviceByName,
    };
  }, [allServicesWithInstructors, categoriesWithSubcategories]);

  const { resolvedSubcategoryId, inferredSubcategoryId } = useMemo(
    () =>
      resolveSubcategoryContext({
        explicitSubcategoryId,
        subcategoryParam,
        serviceCatalogId,
        serviceParam,
        serviceName: serviceNameFromUrl,
        lookup: subcategoryLookup,
      }),
    [
      explicitSubcategoryId,
      subcategoryParam,
      serviceCatalogId,
      serviceParam,
      serviceNameFromUrl,
      subcategoryLookup,
    ]
  );

  const {
    data: resolvedSubcategoryFilters,
    isLoading: isSubcategoryFiltersLoading,
    error: subcategoryFiltersError,
  } = useSubcategoryFilters(resolvedSubcategoryId ?? '');

  const taxonomyContentFiltersFromSubcategory = useMemo(
    () =>
      resolvedSubcategoryId
        ? getDynamicContentFiltersFromTaxonomy(resolvedSubcategoryFilters)
        : [],
    [resolvedSubcategoryFilters, resolvedSubcategoryId]
  );

  useEffect(() => {
    if (!IS_TAXONOMY_DEBUG_ENABLED) return;
    logger.debug('[search:taxonomy] resolveSubcategoryContext', {
      explicitSubcategoryId,
      subcategoryParam,
      serviceCatalogId,
      serviceParam,
      serviceNameFromUrl,
      resolvedSubcategoryId,
      inferredSubcategoryId,
      lookupStats: {
        subcategoryCount: subcategoryLookup.subcategoryIds.size,
        serviceCatalogMappingCount: subcategoryLookup.serviceByCatalogId.size,
      },
    });
  }, [
    explicitSubcategoryId,
    inferredSubcategoryId,
    resolvedSubcategoryId,
    serviceCatalogId,
    serviceNameFromUrl,
    serviceParam,
    subcategoryLookup,
    subcategoryParam,
  ]);

  useEffect(() => {
    if (!IS_TAXONOMY_DEBUG_ENABLED) return;
    logger.debug('[search:taxonomy] useSubcategoryFilters', {
      resolvedSubcategoryId,
      isSubcategoryFiltersLoading,
      hasError: Boolean(subcategoryFiltersError),
      errorMessage:
        subcategoryFiltersError instanceof Error ? subcategoryFiltersError.message : null,
      filterKeys: (resolvedSubcategoryFilters ?? []).map((filter) => filter.filter_key),
    });
  }, [
    isSubcategoryFiltersLoading,
    resolvedSubcategoryFilters,
    resolvedSubcategoryId,
    subcategoryFiltersError,
  ]);

  useEffect(() => {
    if (!IS_TAXONOMY_DEBUG_ENABLED) return;
    logger.debug('[search:taxonomy] getDynamicContentFiltersFromTaxonomy', {
      resolvedSubcategoryId,
      taxonomyContentFilterKeys: taxonomyContentFiltersFromSubcategory.map((filter) => filter.key),
      taxonomyContentFilterCount: taxonomyContentFiltersFromSubcategory.length,
    });
  }, [resolvedSubcategoryId, taxonomyContentFiltersFromSubcategory]);

  const skillLevelOptions = useMemo<SkillLevelOption[]>(() => {
    if (!resolvedSubcategoryId) {
      return UNIVERSAL_SKILL_LEVEL_OPTIONS;
    }
    return getSkillLevelOptionsFromTaxonomy(resolvedSubcategoryFilters);
  }, [resolvedSubcategoryFilters, resolvedSubcategoryId]);

  const selectedSkillLevel = useMemo(() => {
    const allowedValues = new Set(skillLevelOptions.map((option) => option.value));
    return parsedSkillLevelFromUrl.filter((value) => allowedValues.has(value));
  }, [parsedSkillLevelFromUrl, skillLevelOptions]);

  const selectedContentFilters = useMemo(
    () => {
      if (!resolvedSubcategoryId) {
        return parsedContentFiltersFromUrl;
      }
      if (subcategoryFiltersError) {
        return parsedContentFiltersFromUrl;
      }
      if (!resolvedSubcategoryFilters || resolvedSubcategoryFilters.length === 0) {
        return parsedContentFiltersFromUrl;
      }
      return sanitizeContentFiltersForSubcategory(
        parsedContentFiltersFromUrl,
        resolvedSubcategoryFilters
      );
    },
    [
      parsedContentFiltersFromUrl,
      resolvedSubcategoryFilters,
      resolvedSubcategoryId,
      subcategoryFiltersError,
    ]
  );

  const filtersWithTaxonomy = useMemo<FilterState>(
    () => ({
      ...filters,
      skillLevel: selectedSkillLevel,
      contentFilters: selectedContentFilters,
    }),
    [filters, selectedContentFilters, selectedSkillLevel]
  );

  const builtSearchQuery = useMemo(() => {
    if (!query) return '';
    return buildQueryWithFilters(query, filters);
  }, [query, filters]);

  const skillLevelCsv = useMemo(
    () => buildSkillLevelParam(selectedSkillLevel, skillLevelOptions),
    [selectedSkillLevel, skillLevelOptions]
  );
  const contentFiltersParam = useMemo(
    () =>
      buildContentFiltersParam(
        selectedContentFilters,
        taxonomyContentFiltersFromSubcategory.map((filterDefinition) => filterDefinition.key)
      ),
    [selectedContentFilters, taxonomyContentFiltersFromSubcategory]
  );

  useEffect(() => {
    const params = new URLSearchParams(searchParamsString);
    let hasChanges = false;

    if (!params.get('subcategory_id') && resolvedSubcategoryId) {
      params.set('subcategory_id', resolvedSubcategoryId);
      hasChanges = true;
    }

    const existingSkillLevelParam = params.get('skill_level');
    if (skillLevelCsv) {
      if (existingSkillLevelParam !== skillLevelCsv) {
        params.set('skill_level', skillLevelCsv);
        hasChanges = true;
      }
    } else if (existingSkillLevelParam) {
      params.delete('skill_level');
      hasChanges = true;
    }

    const existingContentFiltersParam = params.get('content_filters');
    if (contentFiltersParam) {
      if (existingContentFiltersParam !== contentFiltersParam) {
        params.set('content_filters', contentFiltersParam);
        hasChanges = true;
      }
    } else if (existingContentFiltersParam) {
      params.delete('content_filters');
      hasChanges = true;
    }

    if (!hasChanges) return;

    const queryString = params.toString();
    router.replace(queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
  }, [
    contentFiltersParam,
    pathname,
    resolvedSubcategoryId,
    router,
    searchParamsString,
    skillLevelCsv,
  ]);

  const searchQueryEnabled = Boolean(builtSearchQuery || serviceCatalogId);
  const {
    data: searchResponse,
    error: searchError,
    isLoading: isSearchLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInstructorSearchInfinite({
    searchQuery: builtSearchQuery,
    serviceCatalogId,
    ...(resolvedSubcategoryId ? { subcategoryId: resolvedSubcategoryId } : {}),
    ...(skillLevelCsv ? { skillLevelCsv } : {}),
    ...(contentFiltersParam ? { contentFiltersParam } : {}),
    perPage: 20,
    enabled: searchQueryEnabled,
  });
  const loading = searchQueryEnabled ? isSearchLoading : false;
  const loadingMore = isFetchingNextPage;

  const { instructors, totalResults, nlSearchMeta } = useMemo<AggregatedSearchData>(() => {
    const pages = searchResponse?.pages ?? [];
    if (!searchQueryEnabled || pages.length === 0) {
      return { instructors: [], totalResults: 0, nlSearchMeta: null };
    }

    let total = 0;
    let totalSet = false;
    let meta: Record<string, unknown> | null = null;
    const combined: Instructor[] = [];

    pages.forEach((pageData) => {
      const normalized =
        pageData.mode === 'nl'
          ? normalizeSearchResults({
              mode: 'nl',
              results: pageData.data.results,
              meta: pageData.data.meta,
            })
          : normalizeSearchResults({
              mode: 'catalog',
              results: pageData.data.items,
              total: pageData.data.total,
              hasNext: pageData.data.has_next,
              serviceCatalogId,
            });

      if (!totalSet) {
        total = normalized.totalResults;
        totalSet = true;
      }
      if (!meta && normalized.meta) {
        meta = normalized.meta;
      }

      normalized.instructors.forEach((instructor) => {
        const highlightId =
          (instructor as { _matchedServiceCatalogId?: string | null })._matchedServiceCatalogId ?? null;
        const services = Array.isArray(instructor.services) ? instructor.services : [];
        const deduped = dedupeAndOrderServices(services, highlightId);
        combined.push({
          ...instructor,
          services: deduped,
        });
      });
    });

    return {
      instructors: combined,
      totalResults: totalSet ? total : combined.length,
      nlSearchMeta: meta,
    };
  }, [searchQueryEnabled, searchResponse, serviceCatalogId]);

  const taxonomyContentFiltersFromMeta = useMemo(
    () =>
      getDynamicContentFiltersFromSearchMeta(
        isRecord(nlSearchMeta) ? nlSearchMeta['available_content_filters'] : undefined
      ),
    [nlSearchMeta]
  );

  const hasResolvedSubcategoryFilterDefinitions = useMemo(
    () =>
      Boolean(resolvedSubcategoryId) &&
      !subcategoryFiltersError &&
      taxonomyContentFiltersFromSubcategory.length > 0,
    [resolvedSubcategoryId, subcategoryFiltersError, taxonomyContentFiltersFromSubcategory]
  );

  const taxonomyContentFilters = useMemo(
    () =>
      hasResolvedSubcategoryFilterDefinitions
        ? taxonomyContentFiltersFromSubcategory
        : taxonomyContentFiltersFromMeta,
    [
      hasResolvedSubcategoryFilterDefinitions,
      taxonomyContentFiltersFromMeta,
      taxonomyContentFiltersFromSubcategory,
    ]
  );

  const inferredContentFiltersFromMeta = useMemo<ContentFilterSelections>(() => {
    if (!isRecord(nlSearchMeta) || !isRecord(nlSearchMeta['inferred_filters'])) {
      return {};
    }

    const normalized: ContentFilterSelections = {};
    for (const [rawKey, rawValues] of Object.entries(nlSearchMeta['inferred_filters'])) {
      const key = rawKey.trim().toLowerCase();
      if (!key || key === 'skill_level' || !Array.isArray(rawValues)) continue;

      const values = rawValues
        .filter((value): value is string => typeof value === 'string')
        .map((value) => value.trim().toLowerCase())
        .filter(Boolean);
      if (values.length > 0) {
        normalized[key] = Array.from(new Set(values));
      }
    }

    return normalized;
  }, [nlSearchMeta]);

  const suggestedContentFilters = useMemo<ContentFilterSelections>(() => {
    const sanitizedSuggestions = sanitizeContentFiltersForDefinitions(
      inferredContentFiltersFromMeta,
      taxonomyContentFilters
    );
    if (!Object.keys(sanitizedSuggestions).length) {
      return {};
    }

    const suggestions: ContentFilterSelections = {};
    for (const [key, values] of Object.entries(sanitizedSuggestions)) {
      if ((selectedContentFilters[key] ?? []).length > 0) {
        continue;
      }
      suggestions[key] = values;
    }
    return suggestions;
  }, [inferredContentFiltersFromMeta, selectedContentFilters, taxonomyContentFilters]);

  const inferredSubcategoryIdFromResults = useMemo(() => {
    if (resolvedSubcategoryId || instructors.length === 0) {
      return null;
    }

    const matchedSubcategoryIds = new Set<string>();
    instructors.forEach((instructor) => {
      const services = Array.isArray(instructor.services) ? instructor.services : [];
      services.forEach((service) => {
        const catalogId = (service.service_catalog_id || '').trim().toLowerCase();
        if (!catalogId) return;
        const subcategoryId = subcategoryLookup.serviceByCatalogId.get(catalogId);
        if (!subcategoryId) return;
        matchedSubcategoryIds.add(subcategoryId);
      });
    });

    return matchedSubcategoryIds.size === 1 ? Array.from(matchedSubcategoryIds)[0] ?? null : null;
  }, [instructors, resolvedSubcategoryId, subcategoryLookup.serviceByCatalogId]);

  useEffect(() => {
    if (resolvedSubcategoryId || !inferredSubcategoryIdFromResults) {
      return;
    }

    const params = new URLSearchParams(searchParamsString);
    if (params.get('subcategory_id')) {
      return;
    }

    params.set('subcategory_id', inferredSubcategoryIdFromResults);
    const queryString = params.toString();
    router.replace(queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });

    if (IS_TAXONOMY_DEBUG_ENABLED) {
      logger.debug('[search:taxonomy] inferred subcategory from search results', {
        inferredSubcategoryIdFromResults,
      });
    }
  }, [
    inferredSubcategoryIdFromResults,
    pathname,
    resolvedSubcategoryId,
    router,
    searchParamsString,
  ]);

  const hasMore = Boolean(hasNextPage);

  const softFilteringUsed = nlSearchMeta
    ? getBoolean(nlSearchMeta, 'soft_filtering_used', false)
    : false;
  const softFilterMessage = nlSearchMeta
    ? getString(nlSearchMeta, 'soft_filter_message', '')
    : '';
  const searchQueryId = nlSearchMeta ? getString(nlSearchMeta, 'search_query_id', '') : '';

  const trackSearchClick = useCallback(
    (params: { serviceId: string; instructorId: string; position: number; action?: string }) => {
      if (!searchQueryId) return;
      const { serviceId, instructorId, position, action = 'view' } = params;
      if (!serviceId || !instructorId || !Number.isFinite(position) || position <= 0) return;

      try {
        const qs = new URLSearchParams({
          search_query_id: searchQueryId,
          service_id: serviceId,
          instructor_id: instructorId,
          position: String(position),
          action,
        });
        const url = withApiBase(`/api/v1/search/click?${qs.toString()}`);
        void fetchWithSessionRefresh(url, { method: 'POST', credentials: 'include', keepalive: true });
      } catch {
        // best-effort: never block navigation
      }
    },
    [searchQueryId]
  );

  useEffect(() => {
    const activity = (query || category || '').trim();
    if (activity) {
      setActivity(activity);
    } else {
      setActivity(null);
    }
  }, [query, category, setActivity]);

  const errorMessage = useMemo(() => {
    if (!searchQueryEnabled) {
      return 'Please search for a specific service or use natural language search';
    }

    if (!searchError) return null;
    return searchError.message || 'Failed to load search results';
  }, [searchError, searchQueryEnabled]);

  const rateLimit = useMemo(() => {
    if (!searchQueryEnabled || !searchError) return null;
    const retryAfterSeconds = (searchError as { retryAfterSeconds?: number }).retryAfterSeconds;
    const status = (searchError as { status?: number }).status;
    if (typeof retryAfterSeconds === 'number') {
      return { seconds: retryAfterSeconds };
    }
    if (status === 429) {
      return { seconds: 0 };
    }
    return null;
  }, [searchError, searchQueryEnabled]);

  useEffect(() => {
    if (serviceCatalogId && (serviceSlug || serviceNameFromUrl)) {
      setActivity((serviceSlug || serviceNameFromUrl).toLowerCase());
    }
  }, [serviceCatalogId, serviceSlug, serviceNameFromUrl, setActivity]);

  const searchKey = `${query || ''}-${serviceCatalogId || ''}-${category || ''}-${serviceNameFromUrl || ''}-${fromSource || ''}`;
  const hasSearchResults = searchQueryEnabled && Boolean(searchResponse?.pages?.length);

  useEffect(() => {
    if (!hasSearchResults) return;
    if (searchKey === lastSearchParamsRef.current) return;
    lastSearchParamsRef.current = searchKey;

    let searchType: SearchType = SearchType.NATURAL_LANGUAGE;
    let searchQueryValue = '';

    if (query) {
      if (fromSource === 'recent') {
        searchType = SearchType.SEARCH_HISTORY;
      } else {
        searchType = SearchType.NATURAL_LANGUAGE;
      }
      searchQueryValue = query;
    } else if (serviceCatalogId) {
      searchType = SearchType.SERVICE_PILL;
      searchQueryValue = serviceNameFromUrl || serviceSlug || `Service #${serviceCatalogId}`;
    } else if (category) {
      searchType = SearchType.CATEGORY;
      searchQueryValue = category;
    }

    void recordSearch(
      {
        query: searchQueryValue,
        search_type: searchType,
        results_count: totalResults,
      },
      isAuthenticatedRef.current
    );
  }, [
    hasSearchResults,
    searchKey,
    query,
    fromSource,
    serviceCatalogId,
    serviceNameFromUrl,
    serviceSlug,
    category,
    totalResults,
  ]);

  const availabilityIds = useMemo(
    () =>
      instructors
        .map((instructor) => instructor.user_id)
        .filter((id): id is string => Boolean(id)),
    [instructors]
  );
  const availabilityByInstructor = usePublicAvailability(availabilityIds);

  const sidebarFilteredInstructors = useMemo(() => {
    if (instructors.length === 0) return [];
    return instructors.filter((instructor) => {
      const services = Array.isArray(instructor.services) ? instructor.services : [];
      const activeServices = services.filter((svc) => svc && svc.is_active !== false);

      const offersTravel = activeServices.some((svc) => svc.offers_travel === true);
      const offersAtLocation = activeServices.some((svc) => svc.offers_at_location === true);
      const offersOnline = activeServices.some((svc) => svc.offers_online === true);

      if (filters.location === 'online' && !offersOnline) return false;
      if (filters.location === 'travels' && !offersTravel) return false;
      if (filters.location === 'studio') {
        const hasLocations =
          Array.isArray(instructor.teaching_locations) && instructor.teaching_locations.length > 0;
        if (!offersAtLocation || !hasLocations) return false;
      }

      if (filters.priceMin !== null || filters.priceMax !== null) {
        const rates = activeServices
          .map((svc) => svc.hourly_rate)
          .filter((rate): rate is number => Number.isFinite(rate));
        if (rates.length === 0) return false;
        const matchesRate = rates.some((rate) => {
          if (filters.priceMin !== null && rate < filters.priceMin) return false;
          if (filters.priceMax !== null && rate > filters.priceMax) return false;
          return true;
        });
        if (!matchesRate) return false;
      }

      if (filters.duration.length > 0) {
        const durations = new Set<number>();
        activeServices.forEach((svc) => {
          if (!Array.isArray(svc.duration_options)) return;
          svc.duration_options.forEach((duration) => {
            if (Number.isFinite(duration)) durations.add(duration);
          });
        });
        if (durations.size === 0) return false;
        if (!filters.duration.some((duration) => durations.has(duration))) return false;
      }

      if (selectedSkillLevel.length > 0) {
        const levels = new Set<string>();
        activeServices.forEach((svc) => {
          getFilterSelectionValues(svc, 'skill_level').forEach((level) => levels.add(level));
          normalizeStringSelections(svc.levels_taught).forEach((level) => levels.add(level));
        });
        normalizeStringSelections(instructor._matchedServiceContext?.skill_level).forEach((level) =>
          levels.add(level)
        );
        if (levels.size === 0) return false;
        if (!selectedSkillLevel.some((level) => levels.has(level))) return false;
      }

      const audiences = new Set<string>();
      activeServices.forEach((svc) => {
        getFilterSelectionValues(svc, 'age_groups').forEach((group) => audiences.add(group));
        normalizeStringSelections(svc.age_groups).forEach((group) => audiences.add(group));
      });
      normalizeStringSelections(instructor._matchedServiceContext?.age_groups).forEach((group) =>
        audiences.add(group)
      );
      if (audiences.size > 0 && !audiences.has(activeAudience)) return false;

      if (filters.minRating !== 'any') {
        const ratingValue = typeof instructor.rating === 'number' ? instructor.rating : 0;
        const minRating = filters.minRating === '4.5' ? 4.5 : 4;
        if (ratingValue < minRating) return false;
      }

      const instructorId = instructor.user_id || instructor.id;
      const availability = instructorId ? availabilityByInstructor[instructorId] : undefined;
      if (!availabilityMatchesFilters(availability, filters)) return false;

      return true;
    });
  }, [activeAudience, availabilityByInstructor, filters, instructors, selectedSkillLevel]);

  const instructorCapabilities = useMemo(() => {
    const map = new Map<string, { offersTravel: boolean; offersAtLocation: boolean; offersOnline: boolean }>();
    for (const instructor of sidebarFilteredInstructors) {
      const instructorId = instructor.user_id || instructor.id;
      if (!instructorId) continue;
      const services = Array.isArray(instructor.services) ? instructor.services : [];
      const activeServices = services.filter((svc) => svc && svc.is_active !== false);
      const offersTravel = activeServices.some((svc) => svc.offers_travel === true);
      const offersAtLocation = activeServices.some((svc) => svc.offers_at_location === true);
      const offersOnline = activeServices.some((svc) => svc.offers_online === true);
      map.set(instructorId, { offersTravel, offersAtLocation, offersOnline });
    }
    return map;
  }, [sidebarFilteredInstructors]);

  const coverageIds = useMemo(
    () =>
      Array.from(
        new Set(
          (instructors || [])
            .map((i) => i.user_id)
            .filter((id): id is string => Boolean(id))
        )
      ),
    [instructors]
  );
  const coverageQuery = useInstructorCoverage(coverageIds);
  const emptyCoverage = useMemo(() => ({ type: 'FeatureCollection', features: [] }), []);
  const coverageGeoJSON = coverageQuery.data ?? emptyCoverage;

  const coverageFeatureCollection = useMemo<MapFeatureCollection | null>(() => {
    if (!isFeatureCollection(coverageGeoJSON)) return null;
    const features: GeoJSONFeature[] = [];
    for (const feature of coverageGeoJSON.features) {
      const instructorsList = getArray(feature.properties, 'instructors')
        .map((id) => (typeof id === 'string' ? id : ''))
        .filter(Boolean);
      const filteredInstructors = instructorsList.filter(
        (id) => instructorCapabilities.get(id)?.offersTravel
      );
      if (!filteredInstructors.length) continue;
      features.push({
        ...feature,
        properties: {
          ...(feature.properties || {}),
          instructors: filteredInstructors,
        },
      });
    }
    return {
      type: 'FeatureCollection',
      features,
    };
  }, [coverageGeoJSON, instructorCapabilities]);

  const locationPins = useMemo(() => {
    const pins: Array<{ lat: number; lng: number; label?: string; instructorId?: string }> = [];
    for (const instructor of sidebarFilteredInstructors) {
      const instructorId = instructor.user_id || instructor.id;
      if (!instructorId) continue;
      const capabilities = instructorCapabilities.get(instructorId);
      if (!capabilities?.offersAtLocation) continue;
      const locations = Array.isArray(instructor.teaching_locations)
        ? instructor.teaching_locations
        : [];
      for (const loc of locations) {
        const lat = loc.approx_lat;
        const lng = loc.approx_lng;
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
        const label = typeof loc.neighborhood === 'string' ? loc.neighborhood.trim() : '';
        if (label) {
          pins.push({
            lat,
            lng,
            label,
            instructorId,
          });
        } else {
          pins.push({
            lat,
            lng,
            instructorId,
          });
        }
      }
    }
    return pins;
  }, [sidebarFilteredInstructors, instructorCapabilities]);

  const filteredInstructors = useMemo(() => {
    if (!mapFilterIds || mapFilterIds.length === 0) return sidebarFilteredInstructors;
    const idSet = new Set(mapFilterIds);
    return sidebarFilteredInstructors.filter((instructor) => {
      const instructorId = instructor.user_id || instructor.id;
      return instructorId ? idSet.has(instructorId) : false;
    });
  }, [mapFilterIds, sidebarFilteredInstructors]);

  const sortedInstructors = useMemo(() => {
    if (sortOption === 'recommended') return filteredInstructors;
    const sorted = [...filteredInstructors];
    if (sortOption === 'price_asc') {
      sorted.sort((a, b) =>
        compareNullableNumbers(getInstructorMinRate(a), getInstructorMinRate(b), 'asc')
      );
      return sorted;
    }
    if (sortOption === 'price_desc') {
      sorted.sort((a, b) =>
        compareNullableNumbers(getInstructorMinRate(a), getInstructorMinRate(b), 'desc')
      );
      return sorted;
    }
    if (sortOption === 'rating') {
      sorted.sort((a, b) =>
        compareNullableNumbers(
          typeof a.rating === 'number' ? a.rating : null,
          typeof b.rating === 'number' ? b.rating : null,
          'desc'
        )
      );
      return sorted;
    }
    return sorted;
  }, [filteredInstructors, sortOption]);

  useEffect(() => {
    if (loading) {
      setLiveAnnouncement('Loading instructors...');
      return;
    }

    if (errorMessage) {
      setLiveAnnouncement(errorMessage);
      return;
    }

    if (sortedInstructors.length === 0) {
      setLiveAnnouncement('0 instructors found');
      return;
    }

    setLiveAnnouncement(
      `${sortedInstructors.length} ${sortedInstructors.length === 1 ? 'instructor' : 'instructors'} found`
    );
  }, [errorMessage, loading, sortedInstructors.length]);

  // Handle map bounds change
  const handleMapBoundsChange = useCallback((bounds: unknown) => {
    if (!bounds) return;

    const coverageFeatures = coverageFeatureCollection?.features ?? [];
    const hasPinData = sidebarFilteredInstructors.some((instructor) => {
      const instructorId = instructor.user_id || instructor.id;
      if (!instructorId) return false;
      const capabilities = instructorCapabilities.get(instructorId);
      if (!capabilities?.offersAtLocation) return false;
      return Array.isArray(instructor.teaching_locations) && instructor.teaching_locations.length > 0;
    });
    const hasCoverageData = coverageFeatures.length > 0;

    if (!hasCoverageData && !hasPinData) {
      setShowSearchAreaButton(false);
      setMapBounds(bounds);
      return;
    }

    // Check if any instructors are outside the current bounds
    const instructorsInBounds = sidebarFilteredInstructors.filter((instructor) => {
      let hasCoverageInBounds = false;

      if (hasCoverageData) {
        const instructorId = instructor.user_id || instructor.id;
        const instructorFeatures = coverageFeatures.filter((feature) => {
          const rawInstructors = feature.properties?.['instructors'];
          const instructorsList = Array.isArray(rawInstructors)
            ? (rawInstructors as string[])
            : [];
          return instructorId ? instructorsList.includes(instructorId) : false;
        });

        hasCoverageInBounds = instructorFeatures.some((feature) =>
          featureHasPointInBounds(feature, bounds)
        );
      }

      const instructorId = instructor.user_id || instructor.id;
      const capabilities = instructorId ? instructorCapabilities.get(instructorId) : null;
      const hasStudioInBounds = capabilities?.offersAtLocation && Array.isArray(instructor.teaching_locations)
        ? instructor.teaching_locations.some((loc) => {
          const lat = loc.approx_lat;
          const lng = loc.approx_lng;
          if (!Number.isFinite(lat) || !Number.isFinite(lng)) return false;
          return boundsContains(bounds, lat, lng);
        })
        : false;

      return hasCoverageInBounds || hasStudioInBounds;
    });

    // Show button if:
    // 1. Some instructors would be filtered out (zoomed in)
    // 2. OR we're currently showing a filtered view and more instructors could be shown (zoomed out)
    const hasFilteredInstructors = instructorsInBounds.length < sidebarFilteredInstructors.length;
    const isShowingFilteredView = filteredInstructors.length < sidebarFilteredInstructors.length;
    const wouldShowDifferentResults = instructorsInBounds.length !== filteredInstructors.length;

    setShowSearchAreaButton(hasFilteredInstructors || (isShowingFilteredView && wouldShowDifferentResults));
    setMapBounds(bounds);
  }, [sidebarFilteredInstructors, filteredInstructors, coverageFeatureCollection, instructorCapabilities, boundsContains, featureHasPointInBounds]);

  // Handle search area button click
  const handleSearchArea = useCallback(() => {
    if (!mapBounds) return;

    const coverageFeatures = coverageFeatureCollection?.features ?? [];
    const hasPinData = sidebarFilteredInstructors.some((instructor) => {
      const instructorId = instructor.user_id || instructor.id;
      if (!instructorId) return false;
      const capabilities = instructorCapabilities.get(instructorId);
      if (!capabilities?.offersAtLocation) return false;
      return Array.isArray(instructor.teaching_locations) && instructor.teaching_locations.length > 0;
    });
    const hasCoverageData = coverageFeatures.length > 0;

    if (!hasCoverageData && !hasPinData) {
      setMapFilterIds(null);
      setShowSearchAreaButton(false);
      setFocusedInstructorId(null);
      return;
    }

    // Filter instructors based on current map bounds
    const instructorsInBounds = sidebarFilteredInstructors.filter((instructor) => {
      let hasCoverageInBounds = false;

      if (hasCoverageData) {
        const instructorId = instructor.user_id || instructor.id;
        const instructorFeatures = coverageFeatures.filter((feature) => {
          const rawInstructors = feature.properties?.['instructors'];
          const instructorsList = Array.isArray(rawInstructors)
            ? (rawInstructors as string[])
            : [];
          return instructorId ? instructorsList.includes(instructorId) : false;
        });

        hasCoverageInBounds = instructorFeatures.some((feature) =>
          featureHasPointInBounds(feature, mapBounds)
        );
      }

      const instructorId = instructor.user_id || instructor.id;
      const capabilities = instructorId ? instructorCapabilities.get(instructorId) : null;
      const hasStudioInBounds = capabilities?.offersAtLocation && Array.isArray(instructor.teaching_locations)
        ? instructor.teaching_locations.some((loc) => {
          const lat = loc.approx_lat;
          const lng = loc.approx_lng;
          if (!Number.isFinite(lat) || !Number.isFinite(lng)) return false;
          return boundsContains(mapBounds, lat, lng);
        })
        : false;

      return hasCoverageInBounds || hasStudioInBounds;
    });

    const nextIds = instructorsInBounds
      .map((instructor) => instructor.user_id || instructor.id)
      .filter((id): id is string => Boolean(id));
    setMapFilterIds(nextIds);
    setShowSearchAreaButton(false);
    // Clear focused instructor after filtering
    setFocusedInstructorId(null);
  }, [sidebarFilteredInstructors, mapBounds, coverageFeatureCollection, instructorCapabilities, boundsContains, featureHasPointInBounds]);

  // Track stacked layout (below xl) and compute available height so the page itself doesn't scroll
  useEffect(() => {
    const recompute = () => {
      const stacked = window.matchMedia('(max-width: 1279px)').matches;
      setIsStacked(stacked);
      if (stacked) {
        const headerH = headerRef.current?.offsetHeight || 0;
        setStackedViewportHeight(Math.max(0, window.innerHeight - headerH));
      } else {
        setStackedViewportHeight(null);
      }
    };
    recompute();
    window.addEventListener('resize', recompute);
    return () => window.removeEventListener('resize', recompute);
  }, []);

  // Handle scroll indicator visibility
  useEffect(() => {
    const handleScroll = () => {
      if (!listRef.current || !isStacked) return;
      const { scrollTop, scrollHeight, clientHeight } = listRef.current;
      // Hide indicator when near the bottom (within 200px for snap scrolling)
      const isNearBottom = scrollTop + clientHeight >= scrollHeight - 100;
      setShowScrollIndicator(!isNearBottom);
    };

    const scrollElement = listRef.current;
    if (scrollElement && isStacked) {
      scrollElement.addEventListener('scroll', handleScroll);
      handleScroll(); // Check initial state
    }

    return () => {
      if (scrollElement) {
        scrollElement.removeEventListener('scroll', handleScroll);
      }
    };
  }, [isStacked, instructors.length]);

  useEffect(() => {
    if (observerRef.current) {
      observerRef.current.disconnect();
    }

    observerRef.current = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasMore && !loadingMore && !loading) {
          void fetchNextPage();
        }
      },
      { threshold: 0.1 }
    );

    if (loadMoreRef.current) {
      observerRef.current.observe(loadMoreRef.current);
    }

    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect();
      }
    };
  }, [fetchNextPage, hasMore, loadingMore, loading]);

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header ref={headerRef} className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-4 py-2 md:px-6 md:py-4">
        <div className="flex items-center justify-between max-w-full">
          <Link href="/" className="inline-block">
            <h1 className="text-2xl md:text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-2 md:pl-4">iNSTAiNSTRU</h1>
          </Link>
          <div className="pr-2 md:pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <div className={`${isStacked ? 'grid grid-cols-1' : ''} xl:flex xl:flex-row xl:min-h-[calc(100vh-5rem)] xl:h-auto`}
           style={isStacked && stackedViewportHeight ? {
             height: stackedViewportHeight,
             gridTemplateRows: 'calc(47% - 0.5rem) calc(53% - 0.5rem)',
             gap: '1rem',
             paddingBottom: '1rem'
           } as React.CSSProperties : undefined}>
        {/* Left Side - Filter and Instructor Cards */}
        <div className="flex-1 overflow-visible order-1 xl:order-1">
          {/* Filter Bar */}
          <div className={`px-6 ${isStacked ? 'pt-1 pb-1' : 'pt-0 md:pt-2 pb-1 md:pb-3'}`}>
            <div className={`bg-white/95 backdrop-blur-sm rounded-xl border border-gray-200 ${isStacked ? 'p-1' : 'p-1 md:p-4'}`}>
              <FilterBar
                filters={filtersWithTaxonomy}
                skillLevelOptions={skillLevelOptions}
                taxonomyContentFilters={taxonomyContentFilters}
                suggestedContentFilters={suggestedContentFilters}
                onFiltersChange={(nextFilters) => {
                  setLiveAnnouncement('Filters applied, loading results...');
                  const params = new URLSearchParams(searchParamsString);
                  const nextSkillLevelCsv = buildSkillLevelParam(
                    nextFilters.skillLevel,
                    skillLevelOptions
                  );
                  const nextContentFiltersParam = buildContentFiltersParam(
                    nextFilters.contentFilters,
                    taxonomyContentFilters.map((filterDefinition) => filterDefinition.key)
                  );
                  if (nextSkillLevelCsv) {
                    params.set('skill_level', nextSkillLevelCsv);
                  } else {
                    params.delete('skill_level');
                  }
                  if (nextContentFiltersParam) {
                    params.set('content_filters', nextContentFiltersParam);
                  } else {
                    params.delete('content_filters');
                  }
                  const queryString = params.toString();
                  if (queryString !== searchParamsString) {
                    router.replace(queryString ? `${pathname}?${queryString}` : pathname, {
                      scroll: false,
                    });
                  }
                  setFilters(nextFilters);
                  setMapFilterIds(null);
                  setShowSearchAreaButton(false);
                  setFocusedInstructorId(null);
                }}
                rightSlot={(
                  <div className={`flex items-center gap-1 ${isStacked ? 'ml-1' : 'ml-3 md:ml-4'}`} ref={sortDropdownRef}>
                    <span className={`${isStacked ? 'text-xs hidden' : 'text-xs md:text-sm'} text-gray-600 whitespace-nowrap hidden sm:inline`}>Sort:</span>
                    <div className="relative">
                      <button
                        ref={sortTriggerRef}
                        type="button"
                        onClick={handleSortToggle}
                        onKeyDown={handleSortTriggerKeyDown}
                        aria-haspopup="listbox"
                        aria-expanded={showSortDropdown}
                        aria-controls={sortListboxId}
                        className={`${isStacked ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 md:px-4 md:py-2 text-xs md:text-sm'} border border-gray-300 bg-white text-gray-700 rounded-lg hover:bg-gray-50 flex items-center gap-1 cursor-pointer transition-colors`}
                      >
                        <span>{currentSortTriggerLabel}</span>
                        <ChevronDown className={`h-3 w-3 text-gray-500 transition-transform ${showSortDropdown ? 'rotate-180' : ''}`} />
                      </button>

                      {isClient && showSortDropdown && sortPosition
                        ? createPortal(
                            <div
                              ref={sortMenuRef}
                              id={sortListboxId}
                              role="listbox"
                              aria-label="Sort results"
                              onKeyDown={handleSortListboxKeyDown}
                              className="fixed bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-[9999] min-w-[180px] w-auto"
                              style={{ top: sortPosition.top, left: sortPosition.left }}
                            >
                              {SORT_OPTIONS.map((option, index) => (
                                <button
                                  key={option.value}
                                  ref={(element) => {
                                    sortOptionRefs.current[index] = element;
                                  }}
                                  id={`search-sort-option-${option.value}`}
                                  type="button"
                                  role="option"
                                  tabIndex={activeSortIndex === index ? 0 : -1}
                                  aria-selected={sortOption === option.value}
                                  onFocus={() => setActiveSortIndex(index)}
                                  onMouseEnter={() => setActiveSortIndex(index)}
                                  onClick={() => selectSortOptionAtIndex(index)}
                                  className={`block w-full px-4 py-2 text-left text-sm whitespace-nowrap transition-colors ${
                                    sortOption === option.value
                                      ? 'bg-purple-50 text-[#7E22CE] font-medium'
                                      : 'text-gray-700 hover:bg-gray-50'
                                  }`}
                                >
                                  {option.menuLabel}
                                </button>
                              ))}
                            </div>,
                            document.body
                          )
                        : null}
                    </div>
                  </div>
                )}
              />
            </div>
          </div>

          {/* Instructor Cards - fills the remaining of row 1 on mobile; fixed height area */}
          <div className="relative h-full overflow-hidden">
            <div ref={listRef} className={`overflow-y-auto px-6 py-2 md:py-6 h-full max-h-full xl:h-[calc(100vh-15rem)] ${isStacked ? 'snap-y snap-mandatory' : ''} overscroll-contain scrollbar-hide`} style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
              {/* Rate limit banner */}
              <RateLimitBanner rateLimit={rateLimit} />
              <p
                data-testid="search-results-live-region"
                className="sr-only"
                aria-live="polite"
                aria-atomic="true"
              >
                {liveAnnouncement}
              </p>

            {/* Kids banner */}
            {activeAudience === 'kids' && (
              <div className="mb-3 rounded-md bg-blue-50 border border-blue-200 text-blue-900 px-3 py-2 text-sm">
                Showing instructors who teach kids
              </div>
            )}

            {/* Soft filter banner (constraint relaxation) */}
            {softFilteringUsed && softFilterMessage && (
              <div className="mb-3 rounded-md bg-amber-50 border border-amber-200 text-amber-900 px-3 py-2 text-sm flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-600 flex-shrink-0" />
                <p>{softFilterMessage}</p>
              </div>
            )}

            {loading ? (
              <div className="flex justify-center items-center h-64">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#7E22CE]"></div>
              </div>
            ) : errorMessage ? (
              <div className="text-center py-12">
                <p className="text-red-600">{errorMessage}</p>
                <Link href="/" className="text-[#7E22CE] hover:underline mt-4 inline-block">Return to Home</Link>
              </div>
            ) : sortedInstructors.length === 0 ? (
              <div className="text-center py-12" data-testid="no-results">
                <p className="text-gray-600 text-lg mb-4">No instructors found matching your search.</p>
                <Link href="/" className="text-[#7E22CE] hover:underline">Try a different search</Link>
              </div>
            ) : (
              <>
                <div className={`flex flex-col ${isStacked ? 'gap-20' : 'gap-4 md:gap-6'}`}>
                  {sortedInstructors.map((instructor, index) => {
                    const highlightServiceCatalogId =
                      (instructor as { _matchedServiceCatalogId?: string | null })._matchedServiceCatalogId ??
                      (serviceCatalogId || null);
                    const enhancedInstructor = { ...instructor };

                    const handleInteraction = (
                      interactionType: 'click' | 'hover' | 'bookmark' | 'view_profile' | 'contact' | 'book' = 'click'
                    ) => {
                      if (interactionType === 'view_profile') {
                        router.push(`/instructors/${instructor.user_id}`);
                      }
                    };
                    const position = index + 1;

                    return (
                      <div
                        key={instructor.id}
                        onMouseEnter={() => setHoveredInstructorId(instructor.user_id)}
                        onMouseLeave={() => setHoveredInstructorId(null)}
                        onClick={() => setFocusedInstructorId(instructor.user_id)}
                        className={`snap-center w-full ${isStacked ? 'h-full flex flex-col justify-center' : 'min-h-fit'} cursor-pointer`}
                      >
                        <InstructorCard
                          instructor={enhancedInstructor}
                          {...(highlightServiceCatalogId ? { highlightServiceCatalogId } : {})}
                          {...(availabilityByInstructor[instructor.user_id] && {
                            availabilityData: availabilityByInstructor[instructor.user_id],
                          })}
                          onViewProfile={() => {
                            trackSearchClick({
                              serviceId: enhancedInstructor.services?.[0]?.id || '',
                              instructorId: enhancedInstructor.user_id,
                              position,
                              action: 'view',
                            });
                            handleInteraction('view_profile');
                          }}
                          compact={isStacked}
                          onBookNow={(e) => {
                            e?.preventDefault?.();
                            e?.stopPropagation?.();
                            setShowTimeSelection(true);
                            setTimeSelectionContext({ instructor: enhancedInstructor, preSelectedDate: null, preSelectedTime: null, serviceId: enhancedInstructor.services?.[0]?.id });
                          }}
                        />
                      </div>
                    );
                  })}
                </div>

                {hasMore && (
                  <div ref={loadMoreRef} className="mt-4 md:mt-8 flex justify-center py-4">
                    {loadingMore && (
                      <div className="flex items-center gap-2">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7E22CE]"></div>
                        <span className="text-gray-600">Loading more instructors...</span>
                      </div>
                    )}
                  </div>
                )}

                {sortedInstructors.length > 0 && sortedInstructors.length < sidebarFilteredInstructors.length && (
                  <div className="mt-4 md:mt-8 text-center text-gray-600 py-4">
                    {sortedInstructors.length === 1
                      ? "1 instructor found in this area"
                      : `Showing ${sortedInstructors.length} instructors in this area`}
                  </div>
                )}
              </>
            )}
            </div>
            {/* Scroll indicator positioned above the bottom of cards container */}
            {isStacked && filteredInstructors.length > 1 && showScrollIndicator && (
              <div className="absolute bottom-8 left-0 right-0 flex items-center justify-center pointer-events-none z-10">
                <div className="bg-white/90 backdrop-blur-sm px-3 py-1.5 rounded-full border border-gray-200 shadow-sm">
                  <div className="flex items-center gap-2">
                    <svg className="w-3 h-3 text-gray-500 animate-bounce" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                    </svg>
                    <span className="text-xs text-gray-600 font-medium">Scroll to see more</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right Side - Map (stacked below on small) */}
        <div className="w-full xl:w-1/3 block order-2 xl:order-2">
          <div className="px-6 xl:pl-0 xl:pr-6 pt-0 md:pt-2 pb-0 md:pb-0 h-full mt-0 xl:mt-0">
            <div className="bg-white/95 backdrop-blur-sm rounded-xl border border-gray-200 p-2 md:p-4 h-full">
              <InstructorCoverageMap
                height="100%"
                featureCollection={coverageFeatureCollection}
                showCoverage={true}
                highlightInstructorId={hoveredInstructorId}
                focusInstructorId={focusedInstructorId}
                locationPins={locationPins}
                onBoundsChange={handleMapBoundsChange}
                showSearchAreaButton={showSearchAreaButton}
                onSearchArea={handleSearchArea}
              />
            </div>
          </div>
        </div>
      </div>

      {showTimeSelection && timeSelectionContext && (
        <TimeSelectionModal
          isOpen={showTimeSelection}
          onClose={() => setShowTimeSelection(false)}
          instructor={{
            user_id: getString(timeSelectionContext?.['instructor'], 'user_id', ''),
            user: {
              first_name: getString(isRecord(timeSelectionContext?.['instructor']) ? timeSelectionContext['instructor']['user'] : undefined, 'first_name', ''),
              last_initial: getString(isRecord(timeSelectionContext?.['instructor']) ? timeSelectionContext['instructor']['user'] : undefined, 'last_initial', '')
            },
            services: getArray(timeSelectionContext?.['instructor'], 'services') as Array<{
              id?: string;
              duration_options: number[];
              hourly_rate: number;
              skill: string;
            }>
          }}
          {...(getString(timeSelectionContext, 'preSelectedDate') && { preSelectedDate: getString(timeSelectionContext, 'preSelectedDate') })}
          {...(getString(timeSelectionContext, 'preSelectedTime') && { preSelectedTime: getString(timeSelectionContext, 'preSelectedTime') })}
          {...(getString(timeSelectionContext, 'serviceId') && { serviceId: getString(timeSelectionContext, 'serviceId') })}
        />
      )}
    </div>
  );
}

function SearchPageContent() {
  const searchParams = useSearchParams();
  const searchKey = searchParams.toString();
  return <SearchPageInner key={searchKey} />;
}

export default function SearchResultsPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div></div>}>
      <SearchPageContent />
    </Suspense>
  );
}
