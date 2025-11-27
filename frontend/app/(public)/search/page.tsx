// frontend/app/(public)/search/page.tsx
'use client';

import { useEffect, useState, Suspense, useCallback, useRef } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { publicApi } from '@/features/shared/api/client';
import { validateWithZod } from '@/features/shared/api/validation';
import { loadSearchListSchema } from '@/features/shared/api/schemas/searchList';
import InstructorCard from '@/components/InstructorCard';
import dynamic from 'next/dynamic';
const InstructorCoverageMap = dynamic(() => import('@/components/maps/InstructorCoverageMap'), { ssr: false });
import { Instructor } from '@/types/api';
import { useBackgroundConfig } from '@/lib/config/backgroundProvider';
import { getString, getNumber, getArray, isRecord, isFeatureCollection } from '@/lib/typesafe';
import TimeSelectionModal from '@/features/student/booking/components/TimeSelectionModal';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { recordSearch } from '@/lib/searchTracking';
import { withApiBase } from '@/lib/apiBase';
import { SearchType } from '@/types/enums';
import { useAuth } from '@/features/shared/hooks/useAuth';

const instructorServicesCache = new Map<string, Instructor['services']>();

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
const instructorServicesPromises = new Map<string, Promise<Instructor['services'] | null>>();

const normalizeProfileServices = (services: unknown): Instructor['services'] => {
  if (!Array.isArray(services)) return [];

  return services
    .map((service) => {
      if (!isRecord(service)) return null;

      const id = getString(service, 'id', '');
      const serviceCatalogId =
        getString(service, 'service_catalog_id', '') || getString(service, 'service_catalog', '');
      const hourlyRateRaw = service['hourly_rate'];
      const hourlyRate =
        typeof hourlyRateRaw === 'number'
          ? hourlyRateRaw
          : typeof hourlyRateRaw === 'string'
            ? Number(hourlyRateRaw)
            : getNumber(service, 'hourly_rate', 0);
      const normalizedRate = Number.isFinite(hourlyRate) ? hourlyRate : 0;
      const descriptionRaw = service['description'];
      const description = typeof descriptionRaw === 'string' ? descriptionRaw : undefined;
      const durationOptions = getArray(service, 'duration_options')
        .map((value) => {
          if (typeof value === 'number') return value;
          const parsed = Number(value);
          return Number.isFinite(parsed) ? parsed : null;
        })
        .filter((value): value is number => typeof value === 'number' && Number.isFinite(value) && value > 0);
      const isActiveValue = service['is_active'];
      const isActive = typeof isActiveValue === 'boolean' ? isActiveValue : undefined;

      const normalized: Instructor['services'][number] = {
        id: id || serviceCatalogId || '',
        service_catalog_id: serviceCatalogId || id || '',
        hourly_rate: normalizedRate,
      };

      const catalogName =
        getString(service, 'service_catalog_name', '') ||
        getString(service, 'name', '');

      if (catalogName) {
        (normalized as Instructor['services'][number] & { service_catalog_name?: string }).service_catalog_name =
          catalogName;
      }

      if (description) {
        normalized.description = description;
      }
      if (durationOptions.length > 0) {
        normalized.duration_options = durationOptions;
      }
      if (typeof isActive === 'boolean') {
        normalized.is_active = isActive;
      }

      const displayName = getServiceDisplayName(normalized);
      const fallbackName = getString(service, 'name', '') || getString(service, 'title', '');
      if (!displayName && fallbackName) {
        normalized.service_catalog_name = fallbackName;
      }

      if (!normalized.id || !normalized.service_catalog_id) {
        return null;
      }

      return normalized;
    })
    .filter((value): value is Instructor['services'][number] => value !== null);
};

const mergeInstructorServices = (
  existing: Instructor['services'] | undefined,
  incoming: Instructor['services']
): Instructor['services'] => {
  if (!incoming.length) {
    return existing ?? [];
  }

  if (!existing || !existing.length) {
    return incoming;
  }

  const makeKey = (service: Instructor['services'][number]) => {
    const base = `${service.service_catalog_id || ''}|${service.id}`;
    const name = getServiceDisplayName(service);
    return name ? `${base}|${name.toLowerCase()}` : base;
  };

  const incomingKeys = new Set(incoming.map((service) => makeKey(service)));

  const merged = [...incoming];

  for (const service of existing) {
    const key = makeKey(service);
    if (!incomingKeys.has(key)) {
      merged.push(service);
    }
  }

  return merged;
};

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

async function hydrateInstructorServices(instructors: Instructor[]): Promise<Instructor[]> {
  if (!Array.isArray(instructors) || instructors.length === 0) {
    return instructors;
  }

  const hydrated = await Promise.all(
    instructors.map(async (instructor) => {
      const instructorId = instructor?.user_id || instructor?.id;
      if (!instructorId) {
        return instructor;
      }

      const existingServices = Array.isArray(instructor.services) ? instructor.services : [];
      if (existingServices.length > 1) {
        return instructor;
      }

      const cachedServices = instructorServicesCache.get(instructorId);
      if (cachedServices) {
        return {
          ...instructor,
          services: mergeInstructorServices(existingServices, cachedServices),
        };
      }

      let pending = instructorServicesPromises.get(instructorId);
      if (!pending) {
        pending = (async () => {
          try {
            const response = await publicApi.getInstructorProfile(instructorId);
            if (response.status !== 200 || !response.data) {
              return null;
            }
            const normalized = normalizeProfileServices((response.data as { services?: unknown }).services);
            if (normalized.length) {
              instructorServicesCache.set(instructorId, normalized);
            }
            return normalized.length ? normalized : null;
          } catch {
            return null;
          } finally {
            instructorServicesPromises.delete(instructorId);
          }
        })();
        instructorServicesPromises.set(instructorId, pending);
      }

      const fetchedServices = await pending;
      if (!fetchedServices || !fetchedServices.length) {
        return instructor;
      }

      return {
        ...instructor,
        services: mergeInstructorServices(existingServices, fetchedServices),
      };
    })
  );

  return hydrated;
}

// GeoJSON feature interface for coverage areas
interface GeoJSONFeature {
  properties?: {
    instructors?: string[];
  };
  geometry?: {
    type: string;
    coordinates: number[][][] | number[][][][];
  };
}

function SearchPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { setActivity } = useBackgroundConfig();
  const { isAuthenticated } = useAuth();
  const headerRef = useRef<HTMLDivElement | null>(null);
  const lastSearchParamsRef = useRef<string>('');
  const [stackedViewportHeight, setStackedViewportHeight] = useState<number | null>(null);
  const [isStacked, setIsStacked] = useState<boolean>(false);
  const [instructors, setInstructors] = useState<Instructor[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [_total, setTotal] = useState(0);
  const [serviceName, setServiceName] = useState<string>('');
  const [serviceSlug] = useState<string>('');
  const [rateLimit, setRateLimit] = useState<{ seconds: number } | null>(null);
  const [showTimeSelection, setShowTimeSelection] = useState(false);
  const [timeSelectionContext, setTimeSelectionContext] = useState<Record<string, unknown> | null>(null);

  const observerRef = useRef<IntersectionObserver | null>(null);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const [hoveredInstructorId, setHoveredInstructorId] = useState<string | null>(null);
  const [focusedInstructorId, setFocusedInstructorId] = useState<string | null>(null);
  const [coverageGeoJSON, setCoverageGeoJSON] = useState<unknown | null>(null);
  const [showScrollIndicator, setShowScrollIndicator] = useState(true);
  const [mapBounds, setMapBounds] = useState<unknown>(null);
  const [showSearchAreaButton, setShowSearchAreaButton] = useState(false);
  const [filteredInstructors, setFilteredInstructors] = useState<Instructor[]>([]);

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
  const availableNow = searchParams.get('available_now') === 'true';
  const ageGroup = searchParams.get('age_group') || '';
  const fromSource = searchParams.get('from') || '';

  useEffect(() => {
    // reset page and list when search params change
    setServiceName(serviceNameFromUrl);
    setPage(1);
    setInstructors([]);
    setHasMore(true);
  }, [query, category, serviceCatalogId, serviceNameFromUrl]);

  useEffect(() => {
    const activity = (query || category || '').trim();
    if (activity) {
      setActivity(activity);
    } else {
      setActivity(null);
    }
  }, [query, category, setActivity]);

  useEffect(() => {
    if (serviceCatalogId && (serviceSlug || serviceName)) {
      setActivity((serviceSlug || serviceName).toLowerCase());
    }
  }, [serviceCatalogId, serviceSlug, serviceName, setActivity]);

  const fetchResults = useCallback(async (pageNum: number, append: boolean = false) => {
    if (!append) {
      setLoading(true);
    } else {
      setLoadingMore(true);
    }
    setError(null);

    try {
      let response;
      let instructorsData: Instructor[] = [];
      let totalResults = 0;
      let observabilityCandidates: Array<Record<string, unknown>> | undefined;

      if (query) {
        const nlResponse = await publicApi.searchWithNaturalLanguage(query);
        if (nlResponse.error) {
          // If 429, client returns retryAfterSeconds – show rate limit banner instead of generic error
          const secs = (nlResponse as unknown as { retryAfterSeconds?: number }).retryAfterSeconds;
          if (typeof secs === 'number' && secs > 0) {
            setRateLimit({ seconds: secs });
            // Also set friendly copy in error area for test robustness/visibility
            setError(`Our hamsters are sprinting. Give them ${secs}s.`);
            return;
          }
          // Generic error (no Retry-After) — still show banner for UX consistency/tests
          setRateLimit({ seconds: 0 });
          setError('Our hamsters are sprinting. Please try again shortly.');
          return;
        } else if (nlResponse.data) {
          instructorsData = nlResponse.data.results.map(
            (result: unknown) => {
              const instructor = isRecord(result) ? result['instructor'] : undefined;
              const service = isRecord(result) ? result['service'] : undefined;
              const offering = isRecord(result) ? result['offering'] : undefined;
              const matchedServiceCatalogId = getString(service, 'id', '') || null;

              const levelsFromOffering = getArray(offering, 'levels_taught')
                .map((value) => (typeof value === 'string' ? value : null))
                .filter((value): value is string => Boolean(value));
              const levelsFromService = getArray(service, 'levels_taught')
                .map((value) => (typeof value === 'string' ? value : null))
                .filter((value): value is string => Boolean(value));
              const levelsTaught = levelsFromOffering.length > 0 ? levelsFromOffering : levelsFromService;

              const ageFromOffering = getArray(offering, 'age_groups')
                .map((value) => (typeof value === 'string' ? value : null))
                .filter((value): value is string => Boolean(value));
              const ageFromService = getArray(service, 'age_groups')
                .map((value) => (typeof value === 'string' ? value : null))
                .filter((value): value is string => Boolean(value));
              const ageGroups = ageFromOffering.length > 0 ? ageFromOffering : ageFromService;

              const locationFromOffering = getArray(offering, 'location_types')
                .map((value) => (typeof value === 'string' ? value : null))
                .filter((value): value is string => Boolean(value));
              const locationFromService = getArray(service, 'location_types')
                .map((value) => (typeof value === 'string' ? value : null))
                .filter((value): value is string => Boolean(value));
              const locationTypes = locationFromOffering.length > 0 ? locationFromOffering : locationFromService;

              const servicePayload = {
                id: getString(service, 'id') || '1',
                service_catalog_id: getString(service, 'id') || '1',
                service_catalog_name: getString(service, 'name', ''),
                hourly_rate:
                  getNumber(offering, 'hourly_rate') || getNumber(service, 'actual_min_price', 0),
                description:
                  getString(offering, 'description') || getString(service, 'description', ''),
                duration_options: getArray(offering, 'duration_options').length > 0
                  ? (getArray(offering, 'duration_options') as number[])
                  : [60],
                levels_taught: levelsTaught,
                age_groups: ageGroups,
                location_types: locationTypes,
                is_active: true,
              };

              const mapped = {
                id: getString(instructor, 'id', ''),
                user_id: getString(instructor, 'id', ''),
                bio: getString(instructor, 'bio', ''),
                service_area_summary: getString(instructor, 'service_area_summary', ''),
                service_area_boroughs: getArray(instructor, 'service_area_boroughs')
                  .map((value) => (typeof value === 'string' ? value : null))
                  .filter((value): value is string => Boolean(value && value.trim()))
                  .map((value) => value.trim()),
                service_area_neighborhoods: getArray(instructor, 'service_area_neighborhoods')
                  .filter((value): value is Record<string, unknown> => isRecord(value))
                  .map((value) => ({
                    neighborhood_id: getString(value, 'neighborhood_id', ''),
                    ntacode: getString(value, 'ntacode') || null,
                    name: getString(value, 'name') || null,
                    borough: getString(value, 'borough') || null,
                  }))
                  .filter((value) => value.neighborhood_id.length > 0),
                years_experience: getNumber(instructor, 'years_experience', 0),
                user: {
                  first_name: getString(instructor, 'first_name', 'Unknown'),
                  last_initial: getString(instructor, 'last_initial', ''),
                },
                services: [servicePayload],
                _matchedServiceContext: {
                  levels: levelsTaught,
                  age_groups: ageGroups,
                  location_types: locationTypes,
                },
                relevance_score: getNumber(result, 'match_score', 0),
                _matchedServiceCatalogId: matchedServiceCatalogId,
              } as Instructor & { relevance_score: number; _matchedServiceCatalogId?: string | null };

              return mapped;
            }
          );
          instructorsData.sort(
            (a, b) => ((b.relevance_score as number) || 0) - ((a.relevance_score as number) || 0)
          );
          totalResults = nlResponse.data.total_found;
          // Capture observability candidates for analytics tracking
          observabilityCandidates = nlResponse.data.search_metadata?.observability_candidates ?? undefined;
          setHasMore(false);
        }
      } else if (serviceCatalogId) {
        const apiParams = {
          service_catalog_id: serviceCatalogId,
          page: pageNum,
          per_page: 20,
        };
        response = await publicApi.searchInstructors(apiParams);
        if (response.error) {
          setError(response.error);
          return;
        } else if (response.data) {
          // Dev/test-only validation of the response shape
          const validated = await validateWithZod<{
            items: unknown[];
            total: number;
            page: number;
            per_page: number;
            has_next: boolean;
            has_prev: boolean;
          }>(loadSearchListSchema, response.data, { endpoint: 'GET /instructors' });
          const casted = validated.items as unknown as Instructor[];
          instructorsData = casted.map((item) => {
            const matchId = serviceCatalogId || null;
            const highlightedService = Array.isArray(item.services)
              ? item.services.find((svc) => (svc.service_catalog_id || '').trim().toLowerCase() === (matchId || '').trim().toLowerCase()) || item.services[0]
              : undefined;
            const levels = Array.isArray(highlightedService?.levels_taught)
              ? highlightedService.levels_taught
              : [];
            const ageGroups = Array.isArray(highlightedService?.age_groups)
              ? highlightedService.age_groups
              : [];
            const locationTypes = Array.isArray(highlightedService?.location_types)
              ? highlightedService.location_types
              : [];
            return {
              ...item,
              _matchedServiceCatalogId: matchId,
              _matchedServiceContext: {
                levels,
                age_groups: ageGroups,
                location_types: locationTypes,
              },
            };
          });
          totalResults = validated.total;
          const totalPages = Math.ceil(totalResults / 20);
          setHasMore(pageNum < totalPages);
        }
      } else {
        setError('Please search for a specific service or use natural language search');
        return;
      }

      const needsHydration = instructorsData.some(
        (item) => !Array.isArray(item?.services) || item.services.length <= 1
      );
      let finalResults = instructorsData;
      if (needsHydration) {
        try {
          const hydratedResults = await hydrateInstructorServices(instructorsData);
          if (hydratedResults.length) {
            finalResults = hydratedResults;
          }
        } catch {
          // ignore hydration errors; fallback to base results
        }
      }

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

      if (append) {
        setInstructors((prev) => [...prev, ...finalResults]);
      } else {
        setInstructors(finalResults);

        // Track search only for initial loads, not pagination
        if (pageNum === 1) {
          // Create a unique key for the current search parameters
          const searchKey = `${query || ''}-${serviceCatalogId || ''}-${category || ''}-${serviceNameFromUrl || ''}-${fromSource || ''}`;

          // Only track if this is a different search than the last one
          if (searchKey !== lastSearchParamsRef.current) {
            lastSearchParamsRef.current = searchKey;

            // Determine search type based on what parameters are present
            let searchType: SearchType = SearchType.NATURAL_LANGUAGE;
            let searchQuery = '';

            if (query) {
              // Check if this is from search history
              if (fromSource === 'recent') {
                searchType = SearchType.SEARCH_HISTORY;
              } else {
                searchType = SearchType.NATURAL_LANGUAGE;
              }
              searchQuery = query;
            } else if (serviceCatalogId) {
              searchType = SearchType.SERVICE_PILL;
              searchQuery = serviceNameFromUrl || serviceName || `Service #${serviceCatalogId}`;
            } else if (category) {
              searchType = SearchType.CATEGORY;
              searchQuery = category;
            }

            // Record the search with observability candidates for analytics
            void recordSearch(
              {
                query: searchQuery,
                search_type: searchType,
                results_count: totalResults,
                ...(observabilityCandidates && { observability_candidates: observabilityCandidates }),
              },
              isAuthenticated
            );
          }
        }
      }
      setTotal(totalResults);
    } catch {
      setError('Failed to load search results');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [query, category, serviceCatalogId, isAuthenticated, serviceNameFromUrl, fromSource, serviceName]);

  useEffect(() => {
    void fetchResults(1, false);
  }, [query, category, serviceCatalogId, availableNow, fetchResults]);

  // Initialize filtered instructors when instructors change
  useEffect(() => {
    setFilteredInstructors(instructors);
  }, [instructors]);

  useEffect(() => {
    const fetchCoverage = async () => {
      try {
        const ids = Array.from(new Set((instructors || []).map((i) => i.user_id).filter(Boolean)));
        if (!ids.length) {
          setCoverageGeoJSON({ type: 'FeatureCollection', features: [] });
          return;
        }
        const params = new URLSearchParams({ ids: ids.join(',') });
        const coverageUrl = withApiBase(`/api/v1/addresses/coverage/bulk?${params.toString()}`);
        const res = await fetch(coverageUrl, { credentials: 'include' });
        if (!res.ok) {
          setCoverageGeoJSON({ type: 'FeatureCollection', features: [] });
          return;
        }
        const data = await res.json();
        setCoverageGeoJSON(data);
      } catch {
        setCoverageGeoJSON({ type: 'FeatureCollection', features: [] });
      }
    };
    void fetchCoverage();
  }, [instructors]);

  // Initialize filtered instructors when instructors change
  useEffect(() => {
    setFilteredInstructors(instructors);
  }, [instructors]);

  // Handle map bounds change
  const handleMapBoundsChange = useCallback((bounds: unknown) => {
    if (!bounds || !coverageGeoJSON) return;

    // Check if any instructors are outside the current bounds
    const instructorsInBounds = instructors.filter((instructor) => {
      // Check if this instructor has any coverage in the current bounds
      const instructorFeatures = (coverageGeoJSON as { features: GeoJSONFeature[] })?.features?.filter((feature: GeoJSONFeature) => {
        const instructorsList = feature.properties?.instructors || [];
        return instructorsList.includes(instructor.user_id);
      });

      // Check if any of the instructor's features intersect with the map bounds
      for (const feature of instructorFeatures) {
        if (feature.geometry && feature.geometry.type === 'MultiPolygon') {
          // Simple bounds check - if any part of the polygon is in view
          for (const polygon of feature.geometry.coordinates) {
            for (const ring of polygon) {
              for (const coord of ring) {
                if (Array.isArray(coord) && coord.length >= 2) {
                  const lat = coord[1];
                  const lng = coord[0];
                  if (bounds && typeof bounds === 'object' && 'contains' in bounds && typeof bounds.contains === 'function' && bounds.contains([lat, lng])) {
                    return true; // Instructor has coverage in view
                  }
                }
              }
            }
          }
        }
      }

      return false;
    });

    // Show button if:
    // 1. Some instructors would be filtered out (zoomed in)
    // 2. OR we're currently showing a filtered view and more instructors could be shown (zoomed out)
    const hasFilteredInstructors = instructorsInBounds.length < instructors.length;
    const isShowingFilteredView = filteredInstructors.length < instructors.length;
    const wouldShowDifferentResults = instructorsInBounds.length !== filteredInstructors.length;

    setShowSearchAreaButton(hasFilteredInstructors || (isShowingFilteredView && wouldShowDifferentResults));
    setMapBounds(bounds);
  }, [instructors, filteredInstructors, coverageGeoJSON]);

  // Handle search area button click
  const handleSearchArea = useCallback(() => {
    if (!mapBounds || !coverageGeoJSON) return;

    // Filter instructors based on current map bounds
    const instructorsInBounds = instructors.filter((instructor) => {
      const instructorFeatures = (coverageGeoJSON as { features: GeoJSONFeature[] })?.features?.filter((feature: GeoJSONFeature) => {
        const instructorsList = feature.properties?.instructors || [];
        return instructorsList.includes(instructor.user_id);
      });

      for (const feature of instructorFeatures) {
        if (feature.geometry && feature.geometry.type === 'MultiPolygon') {
          for (const polygon of feature.geometry.coordinates) {
            for (const ring of polygon) {
              for (const coord of ring) {
                if (Array.isArray(coord) && coord.length >= 2) {
                  const lat = coord[1];
                  const lng = coord[0];
                  if (mapBounds && typeof mapBounds === 'object' && 'contains' in mapBounds && typeof mapBounds.contains === 'function' && mapBounds.contains([lat, lng])) {
                    return true;
                  }
                }
              }
            }
          }
        }
      }
      return false;
    });

    setFilteredInstructors(instructorsInBounds);
    setShowSearchAreaButton(false);
    // Clear focused instructor after filtering
    setFocusedInstructorId(null);
  }, [instructors, mapBounds, coverageGeoJSON]);

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
          void fetchResults(nextPage, true);
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
  }, [hasMore, loadingMore, loading, page, fetchResults]);

  // Fetch next available slot for each instructor
  interface InstructorAvailabilitySummary {
    timezone?: string;
    availabilityByDate: Record<
      string,
      {
        available_slots: Array<{ start_time: string; end_time: string }>;
        is_blackout?: boolean;
      }
    >;
  }
  const [availabilityByInstructor, setAvailabilityByInstructor] = useState<Record<string, InstructorAvailabilitySummary>>({});

  useEffect(() => {
    const formatDate = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const normalizeTime = (value?: string | null) => {
      if (!value) return '00:00';
      const [h = '0', m = '0'] = value.split(':');
      return `${String(parseInt(h, 10) || 0).padStart(2, '0')}:${String(parseInt(m, 10) || 0).padStart(2, '0')}`;
    };

    const fetchAvailabilities = async () => {
      try {
        const updates: Record<string, InstructorAvailabilitySummary> = {};
        const today = new Date();
        const startDate = new Date(today);
        const endDate = new Date(startDate);
        endDate.setDate(startDate.getDate() + 14);

        await Promise.all(
          instructors.map(async (i) => {
            try {
              const { data, status } = await publicApi.getInstructorAvailability(i.user_id, {
                start_date: formatDate(startDate),
                end_date: formatDate(endDate),
              });
              if (!data || status !== 200) {
                return;
              }
              const byDate = data.availability_by_date || {};
              const normalizedEntries = Object.entries(byDate).reduce<
                Record<string, { available_slots: Array<{ start_time: string; end_time: string }>; is_blackout?: boolean }>
              >((acc, [date, day]) => {
                if (!day) return acc;
                acc[date] = {
                  available_slots: (day.available_slots || []).map((slot) => ({
                    start_time: normalizeTime(slot.start_time),
                    end_time: normalizeTime(slot.end_time),
                  })),
                  is_blackout: day.is_blackout,
                };
                return acc;
              }, {});

              updates[i.user_id] = {
                timezone: data.timezone ?? undefined,
                availabilityByDate: normalizedEntries,
              };
            } catch {
              // ignore errors for individual instructors
            }
          })
        );

        if (Object.keys(updates).length) {
          setAvailabilityByInstructor((prev) => ({ ...prev, ...updates }));
        }
      } catch {
        // ignore batch errors
      }
    };

    if (instructors && instructors.length) {
      void fetchAvailabilities();
    }
  }, [instructors]);



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
              <div className="flex items-center justify-between">
                <div className="flex gap-1 md:gap-6 pr-1 md:pr-2">
                  {/* Date filters group */}
                  <div className={`bg-gray-100 rounded-lg ${isStacked ? 'px-0.5 py-0.5' : 'px-0.5 py-0.5'} flex gap-0.5`}>
                    <button className={`${isStacked ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 md:px-4 md:py-2 text-xs md:text-sm'} bg-white rounded-md font-medium cursor-pointer`}>Today</button>
                    <button className={`${isStacked ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 md:px-4 md:py-2 text-xs md:text-sm'} text-gray-600 hover:bg-gray-50 rounded-md cursor-pointer`}>This Week</button>
                    <button className={`${isStacked ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 md:px-4 md:py-2 text-xs md:text-sm'} text-gray-600 hover:bg-gray-50 rounded-md cursor-pointer`}>Choose Date</button>
                  </div>

                  {/* Time filters group */}
                  <div className={`bg-gray-100 rounded-lg ${isStacked ? 'px-0.5 py-0.5' : 'px-0.5 py-0.5'} flex gap-0.5`}>
                    <button className={`${isStacked ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 md:px-4 md:py-2 text-xs md:text-sm'} text-gray-600 hover:bg-gray-50 rounded-md cursor-pointer`}>Morning</button>
                    <button className={`${isStacked ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 md:px-4 md:py-2 text-xs md:text-sm'} text-gray-600 hover:bg-gray-50 rounded-md cursor-pointer`}>Afternoon</button>
                  </div>

                  {/* More Filters button */}
                  <button className={`${isStacked ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 md:px-4 md:py-2 text-xs md:text-sm'} border border-gray-300 rounded-lg hover:bg-gray-50 cursor-pointer`}>More Filters</button>
                </div>

                {/* Sort section */}
                <div className={`flex items-center gap-1 ${isStacked ? 'ml-1' : 'ml-3 md:ml-4'}`}>
                  <span className={`${isStacked ? 'text-xs' : 'text-xs md:text-sm'} text-gray-600 whitespace-nowrap`}>Sort by:</span>
                  <button className={`${isStacked ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 md:px-4 md:py-2 text-xs md:text-sm'} border border-gray-300 rounded-lg hover:bg-gray-50 flex items-center gap-1 cursor-pointer`}>
                    <span>Recommended</span>
                    <span className="text-gray-500">▼</span>
                  </button>
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
                  {filteredInstructors.map((instructor) => {
                    const highlightServiceCatalogId =
                      (instructor as { _matchedServiceCatalogId?: string | null })._matchedServiceCatalogId ??
                      (serviceCatalogId || null);
                    const enhancedInstructor = {
                      ...instructor,
                      rating: instructor.rating || 4.8,
                      total_reviews: instructor.total_reviews || Math.floor(Math.random() * 100) + 20,
                      verified: true,
                    };

                    const handleInteraction = (
                      interactionType: 'click' | 'hover' | 'bookmark' | 'view_profile' | 'contact' | 'book' = 'click'
                    ) => {
                      if (interactionType === 'view_profile') {
                        router.push(`/instructors/${instructor.user_id}`);
                      }
                    };

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
                          onViewProfile={() => handleInteraction('view_profile')}
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
                featureCollection={isFeatureCollection(coverageGeoJSON) ? coverageGeoJSON : null}
                showCoverage={true}
                highlightInstructorId={hoveredInstructorId}
                focusInstructorId={focusedInstructorId}
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
