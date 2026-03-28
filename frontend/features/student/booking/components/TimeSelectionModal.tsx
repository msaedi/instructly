'use client';

import { useState, useEffect, useRef, useCallback, useMemo, useId } from 'react';
import { useRouter } from 'next/navigation';
import { X, ArrowLeft } from 'lucide-react';
import { UserAvatar } from '@/components/user/UserAvatar';
import { logger } from '@/lib/logger';
import { timeToMinutes } from '@/lib/time';
import { expandDiscreteStarts } from '@/lib/time/expandDiscreteStarts';
import { at } from '@/lib/ts/safe';
import { publicApi } from '@/features/shared/api/client';
import { ApiProblemError } from '@/lib/api/fetch';
import {
  fetchPricingPreview,
  type PricingPreviewResponse,
} from '@/lib/api/pricing';
import { formatDisplayName } from '@/lib/format/displayName';
import { useAuth, storeBookingIntent } from '../hooks/useAuth';
import Calendar from '@/features/shared/booking/ui/Calendar';
import TimeDropdown from '@/features/shared/booking/ui/TimeDropdown';
import DurationButtons from '@/features/shared/booking/ui/DurationButtons';
import SummarySection from '@/features/shared/booking/ui/SummarySection';
import { usePricingFloors } from '@/lib/pricing/usePricingFloors';
import { useFocusTrap } from '@/hooks/useFocusTrap';
import { useScrollLock } from '@/hooks/useScrollLock';
import {
  formatCents,
  type NormalizedModality,
} from '@/lib/pricing/priceFloors';
import {
  availableFormatsFromPrices,
  getFormatRate,
} from '@/lib/pricing/formatPricing';
import type { LocationType } from '@/types/booking';
import {
  areNumberSetsEqual,
  consumePreparedBookingTiming,
  formatAvailabilityDateLabel,
  getPriceFloorViolation,
  parseDisplayTimeToMinutes,
  prepareBookingTiming,
  reconcileTimeSelection,
} from './TimeSelectionModal.helpers';

// Type for availability slots
interface AvailabilitySlot {
  start_time: string;
  end_time: string;
}

const SLOT_STEP_MINUTES = 15;
type SelectableLocationType = Exclude<LocationType, 'neutral_location'>;
const FORMAT_PICKER_ORDER: readonly SelectableLocationType[] = [
  'online',
  'instructor_location',
  'student_location',
];

const isSelectableLocationType = (
  value: LocationType | string | null | undefined,
): value is SelectableLocationType =>
  value === 'online' || value === 'instructor_location' || value === 'student_location';

const getFormatPickerLabel = (locationType: SelectableLocationType): string => {
  if (locationType === 'online') return 'Online';
  if (locationType === 'instructor_location') return "At instructor's location";
  return 'At your location';
};

const getFormatPickerDescription = (locationType: SelectableLocationType): string => {
  if (locationType === 'online') return 'Live video lesson through the platform';
  if (locationType === 'instructor_location') return 'You travel to the instructor';
  return 'The instructor travels to you';
};

const normalizeDateInput = (value?: string | Date | null): string | null => {
  if (!value) {
    return null;
  }

  if (value instanceof Date) {
    return value.toISOString().slice(0, 10);
  }

  if (typeof value === 'string') {
    if (value.includes('T')) {
      return value.slice(0, 10);
    }
    return value;
  }

  return null;
};

const convertHHMM24ToDisplay = (value?: string | null): string | null => {
  if (!value) {
    return null;
  }

  const parts = value.split(':');
  const hoursPart = at(parts, 0);
  const minutesPart = at(parts, 1);
  if (!hoursPart || !minutesPart) {
    return null;
  }

  const hour = Number(hoursPart);
  const minutes = minutesPart.padStart(2, '0');
  if (!Number.isFinite(hour)) {
    return null;
  }

  const ampm = hour >= 12 ? 'pm' : 'am';
  const displayHour = ((hour % 12) || 12).toString();
  return `${displayHour}:${minutes}${ampm}`;
};

export interface TimeSelectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  instructor: {
    user_id: string;
    user: {
      first_name: string;
      last_initial: string;
      has_profile_picture?: boolean | undefined;
      profile_picture_version?: number | undefined;
      timezone?: string | undefined;
    };
    services: Array<{
      id?: string | undefined;
      duration_options: number[];
      min_hourly_rate: number;
      format_prices: Array<{ format: string; hourly_rate: number }>;
      skill: string;
      location_types?: string[] | undefined;
    }>;
  };
  preSelectedDate?: string | undefined; // From search context (format: "YYYY-MM-DD")
  preSelectedTime?: string | undefined; // Pre-selected time slot
  initialDate?: string | Date | null | undefined;
  initialTimeHHMM24?: string | null | undefined;
  initialDurationMinutes?: number | null | undefined;
  initialLocationType?: LocationType | null | undefined;
  lockLocationType?: boolean | undefined;
  onTimeSelected?: (selection: {
    date: string;
    time: string;
    duration: number;
    locationType: LocationType;
    serviceId?: string | undefined;
    hourlyRate: number;
  }) => void;
  serviceId?: string | undefined; // Optional service ID from search context
  bookingDraftId?: string | undefined;
  appliedCreditCents?: number | undefined;
  prioritizeTimeSelectionOnOpen?: boolean | undefined;
}

export default function TimeSelectionModal({
  isOpen,
  onClose,
  instructor,
  preSelectedDate,
  preSelectedTime,
  initialDate,
  initialTimeHHMM24,
  initialDurationMinutes,
  initialLocationType,
  lockLocationType = false,
  onTimeSelected,
  serviceId,
  bookingDraftId,
  appliedCreditCents,
  prioritizeTimeSelectionOnOpen = false,
}: TimeSelectionModalProps) {
  const router = useRouter();
  const { isAuthenticated, redirectToLogin, user } = useAuth();
  const { floors: pricingFloors } = usePricingFloors();

  const studentTimezone = (user as { timezone?: string })?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;

  const formatDateInTz = (d: Date, tz: string) => {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: tz,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    } as Intl.DateTimeFormatOptions).format(d);
  };

  const selectedService = useMemo(() => {
    if (!instructor.services.length) return null;
    if (serviceId) {
      const found = instructor.services.find((s) => s.id === serviceId);
      if (found) return found;
    }
    return instructor.services[0] ?? null;
  }, [instructor.services, serviceId]);

  const availableLocationTypes = useMemo<SelectableLocationType[]>(() => {
    const formats = availableFormatsFromPrices(selectedService?.format_prices ?? []);
    return FORMAT_PICKER_ORDER.filter((format) => formats.includes(format));
  }, [selectedService]);

  const [selectedLocationType, setSelectedLocationType] = useState<LocationType | null>(() => {
    if (lockLocationType && initialLocationType) {
      return initialLocationType;
    }
    if (
      initialLocationType &&
      isSelectableLocationType(initialLocationType) &&
      availableLocationTypes.includes(initialLocationType)
    ) {
      return initialLocationType;
    }
    if (availableLocationTypes.length === 1) {
      return availableLocationTypes[0] ?? null;
    }
    return null;
  });

  useEffect(() => {
    if (lockLocationType) {
      setSelectedLocationType(initialLocationType ?? null);
      return;
    }

    setSelectedLocationType((previous) => {
      if (
        previous &&
        isSelectableLocationType(previous) &&
        availableLocationTypes.includes(previous)
      ) {
        return previous;
      }
      if (
        initialLocationType &&
        isSelectableLocationType(initialLocationType) &&
        availableLocationTypes.includes(initialLocationType)
      ) {
        return initialLocationType;
      }
      if (availableLocationTypes.length === 1) {
        return availableLocationTypes[0] ?? null;
      }
      return null;
    });
  }, [availableLocationTypes, initialLocationType, lockLocationType]);

  const selectedPricingFormat = useMemo<SelectableLocationType | null>(() => {
    if (selectedLocationType === 'neutral_location') {
      return 'student_location';
    }
    return isSelectableLocationType(selectedLocationType) ? selectedLocationType : null;
  }, [selectedLocationType]);

  const selectedHourlyRate = useMemo(() => {
    if (!selectedService) return 0;
    const exactRate = selectedPricingFormat
      ? getFormatRate(selectedService.format_prices ?? [], selectedPricingFormat)
      : null;
    const raw =
      exactRate ??
      ((selectedService as unknown as Record<string, unknown>)?.['min_hourly_rate'] as unknown);
    const parsed = typeof raw === 'number' ? raw : parseFloat(String(raw ?? '0'));
    return Number.isFinite(parsed) ? parsed : 0;
  }, [selectedPricingFormat, selectedService]);

  const selectedModality = useMemo<NormalizedModality>(() => {
    return selectedLocationType === 'online' ? 'online' : 'in_person';
  }, [selectedLocationType]);

  const hasResolvedLocationType = Boolean(selectedLocationType);

  const instructorAvatarUser = useMemo(
    () => ({
      id: instructor.user_id,
      first_name: instructor.user.first_name,
      ...(instructor.user.last_initial ? { last_name: instructor.user.last_initial } : {}),
      ...(typeof instructor.user.has_profile_picture === 'boolean'
        ? { has_profile_picture: instructor.user.has_profile_picture }
        : {}),
      ...(typeof instructor.user.profile_picture_version === 'number'
        ? { profile_picture_version: instructor.user.profile_picture_version }
        : {}),
    }),
    [
      instructor.user_id,
      instructor.user.first_name,
      instructor.user.last_initial,
      instructor.user.has_profile_picture,
      instructor.user.profile_picture_version,
    ],
  );

  // Get duration options from the selected service
  const durationOptions = useMemo(() => {
    const durations = selectedService?.duration_options?.length
      ? selectedService.duration_options
      : [30, 60, 90, 120];

    const hourlyRate = selectedHourlyRate > 0 ? selectedHourlyRate : 100;
    const result = durations.map((duration) => ({
      duration,
      price: Math.round((hourlyRate * duration) / 60),
    }));

    logger.debug('Final duration options', {
      durationsCount: result.length,
      options: result,
      hourlyRate,
      serviceId,
      selectedService,
    });

    return result;
  }, [selectedHourlyRate, selectedService, serviceId]);

  // Debug logging
  logger.info('Duration options generated', {
    durationOptions,
    servicesCount: instructor.services.length,
    services: instructor.services,
    selectedServiceId: selectedService?.id,
  });

  const durationValues = useMemo(
    () => Array.from(new Set(durationOptions.map((option) => option.duration))),
    [durationOptions]
  );

  const effectiveAppliedCreditCents = useMemo(
    () => Math.max(0, Math.round(appliedCreditCents ?? 0)),
    [appliedCreditCents]
  );

  const normalizedInitialDateValue = normalizeDateInput(initialDate);
  const normalizedPreselectedDateValue = normalizeDateInput(preSelectedDate);
  const effectiveInitialDate = normalizedInitialDateValue ?? normalizedPreselectedDateValue ?? null;
  const normalizedInitialTimeDisplay = convertHHMM24ToDisplay(initialTimeHHMM24);
  const effectiveInitialTimeDisplay = normalizedInitialTimeDisplay ?? preSelectedTime ?? null;
  const effectiveInitialDateRef = useRef(effectiveInitialDate);
  const effectiveInitialTimeDisplayRef = useRef(effectiveInitialTimeDisplay);
  const normalizedInitialDurationValue = Number.isFinite(initialDurationMinutes ?? NaN)
    ? Number(initialDurationMinutes)
    : null;

  // Component state
  const [selectedDate, setSelectedDate] = useState<string | null>(effectiveInitialDate);
  const selectedDateRef = useRef<string | null>(effectiveInitialDate);
  const hasUserChosenDateRef = useRef<boolean>(Boolean(effectiveInitialDate));
  const [selectedTime, setSelectedTime] = useState<string | null>(effectiveInitialTimeDisplay);
  const initialDurationFallback = (() => {
    if (
      normalizedInitialDurationValue &&
      durationOptions.some((option) => option.duration === normalizedInitialDurationValue)
    ) {
      return normalizedInitialDurationValue;
    }
    return durationOptions.length > 0
      ? Math.min(...durationOptions.map((o) => o.duration))
      : 60;
  })();
  const [selectedDuration, setSelectedDuration] = useState<number>(initialDurationFallback);
  const [currentMonth, setCurrentMonth] = useState<Date>(new Date());
  const currentMonthIso = useMemo(() => (currentMonth ? currentMonth.toISOString() : null), [currentMonth]);
  const [showTimeDropdown, setShowTimeDropdown] = useState(false);
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [timeSlots, setTimeSlots] = useState<string[]>([]);
  const [disabledDurations, setDisabledDurations] = useState<number[]>([]);
  const [availabilityData, setAvailabilityData] = useState<{
    availability_by_date?: Record<string, { available_slots: AvailabilitySlot[] }>;
    [key: string]: unknown;
  } | null>(null);
  const [loadingTimeSlots, setLoadingTimeSlots] = useState(false);
  const [pricingPreview, setPricingPreview] = useState<PricingPreviewResponse | null>(null);
  const [isPricingPreviewLoading, setIsPricingPreviewLoading] = useState(false);
  const [pricingPreviewError, setPricingPreviewError] = useState<string | null>(null);
  const [durationAvailabilityNotice, setDurationAvailabilityNotice] = useState<{
    duration: number;
    date: string;
    nextDate: string | null;
  } | null>(null);

  const selectedTimeRef = useRef<string | null>(effectiveInitialTimeDisplay);
  const selectedDurationRef = useRef<number>(initialDurationFallback);

  const logDev = (msg: string, ...args: unknown[]) => {
    if (process.env.NODE_ENV === 'development') {
      logger.debug(`[time-modal] ${msg}`, ...args);
    }
  };

  useEffect(() => {
    selectedDateRef.current = selectedDate;
  }, [selectedDate]);

  useEffect(() => {
    selectedTimeRef.current = selectedTime;
  }, [selectedTime]);

  useEffect(() => {
    effectiveInitialDateRef.current = effectiveInitialDate;
  }, [effectiveInitialDate]);

  useEffect(() => {
    effectiveInitialTimeDisplayRef.current = effectiveInitialTimeDisplay;
  }, [effectiveInitialTimeDisplay]);

  useEffect(() => {
    selectedDurationRef.current = selectedDuration;
  }, [selectedDuration]);

  const chooseValidTime = useCallback(
    (slots: string[], previous: string | null, preferred: string | null) => {
      if (!slots.length) {
        return null;
      }
      if (previous && slots.includes(previous)) {
        return previous;
      }
      if (preferred && slots.includes(preferred)) {
        return preferred;
      }
      return at(slots, 0) ?? null;
    },
    []
  );

  const getSlotsForDate = useCallback(
    (targetDate: string | null): AvailabilitySlot[] => {
      if (!targetDate || !availabilityData) {
        return [];
      }
      const dayData = availabilityData[targetDate] as { available_slots?: AvailabilitySlot[] };
      return (dayData?.available_slots ?? []) as AvailabilitySlot[];
    },
    [availabilityData]
  );

  const buildSlotsByDuration = useCallback(
    (slots: AvailabilitySlot[], durations: number[]) => {
      const uniqueDurations = Array.from(new Set(durations));
      const slotsByDuration: Record<number, string[]> = {};
      uniqueDurations.forEach((dur) => {
        slotsByDuration[dur] = slots.flatMap((slot) =>
          expandDiscreteStarts(slot.start_time, slot.end_time, SLOT_STEP_MINUTES, dur)
        );
      });
      return slotsByDuration;
    },
    []
  );

  const getTimesForDate = useCallback(
    (targetDate: string | null, durationMinutes: number): string[] => {
      const slots = getSlotsForDate(targetDate);
      if (!slots.length) {
        return [];
      }
      const slotsByDuration = buildSlotsByDuration(slots, [durationMinutes]);
      return slotsByDuration[durationMinutes] ?? [];
    },
    [buildSlotsByDuration, getSlotsForDate]
  );

  const applySlotsForDate = useCallback(
    (slots: AvailabilitySlot[], options?: { preferredTime?: string | null }) => {
      const slotsByDuration = buildSlotsByDuration(slots, durationValues);
      const baseDisabledDurations = durationValues.filter(
        (dur) => (slotsByDuration[dur] ?? []).length === 0
      );
      const formattedSlots = slotsByDuration[selectedDuration] ?? [];

      setDisabledDurations(baseDisabledDurations);
      setTimeSlots(formattedSlots);
      setSelectedTime((prev) => {
        const chosen = chooseValidTime(formattedSlots, prev, options?.preferredTime ?? null);
        return chosen;
      });
      return { slotsByDuration, formattedSlots };
    },
    [buildSlotsByDuration, durationValues, selectedDuration, chooseValidTime]
  );

  // Reconciliation effect: Enforce invariant that selectedTime ∈ timeSlots or null
  // This ensures the UI can never display an invalid time selection
  useEffect(() => {
    const nextTime = reconcileTimeSelection({
      selectedTime,
      timeSlots,
      preferredTime: effectiveInitialTimeDisplayRef.current ?? null,
    });
    if (nextTime !== selectedTime) {
      setSelectedTime(nextTime);
    }
  }, [selectedTime, timeSlots]);

  const setDate = useCallback(
    (reason: string, nextDate: string | null) => {
      if (process.env.NODE_ENV !== 'production') {
        logDev('setSelectedDate', {
          reason,
          prevDate: selectedDateRef.current,
          nextDate,
          selectedDuration,
          timesOnPrev: getTimesForDate(selectedDateRef.current, selectedDuration).length,
        });
      }
      if (nextDate !== null) {
        selectedDateRef.current = nextDate;
      }
      if (reason !== 'effect' && nextDate) {
        hasUserChosenDateRef.current = true;
      }
      setSelectedDate(nextDate);
    },
    [getTimesForDate, selectedDuration]
  );
  const setDateRef = useRef(setDate);
  useEffect(() => {
    setDateRef.current = setDate;
  }, [setDate]);

  const formatDateLabel = useCallback((isoDate: string) => formatAvailabilityDateLabel(isoDate), []);

  useEffect(() => {
    const hasSelection = durationOptions.some((option) => option.duration === selectedDuration);
    if (!hasSelection) {
      const [firstOption] = durationOptions;
      if (firstOption) {
        setSelectedDuration(firstOption.duration);
      }
    }
  }, [durationOptions, selectedDuration]);

  useEffect(() => {
    if (!bookingDraftId || !isOpen) {
      setPricingPreview(null);
      setPricingPreviewError(null);
      return;
    }

    let cancelled = false;
    const run = async () => {
      setIsPricingPreviewLoading(true);
      setPricingPreviewError(null);
      try {
        const preview = await fetchPricingPreview(bookingDraftId, effectiveAppliedCreditCents);
        if (!cancelled) {
          setPricingPreview(preview);
        }
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ApiProblemError && error.response.status === 422) {
          setPricingPreviewError(error.problem.detail ?? 'Price is below the minimum.');
        } else {
          setPricingPreviewError('Unable to load pricing preview.');
        }
        setPricingPreview(null);
      } finally {
        if (!cancelled) {
          setIsPricingPreviewLoading(false);
        }
      }
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, [bookingDraftId, effectiveAppliedCreditCents, isOpen]);

  const priceFloorViolation = useMemo(() => {
    if (!hasResolvedLocationType) {
      return null;
    }
    return getPriceFloorViolation({
      pricingFloors,
      hasSelectedService: Boolean(selectedService),
      selectedHourlyRate,
      selectedDuration,
      selectedModality,
    });
  }, [
    hasResolvedLocationType,
    pricingFloors,
    selectedDuration,
    selectedHourlyRate,
    selectedModality,
    selectedService,
  ]);

  const priceFloorWarning = useMemo(() => {
    if (!priceFloorViolation) return null;
    const modalityLabel = selectedModality === 'in_person' ? 'in-person' : 'online';
    return `Minimum for ${modalityLabel} ${selectedDuration}-minute private session is $${formatCents(priceFloorViolation.floorCents)} (current $${formatCents(priceFloorViolation.baseCents)}). Please pick a different duration.`;
  }, [priceFloorViolation, selectedDuration, selectedModality]);

  useEffect(() => {
    if (!priceFloorViolation) return;
    const modalityLabel = selectedModality === 'in_person' ? 'in-person' : 'online';
    logger.warn('Detected price floor violation in TimeSelectionModal', {
      modality: modalityLabel,
      duration: selectedDuration,
      baseCents: priceFloorViolation.baseCents,
      floorCents: priceFloorViolation.floorCents,
      serviceId: selectedService?.id,
    });
  }, [priceFloorViolation, selectedDuration, selectedModality, selectedService]);

  const isSelectionComplete = Boolean(
    hasResolvedLocationType && selectedDate && selectedTime && !priceFloorViolation
  );

  const mobileModalRef = useRef<HTMLDivElement>(null);
  const desktopModalRef = useRef<HTMLDivElement>(null);
  const mobileTimeSectionRef = useRef<HTMLDivElement>(null);
  const desktopTimeSectionRef = useRef<HTMLDivElement>(null);
  const hasAutoScrolledToTimeRef = useRef(false);
  const desktopTitleId = useId();
  const mobileTitleId = useId();
  const [isDesktopViewport, setIsDesktopViewport] = useState(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return false;
    }
    return window.matchMedia('(min-width: 768px)').matches;
  });

  // Get instructor first name and last initial
  const getInstructorDisplayName = () => {
    return formatDisplayName(
      instructor.user.first_name,
      instructor.user.last_initial,
      'Instructor',
    );
  };

  const fetchAvailability = useCallback(async () => {
    try {
      const today = new Date();
      const endDate = new Date();
      endDate.setDate(today.getDate() + 30); // Get 30 days of availability

      const localDateStr = formatDateInTz(today, studentTimezone);
      const localEndStr = formatDateInTz(endDate, studentTimezone);

      const response = await publicApi.getInstructorAvailability(instructor.user_id.toString(), {
        start_date: localDateStr,
        end_date: localEndStr,
        location_type: selectedLocationType!,
      });

      if (response.data?.availability_by_date) {
        const availabilityByDate = response.data.availability_by_date;
        setAvailabilityData(availabilityByDate);

        // Extract available dates - rely on backend-filtered slots
        const datesWithSlots: string[] = Object.keys(availabilityByDate).filter((date) => {
          const dayData = availabilityByDate[date];
          return Boolean(dayData?.available_slots?.length);
        });
        setAvailableDates(datesWithSlots);

        const firstAvailableDate = at(datesWithSlots, 0) ?? null;
        const initialDateValue = effectiveInitialDateRef.current;
        const initialTimeDisplay = effectiveInitialTimeDisplayRef.current;
        const preselectedIsAvailable = Boolean(
          initialDateValue && availabilityByDate[initialDateValue]
        );

        if (!hasUserChosenDateRef.current) {
          const initialDate = preselectedIsAvailable ? initialDateValue : firstAvailableDate;
          if (initialDate) {
            const initReason = preselectedIsAvailable ? 'init-preselected' : 'init';
            setDateRef.current?.(initReason, initialDate);
            selectedDateRef.current = initialDate;
            hasUserChosenDateRef.current = true;
          }
        }

        const activeDate =
          selectedDateRef.current ??
          (preselectedIsAvailable ? initialDateValue : null) ??
          firstAvailableDate;

        if (activeDate) {
          setShowTimeDropdown(true);
          const dayData = availabilityByDate[activeDate];
          if (dayData) {
            applySlotsForDate(dayData.available_slots || [], {
              preferredTime:
                activeDate === initialDateValue ? initialTimeDisplay ?? null : null,
            });
          } else {
            setTimeSlots([]);
            setSelectedTime(null);
          }
        } else {
          setShowTimeDropdown(false);
          setTimeSlots([]);
          setSelectedTime(null);
        }
      }
    } catch (error) {
      logger.error('Failed to fetch availability', error);
    } finally {
      // Loading state cleared
    }
  }, [instructor.user_id, selectedLocationType, studentTimezone, applySlotsForDate]);

  // Fetch availability data when modal opens
  useEffect(() => {
    if (isOpen && instructor.user_id && hasResolvedLocationType) {
      void fetchAvailability();
    }
  }, [fetchAvailability, hasResolvedLocationType, instructor.user_id, isOpen]);

  const initialSelectionAppliedRef = useRef(false);

  useEffect(() => {
    if (initialSelectionAppliedRef.current) {
      return;
    }
    if (!effectiveInitialDate || !normalizedInitialDurationValue) {
      return;
    }
    if (!availabilityData || !availabilityData[effectiveInitialDate]) {
      return;
    }

    if (selectedDuration !== normalizedInitialDurationValue) {
      setSelectedDuration(normalizedInitialDurationValue);
    }

    if (selectedDateRef.current !== effectiveInitialDate) {
      setDate('init-preselected', effectiveInitialDate);
      selectedDateRef.current = effectiveInitialDate;
    }

    hasUserChosenDateRef.current = true;

    initialSelectionAppliedRef.current = true;
  }, [
    availabilityData,
    effectiveInitialDate,
    normalizedInitialDurationValue,
    normalizedInitialTimeDisplay,
    getTimesForDate,
    selectedDuration,
    setDate,
  ]);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;

    const media = window.matchMedia('(min-width: 768px)');
    const syncViewport = () => setIsDesktopViewport(media.matches);
    syncViewport();

    if (typeof media.addEventListener === 'function') {
      media.addEventListener('change', syncViewport);
      return () => media.removeEventListener('change', syncViewport);
    }

    media.addListener(syncViewport);
    return () => media.removeListener(syncViewport);
  }, []);

  useFocusTrap({
    isOpen: isOpen && !isDesktopViewport,
    containerRef: mobileModalRef,
    onEscape: onClose,
    initialFocus: 'first',
  });

  useFocusTrap({
    isOpen: isOpen && isDesktopViewport,
    containerRef: desktopModalRef,
    onEscape: onClose,
    initialFocus: 'first',
  });

  useScrollLock(isOpen);

  useEffect(() => {
    if (!isOpen) {
      hasAutoScrolledToTimeRef.current = false;
      return;
    }

    if (!prioritizeTimeSelectionOnOpen || !showTimeDropdown || hasAutoScrolledToTimeRef.current) {
      return;
    }

    const target = isDesktopViewport ? desktopTimeSectionRef.current : mobileTimeSectionRef.current;

    const rafId = window.requestAnimationFrame(() => {
      const prefersReducedMotion =
        typeof window.matchMedia === 'function' &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      target?.scrollIntoView({
        behavior: prefersReducedMotion ? 'auto' : 'smooth',
        block: 'start',
      });
      hasAutoScrolledToTimeRef.current = target != null;
    });

    return () => {
      window.cancelAnimationFrame(rafId);
    };
  }, [isDesktopViewport, isOpen, prioritizeTimeSelectionOnOpen, showTimeDropdown]);

  // Handle backdrop click
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  const resetSchedulingState = useCallback(() => {
    hasUserChosenDateRef.current = false;
    selectedDateRef.current = null;
    setSelectedDate(null);
    setSelectedTime(null);
    setShowTimeDropdown(false);
    setTimeSlots([]);
    setAvailableDates([]);
    setAvailabilityData(null);
    setLoadingTimeSlots(false);
    setDurationAvailabilityNotice(null);
  }, []);

  const handleLocationTypeSelect = useCallback(
    (nextLocationType: SelectableLocationType) => {
      if (selectedLocationType === nextLocationType) {
        return;
      }
      setSelectedLocationType(nextLocationType);
      resetSchedulingState();
    },
    [resetSchedulingState, selectedLocationType],
  );

  // Handle continue button - go directly to payment
  const handleContinue = () => {
    const resolvedLocationType = selectedLocationType as LocationType;
    if (priceFloorViolation) {
      logger.warn('Blocking continue due to price floor violation', {
        duration: selectedDuration,
        baseCents: priceFloorViolation.baseCents,
        floorCents: priceFloorViolation.floorCents,
      });
      return;
    }
    if (selectedDate && selectedTime) {
      logger.info('Time selection completed, preparing booking data', {
        date: selectedDate,
        time: selectedTime,
        duration: selectedDuration,
        instructorId: instructor.user_id,
        serviceId,
        servicesCount: instructor.services.length,
      });

      const preparedTiming = prepareBookingTiming({
        selectedDate,
        selectedTime,
        selectedDuration,
      });
      const resolvedTiming = consumePreparedBookingTiming(preparedTiming, logger.error);
      if (!resolvedTiming) return;
      const {
        parsedTime: { hour, minute, normalizedTimeHHMM },
        startTime,
        endTime,
        bookingDateTime,
      } = resolvedTiming;

      // If callback provided, use it
      if (onTimeSelected) {
        const resolvedServiceId = serviceId || selectedService?.id;
        onTimeSelected({
          date: selectedDate,
          time: normalizedTimeHHMM,
          duration: selectedDuration,
          locationType: resolvedLocationType,
          hourlyRate: selectedHourlyRate,
          ...(resolvedServiceId ? { serviceId: resolvedServiceId } : {}),
        });
        onClose();
        return;
      }

      // Otherwise, go directly to payment page
      const resolvedService = serviceId
        ? instructor.services.find((s) => s.id === serviceId) || (instructor.services.length > 0 ? instructor.services[0] : null)
        : (instructor.services.length > 0 ? instructor.services[0] : null); // Use first service as fallback

      if (!resolvedService) {
        logger.error('No service found for booking', { serviceId, services: instructor.services });
        onClose();
        return;
      }

      const price = getCurrentPrice();

      const basePrice = price;
      const totalAmount = basePrice;

      // Log parsed values for debugging
      logger.debug('Time parsing results', {
        originalTime: selectedTime,
        parsedHour: hour,
        parsedMinute: minute,
        startTime,
        endTime,
        selectedDate,
      });

      const freeCancellationUntil = new Date(bookingDateTime);
      freeCancellationUntil.setHours(freeCancellationUntil.getHours() - 24);

      // Check if user is authenticated
      if (!isAuthenticated) {
        logger.info('User not authenticated, storing booking intent and redirecting to login');

        // Store booking intent for after login
        const bookingIntent: {
          instructorId: string;
          serviceId?: string;
          locationType?: LocationType;
          date: string;
          time: string;
          duration: number;
          skipModal?: boolean;
        } = {
          instructorId: instructor.user_id,
          date: selectedDate,
          time: normalizedTimeHHMM,
          duration: selectedDuration,
          locationType: resolvedLocationType,
        };

        const finalServiceId = serviceId || selectedService?.id;
        if (finalServiceId) {
          bookingIntent.serviceId = finalServiceId;
        }

        storeBookingIntent(bookingIntent);

        // Close modal and redirect to login
        // After login, return directly to the confirmation flow
        const returnUrl = `/student/booking/confirm`;
        onClose();
        redirectToLogin(returnUrl);
        return;
      }

      // Prepare booking data for payment page
      const locationLabel =
        resolvedLocationType === 'online'
          ? 'Online'
          : resolvedLocationType === 'instructor_location'
            ? "Instructor's location"
            : resolvedLocationType === 'neutral_location'
              ? 'Agreed public location'
              : 'Student provided address';

      const instructorTimezone =
        typeof instructor?.user?.timezone === 'string' ? instructor.user.timezone : undefined;

      const bookingData = {
        instructorId: instructor.user_id,
        instructorName: formatDisplayName(
          instructor.user.first_name,
          instructor.user.last_initial,
          'Instructor',
        ),
        // Ensure we propagate the instructor_service_id ULID, never a display name
        serviceId: serviceId || resolvedService.id,
        skill: resolvedService.skill,
        lessonType: resolvedService.skill, // Same as skill for display
        date: selectedDate,
        startTime: startTime,
        endTime: endTime,
        duration: selectedDuration,
        basePrice: basePrice,
        totalAmount: totalAmount,
        hourlyRate: selectedHourlyRate,
        location: locationLabel,
        metadata: {
          modality: selectedModality,
          location_type: resolvedLocationType,
          ...(instructorTimezone ? { timezone: instructorTimezone } : {}),
        },
        freeCancellationUntil: freeCancellationUntil.toISOString(),
      };

      // Store booking data in session storage
      sessionStorage.setItem('bookingData', JSON.stringify(bookingData));
      sessionStorage.setItem('serviceId', String(bookingData.serviceId));
      // Also store a lightweight selected slot for downstream recovery
      try {
        sessionStorage.setItem(
          'selectedSlot',
          JSON.stringify({
            date: selectedDate,
            time: selectedTime,
            duration: selectedDuration,
            instructorId: instructor.user_id,
            locationType: resolvedLocationType,
          })
        );
      } catch {
        // no-op
      }

      logger.info('Booking data stored in sessionStorage', {
        bookingData,
        storageCheck: sessionStorage.getItem('bookingData') ? 'Data stored' : 'Data NOT stored',
      });

      // Close modal first, then navigate
      onClose();

      // Small delay to ensure modal closes before navigation
      setTimeout(() => {
        router.push('/student/booking/confirm');
      }, 100);
    }
    return undefined;
  };

  // Get current price based on selected duration
  const getCurrentPrice = () => {
    const option = durationOptions.find((opt) => opt.duration === selectedDuration);
    return option?.price || 0;
  };

  // Handle date selection
  const handleDateSelect = async (
    date: string,
    reason: 'user-select' | 'jump-confirm' | 'auto' = 'user-select'
  ) => {
    setDate(reason, date);
    setDurationAvailabilityNotice(null);
    setSelectedTime(null); // Clear previous time selection initially
    setShowTimeDropdown(true);
    setTimeSlots([]); // Clear previous slots
    setLoadingTimeSlots(true); // Show loading state

    // If we don't have availability data yet, fetch it
    if (!availabilityData) {
      await fetchAvailability();
    }

    // Get time slots from availability data
    if (availabilityData && availabilityData[date]) {
      const slots = getSlotsForDate(date);
      const { formattedSlots } = applySlotsForDate(slots, {
        preferredTime:
          date === (effectiveInitialDateRef.current ?? null)
            ? effectiveInitialTimeDisplayRef.current ?? null
            : null,
      });
      setLoadingTimeSlots(false);
      logger.info('Date selected', { date, slotsGenerated: formattedSlots.length });
    } else {
      // Fetch specific date availability if not in cache
      try {
        const response = await publicApi.getInstructorAvailability(instructor.user_id.toString(), {
          start_date: date,
          end_date: date,
          ...(selectedLocationType ? { location_type: selectedLocationType } : {}),
        });

        if (response.data?.availability_by_date?.[date]) {
          const dayData = response.data.availability_by_date[date];
          setAvailabilityData((prev) => ({
            ...prev,
            [date]: dayData,
          }));

          // Process slots
          const { formattedSlots } = applySlotsForDate(dayData.available_slots || [], {
            preferredTime:
              date === (effectiveInitialDateRef.current ?? null)
                ? effectiveInitialTimeDisplayRef.current ?? null
                : null,
          });
          setLoadingTimeSlots(false);
          logger.info('Fetched date-specific availability', { date, slots: formattedSlots.length });
        } else {
          setTimeSlots([]);
          setLoadingTimeSlots(false);
          logger.info('No availability for selected date', { date });
        }
      } catch (error) {
        logger.error('Failed to fetch date-specific availability', error);
        setTimeSlots([]);
        setLoadingTimeSlots(false);
      }
    }
  };

  const handleJumpToNextAvailable = (targetDate: string) => {
    setDurationAvailabilityNotice(null);
    void handleDateSelect(targetDate, 'jump-confirm');
  };

  // Handle time selection
  const handleTimeSelect = (time: string) => {
    // Defensive: Only accept times that are in the current timeSlots
    if (timeSlots.includes(time)) {
      setSelectedTime(time);
      logger.info('Time selected', { time });
    } else {
      logger.warn('Attempted to select invalid time', { time, timeSlots });
    }
  };

  // Recalculate available dates when duration changes
  useEffect(() => {
    if (availabilityData && selectedDuration) {
      const datesWithSlotsForDuration = Object.keys(availabilityData).filter(
        (dateKey) => getTimesForDate(dateKey, selectedDuration).length > 0
      );
      setAvailableDates(datesWithSlotsForDuration);
      logger.info('Updated available dates for duration', {
        duration: selectedDuration,
        availableDates: datesWithSlotsForDuration,
      });
    }
  }, [selectedDuration, availabilityData, getTimesForDate]);

  // Handle duration selection

  const handleDurationSelect = (duration: number) => {
    const previousDuration = selectedDuration;
    setSelectedDuration(duration);

    logger.info('Duration selected', { duration, previousDuration });

    if (!selectedDate || previousDuration === duration) {
      return;
    }

    if (!availabilityData) {
      void handleDateSelect(selectedDate, 'auto');
      return;
    }

    try {
      const slots = getSlotsForDate(selectedDate);
      if (!slots.length) {
        void handleDateSelect(selectedDate, 'auto');
        return;
      }

      const slotsByDuration = buildSlotsByDuration(slots, durationValues);
      const newSlots = slotsByDuration[duration] || [];
      const baseDisabled = durationValues.filter((d) => (slotsByDuration[d] || []).length === 0);

      const additionalDisabled: number[] = [];
      if (selectedTime) {
        const selectedStartMins = parseDisplayTimeToMinutes(selectedTime);

        const isDurationValidForSelectedTime = (dur: number): boolean => {
          return slots.some((slot: AvailabilitySlot) => {
            const slotStart = timeToMinutes(slot.start_time);
            const slotEnd = timeToMinutes(slot.end_time, { isEndTime: true });
            return selectedStartMins >= slotStart && selectedStartMins + dur <= slotEnd;
          });
        };

        durationValues.forEach((dur) => {
          if (!isDurationValidForSelectedTime(dur)) {
            additionalDisabled.push(dur);
          }
        });
      }

      const combinedDisabled = Array.from(new Set([...baseDisabled, ...additionalDisabled])).filter(
        (value) => value !== duration,
      );

      if (newSlots.length === 0) {
        const sortedDates = Object.keys(availabilityData).sort();
        const nextAvailableDate =
          sortedDates
            .filter((dateKey) => dateKey !== selectedDate)
            .find((dateKey) => getTimesForDate(dateKey, duration).length > 0) ?? null;

        setDurationAvailabilityNotice({
          duration,
          date: selectedDate,
          nextDate: nextAvailableDate,
        });
        setDisabledDurations(combinedDisabled);
        setTimeSlots([]);
        setSelectedTime(null);
        return;
      }

      setDurationAvailabilityNotice(null);
      setTimeSlots(newSlots);
      setSelectedTime((prev) => chooseValidTime(newSlots, prev, null));
      setDisabledDurations(combinedDisabled);
    } catch (e) {
      logger.error('Failed to recompute slots on duration change', e);
      void handleDateSelect(selectedDate, 'auto');
    }
  };


  // Recompute disabled durations whenever the selected time changes
  useEffect(() => {
    if (!selectedDate) {
      return;
    }

    try {
      const slots = getSlotsForDate(selectedDate);
      if (!slots.length) {
        setDisabledDurations([]);
        return;
      }

      const slotsByDuration = buildSlotsByDuration(slots, durationValues);
      const baseDisabled = durationValues.filter((d) => (slotsByDuration[d] || []).length === 0);

      const additionalDisabled: number[] = [];
      if (selectedTime) {
        const selectedStartMins = parseDisplayTimeToMinutes(selectedTime);

        const isDurationValidForSelectedTime = (dur: number): boolean => {
          return slots.some((slot: AvailabilitySlot) => {
            const slotStart = timeToMinutes(slot.start_time);
            const slotEnd = timeToMinutes(slot.end_time, { isEndTime: true });
            return selectedStartMins >= slotStart && selectedStartMins + dur <= slotEnd;
          });
        };

        durationValues.forEach((dur) => {
          if (!isDurationValidForSelectedTime(dur)) {
            additionalDisabled.push(dur);
          }
        });
      }

      const combined = Array.from(new Set([...baseDisabled, ...additionalDisabled]));

      setDisabledDurations((prev) => (areNumberSetsEqual(prev, combined) ? prev : combined));
    } catch (e) {
      logger.error('Failed to recompute disabled durations on time change', e);
    }
  }, [selectedTime, selectedDate, durationValues, getSlotsForDate, buildSlotsByDuration]);

  if (!isOpen) return null;

  const showFormatPicker = !lockLocationType && availableLocationTypes.length > 1;
  const renderFormatPicker = () => {
    if (!showFormatPicker || !selectedService) {
      return null;
    }

    return (
      <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800/70">
        <div className="mb-3">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Choose lesson format</h3>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
            Availability and pricing update based on how you want to take this lesson.
          </p>
        </div>
        <div className="grid gap-3">
          {availableLocationTypes.map((locationType) => {
            const rate =
              getFormatRate(selectedService.format_prices ?? [], locationType) ??
              selectedService.min_hourly_rate;
            const isSelected = selectedLocationType === locationType;
            return (
              <button
                key={locationType}
                type="button"
                data-testid={`format-option-${locationType}`}
                aria-pressed={isSelected}
                className={`rounded-xl border px-4 py-3 text-left transition-colors ${
                  isSelected
                    ? 'border-(--color-brand-dark) bg-[#F8F1FF] dark:border-[#C084FC] dark:bg-[#2B143F]'
                    : 'border-gray-200 bg-white hover:border-[#C084FC] hover:bg-[#FAF5FF] dark:border-gray-700 dark:bg-gray-900 dark:hover:border-[#A855F7]'
                }`}
                onClick={() => handleLocationTypeSelect(locationType)}
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-gray-900 dark:text-white">
                      {getFormatPickerLabel(locationType)}
                    </div>
                    <div className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                      {getFormatPickerDescription(locationType)}
                    </div>
                  </div>
                  <div className="shrink-0 text-sm font-semibold text-gray-900 dark:text-white">
                    ${rate}/hr
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  if (process.env.NODE_ENV !== 'production') {
    logDev('render:calendar-props', {
      variant: 'mobile',
      selectedDate,
      preSelectedDate: effectiveInitialDate,
      currentMonth: currentMonthIso,
      keyProp: null,
    });
    logDev('render:calendar-props', {
      variant: 'desktop',
      selectedDate,
      preSelectedDate: effectiveInitialDate,
      currentMonth: currentMonthIso,
      keyProp: null,
    });
  }

  return (
    <>
      {/* Mobile Full Screen View */}
      <div
        ref={mobileModalRef}
        className="md:hidden fixed inset-0 z-50 bg-white dark:bg-gray-900"
        style={{ zIndex: 1200 }}
        role={!isDesktopViewport ? 'dialog' : undefined}
        aria-modal={!isDesktopViewport ? true : undefined}
        aria-labelledby={!isDesktopViewport ? mobileTitleId : undefined}
        aria-hidden={isDesktopViewport}
        tabIndex={-1}
      >
        <div className="h-full flex flex-col">
          {/* Mobile Header */}
          <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
            <button
              onClick={onClose}
              className="p-2 -ml-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
              aria-label="Go back"
            >
              <ArrowLeft className="h-6 w-6 text-gray-600 dark:text-gray-400" />
            </button>
            <h2 id={mobileTitleId} className="text-2xl font-medium text-gray-900 dark:text-white">
              Set your lesson date & time
            </h2>
            <div className="w-10" /> {/* Spacer for centering */}
          </div>

          {/* Instructor Name */}
          <div className="px-4 pt-4 pb-2 flex items-center gap-2">
            <UserAvatar
              user={instructorAvatarUser}
              size={32}
              className="w-8 h-8 rounded-full ring-1 ring-gray-200"
              fallbackBgColor="var(--color-brand-lavender)"
              fallbackTextColor="var(--color-brand-dark)"
            />
            <p className="text-base font-bold text-gray-900 dark:text-white">
              {getInstructorDisplayName()}&apos;s availability
            </p>
          </div>

          {/* Mobile Content */}
          <div className="flex-1 overflow-y-auto overscroll-contain px-4 pb-20">
            {renderFormatPicker()}

            {hasResolvedLocationType ? (
              <>
                {/* Calendar Component */}
                <Calendar
                  currentMonth={currentMonth}
                  selectedDate={selectedDate}
                  {...(effectiveInitialDate ? { preSelectedDate: effectiveInitialDate } : {})}
                  availableDates={availableDates}
                  onDateSelect={handleDateSelect}
                  onMonthChange={setCurrentMonth}
                />

                {/* Time Dropdown (shown when date selected) */}
                {showTimeDropdown && (
                  <div
                    ref={mobileTimeSectionRef}
                    data-testid="mobile-time-dropdown-section"
                    className="mb-4"
                  >
                    <TimeDropdown
                      selectedTime={selectedTime}
                      timeSlots={timeSlots}
                      isVisible={showTimeDropdown}
                      onTimeSelect={handleTimeSelect}
                      disabled={false}
                      isLoading={loadingTimeSlots}
                    />
                  </div>
                )}

                {/* Duration Buttons (only if multiple durations) */}
                <DurationButtons
                  durationOptions={durationOptions}
                  selectedDuration={selectedDuration}
                  onDurationSelect={handleDurationSelect}
                  disabledDurations={disabledDurations}
                />

                {durationAvailabilityNotice && durationAvailabilityNotice.date === selectedDate && (
                  <div
                    className="mb-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
                    role="status"
                    aria-live="polite"
                  >
                    <p>
                      {`No ${durationAvailabilityNotice.duration}-min slots on ${formatDateLabel(durationAvailabilityNotice.date)}.`}
                      {durationAvailabilityNotice.nextDate
                        ? ` The next available is ${formatDateLabel(durationAvailabilityNotice.nextDate)}.`
                        : ' Try another date or duration.'}
                    </p>
                    {durationAvailabilityNotice.nextDate ? (
                      <button
                        type="button"
                        className="mt-2 inline-flex items-center rounded-md bg-(--color-brand-dark) px-3 py-1 text-xs font-semibold text-white hover:bg-[#6b1fb8]"
                        onClick={() => {
                          const nextDate = durationAvailabilityNotice.nextDate;
                          if (nextDate) {
                            handleJumpToNextAvailable(nextDate);
                          }
                        }}
                      >
                        {`Jump to ${formatDateLabel(durationAvailabilityNotice.nextDate)}`}
                      </button>
                    ) : null}
                  </div>
                )}

                {/* Summary Section */}
                <SummarySection
                  selectedDate={selectedDate}
                  selectedTime={selectedTime}
                  selectedDuration={selectedDuration}
                  price={getCurrentPrice()}
                  onContinue={handleContinue}
                  isComplete={isSelectionComplete}
                  floorWarning={priceFloorWarning}
                  pricingPreview={pricingPreview}
                  isPricingPreviewLoading={isPricingPreviewLoading}
                  pricingError={pricingPreviewError}
                  hasBookingDraft={Boolean(bookingDraftId)}
                />
              </>
            ) : (
              <div
                data-testid="format-selection-required"
                className="rounded-xl border border-dashed border-gray-300 bg-gray-50 px-4 py-6 text-sm text-gray-600 dark:border-gray-700 dark:bg-gray-800/40 dark:text-gray-300"
              >
                Choose a lesson format to see available dates and times.
              </div>
            )}
          </div>

          {/* Mobile Sticky CTA - Rendered by SummarySection */}
          {hasResolvedLocationType && (
            <div className="fixed bottom-0 left-0 right-0 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 p-4">
              <SummarySection
                selectedDate={selectedDate}
                selectedTime={selectedTime}
                selectedDuration={selectedDuration}
                price={getCurrentPrice()}
                onContinue={handleContinue}
                isComplete={isSelectionComplete}
                floorWarning={priceFloorWarning}
                pricingPreview={pricingPreview}
                isPricingPreviewLoading={isPricingPreviewLoading}
                pricingError={pricingPreviewError}
                hasBookingDraft={Boolean(bookingDraftId)}
              />
            </div>
          )}
        </div>
      </div>

      {/* Desktop Modal View */}
      <div
        className="hidden md:block fixed inset-0 z-50 overflow-y-auto"
        style={{ zIndex: 1200 }}
        onClick={handleBackdropClick}
      >
        <div className="flex min-h-screen items-center justify-center p-4">
          {/* Backdrop */}
          <div
            className="fixed inset-0 transition-opacity"
            style={{ backgroundColor: 'var(--modal-backdrop)' }}
          />

          {/* Modal */}
          <div
            ref={desktopModalRef}
            tabIndex={-1}
            className="relative bg-white dark:bg-gray-900 rounded-lg shadow-xl w-full max-w-[720px] max-h-[90vh] flex flex-col animate-slideUp"
            onClick={(e) => e.stopPropagation()}
            role={isDesktopViewport ? 'dialog' : undefined}
            aria-modal={isDesktopViewport ? true : undefined}
            aria-labelledby={isDesktopViewport ? desktopTitleId : undefined}
            aria-hidden={!isDesktopViewport}
          >
            {/* Desktop Header */}
            <div className="flex items-center justify-between p-8 pb-0">
              <h2 id={desktopTitleId} className="text-2xl font-medium text-gray-900 dark:text-white">
                Set your lesson date & time
              </h2>
              <button
                onClick={onClose}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                aria-label="Close modal"
              >
                <X className="h-6 w-6 text-gray-600 dark:text-gray-400" aria-hidden="true" />
              </button>
            </div>

            {/* Instructor Name */}
            <div className="px-8 pt-2 pb-6 flex items-center gap-2">
              <UserAvatar
                user={instructorAvatarUser}
                size={32}
                className="w-8 h-8 rounded-full ring-1 ring-gray-200"
                fallbackBgColor="var(--color-brand-lavender)"
                fallbackTextColor="var(--color-brand-dark)"
              />
              <p className="text-base font-bold text-gray-900 dark:text-white">
                {getInstructorDisplayName()}&apos;s availability
              </p>
            </div>

            {/* Desktop Content - Split Layout */}
            <div className="flex-1 overflow-y-auto overscroll-contain px-8 pb-8">
              {renderFormatPicker()}
              <div className="flex gap-8">
                {/* Left Section - Calendar and Controls */}
                <div className="flex-1">
                  {hasResolvedLocationType ? (
                    <>
                      {/* Calendar Component */}
                      <Calendar
                        currentMonth={currentMonth}
                        selectedDate={selectedDate}
                        {...(effectiveInitialDate ? { preSelectedDate: effectiveInitialDate } : {})}
                        availableDates={availableDates}
                        onDateSelect={handleDateSelect}
                        onMonthChange={setCurrentMonth}
                      />

                      {/* Time Dropdown (shown when date selected) */}
                      {showTimeDropdown && (
                        <div
                          ref={desktopTimeSectionRef}
                          data-testid="desktop-time-dropdown-section"
                          className="mb-4"
                        >
                          <TimeDropdown
                            selectedTime={selectedTime}
                            timeSlots={timeSlots}
                            isVisible={showTimeDropdown}
                            onTimeSelect={handleTimeSelect}
                            disabled={false}
                            isLoading={loadingTimeSlots}
                          />
                        </div>
                      )}

                      {/* Duration Buttons (only if multiple durations) */}
                      <DurationButtons
                        durationOptions={durationOptions}
                        selectedDuration={selectedDuration}
                        onDurationSelect={handleDurationSelect}
                        disabledDurations={disabledDurations}
                      />
                    </>
                  ) : (
                    <div
                      data-testid="format-selection-required"
                      className="rounded-xl border border-dashed border-gray-300 bg-gray-50 px-4 py-6 text-sm text-gray-600 dark:border-gray-700 dark:bg-gray-800/40 dark:text-gray-300"
                    >
                      Choose a lesson format to see available dates and times.
                    </div>
                  )}
                </div>

                {/* Vertical Divider */}
                <div
                  className="w-px bg-gray-200 dark:bg-gray-700"
                  style={{ backgroundColor: '#E8E8E8' }}
                />

                {/* Right Section - Summary and CTA */}
                <div className="w-[200px] flex-shrink-0 pt-12">
                  {hasResolvedLocationType &&
                    durationAvailabilityNotice &&
                    durationAvailabilityNotice.date === selectedDate && (
                    <div
                      className="mb-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
                      role="status"
                      aria-live="polite"
                    >
                      <p>
                        {`No ${durationAvailabilityNotice.duration}-min slots on ${formatDateLabel(durationAvailabilityNotice.date)}.`}
                        {durationAvailabilityNotice.nextDate
                          ? ` The next available is ${formatDateLabel(durationAvailabilityNotice.nextDate)}.`
                          : ' Try another date or duration.'}
                      </p>
                      {durationAvailabilityNotice.nextDate ? (
                        <button
                          type="button"
                          className="mt-2 inline-flex items-center rounded-md bg-(--color-brand-dark) px-3 py-1 text-xs font-semibold text-white hover:bg-[#6b1fb8]"
                          onClick={() => {
                            const nextDate = durationAvailabilityNotice.nextDate;
                            if (nextDate) {
                              handleJumpToNextAvailable(nextDate);
                            }
                          }}
                        >
                          {`Jump to ${formatDateLabel(durationAvailabilityNotice.nextDate)}`}
                        </button>
                      ) : null}
                    </div>
                  )}
                  {hasResolvedLocationType && (
                    <SummarySection
                      selectedDate={selectedDate}
                      selectedTime={selectedTime}
                      selectedDuration={selectedDuration}
                      price={getCurrentPrice()}
                      onContinue={handleContinue}
                      isComplete={isSelectionComplete}
                      floorWarning={priceFloorWarning}
                      pricingPreview={pricingPreview}
                      isPricingPreviewLoading={isPricingPreviewLoading}
                      pricingError={pricingPreviewError}
                      hasBookingDraft={Boolean(bookingDraftId)}
                    />
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Animation Styles */}
      <style jsx>{`
        @keyframes slideUp {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .animate-slideUp {
          animation: slideUp 0.3s ease-out;
        }

        /* Design Token Custom Properties */
        :root {
          --primary-purple: #6b46c1;
          --primary-purple-light: #f9f7ff;
          --text-primary: #333333;
          --text-secondary: #666666;
          --border-default: #e0e0e0;
          --border-light: #e8e8e8;
          --background-hover: #f5f5f5;
        }
      `}</style>

      {/* Global styles for dropdown animations */}
      <style jsx global>{`
        @keyframes dropdownOpen {
          from {
            opacity: 0;
            transform: translateY(-10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        @keyframes dropdownClose {
          from {
            opacity: 1;
            transform: translateY(0);
          }
          to {
            opacity: 0;
            transform: translateY(-10px);
          }
        }

        .animate-dropdownOpen {
          animation: dropdownOpen 0.15s ease-out forwards;
        }

        .animate-dropdownClose {
          animation: dropdownClose 0.15s ease-out forwards;
        }
      `}</style>
    </>
  );
}
