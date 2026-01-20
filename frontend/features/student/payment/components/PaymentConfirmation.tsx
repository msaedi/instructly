'use client';

import React, { useState, useEffect, useMemo, useRef, useCallback, useId } from 'react';
import * as Tooltip from '@radix-ui/react-tooltip';
import { Calendar, Clock, MapPin, AlertCircle, Star, ChevronDown, Info } from 'lucide-react';
import { BookingPayment, PaymentMethod } from '../types';
import { BookingType } from '@/features/shared/types/booking';
import { format } from 'date-fns';
import { getPlaceDetails } from '@/features/shared/api/client';
import { fetchBookingsList } from '@/src/api/services/bookings';
import { fetchInstructorProfile } from '@/src/api/services/instructors';
import type { InstructorService } from '@/types/instructor';
import TimeSelectionModal from '@/features/student/booking/components/TimeSelectionModal';
import { calculateEndTime } from '@/features/student/booking/hooks/useCreateBooking';
import { logger } from '@/lib/logger';
import { usePricingFloors } from '@/lib/pricing/usePricingFloors';
import { formatMeetingLocation, toStateCode } from '@/utils/address/format';
import { PlacesAutocompleteInput } from '@/components/forms/PlacesAutocompleteInput';
import type { PlaceSuggestion } from '@/components/forms/PlacesAutocompleteInput';
import { useServiceAreaCheck } from '@/hooks/useServiceAreaCheck';
import { AddressSelector } from '@/components/booking/AddressSelector';
import type { SavedAddress } from '@/hooks/useSavedAddresses';
import { addMinutesHHMM, to24HourTime } from '@/lib/time';
import { overlapsHHMM, minutesSinceHHMM } from '@/lib/time/overlap';
import { toDateOnlyString } from '@/lib/availability/dateHelpers';
import {
  computeBasePriceCents,
  computePriceFloorCents,
  formatCents,
  type NormalizedModality,
} from '@/lib/pricing/priceFloors';
import { formatCentsToDisplay } from '@/lib/api/pricing';
import type { PricingLineItem } from '@/lib/api/pricing';
import { usePricingPreview } from '../hooks/usePricingPreview';
import {
  computeStudentFeePercent,
  formatServiceSupportLabel,
  formatServiceSupportTooltip,
} from '@/lib/pricing/studentFee';

type BookingWithMetadata = BookingPayment & { metadata?: Record<string, unknown> };

type LocationType = 'student_location' | 'instructor_location' | 'online' | 'neutral_location';

type TeachingLocation = {
  address: string;
  label?: string;
};

type ConflictKey = {
  studentId: string;
  instructorId: string;
  bookingDate: string;
  startHHMM24: string;
  durationMinutes: number;
};

type ConflictListItem = {
  booking_date?: string;
  start_time?: string;
  end_time?: string | null;
  duration_minutes?: number | null;
  status?: string;
};

const CONFLICT_CACHE_TTL_MS = 60_000;
const CONFLICT_RELEVANT_STATUSES = new Set(['pending', 'confirmed', 'completed']);

type AddressFields = {
  line1: string;
  city: string;
  state: string;
  postalCode: string;
  country: string;
};

type AddressDetailsCacheEntry = {
  fields: AddressFields;
  formatted?: string;
  lat?: number;
  lng?: number;
  placeId?: string;
};

type AddressCoords = {
  lat: number | null;
  lng: number | null;
  placeId: string | null;
};

const EMPTY_ADDRESS: AddressFields = {
  line1: '',
  city: '',
  state: '',
  postalCode: '',
  country: '',
};

const ADDRESS_PLACEHOLDER = 'Student provided address';
const INSTRUCTOR_LOCATION_PLACEHOLDER = 'Instructor location';

const formatFullAddress = ({ line1, city, state, postalCode }: AddressFields): string =>
  formatMeetingLocation(line1, city, state, postalCode);

interface PaymentConfirmationProps {
  booking: BookingPayment;
  paymentMethod: PaymentMethod;
  cardLast4?: string;
  creditsUsed?: number;
  availableCredits?: number;
  creditEarliestExpiry?: string | Date | null;
  onConfirm: () => void;
  onBack: () => void;
  onChangePaymentMethod?: () => void;
  onCreditToggle?: () => void;
  onCreditAmountChange?: (amount: number) => void;
  cardBrand?: string;
  isDefaultCard?: boolean;
  promoApplied?: boolean;
  onPromoStatusChange?: (applied: boolean) => void;
  referralAppliedCents?: number;
  referralActive?: boolean;
  floorViolationMessage?: string | null;
  onClearFloorViolation?: () => void;
  onBookingUpdate?: (updater: (prev: BookingWithMetadata) => BookingWithMetadata) => void;
  creditsAccordionExpanded?: boolean;
  onCreditsAccordionToggle?: (expanded: boolean) => void;
}

function PaymentConfirmationInner({
  booking,
  paymentMethod,
  cardLast4,
  creditsUsed = 0,
  availableCredits = 0,
  creditEarliestExpiry = null,
  onConfirm,
  onBack: _onBack, // Kept for interface compatibility but not used
  onChangePaymentMethod,
  onCreditToggle,
  onCreditAmountChange,
  cardBrand = 'Card',
  isDefaultCard = false,
  promoApplied = false,
  onPromoStatusChange,
  referralAppliedCents = 0,
  referralActive: referralActiveFromParent = false,
  floorViolationMessage = null,
  onClearFloorViolation,
  onBookingUpdate,
  creditsAccordionExpanded,
  onCreditsAccordionToggle,
}: PaymentConfirmationProps) {
  const [locationType, setLocationType] = useState<LocationType>('student_location');
  const [lastInPersonLocationType, setLastInPersonLocationType] =
    useState<LocationType>('student_location');
  const [hasLocationInitialized, setHasLocationInitialized] = useState(false);
  const [hasConflict, setHasConflict] = useState(false);
  const [conflictMessage, setConflictMessage] = useState<string>('');
  const [isCheckingConflict, setIsCheckingConflict] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [instructorServices, setInstructorServices] = useState<InstructorService[]>([]);
  const [loadingInstructor, setLoadingInstructor] = useState(false);
  const [promoCode, setPromoCode] = useState('');
  const [promoActive, setPromoActive] = useState(promoApplied);
  const [promoError, setPromoError] = useState<string | null>(null);
  const { floors: pricingFloors, config: pricingConfig } = usePricingFloors();
  const pricingPreviewContext = usePricingPreview(true);
  const pricingPreview = pricingPreviewContext?.preview ?? null;
  const isPricingPreviewLoading = pricingPreviewContext?.loading ?? false;
  const pricingPreviewError = pricingPreviewContext?.error ?? null;
  const [selectedSavedAddress, setSelectedSavedAddress] = useState<SavedAddress | null>(null);
  const [teachingLocations, setTeachingLocations] = useState<TeachingLocation[]>([]);
  const [selectedTeachingLocation, setSelectedTeachingLocation] = useState<TeachingLocation | null>(null);
  const [isEditingLocation, setIsEditingLocation] = useState(true);
  const [addressFields, setAddressFields] = useState<AddressFields>(EMPTY_ADDRESS);
  const [addressCoords, setAddressCoords] = useState<AddressCoords>({
    lat: null,
    lng: null,
    placeId: null,
  });
  const [addressDetailsError, setAddressDetailsError] = useState<string | null>(null);
  const addressLine1Ref = useRef<HTMLInputElement>(null);
  const conflictAbortRef = useRef<AbortController | null>(null);
  const conflictCacheRef = useRef<Map<string, { fetchedAt: number; items: ConflictListItem[] }>>(new Map());
  const addressDetailsAbortRef = useRef<AbortController | null>(null);
  const addressDetailsCacheRef = useRef<Map<string, AddressDetailsCacheEntry>>(new Map());
  const lastLocationRef = useRef('');
  const initializedBookingIdRef = useRef<string | null>(null);
  const isOnlineLesson = locationType === 'online';
  const isTravelLocation = locationType === 'student_location' || locationType === 'neutral_location';
  const hasSavedTravelLocation = Boolean(
    selectedSavedAddress ||
      (isTravelLocation &&
        booking.location &&
        booking.location !== '' &&
        !/online|remote/i.test(String(booking.location)))
  );
  const serviceAreaLat = isTravelLocation ? addressCoords.lat ?? undefined : undefined;
  const serviceAreaLng = isTravelLocation ? addressCoords.lng ?? undefined : undefined;
  const { data: serviceAreaCheck, isLoading: isCheckingServiceArea } = useServiceAreaCheck({
    instructorId: booking.instructorId,
    lat: serviceAreaLat,
    lng: serviceAreaLng,
  });
  const isOutsideServiceArea = isTravelLocation && serviceAreaCheck?.is_covered === false;
  const setAddressField = useCallback((updates: Partial<AddressFields>) => {
    setAddressFields((prev) => ({ ...prev, ...updates }));
    setAddressCoords({ lat: null, lng: null, placeId: null });
    setSelectedSavedAddress(null);
  }, []);

  const buildSavedAddressLine1 = useCallback((address: SavedAddress): string => {
    const line1 = address.street_line1?.trim() ?? '';
    const line2 = address.street_line2?.trim() ?? '';
    return [line1, line2].filter((part) => part.length > 0).join(', ');
  }, []);

  const applySavedAddress = useCallback(
    (address: SavedAddress) => {
      setAddressFields({
        line1: buildSavedAddressLine1(address),
        city: address.locality ?? '',
        state: address.administrative_area ?? '',
        postalCode: address.postal_code ?? '',
        country: address.country_code ?? '',
      });
      setAddressCoords({
        lat: typeof address.latitude === 'number' ? address.latitude : null,
        lng: typeof address.longitude === 'number' ? address.longitude : null,
        placeId: typeof address.place_id === 'string' ? address.place_id : null,
      });
      setAddressDetailsError(null);
      setIsEditingLocation(false);
      lastLocationRef.current = '';
    },
    [buildSavedAddressLine1]
  );

  const handleSelectSavedAddress = useCallback(
    (address: SavedAddress | null) => {
      if (!address) {
        setSelectedSavedAddress(null);
        return;
      }
      setSelectedSavedAddress(address);
      if (!isTravelLocation) {
        setLocationType('student_location');
      }
      applySavedAddress(address);
    },
    [applySavedAddress, isTravelLocation]
  );

  const handleEnterNewAddress = useCallback(() => {
    setSelectedSavedAddress(null);
    setIsEditingLocation(true);
    setAddressDetailsError(null);
    requestAnimationFrame(() => {
      addressLine1Ref.current?.focus();
    });
  }, []);

  const handleSelectTeachingLocation = useCallback((location: TeachingLocation) => {
    setSelectedTeachingLocation(location);
    setIsEditingLocation(false);
    setAddressDetailsError(null);
  }, []);

  const resolvedServiceId = useMemo(() => {
    const metadataService = (booking as BookingWithMetadata).metadata?.['serviceId'];
    if (metadataService !== null && metadataService !== undefined) {
      return String(metadataService);
    }
    const bookingService = (booking as { serviceId?: unknown }).serviceId;
    if (bookingService !== null && bookingService !== undefined) {
      return String(bookingService);
    }
    if (typeof window !== 'undefined') {
      const stored = window.sessionStorage?.getItem('serviceId');
      if (stored && stored.trim().length > 0) {
        return stored;
      }
    }
    return null;
  }, [booking]);

  const selectedService = useMemo(() => {
    if (resolvedServiceId) {
      const match = instructorServices.find((service) => service.id === resolvedServiceId);
      if (match) {
        return match;
      }
    }
    return instructorServices.length === 1 ? instructorServices[0] : null;
  }, [instructorServices, resolvedServiceId]);

  const availableLocationTypes = useMemo<LocationType[]>(() => {
    const types: LocationType[] = [];
    if (selectedService) {
      const hasFlags =
        typeof selectedService.offers_online === 'boolean' ||
        typeof selectedService.offers_travel === 'boolean' ||
        typeof selectedService.offers_at_location === 'boolean';

      if (hasFlags) {
        if (selectedService.offers_online) {
          types.push('online');
        }
        if (selectedService.offers_at_location) {
          types.push('instructor_location');
        }
        if (selectedService.offers_travel) {
          types.push('student_location');
          types.push('neutral_location');
        }
      } else if (Array.isArray(selectedService.location_types)) {
        const normalized = selectedService.location_types
          .map((value) => String(value).trim().toLowerCase())
          .filter(Boolean);
        if (normalized.some((value) => value.includes('online'))) {
          types.push('online');
        }
        if (normalized.some((value) => value.includes('in_person') || value.includes('in-person'))) {
          types.push('student_location');
        }
      }
    }

    if (types.length === 0) {
      types.push('online', 'student_location');
    }

    return Array.from(new Set(types));
  }, [selectedService]);

  useEffect(() => () => {
    addressDetailsAbortRef.current?.abort();
  }, []);

  useEffect(() => {
    if (locationType !== 'online') {
      setLastInPersonLocationType(locationType);
    }
  }, [locationType]);

  useEffect(() => {
    if (availableLocationTypes.length === 0) {
      return;
    }
    if (!availableLocationTypes.includes(locationType)) {
      const fallback =
        locationType === 'online'
          ? availableLocationTypes[0]
          : availableLocationTypes.find((type) => type !== 'online') ?? availableLocationTypes[0];
      if (fallback) {
        setLocationType(fallback);
      }
    }
  }, [availableLocationTypes, locationType]);

  useEffect(() => {
    if (locationType !== 'instructor_location') {
      return;
    }
    if (!selectedTeachingLocation && teachingLocations.length > 0) {
      const [firstTeachingLocation] = teachingLocations;
      if (firstTeachingLocation) {
        setSelectedTeachingLocation(firstTeachingLocation);
      }
    }
  }, [locationType, selectedTeachingLocation, teachingLocations]);

  const parseAddressComponents = useCallback(
    (
      details: unknown
    ): { fields: Partial<AddressFields>; formatted?: string; lat?: number; lng?: number; placeId?: string } => {
      const root = (details as Record<string, unknown>) ?? {};
      const result = (root['result'] as Record<string, unknown>) ?? root;
      const address = (result['address'] as Record<string, unknown>) ?? result;
      const sources = [address, result, root].filter(
        (candidate): candidate is Record<string, unknown> => Boolean(candidate) && typeof candidate === 'object',
      );

      const getValue = (...keys: string[]) => {
        for (const source of sources) {
          for (const key of keys) {
            const raw = source[key];
            if (typeof raw === 'string' && raw.trim().length > 0) {
              return raw.trim();
            }
          }
        }
        return '';
      };

      const getNumber = (...keys: string[]) => {
        for (const source of sources) {
          for (const key of keys) {
            const raw = source[key];
            if (typeof raw === 'number' && Number.isFinite(raw)) {
              return raw;
            }
            if (typeof raw === 'string') {
              const parsed = Number(raw);
              if (Number.isFinite(parsed)) {
                return parsed;
              }
            }
          }
        }
        return null;
      };

      const streetNumber = getValue('line1', 'street_line1') ? '' : getValue('street_number', 'house_number');
      const streetName = getValue('street_name', 'route', 'street');
      const explicitLine1 = getValue(
        'line1',
        'line_1',
        'street_line1',
        'address_line1',
        'address1',
        'street_address',
      );
      const derivedLine1 = [streetNumber, streetName].filter((part) => part && part.length > 0).join(' ').trim();
      const cityCandidate = getValue('city', 'locality', 'postal_town', 'town', 'administrative_area_level_2');
      const stateCandidate = getValue(
        'state',
        'state_code',
        'region',
        'administrative_area',
        'administrative_area_level_1',
      );
      const postalCandidate = getValue('postal', 'postal_code', 'postalCode', 'zip', 'zip_code');
      const countryCandidate = getValue('country', 'country_code', 'countryCode');
      const formatted = getValue('formatted_address', 'formattedAddress');
      const placeId = getValue('provider_id', 'place_id', 'placeId');

      let lat = getNumber('latitude', 'lat');
      let lng = getNumber('longitude', 'lng');
      if (lat == null || lng == null) {
        const geometry = (result['geometry'] as Record<string, unknown>) ?? root['geometry'];
        const location = geometry && typeof geometry === 'object'
          ? (geometry['location'] as Record<string, unknown>)
          : null;
        if (location && typeof location === 'object') {
          if (lat == null) {
            const geoLat = location['lat'];
            if (typeof geoLat === 'number' && Number.isFinite(geoLat)) {
              lat = geoLat;
            }
          }
          if (lng == null) {
            const geoLng = location['lng'];
            if (typeof geoLng === 'number' && Number.isFinite(geoLng)) {
              lng = geoLng;
            }
          }
        }
      }

      const fields: Partial<AddressFields> = {};
      const resolvedLine1 = (explicitLine1 || derivedLine1).trim();
      if (resolvedLine1) fields.line1 = resolvedLine1;
      if (cityCandidate) fields.city = cityCandidate;
      if (stateCandidate) fields.state = toStateCode(stateCandidate);
      if (postalCandidate) fields.postalCode = postalCandidate;
      if (countryCandidate) fields.country = countryCandidate;

      const response: {
        fields: Partial<AddressFields>;
        formatted?: string;
        lat?: number;
        lng?: number;
        placeId?: string;
      } = { fields };
      if (formatted) {
        response.formatted = formatted;
      }
      if (lat != null) {
        response.lat = lat;
      }
      if (lng != null) {
        response.lng = lng;
      }
      if (placeId) {
        response.placeId = placeId;
      }

      return response;
    },
    [],
  );

  const parseDescriptionFallback = useCallback((description: string): Partial<AddressFields> => {
    const segments = description
      .split(',')
      .map((segment) => segment.trim())
      .filter((segment) => segment.length > 0);

    const [line1Candidate, cityCandidate, statePostalCandidate, countryCandidate] = segments;
    const fallback: Partial<AddressFields> = {};

    if (line1Candidate) fallback.line1 = line1Candidate;
    if (cityCandidate) fallback.city = cityCandidate;
    if (statePostalCandidate) {
      const parts = statePostalCandidate.split(/\s+/).filter((part) => part.length > 0);
      const postal = parts.pop();
      if (postal) {
        fallback.postalCode = postal;
      }
      if (parts.length > 0) {
        fallback.state = toStateCode(parts.join(' '));
      }
    }
    if (countryCandidate) fallback.country = countryCandidate;

    return fallback;
  }, []);

  const fetchPlaceDetails = useCallback(async (
    placeId: string,
    signal: AbortSignal,
    provider?: string,
  ) => {
    try {
      const response = await getPlaceDetails({
        place_id: placeId,
        ...(provider ? { provider } : {}),
        signal,
      });

      if (signal.aborted) {
        return null;
      }

      if (response.error || !response.data) {
        logger.warn('Place details request failed', {
          placeId,
          status: response.status,
          error: response.error,
        });
        return null;
      }

      return response.data;
    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        return null;
      }
      logger.warn('Failed to fetch place details', { placeId, error });
      return null;
    }
  }, []);

  const handleAddressSuggestionSelect = useCallback(async (suggestion: PlaceSuggestion) => {
    if (!suggestion || !isTravelLocation) {
      return;
    }

    setIsEditingLocation(true);
    setAddressDetailsError(null);
    setSelectedSavedAddress(null);

    const description = (suggestion.description ?? suggestion.text ?? '').trim();
    const fallbackFromDescription = parseDescriptionFallback(description);

    const normalizedPlaceIdRaw =
      typeof suggestion.place_id === 'string' && suggestion.place_id.trim().length > 0
        ? suggestion.place_id.trim()
        : (suggestion as { id?: string }).id && typeof (suggestion as { id?: string }).id === 'string'
          ? ((suggestion as { id?: string }).id as string).trim()
          : '';
    const normalizedPlaceId = normalizedPlaceIdRaw || null;
    const suggestionProvider =
      typeof suggestion.provider === 'string' && suggestion.provider.trim().length > 0
        ? suggestion.provider.trim().toLowerCase()
        : undefined;

    addressDetailsAbortRef.current?.abort();

    if (!normalizedPlaceId) {
      const fallbackFields: AddressFields = {
        line1: fallbackFromDescription.line1 ?? '',
        city: fallbackFromDescription.city ?? '',
        state: toStateCode(fallbackFromDescription.state),
        postalCode: fallbackFromDescription.postalCode ?? '',
        country: fallbackFromDescription.country ?? '',
      };

      setAddressFields(fallbackFields);
      setAddressCoords({ lat: null, lng: null, placeId: null });
      setIsEditingLocation(false);
      lastLocationRef.current = '';
      addressDetailsAbortRef.current = null;
      return;
    }

    const cacheKey = `${suggestionProvider ?? 'default'}:${normalizedPlaceId}`;
    const cached = addressDetailsCacheRef.current.get(cacheKey);
    if (cached) {
      setAddressFields(cached.fields);
      setAddressCoords({
        lat: cached.lat ?? null,
        lng: cached.lng ?? null,
        placeId: cached.placeId ?? null,
      });
      setIsEditingLocation(false);
      lastLocationRef.current = '';
      addressDetailsAbortRef.current = null;
      return;
    }

    const controller = new AbortController();
    addressDetailsAbortRef.current = controller;

    const details = await fetchPlaceDetails(normalizedPlaceId, controller.signal, suggestionProvider);
    if (controller.signal.aborted) {
      return;
    }

    let parsedDetails = details ? parseAddressComponents(details) : null;

    if (!parsedDetails && suggestionProvider) {
      // Provider rejected; attempt a one-time retry using provider inferred from id prefix.
      const prefixMatch = normalizedPlaceIdRaw.match(/^(google|mapbox|mock):(.+)$/i);
      if (prefixMatch) {
        const [, providerFragment, idFragment] = prefixMatch;
        if (providerFragment && idFragment) {
          const inferredProvider = providerFragment.toLowerCase();
          const inferredId = idFragment;
          const retryKey = `${inferredProvider}:${inferredId}`;
          const retryCacheHit = addressDetailsCacheRef.current.get(retryKey);
          if (retryCacheHit) {
            parsedDetails = {
              fields: retryCacheHit.fields,
              ...(retryCacheHit.formatted ? { formatted: retryCacheHit.formatted } : {}),
            };
          } else {
            const retryController = new AbortController();
            addressDetailsAbortRef.current = retryController;
            const retryDetails = await fetchPlaceDetails(
              inferredId,
              retryController.signal,
              inferredProvider,
            );
            if (!retryController.signal.aborted && retryDetails) {
              const parsedRetry = parseAddressComponents(retryDetails);
              parsedDetails = parsedRetry;
              const normalizedRetryFields: AddressFields = {
                line1: parsedRetry.fields.line1 ?? '',
                city: parsedRetry.fields.city ?? '',
                state: toStateCode(parsedRetry.fields.state),
                postalCode: parsedRetry.fields.postalCode ?? '',
                country: parsedRetry.fields.country ?? '',
              };
              addressDetailsCacheRef.current.set(retryKey, {
                fields: normalizedRetryFields,
                ...(parsedRetry.formatted
                  ? { formatted: parsedRetry.formatted }
                  : { formatted: formatFullAddress(normalizedRetryFields) }),
                ...(parsedRetry.lat != null ? { lat: parsedRetry.lat } : {}),
                ...(parsedRetry.lng != null ? { lng: parsedRetry.lng } : {}),
                ...(parsedRetry.placeId ? { placeId: parsedRetry.placeId } : {}),
              });
            }
          }
        }
      }
    }

    const fields = parsedDetails?.fields ?? {};
    const formatted = parsedDetails?.formatted;

    const appliedFields: AddressFields = {
      line1: fields.line1 ?? fallbackFromDescription.line1 ?? description,
      city: fields.city ?? fallbackFromDescription.city ?? '',
      state: toStateCode(fields.state ?? fallbackFromDescription.state),
      postalCode: fields.postalCode ?? fallbackFromDescription.postalCode ?? '',
      country: fields.country ?? fallbackFromDescription.country ?? '',
    };

    const mergedFields: AddressFields = appliedFields;
    const normalizedMergedFields: AddressFields = {
      ...mergedFields,
      state: toStateCode(mergedFields.state),
    };

    const normalizedCoords: AddressCoords = {
      lat: parsedDetails?.lat ?? null,
      lng: parsedDetails?.lng ?? null,
      placeId: parsedDetails?.placeId ?? normalizedPlaceId,
    };

    addressDetailsCacheRef.current.set(cacheKey, {
      fields: normalizedMergedFields,
      formatted: formatted ?? formatFullAddress(normalizedMergedFields),
      ...(normalizedCoords.lat != null ? { lat: normalizedCoords.lat } : {}),
      ...(normalizedCoords.lng != null ? { lng: normalizedCoords.lng } : {}),
      ...(normalizedCoords.placeId ? { placeId: normalizedCoords.placeId } : {}),
    });

    setAddressFields(normalizedMergedFields);
    setAddressCoords(normalizedCoords);
    const hasStructuredAddress =
      normalizedMergedFields.city &&
      normalizedMergedFields.state &&
      normalizedMergedFields.postalCode;

    if (hasStructuredAddress) {
      setAddressDetailsError(null);
    } else {
      setAddressDetailsError("Couldn't fetch address details");
    }
    setIsEditingLocation(false);
    lastLocationRef.current = '';
    addressDetailsAbortRef.current = null;
  }, [fetchPlaceDetails, isTravelLocation, parseAddressComponents, parseDescriptionFallback]);

  if (process.env.NODE_ENV !== 'production') {
    logger.info('PaymentConfirmation component rendered', {
      booking,
      hasConflict,
      isCheckingConflict,
    });
  }
  // Auto-collapse payment if user has a saved card
  const hasSavedCard = !!cardLast4;
  const [isPaymentExpanded, setIsPaymentExpanded] = useState(!hasSavedCard);
  // Auto-collapse location if they have a saved address or it's online
  const [isLocationExpanded, setIsLocationExpanded] = useState(!hasSavedTravelLocation && !isOnlineLesson);
  const isLastMinute = booking.bookingType === BookingType.LAST_MINUTE;
  const creditsUsedCents = Math.max(0, Math.round(creditsUsed * 100));

  // Server-authoritative credit value
  const serverCreditCents = pricingPreview?.credit_applied_cents ?? null;
  const derivedAppliedCreditCents = serverCreditCents != null
    ? Math.max(0, serverCreditCents)
    : creditsUsedCents;

  // Slider drag state - only set during active drag, null otherwise
  // This eliminates the useEffect sync that caused extra renders
  const [sliderDragCents, setSliderDragCents] = useState<number | null>(null);

  // Display value: use drag value during drag, otherwise derive from server
  const displayAppliedCreditCents = sliderDragCents ?? derivedAppliedCreditCents;
  const appliedCreditDollars = displayAppliedCreditCents / 100;

  const totalBeforeCreditsCents = pricingPreview
    ? pricingPreview.student_pay_cents + Math.max(0, pricingPreview.credit_applied_cents)
    : Math.max(0, Math.round(booking.totalAmount * 100));
  const totalBeforeCreditsDollars = totalBeforeCreditsCents / 100;

  const studentPayCents = pricingPreview
    ? pricingPreview.student_pay_cents
    : Math.max(0, totalBeforeCreditsCents - derivedAppliedCreditCents);

  const referralCreditCents = Math.max(0, referralAppliedCents);
  const referralCreditAmount = referralCreditCents / 100;
  const referralActive = referralActiveFromParent || referralCreditAmount > 0;

  const totalAfterCreditsCents = Math.max(0, studentPayCents - referralCreditCents);
  const totalAfterCredits = totalAfterCreditsCents / 100;

  const cardChargeCents = totalAfterCreditsCents;
  const cardCharge = cardChargeCents / 100;

  const remainingBalanceCents = Math.max(0, totalBeforeCreditsCents - displayAppliedCreditCents);
  const remainingBalanceDollars = remainingBalanceCents / 100;
  const promoApplyDisabled = referralActive || (!promoActive && promoCode.trim().length === 0);

  const previewAdditionalLineItems = useMemo<PricingLineItem[]>(() => {
    if (!pricingPreview) {
      return [];
    }
    const lineItems: PricingLineItem[] = pricingPreview.line_items;
    const studentFeeCents = pricingPreview.student_fee_cents;
    return lineItems.filter((item) => {
      const normalizedLabel = item.label.toLowerCase();
      if (normalizedLabel.startsWith('booking protection')) {
        return false;
      }
      if (normalizedLabel.startsWith('service & support')) {
        return false;
      }
      if (normalizedLabel.includes('credit')) {
        return false;
      }
      if (typeof studentFeeCents === 'number' && item.amount_cents === studentFeeCents) {
        return false;
      }
      return true;
    });
  }, [pricingPreview]);

  const renderSummarySkeleton = (widthClass = 'w-16') => (
    <span
      data-testid="pricing-preview-skeleton"
      className={`inline-block h-3 ${widthClass} rounded bg-gray-200 animate-pulse`}
      aria-hidden="true"
    />
  );

  // Consolidated pricing display values - reduces memo chain cascade
  // Previously: 3 chained useMemo + 8 inline calculations recalculating on every render
  // Now: Single memo with all display values computed together
  const pricingDisplayValues = useMemo(() => {
    const fallbackBasePrice = Number.isFinite(booking.basePrice) ? Number(booking.basePrice) : 0;
    const feePercent = computeStudentFeePercent({ preview: pricingPreview, config: pricingConfig });
    const creditsLineCents = pricingPreview
      ? Math.max(0, pricingPreview.credit_applied_cents)
      : displayAppliedCreditCents;

    return {
      // Service fee display
      serviceSupportFeePercent: feePercent,
      serviceSupportFeeLabel: formatServiceSupportLabel(feePercent),
      serviceSupportFeeTooltip: formatServiceSupportTooltip(feePercent),
      // Price amounts
      lessonAmountDisplay: pricingPreview
        ? formatCentsToDisplay(pricingPreview.base_price_cents)
        : `$${fallbackBasePrice.toFixed(2)}`,
      serviceSupportFeeAmountDisplay: pricingPreview
        ? formatCentsToDisplay(pricingPreview.student_fee_cents)
        : null,
      // Credits
      creditsLineCents,
      hasCreditsApplied: creditsLineCents > 0,
      creditsAmountDisplay: formatCentsToDisplay(-creditsLineCents),
      // Total
      totalAmountDisplay: pricingPreview
        ? formatCentsToDisplay(pricingPreview.student_pay_cents)
        : null,
      showFeesPlaceholder: Boolean(pricingPreviewError),
    };
  }, [booking.basePrice, pricingPreview, pricingConfig, displayAppliedCreditCents, pricingPreviewError]);

  // Destructure for backwards compatibility with existing JSX
  const {
    serviceSupportFeeLabel,
    serviceSupportFeeTooltip,
    lessonAmountDisplay,
    serviceSupportFeeAmountDisplay,
    hasCreditsApplied,
    creditsAmountDisplay,
    totalAmountDisplay,
    showFeesPlaceholder,
  } = pricingDisplayValues;

  const studentId = useMemo(() => {
    const fromBooking = (booking as unknown as { studentId?: string | null }).studentId;
    if (typeof fromBooking === 'string' && fromBooking.trim().length > 0) {
      return fromBooking;
    }
    return 'current_student';
  }, [booking]);

  const bookingDateLocal = useMemo(() => {
    if (!booking.date) {
      return null;
    }
    try {
      if (booking.date instanceof Date) {
        return toDateOnlyString(booking.date, 'booking.date');
      }
      return toDateOnlyString(String(booking.date), 'booking.date');
    } catch (error) {
      logger.warn('Unable to normalize booking date for conflict key', {
        bookingDate: booking.date,
        error,
      });
      return null;
    }
  }, [booking.date]);

  const startHHMM24 = useMemo(() => {
    if (!booking.startTime) {
      return null;
    }
    try {
      return to24HourTime(String(booking.startTime));
    } catch (error) {
      logger.warn('Unable to normalize start time for conflict key', {
        startTime: booking.startTime,
        error,
      });
      return null;
    }
  }, [booking.startTime]);

  const summaryDateLabel = useMemo(() => {
    const buildDisplayDate = (value: string | Date | null | undefined): Date | null => {
      if (!value) {
        return null;
      }
      if (value instanceof Date) {
        return Number.isNaN(value.getTime()) ? null : value;
      }
      const isoCandidate = typeof value === 'string' ? value : String(value);
      if (!isoCandidate) {
        return null;
      }
      const parsed = new Date(`${isoCandidate}T00:00:00`);
      return Number.isNaN(parsed.getTime()) ? null : parsed;
    };

    const displayDate = buildDisplayDate(bookingDateLocal) ?? buildDisplayDate(booking.date);
    if (!displayDate) {
      return 'Date to be confirmed';
    }

    try {
      return format(displayDate, 'EEEE, MMMM d, yyyy');
    } catch (error) {
      logger.debug('pricing-preview:date-parse-warning', error);
      return 'Date to be confirmed';
    }
  }, [booking.date, bookingDateLocal]);

  const durationMinutes = useMemo(() => {
    if (Number.isFinite(booking.duration) && booking.duration > 0) {
      return Math.round(booking.duration);
    }
    if (booking.startTime && booking.endTime) {
      try {
        const start = minutesSinceHHMM(to24HourTime(String(booking.startTime)));
        const end = minutesSinceHHMM(to24HourTime(String(booking.endTime)));
        const diff = end - start;
        return diff > 0 ? diff : null;
      } catch (error) {
        logger.warn('Unable to derive duration for conflict key', {
          startTime: booking.startTime,
          endTime: booking.endTime,
          error,
        });
      }
    }
    return null;
  }, [booking.duration, booking.startTime, booking.endTime]);

  const normalizedLessonDuration = useMemo(() => {
    if (Number.isFinite(durationMinutes) && durationMinutes) {
      return durationMinutes;
    }
    if (Number.isFinite(booking.duration) && booking.duration > 0) {
      return Math.round(booking.duration);
    }
    return null;
  }, [booking.duration, durationMinutes]);

  const lessonSummaryLabel = useMemo(() => {
    const minutes = normalizedLessonDuration ?? 0;
    return `Lesson (${minutes} min)`;
  }, [normalizedLessonDuration]);

  const computedEndHHMM24 = useMemo(() => {
    if (booking.endTime) {
      try {
        return to24HourTime(String(booking.endTime));
      } catch (error) {
        logger.debug('pricing-preview:end-time-parse', error);
      }
    }
    if (startHHMM24 && Number.isFinite(durationMinutes) && durationMinutes) {
      try {
        return addMinutesHHMM(startHHMM24, durationMinutes);
      } catch (error) {
        logger.debug('pricing-preview:end-time-derive', error);
      }
    }
    return null;
  }, [booking.endTime, durationMinutes, startHHMM24]);

  const summaryTimeLabel = useMemo(() => {
    if (!startHHMM24) {
      return booking.startTime ? String(booking.startTime) : 'Time to be confirmed';
    }
    const endHHMM24 = computedEndHHMM24 || (durationMinutes ? addMinutesHHMM(startHHMM24, durationMinutes) : null);
    if (!endHHMM24) {
      return startHHMM24;
    }
    return `${startHHMM24} - ${endHHMM24}`;
  }, [booking.startTime, computedEndHHMM24, durationMinutes, startHHMM24]);

  const conflictKey = useMemo<ConflictKey | null>(() => {
    if (
      !booking.instructorId ||
      !bookingDateLocal ||
      !startHHMM24 ||
      !durationMinutes ||
      durationMinutes <= 0
    ) {
      return null;
    }

    return {
      studentId,
      instructorId: String(booking.instructorId),
      bookingDate: bookingDateLocal,
      startHHMM24,
      durationMinutes,
    };
  }, [booking.instructorId, bookingDateLocal, startHHMM24, durationMinutes, studentId]);

  const computeHasConflict = useCallback((key: ConflictKey, items: ConflictListItem[]): boolean => {
    return items.some((existing) => {
      if (!existing) return false;
      if (existing.booking_date && existing.booking_date !== key.bookingDate) {
        return false;
      }
      if (existing.status && !CONFLICT_RELEVANT_STATUSES.has(existing.status.toLowerCase())) {
        return false;
      }
      if (!existing.start_time) {
        return false;
      }

      let existingStart: string;
      try {
        existingStart = to24HourTime(String(existing.start_time));
      } catch {
        return false;
      }

      let existingDuration = Number.isFinite(existing.duration_minutes)
        ? Math.round(Number(existing.duration_minutes))
        : null;

      if (!existingDuration || existingDuration <= 0) {
        if (existing.end_time) {
          try {
            const startMinutes = minutesSinceHHMM(existingStart);
            const endMinutes = minutesSinceHHMM(to24HourTime(String(existing.end_time)));
            const diff = endMinutes - startMinutes;
            existingDuration = diff > 0 ? diff : null;
          } catch {
            existingDuration = null;
          }
        }
      }

      if (!existingDuration || existingDuration <= 0) {
        return false;
      }

      return overlapsHHMM(key.startHHMM24, key.durationMinutes, existingStart, existingDuration);
    });
  }, []);

  const selectedModality = useMemo<NormalizedModality>(
    () => (isOnlineLesson ? 'online' : 'in_person'),
    [isOnlineLesson],
  );
  const inputsDisabled = !isTravelLocation || (hasSavedTravelLocation && !isEditingLocation);
  const instructorFirstName = useMemo(() => {
    const parts = booking.instructorName.split(' ').filter(Boolean);
    return parts[0] || 'Instructor';
  }, [booking.instructorName]);
  const inPersonOptions = useMemo(
    () => availableLocationTypes.filter((type) => type !== 'online'),
    [availableLocationTypes],
  );
  const showOnlineOption = availableLocationTypes.includes('online');

  const getLocationOptionLabel = useCallback(
    (type: LocationType) => {
      switch (type) {
        case 'student_location':
          return 'At your location';
        case 'neutral_location':
          return 'At a public location';
        case 'instructor_location':
          return `At ${instructorFirstName}'s location`;
        case 'online':
          return 'Online';
        default:
          return 'Location';
      }
    },
    [instructorFirstName],
  );

  const formattedAddress = useMemo(() => formatFullAddress(addressFields), [addressFields]);

  const fallbackNonOnlineLocation = useMemo(() => {
    if (typeof booking.location === 'string' && booking.location && !/online|remote/i.test(booking.location)) {
      return booking.location;
    }
    return '';
  }, [booking.location]);

  const resolvedMeetingLocation = useMemo(() => {
    if (locationType === 'online') {
      return 'Online';
    }
    if (locationType === 'instructor_location') {
      if (selectedTeachingLocation?.address) {
        return selectedTeachingLocation.address;
      }
      return fallbackNonOnlineLocation || INSTRUCTOR_LOCATION_PLACEHOLDER;
    }
    if (formattedAddress) {
      return formattedAddress;
    }
    if (fallbackNonOnlineLocation) {
      return fallbackNonOnlineLocation;
    }
    return ADDRESS_PLACEHOLDER;
  }, [fallbackNonOnlineLocation, formattedAddress, locationType, selectedTeachingLocation]);

  const handleLocationTypeChange = useCallback(
    (nextType: LocationType) => {
      addressDetailsAbortRef.current?.abort();
      addressDetailsAbortRef.current = null;
      setLocationType(nextType);
      setIsLocationExpanded(true);
      setAddressDetailsError(null);

      if (nextType === 'online') {
        setAddressCoords({ lat: null, lng: null, placeId: null });
        setIsEditingLocation(false);
      } else if (nextType === 'instructor_location') {
        setIsEditingLocation(false);
      } else if (selectedSavedAddress) {
        applySavedAddress(selectedSavedAddress);
      } else if (!hasSavedTravelLocation) {
        setIsEditingLocation(true);
      }

      onClearFloorViolation?.();
    },
    [applySavedAddress, hasSavedTravelLocation, onClearFloorViolation, selectedSavedAddress]
  );

  const handleOnlineToggleChange = (checked: boolean) => {
    const fallbackType =
      lastInPersonLocationType === 'online' ? 'student_location' : lastInPersonLocationType;
    handleLocationTypeChange(checked ? 'online' : fallbackType);
  };

  const handleChangeLocationClick = () => {
    setIsLocationExpanded(true);
    if (!isTravelLocation) {
      setLocationType('student_location');
    }
    setIsEditingLocation(true);
    setAddressDetailsError(null);
    onClearFloorViolation?.();
    requestAnimationFrame(() => {
      addressLine1Ref.current?.focus();
    });
  };

  useEffect(() => {
    if (!onBookingUpdate || !hasLocationInitialized) {
      return;
    }

    const modalityValue = locationType === 'online' ? 'remote' : 'in_person';

    if (isTravelLocation && isEditingLocation) {
      const cacheKey = `${locationType}|editing`;
      if (lastLocationRef.current === cacheKey) {
        return;
      }
      lastLocationRef.current = cacheKey;
      onBookingUpdate((prev) => ({
        ...prev,
        metadata: {
          ...(prev.metadata ?? {}),
          modality: modalityValue,
          location_type: locationType,
        },
      }));
      return;
    }

    let nextLocation = '';
    let addressPayload: BookingPayment['address'] | null = null;

    if (locationType === 'online') {
      nextLocation = 'Online';
    } else if (locationType === 'instructor_location') {
      const instructorAddress = selectedTeachingLocation?.address ?? '';
      nextLocation = instructorAddress || INSTRUCTOR_LOCATION_PLACEHOLDER;
      addressPayload = nextLocation
        ? {
            fullAddress: nextLocation,
          }
        : null;
    } else {
      nextLocation = formattedAddress || fallbackNonOnlineLocation || '';
      if (nextLocation) {
        addressPayload = {
          fullAddress: nextLocation,
          ...(addressCoords.lat != null ? { lat: addressCoords.lat } : {}),
          ...(addressCoords.lng != null ? { lng: addressCoords.lng } : {}),
          ...(addressCoords.placeId ? { placeId: addressCoords.placeId } : {}),
        };
      }
    }

    const cacheKey = `${locationType}|${nextLocation || 'unset'}`;
    if (lastLocationRef.current === cacheKey) {
      return;
    }
    lastLocationRef.current = cacheKey;

    onBookingUpdate((prev) => {
      const nextBooking: BookingWithMetadata = {
        ...prev,
        location: nextLocation,
        metadata: {
          ...(prev.metadata ?? {}),
          modality: modalityValue,
          location_type: locationType,
        },
      };

      if (addressPayload) {
        return { ...nextBooking, address: addressPayload };
      }

      const { address: _address, ...withoutAddress } = nextBooking;
      return withoutAddress;
    });
  }, [
    locationType,
    formattedAddress,
    fallbackNonOnlineLocation,
    onBookingUpdate,
    hasLocationInitialized,
    isEditingLocation,
    isTravelLocation,
    addressCoords.lat,
    addressCoords.lng,
    addressCoords.placeId,
    selectedTeachingLocation,
  ]);
  const hourlyRate = useMemo(() => {
    if (!Number.isFinite(booking.duration) || booking.duration <= 0) return 0;
    return Number(((booking.basePrice || 0) * 60) / booking.duration);
  }, [booking.basePrice, booking.duration]);

  const clientFloorViolation = useMemo(() => {
    if (!pricingFloors) return null;
    if (!Number.isFinite(hourlyRate) || hourlyRate <= 0) return null;
    if (!Number.isFinite(booking.duration) || booking.duration <= 0) return null;
    const floorCents = computePriceFloorCents(pricingFloors, selectedModality, booking.duration);
    const baseCents = computeBasePriceCents(hourlyRate, booking.duration);
    if (baseCents < floorCents) {
      return { floorCents, baseCents };
    }
    return null;
  }, [pricingFloors, hourlyRate, booking.duration, selectedModality]);

  const clientFloorWarning = useMemo(() => {
    if (!clientFloorViolation) return null;
    const modalityLabel = selectedModality === 'in_person' ? 'in-person' : 'online';
    return `Minimum for ${modalityLabel} ${booking.duration}-minute private session is $${formatCents(clientFloorViolation.floorCents)} (current $${formatCents(clientFloorViolation.baseCents)}).`;
  }, [clientFloorViolation, booking.duration, selectedModality]);

  const activeFloorMessage = clientFloorWarning ?? floorViolationMessage ?? null;
  const isFloorBlocking = Boolean(activeFloorMessage);
  const ctaDisabled =
    isCheckingConflict ||
    hasConflict ||
    isFloorBlocking ||
    isPricingPreviewLoading ||
    isOutsideServiceArea ||
    (isCheckingServiceArea && isTravelLocation);
  const ctaLabel = useMemo(() => {
    if (isCheckingConflict) return 'Checking availability...';
    if (hasConflict) return 'You have a conflict at this time';
    if (isFloorBlocking) return 'Price must meet minimum';
    if (isPricingPreviewLoading) return 'Updating total...';
    return 'Book now!';
  }, [isCheckingConflict, hasConflict, isFloorBlocking, isPricingPreviewLoading]);

  const creditsAccordionPanelId = useId();
  const isCreditsExpandedControlled = typeof creditsAccordionExpanded === 'boolean';
  const [internalCreditsExpanded, setInternalCreditsExpanded] = useState(() => derivedAppliedCreditCents > 0);

  useEffect(() => {
    if (!isCreditsExpandedControlled && derivedAppliedCreditCents > 0 && !internalCreditsExpanded) {
      setInternalCreditsExpanded(true);
    }
  }, [isCreditsExpandedControlled, derivedAppliedCreditCents, internalCreditsExpanded]);

  const creditsAccordionIsExpanded = isCreditsExpandedControlled
    ? Boolean(creditsAccordionExpanded)
    : internalCreditsExpanded;

  const handleCreditsAccordionToggle = useCallback(() => {
    const next = !creditsAccordionIsExpanded;
    if (!isCreditsExpandedControlled) {
      setInternalCreditsExpanded(next);
    }
    onCreditsAccordionToggle?.(next);
  }, [creditsAccordionIsExpanded, isCreditsExpandedControlled, onCreditsAccordionToggle]);
  const creditsAppliedLabel = useMemo(() => `Using $${appliedCreditDollars.toFixed(2)}`, [appliedCreditDollars]);
  const previewAppliedCreditCents = Math.max(0, pricingPreview?.credit_applied_cents ?? 0);
  const collapsedHasCredits = !creditsAccordionIsExpanded && previewAppliedCreditCents > 0;

  useEffect(() => {
    setPromoActive(promoApplied);
    if (!promoApplied) {
      setPromoError(null);
    }
  }, [promoApplied]);

  useEffect(() => {
    const currentBookingId = booking.bookingId ?? '';
    if (hasLocationInitialized && initializedBookingIdRef.current === currentBookingId) {
      return;
    }
    initializedBookingIdRef.current = currentBookingId;

    const metadata = (booking as BookingWithMetadata).metadata ?? {};
    const normalizeLocationHint = (value: unknown): LocationType | null => {
      if (typeof value !== 'string') {
        return null;
      }
      const raw = value.trim().toLowerCase();
      if (!raw) {
        return null;
      }
      if (raw.includes('remote') || raw.includes('online') || raw.includes('virtual')) {
        return 'online';
      }
      if (raw.includes('instructor') || raw.includes('studio')) {
        return 'instructor_location';
      }
      if (raw.includes('neutral') || raw.includes('public')) {
        return 'neutral_location';
      }
      if (raw.includes('student') || raw.includes('home') || raw.includes('in_person') || raw.includes('in-person')) {
        return 'student_location';
      }
      return null;
    };

    const metadataLocationType = normalizeLocationHint(metadata['location_type']);
    const metadataModality = normalizeLocationHint(metadata['modality']);
    let nextLocationType = metadataLocationType ?? metadataModality;

    if (!nextLocationType) {
      if (typeof booking.location === 'string' && booking.location) {
        nextLocationType = /online|remote|virtual/i.test(booking.location)
          ? 'online'
          : 'student_location';
      } else {
        nextLocationType = 'student_location';
      }
    }

    setLocationType(nextLocationType);
    if (nextLocationType !== 'online') {
      setLastInPersonLocationType(nextLocationType);
    }

    if (nextLocationType === 'instructor_location') {
      if (!selectedTeachingLocation && typeof booking.location === 'string' && booking.location) {
        setSelectedTeachingLocation({ address: booking.location });
      }
    } else if (typeof booking.location === 'string' && booking.location && !/online|remote/i.test(booking.location)) {
      setAddressFields((prev) => {
        if (prev.line1 || prev.city || prev.state || prev.postalCode) {
          return prev;
        }
        return {
          ...prev,
          line1: booking.location,
        };
      });
    }

    if (booking.address) {
      setAddressCoords({
        lat: booking.address.lat ?? null,
        lng: booking.address.lng ?? null,
        placeId: booking.address.placeId ?? null,
      });
    }

    if (!hasLocationInitialized) {
      if (nextLocationType === 'student_location' || nextLocationType === 'neutral_location') {
        const hasExistingLocation =
          typeof booking.location === 'string' && booking.location && !/online|remote/i.test(booking.location);
        setIsEditingLocation(!hasExistingLocation);
      } else {
        setIsEditingLocation(false);
      }
    }

    setHasLocationInitialized(true);
  }, [booking, hasLocationInitialized, selectedTeachingLocation, setAddressFields]);

  useEffect(() => {
    if (isEditingLocation && isTravelLocation) {
      const raf = requestAnimationFrame(() => {
        addressLine1Ref.current?.focus();
      });
      return () => cancelAnimationFrame(raf);
    }
    return undefined;
  }, [isEditingLocation, isTravelLocation]);

  useEffect(() => {
    if (!isTravelLocation) {
      setIsEditingLocation(false);
    }
  }, [isTravelLocation]);

  useEffect(() => {
    if (!referralActive) {
      return;
    }
    if (promoActive) {
      setPromoActive(false);
      onPromoStatusChange?.(false);
    }
    if (promoCode) {
      setPromoCode('');
    }
    if (promoError) {
      setPromoError(null);
    }
  }, [referralActive, promoActive, promoCode, promoError, onPromoStatusChange]);

  // Check for booking conflicts when component mounts
  useEffect(() => {
    if (!conflictKey) {
      if (conflictAbortRef.current) {
        conflictAbortRef.current.abort();
        conflictAbortRef.current = null;
      }
      setHasConflict(false);
      setConflictMessage('');
      setIsCheckingConflict(false);
      return;
    }

    if (conflictAbortRef.current) {
      conflictAbortRef.current.abort();
    }

    const controller = new AbortController();
    conflictAbortRef.current = controller;
    setIsCheckingConflict(true);

    if (process.env.NODE_ENV !== 'production') {
      logger.info('Checking for booking conflicts...', conflictKey);
    }

    const timeoutId = window.setTimeout(async () => {
      const cacheKey = `${conflictKey.studentId}|${conflictKey.bookingDate}`;
      const cached = conflictCacheRef.current.get(cacheKey);
      let items: ConflictListItem[] | undefined;

      if (cached && Date.now() - cached.fetchedAt < CONFLICT_CACHE_TTL_MS) {
        items = cached.items;
      } else {
        try {
          // Use v1 bookings service
          const response = await fetchBookingsList({ upcoming_only: true });
          items = (response.items as ConflictListItem[]) ?? [];
          conflictCacheRef.current.set(cacheKey, {
            fetchedAt: Date.now(),
            items,
          });
        } catch (error) {
          if ((error as Error).name === 'AbortError') {
            return;
          }
          logger.error('Failed to check for booking conflicts', error as Error);
          setHasConflict(false);
          setConflictMessage('');
          setIsCheckingConflict(false);
          return;
        }
      }

      if (controller.signal.aborted) {
        return;
      }

      const has = computeHasConflict(conflictKey, items ?? []);
      setHasConflict(has);
      setConflictMessage(has ? 'You already have a booking scheduled at this time.' : '');
      setIsCheckingConflict(false);
    }, 250);

    return () => {
      clearTimeout(timeoutId);
      controller.abort();
    };
  }, [conflictKey, computeHasConflict]);

  const handlePromoAction = () => {
    if (referralActive) {
      setPromoError('Referral credit can’t be combined with a promo code.');
      return;
    }
    if (promoActive) {
      setPromoActive(false);
      setPromoError(null);
      setPromoCode('');
      onPromoStatusChange?.(false);
      return;
    }

    if (!promoCode.trim()) {
      setPromoError('Enter a promo code to apply.');
      return;
    }

    if (referralActive) {
      setPromoError('Referral credit can’t be combined with a promo code.');
      return;
    }

    setPromoActive(true);
    setPromoError(null);
    onPromoStatusChange?.(true);
  };

  const handlePromoInputChange = (value: string) => {
    setPromoCode(value);
    if (promoError) {
      setPromoError(null);
    }
  };

  // Fetch instructor profile to get the actual service duration options
  useEffect(() => {
    const loadInstructorProfile = async () => {
      if (!booking.instructorId) return;

      setLoadingInstructor(true);
      try {
        // Use v1 instructors service
        const data = await fetchInstructorProfile(booking.instructorId);
        const services = data.services || [];
        if (services.length) {
          setInstructorServices(services.map((service) => ({
            ...service,
            description: service.description ?? null
          } as InstructorService)));
          logger.debug('Fetched instructor services', {
            services,
            instructorId: booking.instructorId
          });
        }
        const teaching = Array.isArray(data.preferred_teaching_locations)
          ? data.preferred_teaching_locations
              .map((location: { address?: string; label?: string }) => {
                const address = String(location.address ?? '').trim();
                return {
                  address,
                  ...(location.label ? { label: location.label } : {}),
                };
              })
              .filter((location) => location.address.length > 0)
          : [];
        setTeachingLocations(teaching);
      } catch (error) {
        logger.error('Failed to fetch instructor profile', error);
      } finally {
        setLoadingInstructor(false);
      }
    };

    void loadInstructorProfile();
  }, [booking.instructorId]);


  return (
    <div className="p-6">
      <div className="flex gap-6">
        {/* Left Column - Confirm Details - 60% width */}
        <div className="w-[60%] bg-white dark:bg-gray-900 rounded-lg p-6 order-2 md:order-1">
          <h3 className="font-extrabold text-2xl mb-4">Confirm details</h3>

        {/* Payment Method */}
        <div className="mb-6 rounded-lg p-4" style={{ backgroundColor: 'rgb(249, 247, 255)' }}>
          <div
            className="flex items-center justify-between cursor-pointer"
            onClick={() => setIsPaymentExpanded(!isPaymentExpanded)}
          >
            <div className="flex items-center gap-3 flex-1">
              <h4 className="font-bold text-xl">Payment Method</h4>
              {!isPaymentExpanded && hasSavedCard && (
                <span className="text-sm text-gray-600">•••• {cardLast4}</span>
              )}
            </div>
            <ChevronDown
              className={`h-5 w-5 text-gray-500 transition-transform ${
                isPaymentExpanded ? 'rotate-180' : ''
              }`}
            />
          </div>

          {/* Credit Card Fields */}
          {isPaymentExpanded && (
          <div className="space-y-3 mt-3">
            {hasSavedCard ? (
              <div className="bg-white p-3 rounded-lg border border-gray-200">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{cardBrand} ending in {cardLast4}</span>
                    {isDefaultCard && (
                      <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded">Default</span>
                    )}
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (onChangePaymentMethod) {
                        onChangePaymentMethod();
                      }
                    }}
                    className="text-sm text-[#7E22CE] hover:text-[#7E22CE]"
                  >
                    Change
                  </button>
                </div>
              </div>
            ) : (
              <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Card Number
              </label>
              <input
                type="text"
                placeholder="1234 5678 9012 3456"
                className="w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors"
                style={{ outline: 'none' }}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Expiry Date
                </label>
                <input
                  type="text"
                  placeholder="MM/YY"
                  className="w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors"
                  style={{ outline: 'none' }}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  CVV
                </label>
                <input
                  type="text"
                  placeholder="123"
                  className="w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors"
                  style={{ outline: 'none' }}
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Name on Card
              </label>
              <input
                type="text"
                placeholder="John Doe"
                className="w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors"
                style={{ outline: 'none' }}
              />
            </div>

            {/* Billing Address */}
            <div className="pt-3 mt-3 border-t border-gray-200">
              <label className="block text-sm font-medium text-gray-700 mb-3">
                Billing Address
              </label>

              <div className="space-y-3">
                <div>
                  <input
                    type="text"
                    placeholder="Address"
                    className="w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors"
                    style={{ outline: 'none' }}
                  />
                </div>

                <div className="grid grid-cols-6 gap-3">
                  <input
                    type="text"
                    placeholder="City"
                    className="col-span-3 w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors"
                    style={{ outline: 'none' }}
                  />

                  <input
                    type="text"
                    placeholder="State"
                    className="col-span-1 w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors"
                    style={{ outline: 'none' }}
                  />

                  <input
                    type="text"
                    placeholder="ZIP Code"
                    className="col-span-2 w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors"
                    style={{ outline: 'none' }}
                  />
                </div>

                <div>
                  <select
                    className="w-full p-2.5 border border-gray-200 rounded-lg text-sm text-gray-700 focus:border-purple-500 transition-colors"
                    style={{ outline: 'none' }}
                    defaultValue="US"
                  >
                    <option value="US">United States</option>
                    <option value="CA">Canada</option>
                    <option value="MX">Mexico</option>
                    <option value="GB">United Kingdom</option>
                    <option value="FR">France</option>
                    <option value="DE">Germany</option>
                    <option value="IT">Italy</option>
                    <option value="ES">Spain</option>
                    <option value="NL">Netherlands</option>
                    <option value="BE">Belgium</option>
                    <option value="CH">Switzerland</option>
                    <option value="AT">Austria</option>
                    <option value="SE">Sweden</option>
                    <option value="NO">Norway</option>
                    <option value="DK">Denmark</option>
                    <option value="FI">Finland</option>
                    <option value="PL">Poland</option>
                    <option value="PT">Portugal</option>
                    <option value="IE">Ireland</option>
                    <option value="CZ">Czech Republic</option>
                    <option value="GR">Greece</option>
                    <option value="RO">Romania</option>
                    <option value="HU">Hungary</option>
                    <option value="AU">Australia</option>
                    <option value="NZ">New Zealand</option>
                    <option value="JP">Japan</option>
                    <option value="KR">South Korea</option>
                    <option value="CN">China</option>
                    <option value="IN">India</option>
                    <option value="SG">Singapore</option>
                    <option value="MY">Malaysia</option>
                    <option value="TH">Thailand</option>
                    <option value="ID">Indonesia</option>
                    <option value="PH">Philippines</option>
                    <option value="VN">Vietnam</option>
                    <option value="BR">Brazil</option>
                    <option value="AR">Argentina</option>
                    <option value="CL">Chile</option>
                    <option value="CO">Colombia</option>
                    <option value="PE">Peru</option>
                    <option value="VE">Venezuela</option>
                    <option value="ZA">South Africa</option>
                    <option value="EG">Egypt</option>
                    <option value="NG">Nigeria</option>
                    <option value="KE">Kenya</option>
                    <option value="MA">Morocco</option>
                    <option value="IL">Israel</option>
                    <option value="AE">United Arab Emirates</option>
                    <option value="SA">Saudi Arabia</option>
                    <option value="TR">Turkey</option>
                    <option value="RU">Russia</option>
                    <option value="UA">Ukraine</option>
                    <option value="PK">Pakistan</option>
                    <option value="BD">Bangladesh</option>
                    <option value="LK">Sri Lanka</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="flex items-center mt-3">
              <input
                type="checkbox"
                id="save-card"
                className="w-4 h-4 text-[#7E22CE] border-gray-300 rounded focus:ring-[#7E22CE]"
              />
              <label htmlFor="save-card" className="ml-2 text-sm text-gray-700">
                Save card for future payments
              </label>
            </div>

            {/* Promo Code Section */}
            <div className="mt-4 pt-4 border-t border-gray-200">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Promo Code
              </label>
              {referralActive ? (
                <div className="flex items-start gap-2 rounded-lg border border-[#7E22CE]/20 bg-[#7E22CE]/5 px-3 py-2 text-sm text-[#4f1790]">
                  <AlertCircle className="mt-0.5 h-4 w-4" aria-hidden="true" />
                  <p>Referral credit applied — promotions can’t be combined.</p>
                </div>
              ) : (
                <>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Enter promo code"
                      value={promoCode}
                      onChange={(event) => handlePromoInputChange(event.target.value)}
                      disabled={promoActive}
                      className="flex-1 p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors disabled:bg-gray-100"
                      style={{ outline: 'none' }}
                    />
                    <button
                      type="button"
                      onClick={handlePromoAction}
                      className="px-4 py-2.5 bg-[#7E22CE] text-white rounded-lg text-sm font-medium hover:bg-[#7E22CE] transition-colors disabled:cursor-not-allowed disabled:opacity-70"
                      disabled={promoApplyDisabled}
                    >
                      {promoActive ? 'Remove' : 'Apply'}
                    </button>
                  </div>
                  {promoError && (
                    <p className="mt-2 text-xs text-red-600">{promoError}</p>
                  )}
                  {promoActive && (
                    <p className="mt-2 text-xs text-gray-500">
                      Promo applied. Referral credit is disabled while a promo code is active.
                    </p>
                  )}
                </>
              )}
            </div>
            </>
            )}
          </div>
          )}

          {isPaymentExpanded && (
            <>
            {paymentMethod === PaymentMethod.CREDITS ? (
              <p className="text-sm mt-3">Using platform credits</p>
            ) : paymentMethod === PaymentMethod.MIXED ? (
              <div className="text-sm space-y-1 mt-3">
                <p>Credits: ${appliedCreditDollars.toFixed(2)}</p>
                <p>Card amount: ${cardCharge.toFixed(2)}</p>
              </div>
            ) : null}
            </>
          )}
        </div>

        {/* Available Credits Section - with interactive toggle and slider */}
        {availableCredits > 0 && (
          <div className="mb-6 rounded-lg p-4" style={{ backgroundColor: 'rgb(249, 247, 255)' }}>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 cursor-pointer select-none"
                onClick={handleCreditsAccordionToggle}
                aria-expanded={creditsAccordionIsExpanded}
                aria-controls={creditsAccordionPanelId}
              >
                <div className="flex-1 text-left">
                  <h4 className="font-bold text-xl">Available Credits</h4>
                  <p className="text-sm text-gray-600">
                    Balance: ${availableCredits.toFixed(2)}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">{creditsAppliedLabel}</p>
                  {collapsedHasCredits && (
                    <span className="sr-only">
                      Using {formatCentsToDisplay(previewAppliedCreditCents)}
                    </span>
                  )}
                </div>
                <ChevronDown
                  className={`h-5 w-5 text-gray-500 transition-transform ${
                    creditsAccordionIsExpanded ? 'rotate-180' : ''
                  }`}
                />
              </button>
            </div>

            {creditsAccordionIsExpanded && (
              <div
                id={creditsAccordionPanelId}
                className="mt-3 p-3 bg-white rounded-lg space-y-3"
                aria-hidden={!creditsAccordionIsExpanded}
              >
                <div className="flex items-center justify-between text-sm">
                  <span>Credits to apply:</span>
                  <span className="font-medium">${appliedCreditDollars.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max={Math.min(availableCredits, totalBeforeCreditsDollars)}
                  step="1"
                  value={appliedCreditDollars}
                  onChange={(e) => {
                    const newValue = Number(e.target.value);
                    if (Number.isFinite(newValue)) {
                      // Set drag value for immediate visual feedback
                      setSliderDragCents(Math.max(0, Math.round(newValue * 100)));
                    }
                  }}
                  onMouseUp={(e) => {
                    // Commit: call API and clear drag state so display falls back to server value
                    const newValue = Number((e.target as HTMLInputElement).value);
                    if (Number.isFinite(newValue)) {
                      onCreditAmountChange?.(newValue);
                      setSliderDragCents(null);
                    }
                  }}
                  onTouchEnd={(e) => {
                    // Same for touch: commit and clear drag state
                    const newValue = Number((e.target as HTMLInputElement).value);
                    if (Number.isFinite(newValue)) {
                      onCreditAmountChange?.(newValue);
                      setSliderDragCents(null);
                    }
                  }}
                  className="w-full accent-purple-700"
                />
                <div className="flex items-start justify-between text-xs text-gray-500">
                  <span>
                    {displayAppliedCreditCents >= totalBeforeCreditsCents
                      ? 'Entire lesson covered by credits!'
                      : `Remaining balance: $${remainingBalanceDollars.toFixed(2)}`}
                  </span>
                  {onCreditToggle && (
                    <button
                      type="button"
                      onClick={onCreditToggle}
                      className="text-[#7E22CE] font-medium"
                    >
                      {displayAppliedCreditCents > 0 ? 'Remove credits' : 'Apply full balance'}
                    </button>
                  )}
                </div>
              </div>
            )}

            <p className="text-xs text-gray-500 mt-2">
              {creditEarliestExpiry
                ? `Earliest credit expiry: ${new Date(creditEarliestExpiry).toLocaleDateString()}`
                : 'Credits expire 12 months after issue date'}
            </p>
          </div>
        )}

        {/* Lesson Location */}
        <div className="mb-6 rounded-lg p-4" style={{ backgroundColor: 'rgb(249, 247, 255)' }}>
          <div
            className="flex items-center justify-between cursor-pointer"
            onClick={() => setIsLocationExpanded(!isLocationExpanded)}
          >
            <div className="flex items-center gap-3 flex-1">
              <h4 className="font-bold text-xl">Lesson Location</h4>
              {!isLocationExpanded && (
                <span className="text-sm text-gray-600">{resolvedMeetingLocation}</span>
              )}
            </div>
            <ChevronDown
              className={`h-5 w-5 text-gray-500 transition-transform ${
                isLocationExpanded ? 'rotate-180' : ''
              }`}
            />
          </div>

          {isLocationExpanded && (
            <div className="mt-3 space-y-4">
              {showOnlineOption && (
                <div className="flex items-center">
                  <input
                    type="checkbox"
                    id="online-lesson"
                    checked={isOnlineLesson}
                    onChange={(e) => handleOnlineToggleChange(e.target.checked)}
                    className="w-4 h-4 text-[#7E22CE] border-gray-300 rounded focus:ring-[#7E22CE]"
                  />
                  <label htmlFor="online-lesson" className="ml-2 text-sm font-medium text-gray-700">
                    Online
                  </label>
                </div>
              )}

              {!isOnlineLesson && inPersonOptions.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm font-medium text-gray-700">Choose a location</p>
                  <div className="flex flex-wrap gap-2">
                    {inPersonOptions.map((type) => {
                      const isDisabled = type === 'instructor_location' && teachingLocations.length === 0;
                      return (
                        <button
                          key={type}
                          type="button"
                          onClick={() => handleLocationTypeChange(type)}
                          disabled={isDisabled}
                          className={`rounded-full border px-3 py-1 text-sm transition-colors ${
                            locationType === type
                              ? 'border-[#7E22CE] bg-purple-50 text-[#7E22CE]'
                              : 'border-gray-200 text-gray-700 hover:border-gray-300'
                          } ${isDisabled ? 'cursor-not-allowed opacity-50' : ''}`}
                        >
                          {getLocationOptionLabel(type)}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {!isOnlineLesson && locationType === 'instructor_location' && (
                <div className="space-y-2">
                  <p className="text-sm font-medium text-gray-700">Teaching location</p>
                  {teachingLocations.length > 0 ? (
                    <div className="space-y-2">
                      {teachingLocations.map((location) => {
                        const isSelected = selectedTeachingLocation?.address === location.address;
                        return (
                          <button
                            key={`${location.address}-${location.label ?? ''}`}
                            type="button"
                            onClick={() => handleSelectTeachingLocation(location)}
                            className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                              isSelected
                                ? 'border-[#7E22CE] bg-purple-50 text-[#7E22CE]'
                                : 'border-gray-200 text-gray-700 hover:border-gray-300'
                            }`}
                          >
                            {location.label ? (
                              <div className="font-medium">{location.label}</div>
                            ) : null}
                            <div className="text-xs text-gray-500">{location.address}</div>
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-500">No teaching locations available yet.</p>
                  )}
                </div>
              )}

              {isTravelLocation && isEditingLocation && (
                <AddressSelector
                  instructorId={booking.instructorId}
                  locationType={locationType}
                  selectedAddress={selectedSavedAddress}
                  onSelectAddress={handleSelectSavedAddress}
                  onEnterNewAddress={handleEnterNewAddress}
                />
              )}

              {hasSavedTravelLocation && isTravelLocation && !isEditingLocation && (
                <div className="bg-white p-3 rounded-lg border border-gray-200">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-sm font-medium">{resolvedMeetingLocation}</span>
                      <p className="text-xs text-gray-500 mt-1">Saved address</p>
                    </div>
                    <button
                      type="button"
                      className="text-sm text-[#7E22CE] hover:text-[#7E22CE]"
                      onClick={handleChangeLocationClick}
                    >
                      Change
                    </button>
                  </div>
                </div>
              )}

              <div className={`space-y-3 ${inputsDisabled ? 'opacity-50' : ''}`}>
                <PlacesAutocompleteInput
                  ref={addressLine1Ref}
                  value={addressFields.line1}
                  onValueChange={(next) => {
                    setAddressField({ line1: next });
                    setIsEditingLocation(true);
                    setAddressDetailsError(null);
                  }}
                  onSelectSuggestion={(suggestion: PlaceSuggestion) => {
                    void handleAddressSuggestionSelect(suggestion);
                  }}
                  placeholder={ADDRESS_PLACEHOLDER}
                  disabled={inputsDisabled}
                  autoComplete="off"
                  suggestionScope="global"
                  containerClassName="w-full"
                  inputClassName={`rounded-lg border border-gray-200 px-3 py-2 text-sm placeholder-gray-400 transition-colors ${
                    inputsDisabled ? 'bg-gray-100 cursor-not-allowed' : 'focus:border-purple-500'
                  }`}
                  style={{ outline: 'none' }}
                  inputProps={{ 'data-testid': 'addr-street', 'aria-label': 'Street address' }}
                />
                {addressDetailsError && (
                  <p className="text-xs text-red-600" role="alert">
                    {addressDetailsError}
                  </p>
                )}

                <div className="grid grid-cols-6 gap-3">
                  <input
                    type="text"
                    placeholder="City"
                    aria-label="City"
                    data-testid="addr-city"
                    disabled={inputsDisabled}
                    value={addressFields.city}
                    onChange={(e) => {
                      setAddressField({ city: e.target.value });
                      setIsEditingLocation(true);
                      setAddressDetailsError(null);
                    }}
                    className={`col-span-3 w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 transition-colors ${
                      inputsDisabled ? 'bg-gray-100 cursor-not-allowed' : 'focus:border-purple-500'
                    }`}
                    style={{ outline: 'none' }}
                  />

                  <input
                    type="text"
                    placeholder="State"
                    aria-label="State"
                    data-testid="addr-state"
                    disabled={inputsDisabled}
                    value={addressFields.state}
                    onChange={(e) => {
                      setAddressField({ state: e.target.value });
                      setIsEditingLocation(true);
                      setAddressDetailsError(null);
                    }}
                    className={`col-span-1 w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 transition-colors ${
                      inputsDisabled ? 'bg-gray-100 cursor-not-allowed' : 'focus:border-purple-500'
                    }`}
                    style={{ outline: 'none' }}
                  />

                  <input
                    type="text"
                    placeholder="ZIP Code"
                    aria-label="ZIP code"
                    data-testid="addr-zip"
                    disabled={inputsDisabled}
                    value={addressFields.postalCode}
                    onChange={(e) => {
                      setAddressField({ postalCode: e.target.value });
                      setIsEditingLocation(true);
                      setAddressDetailsError(null);
                    }}
                    className={`col-span-2 w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 transition-colors ${
                      inputsDisabled ? 'bg-gray-100 cursor-not-allowed' : 'focus:border-purple-500'
                    }`}
                    style={{ outline: 'none' }}
                  />
                </div>
              </div>

              {isTravelLocation && isOutsideServiceArea && !selectedSavedAddress && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                  <p className="font-medium">Location not covered</p>
                  <p>
                    This instructor doesn&#39;t serve this address. Choose a different location or
                    select online for a video lesson.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {activeFloorMessage && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
            <div className="flex items-start gap-2">
              <AlertCircle className="h-5 w-5 text-red-600 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-red-700">
                <p>{activeFloorMessage}</p>
                <p className="mt-1">Adjust the lesson duration or choose a different modality to continue.</p>
              </div>
            </div>
          </div>
        )}

        {/* Conflict Warning */}
        {hasConflict && !isCheckingConflict && (
          <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
            <div className="flex items-start gap-2">
              <AlertCircle className="h-5 w-5 text-amber-600 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-amber-800">
                <p className="font-medium">Scheduling Conflict</p>
                <p>{conflictMessage}</p>
                <p className="mt-1">Please select a different time slot to continue.</p>
              </div>
            </div>
          </div>
        )}

        {/* Action Button */}
        <div className="mt-6">
          <button
            onClick={onConfirm}
            disabled={ctaDisabled}
            data-testid="booking-confirm-cta"
            className={`w-full py-2.5 px-4 rounded-lg font-medium transition-colors focus:outline-none focus:ring-0 ${
              ctaDisabled
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-[#7E22CE] text-white hover:bg-[#7E22CE]'
            }`}
          >
            {ctaLabel}
          </button>
        </div>

        <p className="text-xs text-center text-gray-500 dark:text-gray-400 mt-4">
          🔒 Secure payment • {!isLastMinute && 'Cancel free >24hrs'}
        </p>
      </div>

      {/* Right Column - Booking Details - 40% width */}
      <div className="w-[40%] bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700 order-1 md:order-2">
        <h3 className="font-bold text-xl mb-4">Booking Your Lesson with</h3>
        <div className="space-y-4">
          <div className="flex items-start">
            <div className="w-16 h-16 bg-gray-200 dark:bg-gray-700 rounded-full mr-4"></div>
            <div>
              <h4 className="font-semibold">{booking.instructorName}</h4>
              <div className="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
                <Star className="h-4 w-4 text-yellow-500 fill-current" />
                <span className="font-medium">4.8</span>
                <span>·</span>
                <span>47 reviews</span>
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <div className="text-lg font-bold text-gray-800 dark:text-gray-200 mb-2">
              Piano Lesson
            </div>
            <div className="flex items-center text-sm">
              <Calendar size={16} className="mr-2 text-gray-500" />
              <span>{summaryDateLabel}</span>
            </div>
            <div className="flex items-center text-sm">
              <Clock size={16} className="mr-2 text-gray-500" />
              <span>{summaryTimeLabel}</span>
            </div>
            <div className="flex items-start text-sm">
              <MapPin size={16} className="mr-2 text-gray-500 mt-0.5" />
              <div>
                {locationType === 'online' ? (
                  <div>Online</div>
                ) : (
                  <div>{resolvedMeetingLocation}</div>
                )}
              </div>
            </div>
          </div>

          {/* Edit Lesson Button */}
          <div className="mt-4">
            <button
              onClick={() => {
                // Open the calendar modal to reschedule
                setIsModalOpen(true);
              }}
              className="bg-white text-[#7E22CE] py-1.5 px-3 rounded-lg text-sm font-medium border-2 border-[#7E22CE] hover:bg-purple-50 transition-colors"
            >
              Edit lesson
            </button>
          </div>

          {/* Message Instructor Section */}
          <div className="mt-4">
            <textarea
              placeholder="What should your instructor know about this session?"
              className="w-full p-3 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 resize-none transition-colors"
              style={{ outline: 'none', boxShadow: 'none' }}
              onFocus={(e) => e.target.style.boxShadow = 'none'}
              rows={6}
            />
          </div>

          {/* Payment Details Section */}
          <div className="border-t border-gray-300 pt-4">
            <h4 className="font-semibold mb-3">Payment details</h4>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>{lessonSummaryLabel}</span>
                <span>
                  {isPricingPreviewLoading ? (
                    <span className="inline-block h-3 w-16 rounded bg-gray-200 animate-pulse" aria-hidden="true" />
                  ) : (
                    lessonAmountDisplay
                  )}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="flex items-center gap-1" aria-label={serviceSupportFeeLabel}>
                  <span>{serviceSupportFeeLabel}</span>
                  <Tooltip.Provider delayDuration={150} skipDelayDuration={75}>
                    <Tooltip.Root>
                      <Tooltip.Trigger asChild>
                        <button
                          type="button"
                          className="inline-flex h-4 w-4 items-center justify-center rounded-full text-gray-400 transition-colors hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 focus-visible:ring-offset-2"
                          aria-label="Learn about the Service & Support fee"
                        >
                          <Info className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                      </Tooltip.Trigger>
                      <Tooltip.Content
                        side="top"
                        sideOffset={6}
                        className="max-w-xs whitespace-pre-line rounded-md bg-gray-900 px-2 py-1 text-xs text-white shadow text-left"
                      >
                        {serviceSupportFeeTooltip}
                        <Tooltip.Arrow className="fill-gray-900" />
                      </Tooltip.Content>
                    </Tooltip.Root>
                  </Tooltip.Provider>
                </span>
                <span>
                  {isPricingPreviewLoading
                    ? renderSummarySkeleton()
                    : pricingPreview
                      ? serviceSupportFeeAmountDisplay
                      : pricingPreviewError
                        ? 'Unavailable'
                        : renderSummarySkeleton()}
                </span>
              </div>
              {previewAdditionalLineItems.map((item) => (
                <div
                  key={`${item.label}-${item.amount_cents}`}
                  className={`flex justify-between text-sm ${
                    item.amount_cents < 0 ? 'text-green-600 dark:text-green-400' : ''
                  }`}
                >
                  <span>{item.label}</span>
                  <span>
                    {isPricingPreviewLoading ? (
                      <span className="inline-block h-3 w-16 rounded bg-gray-200 animate-pulse" aria-hidden="true" />
                    ) : (
                      formatCentsToDisplay(item.amount_cents)
                    )}
                  </span>
                </div>
              ))}
              {hasCreditsApplied && (
                <div className="flex justify-between text-sm text-green-600 dark:text-green-400">
                  <span>Credits applied</span>
                  <span>
                    {isPricingPreviewLoading ? (
                      <span className="inline-block h-3 w-16 rounded bg-gray-200 animate-pulse" aria-hidden="true" />
                    ) : (
                      creditsAmountDisplay
                    )}
                  </span>
                </div>
              )}
              {referralCreditAmount > 0 && (
                <div className="flex justify-between text-sm text-green-600 dark:text-green-400">
                  <span>Referral credit</span>
                  <span>{formatCentsToDisplay(-referralCreditCents)}</span>
                </div>
              )}
              <div className="border-t border-gray-300 pt-2 mt-2">
                <div className="flex justify-between font-bold text-base">
                  <span>Total</span>
                  <span>
                    {isPricingPreviewLoading
                      ? renderSummarySkeleton('w-20')
                      : pricingPreview
                        ? totalAmountDisplay
                        : pricingPreviewError
                          ? `$${totalAfterCredits.toFixed(2)}`
                          : renderSummarySkeleton('w-20')}
                  </span>
                </div>
                {showFeesPlaceholder && (
                  <p className="text-xs text-red-600 mt-1">{pricingPreviewError}</p>
                )}
              </div>
            </div>
          </div>

          {/* Cancellation Policy */}
          <div className="rounded-lg p-3 text-sm" style={{ backgroundColor: 'rgb(249, 247, 255)' }}>
            <h4 className="font-medium mb-2 flex items-center">
              <AlertCircle size={16} className="mr-1" />
              Cancellation Policy
            </h4>
            <div className="space-y-0.5 text-gray-600 dark:text-gray-400" style={{ fontSize: '11px' }}>
              <p>More than 24 hours before your lesson: Full refund</p>
              <p>12–24 hours before your lesson: Refund issued as platform credit</p>
              <p>Less than 12 hours before your lesson: No refund</p>
            </div>
          </div>

        </div>
      </div>
      </div>

      {/* Time Selection Modal */}
      {isModalOpen && !loadingInstructor && (
        <TimeSelectionModal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          instructor={{
            user_id: booking.instructorId,
            user: {
              first_name: booking.instructorName.split(' ')[0] || 'Instructor',
              last_initial: booking.instructorName.split(' ')[1]?.charAt(0) || ''
            },
            services: instructorServices.length > 0
              ? instructorServices.map((service) => ({
                  id: service.id,
                  skill: service.skill || '',
                  hourly_rate: service.hourly_rate,
                  duration_options: service.duration_options || [30, 60, 90],
                  ...(Array.isArray(service.location_types)
                    ? { location_types: service.location_types }
                    : {}),
                }))
              : [{
                  id: sessionStorage.getItem('serviceId') || '',
                  skill: booking.lessonType,
                  hourly_rate: booking.basePrice / (booking.duration / 60),
                  duration_options: [30, 60, 90], // fallback to standard durations
                  location_types: ['online'],
                }]
          }}
          initialDate={bookingDateLocal ?? (booking.date ?? null)}
          initialTimeHHMM24={startHHMM24 ?? null}
          initialDurationMinutes={
            typeof booking.duration === 'number' && Number.isFinite(booking.duration)
              ? booking.duration
              : null
          }
          {...(sessionStorage.getItem('serviceId') && { serviceId: sessionStorage.getItem('serviceId')! })}
          bookingDraftId={booking.bookingId}
          appliedCreditCents={derivedAppliedCreditCents}
          onTimeSelected={(selection) => {
            const newBookingDate = new Date(`${selection.date}T${selection.time}`);
            const newEndTime = calculateEndTime(selection.time, selection.duration);

            if (onBookingUpdate) {
              onBookingUpdate((prev) => ({
                ...prev,
                date: newBookingDate,
                startTime: selection.time,
                endTime: newEndTime,
                duration: selection.duration,
              }));
            }

            setIsModalOpen(false);
            onClearFloorViolation?.();
          }}
        />
      )}
    </div>
  );
}

// Wrap in React.memo to prevent re-renders from parent state changes
const PaymentConfirmation = React.memo(PaymentConfirmationInner);
export default PaymentConfirmation;
