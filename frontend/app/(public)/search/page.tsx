// frontend/app/(public)/search/page.tsx
'use client';

import { useEffect, useState, Suspense, useCallback, useRef, useMemo } from 'react';
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
import { SearchType } from '@/types/enums';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useInstructorSearch } from '@/hooks/queries/useInstructorSearch';
import { useInstructorCoverage } from '@/hooks/queries/useInstructorCoverage';
import { usePublicAvailability } from '@/hooks/queries/usePublicAvailability';
import { AlertTriangle, ChevronDown, X, Calendar, SlidersHorizontal } from 'lucide-react';

// Filter types
type DateFilter = 'today' | 'this_week' | 'custom' | null;
type TimeFilter = 'morning' | 'afternoon' | null;
type LessonTypeFilter = 'online' | 'in_person' | null;
type SortOption = 'recommended' | 'price_asc' | 'price_desc' | 'rating';


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
            levels: [] as string[],
            age_groups: [] as string[],
            location_types: [] as string[],
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
    const levels = Array.isArray(highlightedService?.levels_taught) ? highlightedService.levels_taught : [];
    const ageGroups = Array.isArray(highlightedService?.age_groups) ? highlightedService.age_groups : [];
    const locationTypes = Array.isArray(highlightedService?.location_types)
      ? highlightedService.location_types
      : [];
    return {
      ...item,
      ...(teachingLocations.length ? { teaching_locations: teachingLocations } : {}),
      _matchedServiceCatalogId: matchId,
      _matchedServiceContext: {
        levels,
        age_groups: ageGroups,
        location_types: locationTypes,
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

// Helper to build query with filters appended
const buildQueryWithFilters = (
  baseQuery: string,
  dateFilter: DateFilter,
  timeFilter: TimeFilter,
  lessonType: LessonTypeFilter,
  minPrice: number | null,
  maxPrice: number | null,
  customDate: string | null
): string => {
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
  if (dateFilter === 'today') {
    query = `${query} today`;
  } else if (dateFilter === 'this_week') {
    query = `${query} this week`;
  } else if (dateFilter === 'custom' && customDate) {
    // Format: "on January 25" - backend parser handles date expressions
    const date = new Date(customDate);
    const monthName = date.toLocaleDateString('en-US', { month: 'long' });
    const day = date.getDate();
    query = `${query} on ${monthName} ${day}`;
  }

  // Append time filter
  if (timeFilter === 'morning') {
    query = `${query} morning`;
  } else if (timeFilter === 'afternoon') {
    query = `${query} afternoon`;
  }

  // Append lesson type
  if (lessonType === 'online') {
    query = `${query} online`;
  } else if (lessonType === 'in_person') {
    query = `${query} in-person`;
  }

  // Append price filters
  if (minPrice !== null && maxPrice !== null) {
    query = `${query} $${minPrice}-$${maxPrice}`;
  } else if (maxPrice !== null) {
    query = `${query} under $${maxPrice}`;
  } else if (minPrice !== null) {
    query = `${query} above $${minPrice}`;
  }

  return query.trim();
};

function SearchPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { setActivity } = useBackgroundConfig();
  const { isAuthenticated } = useAuth();
  const headerRef = useRef<HTMLDivElement | null>(null);
  const lastSearchParamsRef = useRef<string>('');
  const pagesLoadedRef = useRef<Set<number>>(new Set());
  const [stackedViewportHeight, setStackedViewportHeight] = useState<number | null>(null);
  const [isStacked, setIsStacked] = useState<boolean>(false);
  const [instructors, setInstructors] = useState<Instructor[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [_total, setTotal] = useState(0);
  const isAuthenticatedRef = useRef(isAuthenticated);
  useEffect(() => {
    isAuthenticatedRef.current = isAuthenticated;
  }, [isAuthenticated]);
  const [serviceSlug] = useState<string>('');
  const [rateLimit, setRateLimit] = useState<{ seconds: number } | null>(null);
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
  const [filteredInstructors, setFilteredInstructors] = useState<Instructor[]>([]);

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

  const instructorCapabilities = useMemo(() => {
    const map = new Map<string, { offersTravel: boolean; offersAtLocation: boolean; offersOnline: boolean }>();
    for (const instructor of instructors) {
      const instructorId = instructor.user_id || instructor.id;
      if (!instructorId) continue;
      const services = Array.isArray(instructor.services) ? instructor.services : [];
      const offersTravel = services.some((svc) => svc.offers_travel === true);
      const offersAtLocation = services.some((svc) => svc.offers_at_location === true);
      const offersOnline = services.some((svc) => svc.offers_online === true);
      map.set(instructorId, { offersTravel, offersAtLocation, offersOnline });
    }
    return map;
  }, [instructors]);

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
    for (const instructor of filteredInstructors) {
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
  }, [filteredInstructors, instructorCapabilities]);
  const [nlSearchMeta, setNlSearchMeta] = useState<Record<string, unknown> | null>(null);

  // Filter state - read from URL params on mount
  const dateFilterParam = searchParams.get('date') as DateFilter;
  const timeFilterParam = searchParams.get('time') as TimeFilter;
  const lessonTypeParam = searchParams.get('lesson_type') as LessonTypeFilter;
  const minPriceParam = searchParams.get('min_price');
  const maxPriceParam = searchParams.get('max_price');
  const customDateParam = searchParams.get('custom_date');
  const sortParam = (searchParams.get('sort') || 'recommended') as SortOption;

  const [dateFilter, setDateFilter] = useState<DateFilter>(dateFilterParam);
  const [timeFilter, setTimeFilter] = useState<TimeFilter>(timeFilterParam);
  const [lessonType, setLessonType] = useState<LessonTypeFilter>(lessonTypeParam);
  const [minPrice, setMinPrice] = useState<number | null>(minPriceParam ? parseInt(minPriceParam, 10) : null);
  const [maxPrice, setMaxPrice] = useState<number | null>(maxPriceParam ? parseInt(maxPriceParam, 10) : null);
  const [customDate, setCustomDate] = useState<string | null>(customDateParam);
  const [sortOption, setSortOption] = useState<SortOption>(sortParam);
  const [showMoreFilters, setShowMoreFilters] = useState(false);
  const [showSortDropdown, setShowSortDropdown] = useState(false);
  const [showDatePicker, setShowDatePicker] = useState(false);
  const moreFiltersRef = useRef<HTMLDivElement>(null);
  const sortDropdownRef = useRef<HTMLDivElement>(null);

  // Update URL params when filters change
  const updateFilters = useCallback((updates: {
    date?: DateFilter;
    time?: TimeFilter;
    lesson_type?: LessonTypeFilter;
    min_price?: number | null;
    max_price?: number | null;
    custom_date?: string | null;
    sort?: SortOption;
  }) => {
    const params = new URLSearchParams(searchParams.toString());

    // Handle date filter
    if ('date' in updates) {
      if (updates.date) {
        params.set('date', updates.date);
      } else {
        params.delete('date');
      }
      setDateFilter(updates.date ?? null);
    }

    // Handle time filter
    if ('time' in updates) {
      if (updates.time) {
        params.set('time', updates.time);
      } else {
        params.delete('time');
      }
      setTimeFilter(updates.time ?? null);
    }

    // Handle lesson type filter
    if ('lesson_type' in updates) {
      if (updates.lesson_type) {
        params.set('lesson_type', updates.lesson_type);
      } else {
        params.delete('lesson_type');
      }
      setLessonType(updates.lesson_type ?? null);
    }

    // Handle min price
    if ('min_price' in updates) {
      if (updates.min_price !== null && updates.min_price !== undefined) {
        params.set('min_price', String(updates.min_price));
      } else {
        params.delete('min_price');
      }
      setMinPrice(updates.min_price ?? null);
    }

    // Handle max price
    if ('max_price' in updates) {
      if (updates.max_price !== null && updates.max_price !== undefined) {
        params.set('max_price', String(updates.max_price));
      } else {
        params.delete('max_price');
      }
      setMaxPrice(updates.max_price ?? null);
    }

    // Handle custom date
    if ('custom_date' in updates) {
      if (updates.custom_date) {
        params.set('custom_date', updates.custom_date);
      } else {
        params.delete('custom_date');
      }
      setCustomDate(updates.custom_date ?? null);
    }

    // Handle sort
    if ('sort' in updates) {
      if (updates.sort && updates.sort !== 'recommended') {
        params.set('sort', updates.sort);
      } else {
        params.delete('sort');
      }
      setSortOption(updates.sort ?? 'recommended');
    }

    const queryString = params.toString();
    router.push(queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
  }, [searchParams, pathname, router]);

  // Clear all filters
  const clearAllFilters = useCallback(() => {
    const params = new URLSearchParams(searchParams.toString());
    params.delete('date');
    params.delete('time');
    params.delete('lesson_type');
    params.delete('min_price');
    params.delete('max_price');
    params.delete('custom_date');
    params.delete('sort');

    setDateFilter(null);
    setTimeFilter(null);
    setLessonType(null);
    setMinPrice(null);
    setMaxPrice(null);
    setCustomDate(null);
    setSortOption('recommended');

    const queryString = params.toString();
    router.push(queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
  }, [searchParams, pathname, router]);

  // Check if any filters are active
  const hasActiveFilters = dateFilter !== null || timeFilter !== null || lessonType !== null ||
    minPrice !== null || maxPrice !== null;

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (moreFiltersRef.current && !moreFiltersRef.current.contains(event.target as Node)) {
        setShowMoreFilters(false);
      }
      if (sortDropdownRef.current && !sortDropdownRef.current.contains(event.target as Node)) {
        setShowSortDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const RateLimitBanner = () =>
    rateLimit ? (
      <div data-testid="rate-limit-banner" className="mb-4 rounded-md bg-yellow-50 border border-yellow-200 text-yellow-900 px-3 py-2 text-sm">
        Our hamsters are sprinting. Give them {rateLimit.seconds}s.
      </div>
    ) : null;

  const query = searchParams.get('q') || '';
  const category = searchParams.get('category') || '';
  const serviceCatalogId = searchParams.get('service_catalog_id') || '';
  const serviceNameFromUrl = searchParams.get('service_name') || '';
  const ageGroup = searchParams.get('age_group') || '';
  const fromSource = searchParams.get('from') || '';
  const softFilteringUsed = nlSearchMeta ? getBoolean(nlSearchMeta, 'soft_filtering_used', false) : false;
  const softFilterMessage = nlSearchMeta ? getString(nlSearchMeta, 'soft_filter_message', '') : '';
  const searchQueryId = nlSearchMeta ? getString(nlSearchMeta, 'search_query_id', '') : '';
  const builtSearchQuery = useMemo(() => {
    if (!query) return '';
    return buildQueryWithFilters(
      query,
      dateFilter,
      timeFilter,
      lessonType,
      minPrice,
      maxPrice,
      customDate
    );
  }, [query, dateFilter, timeFilter, lessonType, minPrice, maxPrice, customDate]);

  const searchQueryEnabled = Boolean(builtSearchQuery || serviceCatalogId);
  const {
    data: searchResponse,
    error: searchError,
    isLoading: isSearchLoading,
    isFetching: isSearchFetching,
  } = useInstructorSearch({
    searchQuery: builtSearchQuery,
    serviceCatalogId,
    page,
    perPage: 20,
    enabled: searchQueryEnabled,
  });
  const loading = searchQueryEnabled ? isSearchLoading : false;
  const loadingMore = isSearchFetching && page > 1;

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
        void fetch(url, { method: 'POST', credentials: 'include', keepalive: true });
      } catch {
        // best-effort: never block navigation
      }
    },
    [searchQueryId]
  );

  useEffect(() => {
    // reset page and list when search params change
    setPage(1);
    setInstructors([]);
    setHasMore(true);
    setNlSearchMeta(null);
    setError(null);
    setRateLimit(null);
    pagesLoadedRef.current = new Set();
  }, [
    query,
    category,
    serviceCatalogId,
    serviceNameFromUrl,
    dateFilter,
    timeFilter,
    lessonType,
    minPrice,
    maxPrice,
    customDate,
  ]);

  useEffect(() => {
    const activity = (query || category || '').trim();
    if (activity) {
      setActivity(activity);
    } else {
      setActivity(null);
    }
  }, [query, category, setActivity]);

  useEffect(() => {
    if (!searchQueryEnabled) {
      setError('Please search for a specific service or use natural language search');
      setRateLimit(null);
      return;
    }

    if (!searchError) {
      setError(null);
      setRateLimit(null);
      return;
    }

    setError(searchError.message || 'Failed to load search results');
    const retryAfterSeconds = (searchError as { retryAfterSeconds?: number }).retryAfterSeconds;
    const status = (searchError as { status?: number }).status;
    if (typeof retryAfterSeconds === 'number') {
      setRateLimit({ seconds: retryAfterSeconds });
    } else if (status === 429) {
      setRateLimit({ seconds: 0 });
    } else {
      setRateLimit(null);
    }
  }, [searchError, searchQueryEnabled]);

  useEffect(() => {
    if (serviceCatalogId && (serviceSlug || serviceNameFromUrl)) {
      setActivity((serviceSlug || serviceNameFromUrl).toLowerCase());
    }
  }, [serviceCatalogId, serviceSlug, serviceNameFromUrl, setActivity]);

  useEffect(() => {
    if (!searchResponse) return;

    const responsePage =
      searchResponse.mode === 'catalog' && Number.isFinite(searchResponse.data.page)
        ? searchResponse.data.page
        : 1;

    const normalized =
      searchResponse.mode === 'nl'
        ? normalizeSearchResults({
            mode: 'nl',
            results: searchResponse.data.results,
            meta: searchResponse.data.meta,
          })
        : normalizeSearchResults({
            mode: 'catalog',
            results: searchResponse.data.items,
            total: searchResponse.data.total,
            hasNext: searchResponse.data.has_next,
            serviceCatalogId,
          });

    let instructorsData: Instructor[] = normalized.instructors;
    const totalResults = normalized.totalResults;
    const nextHasMore = normalized.hasMore;
    setNlSearchMeta(normalized.meta);

    let finalResults = instructorsData;
    finalResults = finalResults.map((instructor) => {
      const highlightId =
        (instructor as { _matchedServiceCatalogId?: string | null })._matchedServiceCatalogId ?? null;
      const services = Array.isArray(instructor.services) ? instructor.services : [];
      const deduped = dedupeAndOrderServices(services, highlightId);
      return {
        ...instructor,
        services: deduped,
      };
    });

    if (responsePage === 1) {
      setInstructors(finalResults);
    } else if (!pagesLoadedRef.current.has(responsePage)) {
      setInstructors((prev) => [...prev, ...finalResults]);
    }
    pagesLoadedRef.current.add(responsePage);

    setHasMore(nextHasMore);
    setTotal(totalResults);

    if (responsePage === 1) {
      const searchKey = `${query || ''}-${serviceCatalogId || ''}-${category || ''}-${serviceNameFromUrl || ''}-${fromSource || ''}`;

      if (searchKey !== lastSearchParamsRef.current) {
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
      }
    }
  }, [
    searchResponse,
    query,
    category,
    serviceCatalogId,
    serviceNameFromUrl,
    fromSource,
    serviceSlug,
  ]);

  // Initialize filtered instructors when instructors change
  useEffect(() => {
    setFilteredInstructors(instructors);
  }, [instructors]);

  // Handle map bounds change
  const handleMapBoundsChange = useCallback((bounds: unknown) => {
    if (!bounds) return;

    const coverageFeatures = coverageFeatureCollection?.features ?? [];
    const hasPinData = instructors.some((instructor) => {
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
    const instructorsInBounds = instructors.filter((instructor) => {
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
    const hasFilteredInstructors = instructorsInBounds.length < instructors.length;
    const isShowingFilteredView = filteredInstructors.length < instructors.length;
    const wouldShowDifferentResults = instructorsInBounds.length !== filteredInstructors.length;

    setShowSearchAreaButton(hasFilteredInstructors || (isShowingFilteredView && wouldShowDifferentResults));
    setMapBounds(bounds);
  }, [instructors, filteredInstructors, coverageFeatureCollection, instructorCapabilities, boundsContains, featureHasPointInBounds]);

  // Handle search area button click
  const handleSearchArea = useCallback(() => {
    if (!mapBounds) return;

    const coverageFeatures = coverageFeatureCollection?.features ?? [];
    const hasPinData = instructors.some((instructor) => {
      const instructorId = instructor.user_id || instructor.id;
      if (!instructorId) return false;
      const capabilities = instructorCapabilities.get(instructorId);
      if (!capabilities?.offersAtLocation) return false;
      return Array.isArray(instructor.teaching_locations) && instructor.teaching_locations.length > 0;
    });
    const hasCoverageData = coverageFeatures.length > 0;

    if (!hasCoverageData && !hasPinData) {
      setFilteredInstructors(instructors);
      setShowSearchAreaButton(false);
      setFocusedInstructorId(null);
      return;
    }

    // Filter instructors based on current map bounds
    const instructorsInBounds = instructors.filter((instructor) => {
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

    setFilteredInstructors(instructorsInBounds);
    setShowSearchAreaButton(false);
    // Clear focused instructor after filtering
    setFocusedInstructorId(null);
  }, [instructors, mapBounds, coverageFeatureCollection, instructorCapabilities, boundsContains, featureHasPointInBounds]);

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
          const nextPage = page + 1;
          setPage(nextPage);
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
  }, [hasMore, loadingMore, loading, page]);

  const availabilityIds = useMemo(
    () =>
      instructors
        .map((instructor) => instructor.user_id)
        .filter((id): id is string => Boolean(id)),
    [instructors]
  );
  const availabilityByInstructor = usePublicAvailability(availabilityIds);



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
          {/* Filter Bar - Extra compact on stacked view */}
          <div className={`px-6 ${isStacked ? 'pt-1 pb-1' : 'pt-0 md:pt-2 pb-1 md:pb-3'}`}>
            <div className={`bg-white/95 backdrop-blur-sm rounded-xl border border-gray-200 ${isStacked ? 'p-1' : 'p-1 md:p-4'}`}>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex gap-1 md:gap-3 pr-1 md:pr-2 flex-wrap">
                  {/* Date filters group */}
                  <div className={`bg-gray-100 rounded-lg ${isStacked ? 'px-0.5 py-0.5' : 'px-0.5 py-0.5'} flex gap-0.5`}>
                    <button
                      onClick={() => updateFilters({ date: dateFilter === 'today' ? null : 'today', custom_date: null })}
                      className={`${isStacked ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 md:px-4 md:py-2 text-xs md:text-sm'} ${
                        dateFilter === 'today'
                          ? 'bg-[#7E22CE] text-white'
                          : 'text-gray-600 hover:bg-gray-50'
                      } rounded-md font-medium cursor-pointer transition-colors`}
                    >
                      Today
                    </button>
                    <button
                      onClick={() => updateFilters({ date: dateFilter === 'this_week' ? null : 'this_week', custom_date: null })}
                      className={`${isStacked ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 md:px-4 md:py-2 text-xs md:text-sm'} ${
                        dateFilter === 'this_week'
                          ? 'bg-[#7E22CE] text-white'
                          : 'text-gray-600 hover:bg-gray-50'
                      } rounded-md font-medium cursor-pointer transition-colors`}
                    >
                      This Week
                    </button>
                    <div className="relative">
                      <button
                        onClick={() => setShowDatePicker(!showDatePicker)}
                        className={`${isStacked ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 md:px-4 md:py-2 text-xs md:text-sm'} ${
                          dateFilter === 'custom'
                            ? 'bg-[#7E22CE] text-white'
                            : 'text-gray-600 hover:bg-gray-50'
                        } rounded-md font-medium cursor-pointer transition-colors flex items-center gap-1`}
                      >
                        <Calendar className="h-3 w-3" />
                        {dateFilter === 'custom' && customDate
                          ? new Date(customDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                          : 'Date'}
                      </button>
                      {showDatePicker && (
                        <div className="absolute top-full left-0 mt-1 bg-white rounded-lg shadow-lg border border-gray-200 p-3 z-50">
                          <input
                            type="date"
                            value={customDate || ''}
                            min={new Date().toISOString().split('T')[0]}
                            onChange={(e) => {
                              const newDate = e.target.value;
                              if (newDate) {
                                updateFilters({ date: 'custom', custom_date: newDate });
                              }
                              setShowDatePicker(false);
                            }}
                            className="block w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE] focus:border-transparent"
                          />
                          {dateFilter === 'custom' && (
                            <button
                              onClick={() => {
                                updateFilters({ date: null, custom_date: null });
                                setShowDatePicker(false);
                              }}
                              className="mt-2 text-xs text-gray-500 hover:text-gray-700"
                            >
                              Clear date
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Time filters group */}
                  <div className={`bg-gray-100 rounded-lg ${isStacked ? 'px-0.5 py-0.5' : 'px-0.5 py-0.5'} flex gap-0.5`}>
                    <button
                      onClick={() => updateFilters({ time: timeFilter === 'morning' ? null : 'morning' })}
                      className={`${isStacked ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 md:px-4 md:py-2 text-xs md:text-sm'} ${
                        timeFilter === 'morning'
                          ? 'bg-[#7E22CE] text-white'
                          : 'text-gray-600 hover:bg-gray-50'
                      } rounded-md font-medium cursor-pointer transition-colors`}
                    >
                      Morning
                    </button>
                    <button
                      onClick={() => updateFilters({ time: timeFilter === 'afternoon' ? null : 'afternoon' })}
                      className={`${isStacked ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 md:px-4 md:py-2 text-xs md:text-sm'} ${
                        timeFilter === 'afternoon'
                          ? 'bg-[#7E22CE] text-white'
                          : 'text-gray-600 hover:bg-gray-50'
                      } rounded-md font-medium cursor-pointer transition-colors`}
                    >
                      Afternoon
                    </button>
                  </div>

                  {/* More Filters dropdown */}
                  <div className="relative" ref={moreFiltersRef}>
                    <button
                      onClick={() => setShowMoreFilters(!showMoreFilters)}
                      className={`${isStacked ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 md:px-4 md:py-2 text-xs md:text-sm'} ${
                        lessonType !== null || minPrice !== null || maxPrice !== null
                          ? 'bg-[#7E22CE] text-white border-[#7E22CE]'
                          : 'border-gray-300 text-gray-700 hover:bg-gray-50'
                      } border rounded-lg cursor-pointer flex items-center gap-1 transition-colors`}
                    >
                      <SlidersHorizontal className="h-3.5 w-3.5" />
                      <span>Filters</span>
                      {(lessonType !== null || minPrice !== null || maxPrice !== null) && (
                        <span className="bg-white text-[#7E22CE] text-xs rounded-full px-1.5 py-0.5 font-medium">
                          {[lessonType, minPrice !== null || maxPrice !== null ? 'price' : null].filter(Boolean).length}
                        </span>
                      )}
                    </button>

                    {showMoreFilters && (
                      <div className="absolute top-full left-0 mt-1 bg-white rounded-lg shadow-lg border border-gray-200 p-4 z-50 min-w-[280px]">
                        {/* Price Range */}
                        <div className="mb-4">
                          <label className="block text-sm font-medium text-gray-700 mb-2">Price Range</label>
                          <div className="flex items-center gap-2">
                            <div className="flex-1">
                              <div className="relative">
                                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">$</span>
                                <input
                                  type="number"
                                  placeholder="Min"
                                  value={minPrice ?? ''}
                                  onChange={(e) => {
                                    const val = e.target.value ? parseInt(e.target.value, 10) : null;
                                    setMinPrice(val);
                                  }}
                                  className="w-full pl-7 pr-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE] focus:border-transparent"
                                />
                              </div>
                            </div>
                            <span className="text-gray-400">-</span>
                            <div className="flex-1">
                              <div className="relative">
                                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">$</span>
                                <input
                                  type="number"
                                  placeholder="Max"
                                  value={maxPrice ?? ''}
                                  onChange={(e) => {
                                    const val = e.target.value ? parseInt(e.target.value, 10) : null;
                                    setMaxPrice(val);
                                  }}
                                  className="w-full pl-7 pr-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE] focus:border-transparent"
                                />
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* Lesson Type */}
                        <div className="mb-4">
                          <label className="block text-sm font-medium text-gray-700 mb-2">Lesson Type</label>
                          <div className="flex gap-2">
                            <button
                              onClick={() => setLessonType(lessonType === 'online' ? null : 'online')}
                              className={`flex-1 px-3 py-2 text-sm rounded-md border transition-colors ${
                                lessonType === 'online'
                                  ? 'bg-[#7E22CE] text-white border-[#7E22CE]'
                                  : 'border-gray-300 text-gray-700 hover:bg-gray-50'
                              }`}
                            >
                              Online
                            </button>
                            <button
                              onClick={() => setLessonType(lessonType === 'in_person' ? null : 'in_person')}
                              className={`flex-1 px-3 py-2 text-sm rounded-md border transition-colors ${
                                lessonType === 'in_person'
                                  ? 'bg-[#7E22CE] text-white border-[#7E22CE]'
                                  : 'border-gray-300 text-gray-700 hover:bg-gray-50'
                              }`}
                            >
                              In-Person
                            </button>
                          </div>
                        </div>

                        {/* Actions */}
                        <div className="flex gap-2 pt-2 border-t border-gray-100">
                          <button
                            onClick={() => {
                              setMinPrice(null);
                              setMaxPrice(null);
                              setLessonType(null);
                            }}
                            className="flex-1 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 rounded-md transition-colors"
                          >
                            Clear
                          </button>
                          <button
                            onClick={() => {
                              updateFilters({
                                min_price: minPrice,
                                max_price: maxPrice,
                                lesson_type: lessonType,
                              });
                              setShowMoreFilters(false);
                            }}
                            className="flex-1 px-3 py-2 text-sm bg-[#7E22CE] text-white rounded-md hover:bg-[#6B1D9E] transition-colors"
                          >
                            Apply
                          </button>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Clear all filters button */}
                  {hasActiveFilters && (
                    <button
                      onClick={clearAllFilters}
                      className={`${isStacked ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 md:px-3 md:py-2 text-xs md:text-sm'} text-gray-500 hover:text-gray-700 flex items-center gap-1 cursor-pointer transition-colors`}
                    >
                      <X className="h-3 w-3" />
                      <span className="hidden sm:inline">Clear</span>
                    </button>
                  )}
                </div>

                {/* Sort section */}
                <div className={`flex items-center gap-1 ${isStacked ? 'ml-1' : 'ml-3 md:ml-4'}`} ref={sortDropdownRef}>
                  <span className={`${isStacked ? 'text-xs hidden' : 'text-xs md:text-sm'} text-gray-600 whitespace-nowrap hidden sm:inline`}>Sort:</span>
                  <div className="relative">
                    <button
                      onClick={() => setShowSortDropdown(!showSortDropdown)}
                      className={`${isStacked ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 md:px-4 md:py-2 text-xs md:text-sm'} border border-gray-300 rounded-lg hover:bg-gray-50 flex items-center gap-1 cursor-pointer transition-colors`}
                    >
                      <span>
                        {sortOption === 'recommended' && 'Recommended'}
                        {sortOption === 'price_asc' && 'Price: Low'}
                        {sortOption === 'price_desc' && 'Price: High'}
                        {sortOption === 'rating' && 'Top Rated'}
                      </span>
                      <ChevronDown className={`h-3 w-3 text-gray-500 transition-transform ${showSortDropdown ? 'rotate-180' : ''}`} />
                    </button>

                    {showSortDropdown && (
                      <div className="absolute top-full right-0 mt-1 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-50 min-w-[160px]">
                        {[
                          { value: 'recommended', label: 'Recommended' },
                          { value: 'price_asc', label: 'Price: Low to High' },
                          { value: 'price_desc', label: 'Price: High to Low' },
                          { value: 'rating', label: 'Highest Rated' },
                        ].map((option) => (
                          <button
                            key={option.value}
                            onClick={() => {
                              updateFilters({ sort: option.value as SortOption });
                              setShowSortDropdown(false);
                            }}
                            className={`w-full px-4 py-2 text-left text-sm transition-colors ${
                              sortOption === option.value
                                ? 'bg-purple-50 text-[#7E22CE] font-medium'
                                : 'text-gray-700 hover:bg-gray-50'
                            }`}
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Instructor Cards - fills the remaining of row 1 on mobile; fixed height area */}
          <div className="relative h-full overflow-hidden">
            <div ref={listRef} className={`overflow-y-auto px-6 py-2 md:py-6 h-full max-h-full xl:h-[calc(100vh-15rem)] ${isStacked ? 'snap-y snap-mandatory' : ''} overscroll-contain scrollbar-hide`} style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
              {/* Rate limit banner */}
              <RateLimitBanner />

            {/* Kids banner */}
            {ageGroup === 'kids' && (
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
            ) : error ? (
              <div className="text-center py-12">
                <p className="text-red-600">{error}</p>
                <Link href="/" className="text-[#7E22CE] hover:underline mt-4 inline-block">Return to Home</Link>
              </div>
            ) : filteredInstructors.length === 0 ? (
              <div className="text-center py-12" data-testid="no-results">
                <p className="text-gray-600 text-lg mb-4">No instructors found matching your search.</p>
                <Link href="/" className="text-[#7E22CE] hover:underline">Try a different search</Link>
              </div>
            ) : (
              <>
                <div className={`flex flex-col ${isStacked ? 'gap-20' : 'gap-4 md:gap-6'}`}>
                  {filteredInstructors.map((instructor, index) => {
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

                {filteredInstructors.length > 0 && filteredInstructors.length < instructors.length && (
                  <div className="mt-4 md:mt-8 text-center text-gray-600 py-4">
                    {filteredInstructors.length === 1
                      ? "1 instructor found in this area"
                      : `Showing ${filteredInstructors.length} instructors in this area`}
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

export default function SearchResultsPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div></div>}>
      <SearchPageContent />
    </Suspense>
  );
}
