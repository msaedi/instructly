// app/dashboard/instructor/availability/page.tsx
"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { fetchWithAuth, API_ENDPOINTS, validateWeekChanges } from "@/lib/api";
import { Calendar, Clock, Copy, Save, ChevronLeft, ChevronRight, AlertCircle, Trash2, CalendarDays } from "lucide-react";
import { SlotOperation, BulkUpdateRequest, BulkUpdateResponse, OperationResult, ExistingSlot, WeekValidationResponse } from '@/types/availability';
import { BookedSlotPreview } from '@/types/booking';
import BookingQuickPreview from '@/components/BookingQuickPreview';
import BookedSlotCell from '@/components/BookedSlotCell';
import TimeSlotButton from '@/components/TimeSlotButton';
import WeekCalendarGrid from '@/components/WeekCalendarGrid';
import { logger } from '@/lib/logger';
import { BRAND } from '@/app/config/brand'

type DayOfWeek = 'monday' | 'tuesday' | 'wednesday' | 'thursday' | 'friday' | 'saturday' | 'sunday';

interface TimeSlot {
  start_time: string;
  end_time: string;
  is_available: boolean;
}

type BookedSlot = BookedSlotPreview;

interface WeekSchedule {
  [date: string]: TimeSlot[];
}

interface DateInfo {
  date: Date;
  dateStr: string;
  dayOfWeek: DayOfWeek;
  fullDate: string; // YYYY-MM-DD format
}

const DAYS: DayOfWeek[] = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];

/**
 * AvailabilityPage Component
 * 
 * Manages instructor availability on a week-by-week basis.
 * Features:
 * - Week-based navigation and editing
 * - Visual calendar grid with time slots
 * - Booking protection (can't modify booked slots)
 * - Preset schedules for quick setup
 * - Copy from previous week functionality
 * - Apply to future weeks with automatic saving
 * - Real-time validation before saving
 * - Mobile-responsive design
 */
export default function AvailabilityPage() {
  // Core state
  const [currentWeekStart, setCurrentWeekStart] = useState<Date>(new Date());
  const [weekSchedule, setWeekSchedule] = useState<WeekSchedule>({});
  const [savedWeekSchedule, setSavedWeekSchedule] = useState<WeekSchedule>({});
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  
  // Loading states
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  
  // UI state
  const [message, setMessage] = useState<{ type: 'success' | 'error' | 'info', text: string } | null>(null);
  const [showApplyModal, setShowApplyModal] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [showValidationPreview, setShowValidationPreview] = useState(false);
  const [showBookingPreview, setShowBookingPreview] = useState(false);
  
  // Modal state
  const [applyUntilDate, setApplyUntilDate] = useState<string>('');
  const [applyUntilOption, setApplyUntilOption] = useState<'date' | 'end-of-year' | 'indefinitely'>('end-of-year');
  const [selectedBookingId, setSelectedBookingId] = useState<number | null>(null);
  
  // Data state
  const [bookedSlots, setBookedSlots] = useState<BookedSlot[]>([]);
  const [existingSlots, setExistingSlots] = useState<ExistingSlot[]>([]);
  const [validationResults, setValidationResults] = useState<WeekValidationResponse | null>(null);
  const [pendingOperations, setPendingOperations] = useState<SlotOperation[]>([]);
  
  const router = useRouter();

  // Define preset schedules
  const PRESET_SCHEDULES: { [key: string]: { [day: string]: TimeSlot[] } } = {
    'weekday_9_to_5': {
      monday: [{ start_time: '09:00:00', end_time: '17:00:00', is_available: true }],
      tuesday: [{ start_time: '09:00:00', end_time: '17:00:00', is_available: true }],
      wednesday: [{ start_time: '09:00:00', end_time: '17:00:00', is_available: true }],
      thursday: [{ start_time: '09:00:00', end_time: '17:00:00', is_available: true }],
      friday: [{ start_time: '09:00:00', end_time: '17:00:00', is_available: true }],
      saturday: [],
      sunday: []
    },
    'mornings_only': {
      monday: [{ start_time: '08:00:00', end_time: '12:00:00', is_available: true }],
      tuesday: [{ start_time: '08:00:00', end_time: '12:00:00', is_available: true }],
      wednesday: [{ start_time: '08:00:00', end_time: '12:00:00', is_available: true }],
      thursday: [{ start_time: '08:00:00', end_time: '12:00:00', is_available: true }],
      friday: [{ start_time: '08:00:00', end_time: '12:00:00', is_available: true }],
      saturday: [{ start_time: '08:00:00', end_time: '12:00:00', is_available: true }],
      sunday: [{ start_time: '08:00:00', end_time: '12:00:00', is_available: true }]
    },
    'evenings_only': {
      monday: [{ start_time: '17:00:00', end_time: '21:00:00', is_available: true }],
      tuesday: [{ start_time: '17:00:00', end_time: '21:00:00', is_available: true }],
      wednesday: [{ start_time: '17:00:00', end_time: '21:00:00', is_available: true }],
      thursday: [{ start_time: '17:00:00', end_time: '21:00:00', is_available: true }],
      friday: [{ start_time: '17:00:00', end_time: '21:00:00', is_available: true }],
      saturday: [],
      sunday: []
    },
    'weekends_only': {
      monday: [],
      tuesday: [],
      wednesday: [],
      thursday: [],
      friday: [],
      saturday: [{ start_time: '09:00:00', end_time: '17:00:00', is_available: true }],
      sunday: [{ start_time: '09:00:00', end_time: '17:00:00', is_available: true }]
    }
  };

  // Initialize current week to start on Monday
  useEffect(() => {
    const today = new Date();
    const dayOfWeek = today.getDay();
    const diff = today.getDate() - dayOfWeek + (dayOfWeek === 0 ? -6 : 1);
    const monday = new Date(today.setDate(diff));
    monday.setHours(0, 0, 0, 0);
    setCurrentWeekStart(monday);
    
    // Set default "until" date to end of current month
    const endOfMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0);
    setApplyUntilDate(endOfMonth.toISOString().split('T')[0]);
  }, []);

  // Auto-hide messages after 5 seconds
  useEffect(() => {
    if (message) {
      const timer = setTimeout(() => setMessage(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [message]);

  // Fetch data when week changes
  useEffect(() => {
    setWeekSchedule({});
    setSavedWeekSchedule({});
    setExistingSlots([]); 
    setHasUnsavedChanges(false);
    fetchWeekSchedule();
    fetchBookedSlots();
  }, [currentWeekStart]);

  /**
   * Fetch booked slots for the current week
   */
  const fetchBookedSlots = async () => {
    try {
      const response = await fetchWithAuth(
        `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK}/booked-slots?start_date=${formatDateForAPI(currentWeekStart)}`
      );
      if (response.ok) {
        const data = await response.json();
        logger.debug('Fetched booked slots', { 
          count: data.booked_slots?.length || 0,
          weekStart: formatDateForAPI(currentWeekStart) 
        });
        setBookedSlots(data.booked_slots || []);
      }
    } catch (error) {
      logger.error('Failed to fetch booked slots', error);
    }
  };

  /**
   * Format date for API (YYYY-MM-DD)
   */
  const formatDateForAPI = (date: Date): string => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  /**
   * Get week dates starting from Monday
   */
  const getWeekDates = (): DateInfo[] => {
    const dates: DateInfo[] = [];
    for (let i = 0; i < 7; i++) {
      const date = new Date(currentWeekStart);
      date.setDate(currentWeekStart.getDate() + i);
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      
      dates.push({
        date,
        dateStr: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        dayOfWeek: DAYS[i],
        fullDate: `${year}-${month}-${day}`
      });
    }
    return dates;
  };

  /**
   * Check if a specific time slot is in the past
   */
  const isTimeSlotInPast = (dateStr: string, hour: number): boolean => {
    const [year, month, day] = dateStr.split('-').map(num => parseInt(num));
    const slotDateTime = new Date(year, month - 1, day, hour, 0, 0, 0);
    const now = new Date();
    return slotDateTime < now;
  };

  /**
   * Check if a date is in the past
   */
  const isDateInPast = (dateStr: string): boolean => {
    const date = new Date(dateStr);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    date.setHours(0, 0, 0, 0);
    return date < today;
  };

  /**
   * Check if a slot is booked
   */
  const isSlotBooked = (date: string, hour: number): boolean => {
    return bookedSlots.some(slot => {
      if (slot.date !== date) return false;
      const slotStartHour = parseInt(slot.start_time.split(':')[0]);
      const slotEndHour = parseInt(slot.end_time.split(':')[0]);
      return hour >= slotStartHour && hour < slotEndHour;
    });
  };

  /**
   * Check if a time slot is within an availability range
   */
  const isHourInTimeRange = (date: string, hour: number): boolean => {
    const daySlots = weekSchedule[date] || [];
    return daySlots.some(range => {
      const startHour = parseInt(range.start_time.split(':')[0]);
      const endHour = parseInt(range.end_time.split(':')[0]);
      return hour >= startHour && hour < endHour && range.is_available;
    });
  };

  /**
   * Get booking for a specific slot
   */
  const getBookingForSlot = (date: string, hour: number): BookedSlotPreview | null => {
    return bookedSlots.find(slot => {
      if (slot.date !== date) return false;
      const slotStartHour = parseInt(slot.start_time.split(':')[0]);
      const slotEndHour = parseInt(slot.end_time.split(':')[0]);
      return hour >= slotStartHour && hour < slotEndHour;
    }) || null;
  };

  /**
   * Handle click on a booked slot
   */
  const handleBookedSlotClick = (bookingId: number, event?: React.MouseEvent) => {
    logger.debug('Booking slot clicked', { bookingId });
    setSelectedBookingId(bookingId);
    setShowBookingPreview(true);
  };

  /**
   * Fetch week schedule from API
   */
  const fetchWeekSchedule = async () => {
    setIsLoading(true);
    logger.time('fetchWeekSchedule');

    try {
      const mondayDate = formatDateForAPI(currentWeekStart);
      const endDate = formatDateForAPI(new Date(currentWeekStart.getTime() + 6 * 24 * 60 * 60 * 1000));
      logger.debug('Fetching week schedule', { mondayDate, endDate });
      
      // First get the detailed slots with IDs
      const detailedResponse = await fetchWithAuth(
        `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY}?start_date=${mondayDate}&end_date=${endDate}`
      );
      
      if (detailedResponse.ok) {
        const detailedData = await detailedResponse.json();
        logger.debug('Fetched detailed slots', { count: detailedData.length });
  
        const slots: ExistingSlot[] = detailedData.map((slot: any) => ({
          id: slot.id,
          date: slot.specific_date,
          start_time: slot.start_time,
          end_time: slot.end_time
        }));
        setExistingSlots(slots);
      } else {
        const errorData = await detailedResponse.text();
        logger.error('Failed to fetch detailed slots', new Error(errorData), {
          status: detailedResponse.status,
          endpoint: 'INSTRUCTOR_AVAILABILITY'
        });
      }
      
      // Fetch booked slots
      const bookedResponse = await fetchWithAuth(
        `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK}/booked-slots?start_date=${mondayDate}`
      );
      
      if (bookedResponse.ok) {
        const bookedData = await bookedResponse.json();
        logger.debug('Fetched booked slots', { 
          count: bookedData.booked_slots?.length || 0 
        });
        setBookedSlots(bookedData.booked_slots || []);
      }
      
      // Then get the week view for display
      const response = await fetchWithAuth(
        `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK}?start_date=${mondayDate}`
      );
      
      if (!response.ok) throw new Error('Failed to fetch availability');
      const data = await response.json();
  
      logger.debug('Fetched week data', { 
        dates: Object.keys(data),
        totalSlots: Object.values(data).flat().length 
      });
      
      // Use slots as provided by backend (already merged appropriately)
      const cleanedData: WeekSchedule = {};
      Object.entries(data).forEach(([date, slots]) => {
        if (Array.isArray(slots) && slots.length > 0) {
          cleanedData[date] = slots as TimeSlot[];
        }
      });
  
      logger.info('Week schedule loaded successfully', {
        weekStart: mondayDate,
        daysWithAvailability: Object.keys(cleanedData).length
      });
      
      setWeekSchedule(cleanedData);
      setSavedWeekSchedule(cleanedData);
      setHasUnsavedChanges(false);
    } catch (error) {
      logger.error('Failed to load availability', error);
      setMessage({ type: 'error', text: 'Failed to load availability. Please try again.' });
    } finally {
      logger.timeEnd('fetchWeekSchedule');
      setIsLoading(false);
    }
  };

  /**
   * Navigate between weeks
   */
  const navigateWeek = (direction: 'prev' | 'next') => {
    if (hasUnsavedChanges) {
      if (!confirm('You have unsaved changes. Are you sure you want to leave without saving?')) {
        return;
      }
    }
    const newDate = new Date(currentWeekStart);
    newDate.setDate(newDate.getDate() + (direction === 'next' ? 7 : -7));
    setCurrentWeekStart(newDate);
  };

  /**
   * Toggle time slot availability
   */
  const toggleTimeSlot = (date: string, hour: number) => {
    // Check if time slot is in the past
    if (isTimeSlotInPast(date, hour)) {
      setMessage({ 
        type: 'error', 
        text: 'Cannot modify availability for past time slots.' 
      });
      return;
    }

    // Check if slot is booked
    if (isSlotBooked(date, hour)) {
      setMessage({ 
        type: 'error', 
        text: 'Cannot modify time slots that have existing bookings. Please cancel the booking first.' 
      });
      return;
    }
    
    const daySlots = weekSchedule[date] || [];
    const isCurrentlyAvailable = isHourInTimeRange(date, hour);
    
    let newSlots: TimeSlot[];
    
    if (isCurrentlyAvailable) {
      // Remove this hour from availability
      newSlots = [];
      daySlots.forEach(slot => {
        const startHour = parseInt(slot.start_time.split(':')[0]);
        const endHour = parseInt(slot.end_time.split(':')[0]);
        
        if (hour < startHour || hour >= endHour) {
          newSlots.push(slot);
        } else if (hour === startHour && hour === endHour - 1) {
          // Single hour slot, remove entirely
        } else if (hour === startHour) {
          newSlots.push({
            ...slot,
            start_time: `${(hour + 1).toString().padStart(2, '0')}:00:00`
          });
        } else if (hour === endHour - 1) {
          newSlots.push({
            ...slot,
            end_time: `${hour.toString().padStart(2, '0')}:00:00`
          });
        } else {
          // Split the slot
          newSlots.push({
            ...slot,
            end_time: `${hour.toString().padStart(2, '0')}:00:00`
          });
          newSlots.push({
            ...slot,
            start_time: `${(hour + 1).toString().padStart(2, '0')}:00:00`
          });
        }
      });
    } else {
      // Add this hour
      const newSlot: TimeSlot = {
        start_time: `${hour.toString().padStart(2, '0')}:00:00`,
        end_time: `${(hour + 1).toString().padStart(2, '0')}:00:00`,
        is_available: true
      };
      
      newSlots = [...daySlots, newSlot].sort((a, b) => 
        a.start_time.localeCompare(b.start_time)
      );
      
      // Merge adjacent slots BUT respect booking boundaries
      const mergedSlots: TimeSlot[] = [];
      newSlots.forEach((slot, index) => {
        if (index === 0) {
          mergedSlots.push(slot);
        } else {
          const lastSlot = mergedSlots[mergedSlots.length - 1];
          const lastEndHour = parseInt(lastSlot.end_time.split(':')[0]);
          const currentStartHour = parseInt(slot.start_time.split(':')[0]);
          
          // Check if there's a booked slot between the last slot and current slot
          let hasBookingBetween = false;
          for (let h = lastEndHour; h < currentStartHour; h++) {
            if (isSlotBooked(date, h)) {
              hasBookingBetween = true;
              break;
            }
          }
          
          // Only merge if slots are adjacent and no booking between
          if (lastSlot.end_time === slot.start_time && 
              lastSlot.is_available === slot.is_available && 
              !hasBookingBetween) {
            // Check that merging wouldn't span across a booked slot
            const mergedStartHour = parseInt(lastSlot.start_time.split(':')[0]);
            const mergedEndHour = parseInt(slot.end_time.split(':')[0]);
            
            let wouldSpanBooking = false;
            for (let h = mergedStartHour; h < mergedEndHour; h++) {
              if (isSlotBooked(date, h)) {
                wouldSpanBooking = true;
                break;
              }
            }
            
            if (!wouldSpanBooking) {
              // Safe to merge
              lastSlot.end_time = slot.end_time;
            } else {
              // Can't merge - would span a booking
              mergedSlots.push(slot);
            }
          } else {
            mergedSlots.push(slot);
          }
        }
      });
      newSlots = mergedSlots;
    }
    
    setWeekSchedule({
      ...weekSchedule,
      [date]: newSlots
    });
    setHasUnsavedChanges(true);
  };

  /**
   * Clear week (preserving booked slots)
   */
  const confirmClearWeek = () => {
    // Get all booked dates and times
    const bookedDateTimes = new Set<string>();
    bookedSlots.forEach(slot => {
      const startHour = parseInt(slot.start_time.split(':')[0]);
      const endHour = parseInt(slot.end_time.split(':')[0]);
      for (let hour = startHour; hour < endHour; hour++) {
        bookedDateTimes.add(`${slot.date}-${hour}`);
      }
    });
    
    // Clear only non-booked slots
    const newSchedule: WeekSchedule = {};
    const weekDates = getWeekDates();
    let preservedSlotCount = 0;
    
    weekDates.forEach(dateInfo => {
      const dateStr = dateInfo.fullDate;
      const currentSlots = weekSchedule[dateStr] || [];
      const preservedSlots: TimeSlot[] = [];
      
      // Check each slot individually
      currentSlots.forEach(slot => {
        const startHour = parseInt(slot.start_time.split(':')[0]);
        const endHour = parseInt(slot.end_time.split(':')[0]);
        let hasBooking = false;
        
        // Check if any hour in this slot is booked
        for (let hour = startHour; hour < endHour; hour++) {
          if (bookedDateTimes.has(`${dateStr}-${hour}`)) {
            hasBooking = true;
            break;
          }
        }
        
        if (hasBooking) {
          // Preserve this slot
          preservedSlots.push(slot);
          preservedSlotCount++;
        }
      });
      
      newSchedule[dateStr] = preservedSlots;
    });
    
    setWeekSchedule(newSchedule);
    setHasUnsavedChanges(true);
    
    if (preservedSlotCount > 0) {
      setMessage({ 
        type: 'info', 
        text: `Week cleared except for ${preservedSlotCount} slot(s) with bookings. Remember to save your changes.` 
      });
    } else {
      setMessage({ 
        type: 'info', 
        text: 'Week cleared. Remember to save your changes.' 
      });
    }
    
    setShowClearConfirm(false);
  };

  /**
   * Apply preset schedule to current week
   */
  const applyPresetToWeek = (preset: string) => {
    try {
      const presetData = PRESET_SCHEDULES[preset];
      if (!presetData) {
        throw new Error(`Invalid preset: ${preset}`);
      }
      
      // Start with an empty schedule for ALL days
      const newSchedule: WeekSchedule = {};
      const weekDates = getWeekDates();
      
      // First, clear all days
      weekDates.forEach(dateInfo => {
        newSchedule[dateInfo.fullDate] = [];
      });
      
      // Then apply the preset
      weekDates.forEach(dateInfo => {
        const daySlots = presetData[dateInfo.dayOfWeek];
        if (daySlots && daySlots.length > 0) {
          newSchedule[dateInfo.fullDate] = [...daySlots];
        }
        // Empty days remain as empty arrays
      });
      
      setWeekSchedule(newSchedule);
      setHasUnsavedChanges(true);
      
      const presetName = preset.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
      setMessage({ type: 'success', text: `${presetName} schedule applied. Don't forget to save!` });
      
    } catch (error) {
      logger.error('Failed to apply preset', error);
      setMessage({ type: 'error', text: `Failed to apply preset: ${error instanceof Error ? error.message : 'Unknown error'}` });
    }
  };

  /**
   * Save week schedule with validation
   */
  const saveWeekSchedule = async (skipValidation = false) => {
    logger.time('saveWeekSchedule');
    setIsSaving(true);

    // Move mondayDate declaration to the top level of the function
    const mondayDate = formatDateForAPI(currentWeekStart);
    
    // If not skipping validation, validate first
    if (!skipValidation && hasUnsavedChanges) {
      setIsValidating(true);
      logger.debug('Starting validation for week changes');
      try {
        const validation = await validateWeekChanges(
          weekSchedule,
          savedWeekSchedule,
          currentWeekStart
        );
        
        setValidationResults(validation);
        logger.debug('Validation completed', {
          valid: validation.valid,
          warningCount: validation.warnings.length,
          operations: validation.summary.total_operations
        });
        setIsValidating(false);
        
        // If there are conflicts, show preview modal
        if (!validation.valid) {
          setShowValidationPreview(true);
          setIsSaving(false);
          return;
        }
        
        // If valid but has warnings, optionally show them
        if (validation.warnings.length > 0) {
          logger.warn('Validation warnings', { warnings: validation.warnings });
          setMessage({
            type: 'info',
            text: `Note: ${validation.warnings.join('. ')}`
          });
        }
      } catch (error) {
        setIsValidating(false);
        setIsSaving(false);
        logger.error('Validation failed', error);
        setMessage({
          type: 'error',
          text: 'Failed to validate changes. Saving anyway...'
        });
        // Continue with save even if validation fails
      }
    }
    
    try {
      let operations: SlotOperation[];
      
      if (skipValidation && pendingOperations.length > 0) {
        // Use stored operations from validation
        operations = pendingOperations;
        logger.debug('Using pending operations from validation', { count: operations.length });
      } else {
        logger.group('Generating save operations', () => {
          logger.debug('Current week state', { 
            dates: Object.keys(weekSchedule),
            totalSlots: Object.values(weekSchedule).flat().length 
          });
          logger.debug('Saved week state', { 
            dates: Object.keys(savedWeekSchedule),
            totalSlots: Object.values(savedWeekSchedule).flat().length 
          });
        });
        
        // First, fetch current existing slots to ensure we have the latest IDs
        const endDate = formatDateForAPI(new Date(currentWeekStart.getTime() + 6 * 24 * 60 * 60 * 1000));

        logger.debug('Fetching current slot IDs', { mondayDate, endDate });

        const detailedResponse = await fetchWithAuth(
          `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY}?start_date=${mondayDate}&end_date=${endDate}`
        );
        
        let currentExistingSlots: ExistingSlot[] = [];
        if (detailedResponse.ok) {
          const detailedData = await detailedResponse.json();
          currentExistingSlots = detailedData.map((slot: any) => ({
            id: slot.id,
            date: slot.specific_date,
            start_time: slot.start_time,
            end_time: slot.end_time
          }));
          logger.debug('Fetched existing slots for ID mapping', { count: currentExistingSlots.length });
        } else {
          const errorData = await detailedResponse.text();
          logger.error('Failed to fetch existing slots', new Error(errorData), {
            status: detailedResponse.status,
            endpoint: 'INSTRUCTOR_AVAILABILITY'
          });
          logger.warn('Continuing without existing slot IDs - remove operations may not work');
        }
        
        // Generate operations by comparing current state with saved state
        operations = [];
        const weekDates = getWeekDates();
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        
        // Process each date
        weekDates.forEach(dateInfo => {
          const dateStr = dateInfo.fullDate;
          const currentSlots = weekSchedule[dateStr] || [];
          const savedSlots = savedWeekSchedule[dateStr] || [];

          logger.debug('Comparing date', { 
            date: dateStr, 
            currentSlots: currentSlots.length, 
            savedSlots: savedSlots.length 
          });
          
          // Skip past dates (but include today)
          if (dateInfo.fullDate !== today.toISOString().split('T')[0] && new Date(dateStr) < today) {
            logger.debug('Skipping past date', { date: dateStr });
            return;
          }
          
          // Find slots to remove (in saved but not in current)
          savedSlots.forEach(savedSlot => {
            const stillExists = currentSlots.some(currentSlot => 
              currentSlot.start_time === savedSlot.start_time &&
              currentSlot.end_time === savedSlot.end_time
            );
            
            if (!stillExists) {
              // Find the slot ID using the freshly fetched data
              const existingSlot = currentExistingSlots.find(s => 
                s.date === dateStr &&
                s.start_time === savedSlot.start_time &&
                s.end_time === savedSlot.end_time
              );
              
              if (existingSlot) {
                logger.debug('Marking slot for removal', { 
                  date: dateStr, 
                  slotId: existingSlot.id,
                  time: `${savedSlot.start_time} - ${savedSlot.end_time}`
                });
                operations.push({
                  action: 'remove',
                  slot_id: existingSlot.id
                });
              } else {
                logger.debug('Could not find exact slot ID for removal', { 
                  date: dateStr,
                  time: `${savedSlot.start_time} - ${savedSlot.end_time}`
                });
                
                // Find overlapping slots
                const overlappingSlots = currentExistingSlots.filter(s => {
                  if (s.date !== dateStr) return false;
                  
                  const slotStart = s.start_time;
                  const slotEnd = s.end_time;
                  const savedStart = savedSlot.start_time;
                  const savedEnd = savedSlot.end_time;
                  
                  // Check if there's any overlap
                  return slotStart < savedEnd && slotEnd > savedStart;
                });
                
                logger.debug('Overlapping slots found', { count: overlappingSlots.length });
                
                // Remove all overlapping slots
                overlappingSlots.forEach(slot => {
                  operations.push({
                    action: 'remove',
                    slot_id: slot.id
                  });
                });
              }
            }
          });
          
          // Find slots to add (in current but not in saved)
          currentSlots.forEach(currentSlot => {
            const existsInSaved = savedSlots.some(savedSlot => 
              savedSlot.start_time === currentSlot.start_time &&
              savedSlot.end_time === currentSlot.end_time
            );
            
            if (!existsInSaved) {
              logger.debug('Marking slot for addition', { 
                date: dateStr,
                time: `${currentSlot.start_time} - ${currentSlot.end_time}`
              });
              operations.push({
                action: 'add',
                date: dateStr,
                start_time: currentSlot.start_time,
                end_time: currentSlot.end_time
              });
            }
          });
        });
        
        logger.info('Generated operations summary', { 
          total: operations.length,
          adds: operations.filter(op => op.action === 'add').length,
          removes: operations.filter(op => op.action === 'remove').length
        });
        
        if (operations.length === 0) {
          setMessage({ type: 'info', text: 'No changes to save.' });
          setHasUnsavedChanges(false);
          return;
        }
        
        // Store operations for potential reuse
        setPendingOperations(operations);
      }
      
      // Apply the changes
      const applyRequest: BulkUpdateRequest = {
        operations,
        validate_only: false
      };
      
      logger.debug('Sending bulk update request', { operationCount: operations.length });
      
      const response = await fetchWithAuth(
        API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_BULK_UPDATE,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(applyRequest)
        });
      
      if (!response.ok) {
        const error = await response.json();
        logger.error('Bulk update failed', error, {
          status: response.status,
          endpoint: 'INSTRUCTOR_AVAILABILITY_BULK_UPDATE'
        });
        
        // Handle Pydantic validation errors properly
        if (error.detail && Array.isArray(error.detail)) {
          const errorMessages = error.detail.map((err: any) => 
            `${err.loc?.join(' > ')}: ${err.msg}`
          ).join(', ');
          throw new Error(errorMessages);
        } else if (error.detail) {
          throw new Error(error.detail);
        } else {
          throw new Error('Failed to save changes');
        }
      }
      
      const result: BulkUpdateResponse = await response.json();
      
      logger.info('Save operation completed', {
        successful: result.successful,
        failed: result.failed,
        skipped: result.skipped,
        weekStart: mondayDate
      });
      
      // Show detailed results
      if (result.successful === operations.length) {
        setMessage({ 
          type: 'success', 
          text: result.successful === 1 
            ? 'Successfully saved the change!' 
            : `Successfully saved all ${result.successful} changes!` 
        });
      } else if (result.successful > 0) {
        const changeText = result.successful === 1 ? 'change' : 'changes';
        const failedText = result.failed === 1 ? 'failed' : 'failed';
        const skippedText = result.skipped === 1 ? 'skipped' : 'skipped';
        
        setMessage({ 
          type: 'info', 
          text: `Saved ${result.successful} ${changeText}. ${result.failed} ${failedText}, ${result.skipped} ${skippedText}.` 
        });
      } else {
        const operationText = result.failed === 1 ? 'operation' : 'operations';
        setMessage({ 
          type: 'error', 
          text: `Failed to save changes. ${result.failed} ${operationText} failed.` 
        });
      }
      
      // Refresh the schedule to get the updated state
      await fetchWeekSchedule();
      setHasUnsavedChanges(false);
      
    } catch (error) {
      logger.error('Save operation failed', error, {
        weekStart: mondayDate
      });
      setMessage({ 
        type: 'error', 
        text: error instanceof Error ? error.message : 'Failed to save schedule. Please try again.' 
      });
    } finally {
      logger.timeEnd('saveWeekSchedule');
      setIsSaving(false);
      setPendingOperations([]); // Clear pending operations
    }
  };

  /**
   * Copy schedule from previous week
   */
  const copyFromPreviousWeek = async () => {
    logger.time('copyFromPreviousWeek');
    setIsSaving(true);
    try {
      const previousWeek = new Date(currentWeekStart);
      previousWeek.setDate(previousWeek.getDate() - 7);
      
      logger.debug('Copying from previous week', {
        currentWeek: formatDateForAPI(currentWeekStart),
        previousWeek: formatDateForAPI(previousWeek)
      });
      
      const response = await fetchWithAuth(
        `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK}?start_date=${formatDateForAPI(previousWeek)}`
      );
      
      if (!response.ok) throw new Error('Failed to fetch previous week');
      const previousWeekData = await response.json();
      
      logger.debug('Previous week data fetched', {
        dates: Object.keys(previousWeekData),
        totalSlots: Object.values(previousWeekData).flat().length
      });
      
      // Get current week's booked slots to avoid modifying them
      await fetchBookedSlots();
      
      // Start with the CURRENT week's schedule to preserve booked slots
      const copiedSchedule: WeekSchedule = {};
      const weekDates = getWeekDates();

      let preservedBookings = 0;
      let copiedSlots = 0;
      
      weekDates.forEach((dateInfo, index) => {
        const currentDateStr = dateInfo.fullDate;
        const prevDate = new Date(previousWeek);
        prevDate.setDate(prevDate.getDate() + index);
        const prevDateStr = formatDateForAPI(prevDate);
        
        logger.debug('Processing date mapping', { 
          from: prevDateStr, 
          to: currentDateStr 
        });
        
        // Check if this date has any bookings
        const hasBookingsOnDate = bookedSlots.some(slot => slot.date === currentDateStr);
        
        if (hasBookingsOnDate) {
          // This date has bookings - preserve existing slots that contain bookings
          const existingSlots = weekSchedule[currentDateStr] || [];
          const preservedSlots: TimeSlot[] = [];
          
          // Check each existing slot to see if it contains bookings
          existingSlots.forEach(slot => {
            const slotStartHour = parseInt(slot.start_time.split(':')[0]);
            const slotEndHour = parseInt(slot.end_time.split(':')[0]);
            
            // Check if any hour in this slot is booked
            let hasBookingInSlot = false;
            for (let hour = slotStartHour; hour < slotEndHour; hour++) {
              if (isSlotBooked(currentDateStr, hour)) {
                hasBookingInSlot = true;
                break;
              }
            }
            
            if (hasBookingInSlot) {
              preservedSlots.push(slot);
              preservedBookings++;
            }
          });
          
          // Now add slots from previous week that don't conflict with bookings
          if (previousWeekData[prevDateStr] && previousWeekData[prevDateStr].length > 0) {
            previousWeekData[prevDateStr].forEach((prevSlot: TimeSlot) => {
              const prevStartHour = parseInt(prevSlot.start_time.split(':')[0]);
              const prevEndHour = parseInt(prevSlot.end_time.split(':')[0]);
              
              // Check if this time range would conflict with any bookings
              let conflictsWithBooking = false;
              for (let hour = prevStartHour; hour < prevEndHour; hour++) {
                if (isSlotBooked(currentDateStr, hour)) {
                  conflictsWithBooking = true;
                  break;
                }
              }
              
              if (!conflictsWithBooking) {
                preservedSlots.push(prevSlot);
                copiedSlots++;
              }
            });
          }
          
          // Sort and merge adjacent slots (but respect booking boundaries)
          copiedSchedule[currentDateStr] = mergeAdjacentSlots(preservedSlots, currentDateStr);
          
        } else {
          // No bookings on this date - safe to copy directly from previous week
          if (previousWeekData[prevDateStr] && previousWeekData[prevDateStr].length > 0) {
            copiedSchedule[currentDateStr] = previousWeekData[prevDateStr];
            copiedSlots += previousWeekData[prevDateStr].length;
          } else {
            copiedSchedule[currentDateStr] = [];
          }
        }
      });
      
      logger.info('Copy from previous week completed', {
        preservedBookings,
        copiedSlots,
        totalDates: weekDates.length
      });
      
      setWeekSchedule(copiedSchedule);
      setHasUnsavedChanges(true);
      setMessage({ type: 'success', text: 'Copied schedule from previous week. Booked time slots were preserved. Remember to save!' });
    } catch (error) {
      logger.error('Failed to copy from previous week', error);
      setMessage({ type: 'error', text: 'Failed to copy from previous week.' });
    } finally {
      logger.timeEnd('copyFromPreviousWeek');
      setIsSaving(false);
    }
  };

  /**
   * Helper function to merge adjacent slots while respecting booking boundaries
   */
  const mergeAdjacentSlots = (slots: TimeSlot[], dateStr: string): TimeSlot[] => {
    if (slots.length === 0) return [];
    
    // Sort by start time
    const sorted = [...slots].sort((a, b) => a.start_time.localeCompare(b.start_time));
    
    const merged: TimeSlot[] = [];
    let current = { ...sorted[0] };
    
    for (let i = 1; i < sorted.length; i++) {
      const next = sorted[i];
      const currentEndHour = parseInt(current.end_time.split(':')[0]);
      const nextStartHour = parseInt(next.start_time.split(':')[0]);
      
      // Check if there's a booking between current and next
      let hasBookingBetween = false;
      for (let hour = currentEndHour; hour < nextStartHour; hour++) {
        if (isSlotBooked(dateStr, hour)) {
          hasBookingBetween = true;
          break;
        }
      }
      
      // Can merge if adjacent and no booking between
      if (current.end_time === next.start_time && !hasBookingBetween) {
        current.end_time = next.end_time;
      } else {
        merged.push(current);
        current = { ...next };
      }
    }
    
    merged.push(current);
    return merged;
  };

  /**
   * Apply schedule to future weeks
   */
  const handleApplyToFutureWeeks = async () => {
    setShowApplyModal(true);
  };

  const confirmApplyToFutureWeeks = async () => {
    setShowApplyModal(false);
    setIsSaving(true);
    try {
      let endDate: string;
      if (applyUntilOption === 'indefinitely') {
        // Set to end of next year
        const nextYear = new Date();
        nextYear.setFullYear(nextYear.getFullYear() + 1);
        endDate = formatDateForAPI(nextYear);
      } else if (applyUntilOption === 'end-of-year') {
        const endOfYear = new Date(new Date().getFullYear(), 11, 31);
        endDate = formatDateForAPI(endOfYear);
      } else {
        endDate = applyUntilDate;
      }
      
      // First save current week if there are unsaved changes
      if (hasUnsavedChanges) {
        await saveWeekSchedule();
      }
      
      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_APPLY_RANGE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from_week_start: formatDateForAPI(currentWeekStart),
          start_date: formatDateForAPI(new Date(currentWeekStart.getTime() + 7 * 24 * 60 * 60 * 1000)),
          end_date: endDate
        })
      });
      
      if (!response.ok) throw new Error('Failed to apply to future weeks');
      
      const result = await response.json();
      setMessage({ 
        type: 'success', 
        text: `Schedule applied to ${result.slots_created} time slots through ${new Date(endDate).toLocaleDateString()}.` 
      });
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to apply to future weeks. Please try again.' });
    } finally {
      setIsSaving(false);
    }
  };

  /**
   * Cell renderer for desktop calendar grid
   */
  const renderCell = (date: string, hour: number) => {
    const isPastSlot = isTimeSlotInPast(date, hour);
    const isAvailable = isHourInTimeRange(date, hour);
    const booking = getBookingForSlot(date, hour);
    const isBooked = !!booking;
    const isFirstSlot = !!(booking && parseInt(booking.start_time.split(':')[0]) === hour);
    
    if (isBooked && booking) {
      return (
        <BookedSlotCell
          slot={booking}
          isFirstSlot={isFirstSlot}
          onClick={(e) => handleBookedSlotClick(booking.booking_id, e)}
        />
      );
    }
    
    return (
      <TimeSlotButton
        hour={hour}
        isAvailable={isAvailable}
        isBooked={isBooked}
        isPast={isPastSlot}
        onClick={() => toggleTimeSlot(date, hour)}
      />
    );
  };

  /**
   * Cell renderer for mobile calendar grid
   */
  const renderMobileCell = (date: string, hour: number) => {
    const isPastSlot = isTimeSlotInPast(date, hour);
    const isAvailable = isHourInTimeRange(date, hour);
    const booking = getBookingForSlot(date, hour);
    const isBooked = !!booking;
    const isFirstSlot = !!(booking && parseInt(booking.start_time.split(':')[0]) === hour);
    
    if (isBooked && booking) {
      return (
        <BookedSlotCell
          key={`${date}-${hour}`}
          slot={booking}
          isFirstSlot={isFirstSlot}
          isMobile={true}
          onClick={(e) => handleBookedSlotClick(booking.booking_id, e)}
        />
      );
    }
    
    return (
      <TimeSlotButton
        key={`${date}-${hour}`}
        hour={hour}
        isAvailable={isAvailable}
        isBooked={isBooked}
        isPast={isPastSlot}
        onClick={() => toggleTimeSlot(date, hour)}
        isMobile={true}
      />
    );
  };

  // Get the week dates
  const weekDates = getWeekDates();
  const currentWeekDisplay = weekDates[0].date.toLocaleDateString('en-US', { 
    month: 'long', 
    day: 'numeric',
    year: 'numeric'
  }) + ' - ' + weekDates[6].date.toLocaleDateString('en-US', { 
    month: 'long', 
    day: 'numeric',
    year: 'numeric'
  });

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <Link href="/dashboard/instructor" className="inline-flex items-center text-gray-600 hover:text-gray-900 mb-4">
        <ArrowLeft className="w-4 h-4 mr-2" />
        Back to Dashboard
      </Link>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Manage Your Availability</h1>
        <p className="text-gray-600">Set your schedule week by week for maximum flexibility</p>
      </div>

      {/* Message */}
      {message && (
        <div className={`mb-6 p-4 rounded-lg flex items-start gap-2 ${
          message.type === 'success' ? 'bg-green-50 text-green-800' : 
          message.type === 'error' ? 'bg-red-50 text-red-800' :
          'bg-blue-50 text-blue-800'
        }`}>
          <AlertCircle className="w-5 h-5 mt-0.5" />
          {message.text}
        </div>
      )}

      {/* Unsaved Changes Warning */}
      {hasUnsavedChanges && (
        <div className="mb-6 p-4 rounded-lg bg-yellow-50 text-yellow-800 flex items-start gap-2">
          <AlertCircle className="w-5 h-5 mt-0.5" />
          You have unsaved changes for this week. Don't forget to save!
        </div>
      )}

      {/* Week Navigation */}
      <div className="mb-6 bg-white rounded-lg shadow p-4 flex items-center justify-between">
        <button
          onClick={() => navigateWeek('prev')}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          title="Previous week"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <div className="text-center">
          <h2 className="text-xl font-semibold">{currentWeekDisplay}</h2>
          <p className="text-sm text-gray-600">Edit availability for this specific week</p>
        </div>
        <button
          onClick={() => navigateWeek('next')}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          title="Next week"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>

      {/* Action Buttons */}
      <div className="mb-6 flex flex-wrap gap-3 justify-between">
        <div className="flex gap-3">
          <button
            onClick={copyFromPreviousWeek}
            disabled={isSaving}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            <Copy className="w-4 h-4" />
            Copy from Previous Week
          </button>
          <button
            onClick={handleApplyToFutureWeeks}
            disabled={isSaving}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
          >
            <CalendarDays className="w-4 h-4" />
            Apply to Future Weeks
          </button>
        </div>
        <button
          onClick={() => saveWeekSchedule()}
          disabled={isSaving || !hasUnsavedChanges || isValidating}
          className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
        >
          <Save className="w-4 h-4" />
          {isValidating ? 'Validating...' : 'Save This Week'}
        </button>
      </div>

      {/* Preset Buttons */}
      <div className="mb-8">
        <h3 className="text-lg font-semibold mb-4">Quick Presets</h3>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => applyPresetToWeek('weekday_9_to_5')}
            disabled={isSaving}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            Weekday 9-5
          </button>
          <button
            onClick={() => applyPresetToWeek('mornings_only')}
            disabled={isSaving}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            Mornings Only
          </button>
          <button
            onClick={() => applyPresetToWeek('evenings_only')}
            disabled={isSaving}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            Evenings Only
          </button>
          <button
            onClick={() => applyPresetToWeek('weekends_only')}
            disabled={isSaving}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            Weekends Only
          </button>
          <button
            onClick={() => setShowClearConfirm(true)}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
          >
            <Trash2 className="w-4 h-4" />
            Clear Week
          </button>
        </div>
      </div>

      {/* Weekly Calendar Grid */}
      <WeekCalendarGrid
        weekDates={weekDates}
        startHour={8}
        endHour={20}
        renderCell={renderCell}
        renderMobileCell={renderMobileCell}
        currentWeekDisplay={currentWeekDisplay}
      />

      {/* Instructions */}
      <div className="mt-8 p-4 bg-blue-50 rounded-lg">
        <h3 className="font-semibold text-blue-900 mb-2">How it works:</h3>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>• Each week's schedule is independent - changes only affect the displayed week</li>
          <li>• Use "Save This Week" to save changes for the current week only</li>
          <li>• Use "Copy from Previous Week" to duplicate last week's schedule</li>
          <li>• Use "Apply to Future Weeks" to copy this pattern forward with automatic saving</li>
          <li>• Presets apply a standard schedule pattern</li>
          <li>• Navigate between weeks using the arrow buttons</li>
        </ul>
      </div>

      {/* Clear Week Confirmation Modal */}
      {showClearConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-sm w-full mx-4">
            <h3 className="text-lg font-semibold mb-3">Clear Week Schedule</h3>
            <p className="text-gray-600 mb-6">
              Are you sure you want to clear all availability for this week? This action cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowClearConfirm(false)}
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={confirmClearWeek}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
              >
                Clear Week
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Apply to Future Weeks Modal */}
      {showApplyModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold mb-4">Apply Schedule to Future Weeks</h3>
            <p className="text-sm text-gray-600 mb-4">
              {Object.keys(weekSchedule).length > 0 
                ? "This will copy the current week's schedule to future weeks and save automatically."
                : "This will clear the schedule for future weeks and save automatically."}
            </p>
            
            <div className="space-y-4 mb-6">
              <label className="flex items-center gap-3">
                <input
                  type="radio"
                  value="end-of-year"
                  checked={applyUntilOption === 'end-of-year'}
                  onChange={(e) => setApplyUntilOption('end-of-year')}
                  className="w-4 h-4"
                />
                <span>Until end of this year</span>
              </label>
              
              <label className="flex items-center gap-3">
                <input
                  type="radio"
                  value="date"
                  checked={applyUntilOption === 'date'}
                  onChange={(e) => setApplyUntilOption('date')}
                  className="w-4 h-4"
                />
                <span>Until specific date</span>
              </label>
              
              {applyUntilOption === 'date' && (
                <input
                  type="date"
                  value={applyUntilDate}
                  onChange={(e) => setApplyUntilDate(e.target.value)}
                  min={new Date().toISOString().split('T')[0]}
                  className="ml-7 px-3 py-2 border rounded-lg"
                />
              )}
              
              <label className="flex items-center gap-3">
                <input
                  type="radio"
                  value="indefinitely"
                  checked={applyUntilOption === 'indefinitely'}
                  onChange={(e) => setApplyUntilOption('indefinitely')}
                  className="w-4 h-4"
                />
                <span>Apply indefinitely</span>
              </label>
            </div>
            
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowApplyModal(false)}
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={confirmApplyToFutureWeeks}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
              >
                Apply & Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Validation Preview Modal */}
      {showValidationPreview && validationResults && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto">
            <h3 className="text-lg font-semibold mb-4">
              {validationResults.valid ? 'Review Changes' : 'Conflicts Detected'}
            </h3>
            
            {/* Summary */}
            <div className="mb-6 p-4 bg-gray-50 rounded-lg">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="font-medium">Total Operations:</span> {validationResults.summary.total_operations}
                </div>
                <div>
                  <span className="font-medium">Valid:</span> 
                  <span className="text-green-600 ml-2">{validationResults.summary.valid_operations}</span>
                </div>
                <div>
                  <span className="font-medium">Conflicts:</span> 
                  <span className="text-red-600 ml-2">{validationResults.summary.invalid_operations}</span>
                </div>
                <div>
                  <span className="font-medium">Changes:</span> 
                  <span className="ml-2">
                    +{validationResults.summary.estimated_changes.slots_added} / 
                    -{validationResults.summary.estimated_changes.slots_removed}
                  </span>
                </div>
              </div>
            </div>

            {/* Warnings */}
            {validationResults.warnings.length > 0 && (
              <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded">
                <p className="font-medium text-yellow-800 mb-1">Warnings:</p>
                <ul className="list-disc list-inside text-sm text-yellow-700">
                  {validationResults.warnings.map((warning, idx) => (
                    <li key={idx}>{warning}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Conflict Details */}
            {validationResults.summary.invalid_operations > 0 && (
              <div className="mb-4">
                <h4 className="font-medium mb-2 text-red-600">Conflicts:</h4>
                <div className="space-y-2">
                  {validationResults.details
                    .filter(d => d.reason && !d.reason.includes('Valid'))
                    .map((detail, idx) => (
                      <div key={idx} className="p-3 bg-red-50 border border-red-200 rounded text-sm">
                        <div className="font-medium">
                          {detail.action === 'add' ? '+ Add' : detail.action === 'remove' ? '- Remove' : '↻ Update'} 
                          {detail.date && ` on ${new Date(detail.date).toLocaleDateString()}`}
                          {detail.start_time && detail.end_time && ` ${detail.start_time} - ${detail.end_time}`}
                        </div>
                        <div className="text-red-600 mt-1">{detail.reason}</div>
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* Valid Operations */}
            <div className="mb-4">
              <h4 className="font-medium mb-2 text-green-600">Valid Operations:</h4>
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {validationResults.details
                  .filter(d => d.reason && d.reason.includes('Valid'))
                  .map((detail, idx) => (
                    <div key={idx} className="p-2 bg-green-50 rounded text-sm">
                      {detail.action === 'add' ? '+ Add' : detail.action === 'remove' ? '- Remove' : '↻ Update'}
                      {detail.date && ` on ${new Date(detail.date).toLocaleDateString()}`}
                      {detail.start_time && detail.end_time && ` ${detail.start_time} - ${detail.end_time}`}
                    </div>
                  ))}
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-3 justify-end mt-6">
              <button
                onClick={() => {
                  setShowValidationPreview(false);
                  setValidationResults(null);
                }}
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg"
              >
                Cancel
              </button>
              {validationResults.valid && (
                <button
                  onClick={() => {
                    setShowValidationPreview(false);
                    saveWeekSchedule(true); // Skip validation since we already did it
                  }}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
                >
                  Confirm Save
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Booking Preview Modal */}
      {showBookingPreview && selectedBookingId && (
        <BookingQuickPreview
          bookingId={selectedBookingId}
          onClose={() => {
            setShowBookingPreview(false);
            setSelectedBookingId(null);
          }}
          onViewFullDetails={() => {
            router.push(`/dashboard/instructor/bookings/${selectedBookingId}`);
          }}
        />
      )}
    </div>
  );
}