'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { X, ArrowLeft } from 'lucide-react';
import { logger } from '@/lib/logger';
import { at } from '@/lib/ts/safe';
import { publicApi } from '@/features/shared/api/client';
import { useAuth, storeBookingIntent } from '../hooks/useAuth';
import Calendar from './TimeSelectionModal/Calendar';
import TimeDropdown from './TimeSelectionModal/TimeDropdown';
import DurationButtons from './TimeSelectionModal/DurationButtons';
import SummarySection from './TimeSelectionModal/SummarySection';

// Type for availability slots
interface AvailabilitySlot {
  start_time: string;
  end_time: string;
}

// Helper function to expand discrete time slots
const expandDiscreteStarts = (
  start: string,
  end: string,
  stepMinutes: number,
  requiredMinutes: number
): string[] => {
  const startParts = start.split(':');
  const endParts = end.split(':');
  const sh = parseInt(at(startParts, 0) || '0', 10);
  const sm = parseInt(at(startParts, 1) || '0', 10);
  const eh = parseInt(at(endParts, 0) || '0', 10);
  const em = parseInt(at(endParts, 1) || '0', 10);
  const startTotal = sh * 60 + sm;
  const endTotal = eh * 60 + em;

  const times: string[] = [];
  for (let t = startTotal; t + requiredMinutes <= endTotal; t += stepMinutes) {
    const h = Math.floor(t / 60);
    const m = t % 60;
    const ampm = h >= 12 ? 'pm' : 'am';
    const displayHour = (h % 12) || 12;
    times.push(`${displayHour}:${String(m).padStart(2, '0')}${ampm}`);
  }
  return times;
};

interface TimeSelectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  instructor: {
    user_id: string;
    user: {
      first_name: string;
      last_initial: string;
    };
    services: Array<{
      id?: string;
      duration_options: number[];
      hourly_rate: number;
      skill: string;
    }>;
  };
  preSelectedDate?: string; // From search context (format: "YYYY-MM-DD")
  preSelectedTime?: string; // Pre-selected time slot
  onTimeSelected?: (selection: { date: string; time: string; duration: number }) => void;
  serviceId?: string; // Optional service ID from search context
}

export default function TimeSelectionModal({
  isOpen,
  onClose,
  instructor,
  preSelectedDate,
  preSelectedTime,
  onTimeSelected,
  serviceId,
}: TimeSelectionModalProps) {
  const { isAuthenticated, redirectToLogin, user } = useAuth();

  const studentTimezone = (user as { timezone?: string })?.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;

  const formatDateInTz = (d: Date, tz: string) => {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: tz,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    } as Intl.DateTimeFormatOptions).format(d);
  };

  const nowHHMMInTz = (tz: string) => {
    return new Intl.DateTimeFormat('en-GB', {
      timeZone: tz,
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
    } as Intl.DateTimeFormatOptions).format(new Date());
  };

  // Get duration options from the selected service
  const getDurationOptions = useCallback(() => {
    // Get the selected service if serviceId is provided, otherwise use first
    const selectedService = serviceId
      ? instructor.services.find((s) => s.id === serviceId) || at(instructor.services, 0)
      : at(instructor.services, 0);

    // Use duration_options from the service, or fallback to standard durations
    const durations = selectedService?.duration_options || [30, 60, 90, 120];

    logger.debug('Using service duration options', {
      durations,
      serviceId,
      selectedService,
    });

    // Coerce hourly rate to a number (API may send string)
    const hourlyRateRaw = (selectedService as unknown as Record<string, unknown>)?.['hourly_rate'] as unknown;
    const hourlyRateParsed = typeof hourlyRateRaw === 'number' ? hourlyRateRaw : parseFloat(String(hourlyRateRaw ?? '100'));
    const hourlyRate = Number.isNaN(hourlyRateParsed) ? 100 : hourlyRateParsed; // fallback to 100

    const result = durations.map((duration) => ({
      duration,
      price: Math.round((hourlyRate * duration) / 60),
    }));

    logger.debug('Final duration options', {
      durationsCount: result.length,
      options: result,
      hourlyRate,
    });

    return result;
  }, [serviceId, instructor.services]);

  const durationOptions = useMemo(() => getDurationOptions(), [getDurationOptions]);

  // Debug logging
  logger.info('Duration options generated', {
    durationOptions,
    servicesCount: instructor.services.length,
    services: instructor.services,
  });

  // Component state
  const [selectedDate, setSelectedDate] = useState<string | null>(preSelectedDate || null);
  const [selectedTime, setSelectedTime] = useState<string | null>(preSelectedTime || null);
  // Pre-select middle duration option by default
  const [selectedDuration, setSelectedDuration] = useState<number>(
    durationOptions.length > 0
      ? Math.min(...durationOptions.map((o) => o.duration))
      : 60
  );
  const [currentMonth, setCurrentMonth] = useState<Date>(new Date());
  const [showTimeDropdown, setShowTimeDropdown] = useState(false);
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [timeSlots, setTimeSlots] = useState<string[]>([]);
  const [disabledDurations, setDisabledDurations] = useState<number[]>([]);
  const [availabilityData, setAvailabilityData] = useState<{
    availability_by_date?: Record<string, { available_slots: AvailabilitySlot[] }>;
    [key: string]: unknown;
  } | null>(null);
  const [loadingTimeSlots, setLoadingTimeSlots] = useState(false);
  const lastChangeWasDurationRef = useRef<boolean>(false);

  const modalRef = useRef<HTMLDivElement>(null);
  const previousActiveElement = useRef<HTMLElement | null>(null);

  // Get instructor first name and last initial
  const getInstructorDisplayName = () => {
    const firstName = instructor.user.first_name;
    const lastInitial = instructor.user.last_initial;
    return `${firstName} ${lastInitial}.`;
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
      });

      if (response.data?.availability_by_date) {
        const availabilityByDate = response.data.availability_by_date;
        setAvailabilityData(availabilityByDate);

        // Extract available dates - only include dates with actual time slots
        const datesWithSlots: string[] = [];
        Object.keys(availabilityByDate).forEach((date) => {
          const dayData = availabilityByDate[date];
          if (!dayData) return;
          const slots = dayData.available_slots || [];
          // Filter out past times if it's today
          const now = new Date();
          const nowLocalStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
          const isToday = date === nowLocalStr;

          const validSlots = slots.filter((slot: AvailabilitySlot) => {
            if (!isToday) return true;
            const timeParts = slot.start_time.split(':');
            const hours = at(timeParts, 0);
            const minutes = at(timeParts, 1);
            if (!hours || !minutes) return false;
            const slotTime = new Date();
            slotTime.setHours(parseInt(hours), parseInt(minutes), 0, 0);
            return slotTime > now;
          });

          if (validSlots.length > 0) {
            datesWithSlots.push(date);
          }
        });
        setAvailableDates(datesWithSlots);

        // Auto-select first available date if no pre-selection
        if (!preSelectedDate && datesWithSlots.length > 0) {
          const firstDate = at(datesWithSlots, 0);
          if (!firstDate) return;
          setSelectedDate(firstDate);
          setShowTimeDropdown(true); // Show time dropdown immediately

          // Load time slots for the first available date
          const dayData = availabilityByDate[firstDate];
          if (!dayData) return;
          const slots = dayData.available_slots || [];

          const formattedSlots = slots.flatMap((slot: AvailabilitySlot) =>
            expandDiscreteStarts(slot.start_time, slot.end_time, 60, selectedDuration)
          );

          setTimeSlots(formattedSlots);

          // Auto-select first available time slot
          if (formattedSlots.length > 0 && !preSelectedTime) {
            const firstSlot = at(formattedSlots, 0);
            if (firstSlot) {
              setSelectedTime(firstSlot);
            }
          }
        }

        // If we have a pre-selected date, load its time slots
        if (preSelectedDate && availabilityByDate[preSelectedDate]) {
          setSelectedDate(preSelectedDate);
          setShowTimeDropdown(true); // Show time dropdown immediately
          const availableSlots = availabilityByDate[preSelectedDate];
          if (!availableSlots) return;
          const slots = availableSlots.available_slots || [];

          const formattedSlots = slots.flatMap((slot: AvailabilitySlot) =>
            expandDiscreteStarts(slot.start_time, slot.end_time, 60, selectedDuration)
          );

          setTimeSlots(formattedSlots);

          // If pre-selected time is provided, format it to match
          if (preSelectedTime) {
            const parts = preSelectedTime.split(':');
            const hours = at(parts, 0);
            const minutes = at(parts, 1);
            if (!hours || !minutes) return;
            const hour = parseInt(hours);
            const ampm = hour >= 12 ? 'pm' : 'am';
            const displayHour = hour % 12 || 12;
            const formattedTime = `${displayHour}:${minutes.padStart(2, '0')}${ampm}`;
            setSelectedTime(formattedTime);
          } else if (formattedSlots.length > 0) {
            // Auto-select first time if no pre-selected time
            const firstSlot = at(formattedSlots, 0);
            if (firstSlot) {
              setSelectedTime(firstSlot);
            }
          }
        }
      }
    } catch (error) {
      logger.error('Failed to fetch availability', error);
    } finally {
      // Loading state cleared
    }
  }, [instructor.user_id, selectedDuration, preSelectedDate, preSelectedTime, studentTimezone]);

  // Fetch availability data when modal opens
  useEffect(() => {
    if (isOpen && instructor.user_id) {
      fetchAvailability();
    }
  }, [isOpen, instructor.user_id, fetchAvailability]);

  // Handle escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      // Store the currently focused element
      previousActiveElement.current = document.activeElement as HTMLElement;
      // Focus the modal
      modalRef.current?.focus();
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      // Restore focus when modal closes
      if (!isOpen && previousActiveElement.current) {
        previousActiveElement.current.focus();
      }
    };
  }, [isOpen, onClose]);

  // Body scroll lock
  useEffect(() => {
    if (isOpen) {
      const originalStyle = window.getComputedStyle(document.body).overflow;
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = originalStyle;
      };
    }
    return undefined;
  }, [isOpen]);

  // Handle backdrop click
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  // Handle continue button - go directly to payment
  const handleContinue = () => {
    if (selectedDate && selectedTime) {
      logger.info('Time selection completed, preparing booking data', {
        date: selectedDate,
        time: selectedTime,
        duration: selectedDuration,
        instructorId: instructor.user_id,
        serviceId,
        servicesCount: instructor.services.length,
      });

      // If callback provided, use it (for backward compatibility)
      if (onTimeSelected) {
        onTimeSelected({
          date: selectedDate,
          time: selectedTime,
          duration: selectedDuration,
        });
        onClose();
        return;
      }

      // Otherwise, go directly to payment page
      const selectedService = serviceId
        ? instructor.services.find((s) => s.id === serviceId) || (instructor.services.length > 0 ? instructor.services[0] : null)
        : (instructor.services.length > 0 ? instructor.services[0] : null); // Use first service as fallback

      if (!selectedService) {
        logger.error('No service found for booking', { serviceId, services: instructor.services });
        onClose();
        return;
      }

      const price = getCurrentPrice();

      // Parse time - handle both "8:00am" and "8:00" formats
      const timeWithoutAmPm = selectedTime.replace(/[ap]m/gi, '').trim();
      const timeParts = timeWithoutAmPm.split(':');
      const hourStr = at(timeParts, 0);
      const minuteStr = at(timeParts, 1);
      if (!hourStr || !minuteStr) return 'Invalid time';

      if (timeParts.length !== 2) {
        logger.error('Invalid time format', { selectedTime });
        return;
      }

      let hour = parseInt(hourStr);
      const minute = parseInt(minuteStr) || 0;

      if (isNaN(hour) || isNaN(minute)) {
        logger.error('Invalid time values', { hourStr, minuteStr, selectedTime });
        return;
      }

      const isAM = selectedTime.toLowerCase().includes('am');
      const isPM = selectedTime.toLowerCase().includes('pm');

      // Convert to 24-hour format if AM/PM is present
      if (isPM && hour !== 12) hour += 12;
      if (isAM && hour === 12) hour = 0;

      const startTime = `${hour.toString().padStart(2, '0')}:${minute
        .toString()
        .padStart(2, '0')}:00`;
      const endHour = hour + Math.floor(selectedDuration / 60);
      const endMinute = minute + (selectedDuration % 60);

      // Handle minute overflow
      let finalEndHour = endHour;
      let finalEndMinute = endMinute;
      if (endMinute >= 60) {
        finalEndHour += Math.floor(endMinute / 60);
        finalEndMinute = endMinute % 60;
      }

      const endTime = `${finalEndHour.toString().padStart(2, '0')}:${finalEndMinute
        .toString()
        .padStart(2, '0')}:00`;

      // Calculate fees
      const basePrice = price;
      const serviceFee = Math.round(basePrice * 0.1); // 10% service fee
      const totalAmount = basePrice + serviceFee;

      // Log parsed values for debugging
      logger.debug('Time parsing results', {
        originalTime: selectedTime,
        parsedHour: hour,
        parsedMinute: minute,
        startTime,
        endTime,
        selectedDate,
      });

      // Calculate free cancellation deadline (24 hours before)
      const bookingDateTimeString = `${selectedDate}T${startTime}`;
      const bookingDateTime = new Date(bookingDateTimeString);

      if (isNaN(bookingDateTime.getTime())) {
        logger.error('Invalid booking date/time', {
          dateTimeString: bookingDateTimeString,
          selectedDate,
          startTime,
        });
        return;
      }

      const freeCancellationUntil = new Date(bookingDateTime);
      freeCancellationUntil.setHours(freeCancellationUntil.getHours() - 24);

      // Check if user is authenticated
      if (!isAuthenticated) {
        logger.info('User not authenticated, storing booking intent and redirecting to login');

        // Store booking intent for after login
        const bookingIntent: {
          instructorId: string;
          serviceId?: string;
          date: string;
          time: string;
          duration: number;
          skipModal?: boolean;
        } = {
          instructorId: instructor.user_id,
          date: selectedDate,
          time: selectedTime,
          duration: selectedDuration,
        };

        const finalServiceId = serviceId || selectedService.id;
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
      // Ensure hourly rate is numeric
      const selectedRateRaw = (selectedService as unknown as Record<string, unknown>)?.['hourly_rate'] as unknown;
      const selectedRateParsed = typeof selectedRateRaw === 'number' ? selectedRateRaw : parseFloat(String(selectedRateRaw ?? '0'));
      const selectedHourlyRate = Number.isNaN(selectedRateParsed) ? 0 : selectedRateParsed;

      const bookingData = {
        instructorId: instructor.user_id,
        instructorName: `${instructor.user.first_name} ${instructor.user.last_initial}.`,
        // Ensure we propagate the instructor_service_id ULID, never a display name
        serviceId: serviceId || selectedService.id,
        skill: selectedService.skill,
        lessonType: selectedService.skill, // Same as skill for display
        date: selectedDate,
        startTime: startTime,
        endTime: endTime,
        duration: selectedDuration,
        basePrice: basePrice,
        serviceFee: serviceFee,
        totalAmount: totalAmount,
        hourlyRate: selectedHourlyRate,
        location: 'Online', // Default to online, could be enhanced later
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
        // Use window.location for a hard navigation to ensure sessionStorage persists
        window.location.href = '/student/booking/confirm';
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
  const handleDateSelect = async (date: string) => {
    setSelectedDate(date);
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
      const slots = (availabilityData[date] as Record<string, unknown>)?.['available_slots'] || [];

      // Filter out past times if selecting today
      const now = new Date();
      const nowLocalStr = formatDateInTz(now, studentTimezone);
      const isToday = date === nowLocalStr;

      const validSlots = (slots as unknown as AvailabilitySlot[]).filter((slot: AvailabilitySlot) => {
        // Check if slot is in the past (for today)
        if (isToday) {
          const currentHHMM = nowHHMMInTz(studentTimezone);
          if (slot.start_time.slice(0, 5) <= currentHHMM) return false;
        }

        // Check if slot has enough time for selected duration
        const slotStart = new Date(`${date}T${slot.start_time}`);
        const slotEnd = new Date(`${date}T${slot.end_time}`);
        const slotDurationMinutes = (slotEnd.getTime() - slotStart.getTime()) / (1000 * 60);

        const hasEnoughTime = slotDurationMinutes >= selectedDuration;
        if (!hasEnoughTime) {
          logger.debug('Filtering out slot - insufficient duration', {
            slot: slot.start_time,
            slotDuration: slotDurationMinutes,
            requiredDuration: selectedDuration,
          });
        }

        return hasEnoughTime;
      });

      const uniqueDurations = Array.from(new Set(durationOptions.map((o) => o.duration)));
      const slotsByDuration: Record<number, string[]> = {};
      uniqueDurations.forEach((dur) => {
        slotsByDuration[dur] = validSlots.flatMap((slot: AvailabilitySlot) =>
          expandDiscreteStarts(slot.start_time, slot.end_time, 60, dur)
        );
      });
      // Base disabled durations for the whole day (no slots at all for that duration)
      const baseDisabledDurations = uniqueDurations.filter((d) => (slotsByDuration[d] || []).length === 0);

      // Build formatted slots for currently selected duration
      const formattedSlots = slotsByDuration[selectedDuration] || [];
      setDisabledDurations(baseDisabledDurations);
      setTimeSlots(formattedSlots);

      // Auto-select first available time slot
      if (formattedSlots.length > 0 && !selectedTime) {
        const firstSlot = formattedSlots[0];
        if (firstSlot) {
          setSelectedTime(firstSlot);
        }
      }

      setLoadingTimeSlots(false);
      logger.info('Date selected', { date, slotsGenerated: formattedSlots.length, isToday });
    } else {
      // Fetch specific date availability if not in cache
      try {
        const response = await publicApi.getInstructorAvailability(instructor.user_id.toString(), {
          start_date: date,
          end_date: date,
        });

        if (response.data?.availability_by_date?.[date]) {
          const dayData = response.data.availability_by_date[date];
          const slots = dayData.available_slots || [];

          // Update availability data cache
          setAvailabilityData((prev) => ({
            ...prev,
            [date]: dayData,
          }));

          // Process slots
          const now = new Date();
          const isToday = date === formatDateInTz(now, studentTimezone);

          const validSlots = slots.filter((slot: AvailabilitySlot) => {
            // Check if slot is in the past (for today)
            if (isToday) {
              const currentHHMM = nowHHMMInTz(studentTimezone);
              if (slot.start_time.slice(0, 5) <= currentHHMM) return false;
            }

            // Check if slot has enough time for selected duration
            const slotStart = new Date(`${date}T${slot.start_time}`);
            const slotEnd = new Date(`${date}T${slot.end_time}`);
            const slotDurationMinutes = (slotEnd.getTime() - slotStart.getTime()) / (1000 * 60);

            const hasEnoughTime = slotDurationMinutes >= selectedDuration;
            if (!hasEnoughTime) {
              logger.debug('Filtering out slot - insufficient duration', {
                slot: slot.start_time,
                slotDuration: slotDurationMinutes,
                requiredDuration: selectedDuration,
              });
            }

            return hasEnoughTime;
          });

          const uniqueDurations = Array.from(new Set(durationOptions.map((o) => o.duration)));
          const slotsByDuration: Record<number, string[]> = {};
          uniqueDurations.forEach((dur) => {
            slotsByDuration[dur] = validSlots.flatMap((slot: AvailabilitySlot) =>
              (() => {
                const startParts = slot.start_time.split(':');
                const endParts = slot.end_time.split(':');
                const sh = parseInt(at(startParts, 0) || '0', 10);
                const sm = parseInt(at(startParts, 1) || '0', 10);
                const eh = parseInt(at(endParts, 0) || '0', 10);
                const em = parseInt(at(endParts, 1) || '0', 10);
                const startTotal = sh * 60 + (sm || 0);
                const endTotal = eh * 60 + (em || 0);
                const times: string[] = [];
                for (let t = startTotal; t + dur <= endTotal; t += 60) {
                  const h = Math.floor(t / 60);
                  const m = t % 60;
                  const ampm = h >= 12 ? 'pm' : 'am';
                  const displayHour = (h % 12) || 12;
                  times.push(`${displayHour}:${String(m).padStart(2, '0')}${ampm}`);
                }
                return times;
              })()
            );
          });
          // Base disabled durations for the whole day (no slots at all for that duration)
          const baseDisabledDurations = uniqueDurations.filter((d) => (slotsByDuration[d] || []).length === 0);

          const formattedSlots = slotsByDuration[selectedDuration] || [];
          setDisabledDurations(baseDisabledDurations);
          setTimeSlots(formattedSlots);

          // Auto-select first available time slot
          if (formattedSlots.length > 0 && !selectedTime) {
            const firstSlot = at(formattedSlots, 0);
            if (firstSlot) {
              setSelectedTime(firstSlot);
            }
          }

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

  // Handle time selection
  const handleTimeSelect = (time: string) => {
    setSelectedTime(time);
    logger.info('Time selected', { time });
  };

  // Auto-select first available time when time slots load
  useEffect(() => {
    if (timeSlots.length > 0 && !selectedTime && !loadingTimeSlots) {
      if (lastChangeWasDurationRef.current) {
        // Skip auto-select when list changed due to a duration change
        lastChangeWasDurationRef.current = false;
      } else {
        const firstSlot = at(timeSlots, 0);
        if (firstSlot) {
          setSelectedTime(firstSlot);
          logger.info('Auto-selected first available time', { time: firstSlot });
        }
      }
    } else if (!loadingTimeSlots) {
      // Reset the flag once loading settles to avoid stale state
      lastChangeWasDurationRef.current = false;
    }
  }, [timeSlots, selectedTime, loadingTimeSlots]);

  // Recalculate available dates when duration changes
  useEffect(() => {
    if (availabilityData && selectedDuration) {
      const datesWithSlotsForDuration: string[] = [];
      const now = new Date();
      const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;

      Object.keys(availabilityData).forEach((date) => {
        const slots = (availabilityData[date] as Record<string, unknown>)?.['available_slots'] || [];

        // Check if any slot on this date can accommodate the selected duration
        const hasValidSlot = (slots as unknown as AvailabilitySlot[]).some((slot: AvailabilitySlot) => {
          // Check if it's in the past
          if (date === todayStr) {
            const currentHHMM = nowHHMMInTz(studentTimezone);
            if (slot.start_time.slice(0, 5) <= currentHHMM) return false;
          }

          // Check if slot duration is enough
          const startParts = slot.start_time.split(':');
          const endParts = slot.end_time.split(':');
          const sh = parseInt(at(startParts, 0) || '0', 10);
          const sm = parseInt(at(startParts, 1) || '0', 10);
          const eh = parseInt(at(endParts, 0) || '0', 10);
          const em = parseInt(at(endParts, 1) || '0', 10);
          const slotDuration = (eh * 60 + em) - (sh * 60 + sm);
          return slotDuration >= selectedDuration;
        });

        if (hasValidSlot) {
          datesWithSlotsForDuration.push(date);
        }
      });

      setAvailableDates(datesWithSlotsForDuration);
      logger.info('Updated available dates for duration', { duration: selectedDuration, availableDates: datesWithSlotsForDuration });
    }
  }, [selectedDuration, availabilityData, studentTimezone]);

  // Handle duration selection
  const handleDurationSelect = (duration: number) => {
    const previousDuration = selectedDuration;
    setSelectedDuration(duration);

    logger.info('Duration selected', { duration, previousDuration });

    // Re-filter time slots if we have a selected date
    if (selectedDate && previousDuration !== duration && availabilityData) {
      try {
        // First check if current date still has availability for new duration
        const currentDateData = availabilityData[selectedDate];
        if (currentDateData) {
          const slots = (currentDateData as Record<string, unknown>)?.['available_slots'] || [];

          // Check if any slot can accommodate the new duration
          const canAccommodate = (slots as unknown as AvailabilitySlot[]).some((slot: AvailabilitySlot) => {
            const startParts = slot.start_time.split(':');
            const endParts = slot.end_time.split(':');
            const sh = parseInt(at(startParts, 0) || '0', 10);
            const sm = parseInt(at(startParts, 1) || '0', 10);
            const eh = parseInt(at(endParts, 0) || '0', 10);
            const em = parseInt(at(endParts, 1) || '0', 10);
            const slotDuration = (eh * 60 + em) - (sh * 60 + sm);
            return slotDuration >= duration;
          });

          if (!canAccommodate) {
            // Current date can't accommodate new duration, find next available date
            const sortedDates = Object.keys(availabilityData).sort();
            let newSelectedDate: string | null = null;

            for (const date of sortedDates) {
              const dayData = availabilityData[date];
              const daySlots = (dayData as Record<string, unknown>)?.['available_slots'] || [];

              // Check if this date can accommodate the duration
              const dateCanAccommodate = (daySlots as unknown as AvailabilitySlot[]).some((slot: AvailabilitySlot) => {
                const startParts = slot.start_time.split(':');
                const endParts = slot.end_time.split(':');
                const sh = parseInt(at(startParts, 0) || '0', 10);
                const sm = parseInt(at(startParts, 1) || '0', 10);
                const eh = parseInt(at(endParts, 0) || '0', 10);
                const em = parseInt(at(endParts, 1) || '0', 10);
                const slotDuration = (eh * 60 + em) - (sh * 60 + sm);
                return slotDuration >= duration;
              });

              if (dateCanAccommodate) {
                // Also check if it's not in the past
                const now = new Date();
                const dateObj = new Date(date);
                if (dateObj >= new Date(now.getFullYear(), now.getMonth(), now.getDate())) {
                  newSelectedDate = date;
                  break;
                }
              }
            }

            if (newSelectedDate) {
              // Switch to the new date that can accommodate the duration
              setSelectedDate(newSelectedDate);
              handleDateSelect(newSelectedDate);
              logger.info('Switched to new date for duration', { newDate: newSelectedDate, duration });
              return;
            }
          }
        }

        // If we get here, either current date works or we couldn't find a better date
        // Continue with existing logic
        if (!availabilityData[selectedDate]) {
          handleDateSelect(selectedDate);
          return;
        }

        // Mark that the next slots update is due to duration change
        lastChangeWasDurationRef.current = true;

        const dayData = availabilityData[selectedDate];
        const slots = (dayData as Record<string, unknown>)?.['available_slots'] || [];

        const now = new Date();
        const isToday = selectedDate === formatDateInTz(now, studentTimezone);

        // Filter out past slots for today
        const validSlots = (slots as unknown as AvailabilitySlot[]).filter((slot: AvailabilitySlot) => {
          if (isToday) {
            const currentHHMM = nowHHMMInTz(studentTimezone);
            if (slot.start_time.slice(0, 5) <= currentHHMM) return false;
          }
          // Keep slot; per-start-time filtering happens below
          return true;
        });

        // Helper to expand starts for a given duration
        const expandForDuration = (dur: number): string[] => {
          return validSlots.flatMap((slot: AvailabilitySlot) => {
            const startParts = slot.start_time.split(':');
            const endParts = slot.end_time.split(':');
            const sh = parseInt(at(startParts, 0) || '0', 10);
            const sm = parseInt(at(startParts, 1) || '0', 10);
            const eh = parseInt(at(endParts, 0) || '0', 10);
            const em = parseInt(at(endParts, 1) || '0', 10);
            const startTotal = sh * 60 + (sm || 0);
            const endTotal = eh * 60 + (em || 0);
            const times: string[] = [];
            for (let t = startTotal; t + dur <= endTotal; t += 60) {
              const h = Math.floor(t / 60);
              const m = t % 60;
              const ampm = h >= 12 ? 'pm' : 'am';
              const displayHour = (h % 12) || 12;
              times.push(`${displayHour}:${String(m).padStart(2, '0')}${ampm}`);
            }
            return times;
          });
        };

        const uniqueDurations = Array.from(new Set(durationOptions.map((o) => o.duration)));
        const slotsByDuration: Record<number, string[]> = {};
        uniqueDurations.forEach((dur) => {
          slotsByDuration[dur] = expandForDuration(dur);
        });

        // Base: disable durations with no starts at all for the date
        const baseDisabled = uniqueDurations.filter((d) => (slotsByDuration[d] || []).length === 0);

        // Build new list for the selected duration
        const newSlots = slotsByDuration[duration] || [];
        setTimeSlots(newSlots);

        // Preserve selected time if still valid for new duration
        if (selectedTime && newSlots.includes(selectedTime)) {
          // keep selection
        } else {
          // Clear selection but do not auto-select
          setSelectedTime(null);
        }

        // Additionally disable durations incompatible with the currently selected start time
        const additionalDisabled: number[] = [];
        if (selectedTime) {
          // Convert selected display time to minutes since 00:00
          const parseDisplayTimeToMinutes = (display: string): number => {
            const lower = display.toLowerCase();
            const isPM = lower.includes('pm');
            const core = lower.replace(/am|pm/g, '').trim();
            const parts = core.split(':');
            const hh = at(parts, 0);
            const mm = at(parts, 1);
            if (!hh || !mm) return 0; // Return 0 for invalid times instead of continue
            let hour = parseInt(hh, 10);
            const minute = parseInt(mm || '0', 10);
            if (isPM && hour !== 12) hour += 12;
            if (!isPM && lower.includes('am') && hour === 12) hour = 0;
            return hour * 60 + minute;
          };

          const selectedStartMins = parseDisplayTimeToMinutes(selectedTime);

          const isDurationValidForSelectedTime = (dur: number): boolean => {
            return validSlots.some((slot: AvailabilitySlot) => {
              const startParts = slot.start_time.split(':');
              const endParts = slot.end_time.split(':');
              const sh = parseInt(at(startParts, 0) || '0', 10);
              const sm = parseInt(at(startParts, 1) || '0', 10);
              const eh = parseInt(at(endParts, 0) || '0', 10);
              const em = parseInt(at(endParts, 1) || '0', 10);
              const slotStart = sh * 60 + (sm || 0);
              const slotEnd = eh * 60 + (em || 0);
              return selectedStartMins >= slotStart && selectedStartMins + dur <= slotEnd;
            });
          };

          uniqueDurations.forEach((dur) => {
            if (!isDurationValidForSelectedTime(dur)) {
              additionalDisabled.push(dur);
            }
          });
        }

        const combinedDisabled = Array.from(new Set([...baseDisabled, ...additionalDisabled]));
        setDisabledDurations(combinedDisabled);
      } catch (e) {
        logger.error('Failed to recompute slots on duration change', e);
        handleDateSelect(selectedDate);
      }
    }
  };

  // Recompute disabled durations whenever the selected time changes
  useEffect(() => {
    if (!selectedDate || !availabilityData || !availabilityData[selectedDate]) {
      return;
    }

    try {
      const dayData = availabilityData[selectedDate];
      const slots = (dayData as Record<string, unknown>)?.['available_slots'] || [];

      const now = new Date();
      const isToday = selectedDate === formatDateInTz(now, studentTimezone);

      const validSlots = (slots as unknown as AvailabilitySlot[]).filter((slot: AvailabilitySlot) => {
        if (isToday) {
          const currentHHMM = nowHHMMInTz(studentTimezone);
          if (slot.start_time.slice(0, 5) <= currentHHMM) return false;
        }
        return true;
      });

      const uniqueDurations = Array.from(new Set(durationOptions.map((o) => o.duration)));

      const slotsByDuration: Record<number, string[]> = {};
      uniqueDurations.forEach((dur) => {
        slotsByDuration[dur] = validSlots.flatMap((slot: AvailabilitySlot) => {
          const startParts = slot.start_time.split(':');
          const endParts = slot.end_time.split(':');
          const sh = parseInt(startParts[0] || '0', 10);
          const sm = parseInt(startParts[1] || '0', 10);
          const eh = parseInt(endParts[0] || '0', 10);
          const em = parseInt(endParts[1] || '0', 10);
          const startTotal = (sh || 0) * 60 + (sm || 0);
          const endTotal = (eh || 0) * 60 + (em || 0);
          const times: string[] = [];
          for (let t = startTotal; t + dur <= endTotal; t += 60) {
            const h = Math.floor(t / 60);
            const m = t % 60;
            const ampm = h >= 12 ? 'pm' : 'am';
            const displayHour = (h % 12) || 12;
            times.push(`${displayHour}:${String(m).padStart(2, '0')}${ampm}`);
          }
          return times;
        });
      });

      const baseDisabled = uniqueDurations.filter((d) => (slotsByDuration[d] || []).length === 0);

      const additionalDisabled: number[] = [];
      if (selectedTime) {
        const parseDisplayTimeToMinutes = (display: string): number => {
          const lower = display.toLowerCase();
          const isPM = lower.includes('pm');
          const isAM = lower.includes('am');
          const core = lower.replace(/am|pm/g, '').trim();
          const [hh, mm] = core.split(':');
          let hour = parseInt(hh || '0', 10);
          const minute = parseInt(mm || '0', 10);
          if (isPM && hour !== 12) hour += 12;
          if (isAM && hour === 12) hour = 0;
          return hour * 60 + minute;
        };

        const selectedStartMins = parseDisplayTimeToMinutes(selectedTime);

        const isDurationValidForSelectedTime = (dur: number): boolean => {
          return validSlots.some((slot: AvailabilitySlot) => {
            const startParts = slot.start_time.split(':');
            const endParts = slot.end_time.split(':');
            const sh = parseInt(at(startParts, 0) || '0', 10);
            const sm = parseInt(at(startParts, 1) || '0', 10);
            const eh = parseInt(at(endParts, 0) || '0', 10);
            const em = parseInt(at(endParts, 1) || '0', 10);
            const slotStart = sh * 60 + (sm || 0);
            const slotEnd = eh * 60 + (em || 0);
            return selectedStartMins >= slotStart && selectedStartMins + dur <= slotEnd;
          });
        };

        uniqueDurations.forEach((dur) => {
          if (!isDurationValidForSelectedTime(dur)) {
            additionalDisabled.push(dur);
          }
        });
      }

      const combined = Array.from(new Set([...baseDisabled, ...additionalDisabled]));

      // Only update state if the computed list actually changed
      const areSetsEqual = (a: number[], b: number[]) => {
        if (a.length !== b.length) return false;
        const setA = new Set(a);
        for (const v of b) {
          if (!setA.has(v)) return false;
        }
        return true;
      };

      setDisabledDurations((prev) => (areSetsEqual(prev, combined) ? prev : combined));
    } catch (e) {
      logger.error('Failed to recompute disabled durations on time change', e);
    }
  }, [selectedTime, selectedDate, availabilityData, studentTimezone, durationOptions]);

  if (!isOpen) return null;

  return (
    <>
      {/* Mobile Full Screen View */}
      <div className="md:hidden fixed inset-0 z-50 bg-white dark:bg-gray-900">
        <div className="h-full flex flex-col">
          {/* Mobile Header */}
          <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
            <button
              onClick={onClose}
              className="p-2 -ml-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
              aria-label="Go back"
            >
              <ArrowLeft className="h-6 w-6 text-gray-600 dark:text-gray-400" />
            </button>
            <h2 className="text-2xl font-medium text-gray-900 dark:text-white">
              Set your lesson date & time
            </h2>
            <div className="w-10" /> {/* Spacer for centering */}
          </div>

          {/* Instructor Name */}
          <div className="px-4 pt-4 pb-2 flex items-center gap-2">
            <div className="w-8 h-8 rounded-full overflow-hidden bg-gray-200" />
            <p className="text-base font-bold text-black">
              {getInstructorDisplayName()}&apos;s availability
            </p>
          </div>

          {/* Mobile Content */}
          <div className="flex-1 overflow-y-auto px-4 pb-20">
            {/* Calendar Component */}
            <Calendar
              currentMonth={currentMonth}
              selectedDate={selectedDate}
              {...(preSelectedDate && { preSelectedDate })}
              availableDates={availableDates}
              onDateSelect={handleDateSelect}
              onMonthChange={setCurrentMonth}
            />

            {/* Time Dropdown (shown when date selected) */}
            {showTimeDropdown && (
              <div className="mb-4">
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

            {/* Summary Section */}
            <SummarySection
              selectedDate={selectedDate}
              selectedTime={selectedTime}
              selectedDuration={selectedDuration}
              price={getCurrentPrice()}
              onContinue={handleContinue}
              isComplete={!!selectedDate && !!selectedTime}
            />
          </div>

          {/* Mobile Sticky CTA - Rendered by SummarySection */}
          <div className="fixed bottom-0 left-0 right-0 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 p-4">
            <SummarySection
              selectedDate={selectedDate}
              selectedTime={selectedTime}
              selectedDuration={selectedDuration}
              price={getCurrentPrice()}
              onContinue={handleContinue}
              isComplete={!!selectedDate && !!selectedTime}
            />
          </div>
        </div>
      </div>

      {/* Desktop Modal View */}
      <div
        className="hidden md:block fixed inset-0 z-50 overflow-y-auto"
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
            ref={modalRef}
            tabIndex={-1}
            className="relative bg-white dark:bg-gray-900 rounded-lg shadow-xl w-full max-w-[720px] max-h-[90vh] flex flex-col animate-slideUp"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Desktop Header */}
            <div className="flex items-center justify-between p-8 pb-0">
              <h2
                className="text-2xl font-medium text-gray-900 dark:text-white"
                style={{ color: '#333333' }}
              >
                Set your lesson date & time
              </h2>
              <button
                onClick={onClose}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
                aria-label="Close modal"
              >
                <X className="h-6 w-6 text-gray-600 dark:text-gray-400" />
              </button>
            </div>

            {/* Instructor Name */}
            <div className="px-8 pt-2 pb-6 flex items-center gap-2">
              <div className="w-8 h-8 rounded-full overflow-hidden bg-gray-200" />
              <p className="text-base font-bold text-black">
                {getInstructorDisplayName()}&apos;s availability
              </p>
            </div>

            {/* Desktop Content - Split Layout */}
            <div className="flex-1 overflow-y-auto px-8 pb-8">
              <div className="flex gap-8">
                {/* Left Section - Calendar and Controls */}
                <div className="flex-1">
                  {/* Calendar Component */}
                  <Calendar
                    currentMonth={currentMonth}
                    selectedDate={selectedDate}
                    {...(preSelectedDate && { preSelectedDate })}
                    availableDates={availableDates}
                    onDateSelect={handleDateSelect}
                    onMonthChange={setCurrentMonth}
                  />

                  {/* Time Dropdown (shown when date selected) */}
                  {showTimeDropdown && (
                    <div className="mb-4">
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
                </div>

                {/* Vertical Divider */}
                <div
                  className="w-px bg-gray-200 dark:bg-gray-700"
                  style={{ backgroundColor: '#E8E8E8' }}
                />

                {/* Right Section - Summary and CTA */}
                <div className="w-[200px] flex-shrink-0 pt-12">
                  <SummarySection
                    selectedDate={selectedDate}
                    selectedTime={selectedTime}
                    selectedDuration={selectedDuration}
                    price={getCurrentPrice()}
                    onContinue={handleContinue}
                    isComplete={!!selectedDate && !!selectedTime}
                  />
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
