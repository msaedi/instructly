import { BRAND } from '@/app/config/brand'
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
const HOURS = Array.from({ length: 13 }, (_, i) => i + 8); // 8 AM to 8 PM

export default function AvailabilityPage() {
  const [currentWeekStart, setCurrentWeekStart] = useState<Date>(new Date());
  const [weekSchedule, setWeekSchedule] = useState<WeekSchedule>({});
  const [savedWeekSchedule, setSavedWeekSchedule] = useState<WeekSchedule>({});
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error' | 'info', text: string } | null>(null);
  const [showApplyModal, setShowApplyModal] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [applyUntilDate, setApplyUntilDate] = useState<string>('');
  const [applyUntilOption, setApplyUntilOption] = useState<'date' | 'end-of-year' | 'indefinitely'>('end-of-year');
  const [bookedSlots, setBookedSlots] = useState<BookedSlot[]>([]);
  const [existingSlots, setExistingSlots] = useState<ExistingSlot[]>([]);
  const [showValidationPreview, setShowValidationPreview] = useState(false);
  const [validationResults, setValidationResults] = useState<WeekValidationResponse | null>(null);
  const [pendingOperations, setPendingOperations] = useState<SlotOperation[]>([]);
  const [isValidating, setIsValidating] = useState(false);
  const [selectedBookingId, setSelectedBookingId] = useState<number | null>(null);
  const [showBookingPreview, setShowBookingPreview] = useState(false);
  const [previewPosition, setPreviewPosition] = useState<{ top: number; left: number } | null>(null);
  const router = useRouter();

  // Define presets once at the component level
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

  const fetchBookedSlots = async () => {
    try {
      const response = await fetchWithAuth(
        `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK}/booked-slots?start_date=${formatDateForAPI(currentWeekStart)}`
      );
      if (response.ok) {
        const data = await response.json();
        console.log('Booked slots data:', data);
        setBookedSlots(data.booked_slots || []);
      }
    } catch (error) {
      console.error('Failed to fetch booked slots:', error);
    }
  };

  useEffect(() => {
    console.log('Preview state changed:', { showBookingPreview, selectedBookingId });
  }, [showBookingPreview, selectedBookingId]);

  useEffect(() => {
    setWeekSchedule({});
    setSavedWeekSchedule({});
    setExistingSlots([]); 
    setHasUnsavedChanges(false);
    fetchWeekSchedule();
    fetchBookedSlots();
  }, [currentWeekStart]);

  const isSlotBooked = (date: string, hour: number): boolean => {
    return bookedSlots.some(slot => {
      if (slot.date !== date) return false;
      const slotStartHour = parseInt(slot.start_time.split(':')[0]);
      const slotEndHour = parseInt(slot.end_time.split(':')[0]);
      return hour >= slotStartHour && hour < slotEndHour;
    });
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

  // Fetch schedule when week changes
  useEffect(() => {
    // Clear the schedule when week changes to prevent old data from persisting
    setWeekSchedule({});
    setHasUnsavedChanges(false);
    // Fetch the new week's data
    fetchWeekSchedule();
  }, [currentWeekStart]);

  // Helper to check if this is the first hour of a multi-hour booking
  const isFirstHourOfBooking = (date: string, hour: number): BookedSlotPreview | null => {
    const booking = bookedSlots.find(slot => {
      if (slot.date !== date) return false;
      const slotStartHour = parseInt(slot.start_time.split(':')[0]);
      return slotStartHour === hour;
    });
    return booking || null;
  };

  // Helper to find the booking for a given slot
  const getBookingForSlot = (date: string, hour: number): BookedSlotPreview | null => {
    return bookedSlots.find(slot => {
      if (slot.date !== date) return false;
      const slotStartHour = parseInt(slot.start_time.split(':')[0]);
      const slotEndHour = parseInt(slot.end_time.split(':')[0]);
      return hour >= slotStartHour && hour < slotEndHour;
    }) || null;
  };

  const handleBookedSlotClick = (bookingId: number, event?: React.MouseEvent) => {
    console.log('Clicked booking:', bookingId);
    setSelectedBookingId(bookingId);
    
    // For desktop, calculate popover position
    if (event && !isMobile()) {
      const rect = event.currentTarget.getBoundingClientRect();
      const scrollTop = window.scrollY || document.documentElement.scrollTop;
      const position = {
        top: rect.bottom + scrollTop + 5,
        left: rect.left + (rect.width / 2)
      };
      console.log('Setting position:', position);
      setPreviewPosition(position);
    }
    console.log('Setting showBookingPreview to true');
    setShowBookingPreview(true);
  };
  
  // Add this helper function to detect mobile
  const isMobile = () => {
    return window.innerWidth < 768; // md breakpoint
  };

  // Get week dates
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

  const isTimeSlotInPast = (dateStr: string, hour: number): boolean => {
    // Parse the date string as local time, not UTC
    const [year, month, day] = dateStr.split('-').map(num => parseInt(num));
    const slotDateTime = new Date(year, month - 1, day, hour, 0, 0, 0);
    const now = new Date();
    return slotDateTime < now;
  };

  const isDateInPast = (dateStr: string): boolean => {
    const date = new Date(dateStr);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    date.setHours(0, 0, 0, 0);
    return date < today;
  };

  // Format date for API (YYYY-MM-DD)
  const formatDateForAPI = (date: Date): string => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  const fetchWeekSchedule = async () => {
    setIsLoading(true);
    try {
      const mondayDate = formatDateForAPI(currentWeekStart);
      const endDate = formatDateForAPI(new Date(currentWeekStart.getTime() + 6 * 24 * 60 * 60 * 1000));
      console.log('Fetching detailed slots:', mondayDate, 'to', endDate);
      
      // First get the detailed slots with IDs
      const detailedResponse = await fetchWithAuth(
        `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY}?start_date=${mondayDate}&end_date=${endDate}`
      );
      
      if (detailedResponse.ok) {
        const detailedData = await detailedResponse.json();
        console.log('Detailed slots data:', detailedData);
  
        const slots: ExistingSlot[] = detailedData.map((slot: any) => ({
          id: slot.id,
          date: slot.specific_date,
          start_time: slot.start_time,
          end_time: slot.end_time
        }));
        setExistingSlots(slots);
        console.log('Mapped existing slots:', slots);
      } else {
        // Log error details
        const errorData = await detailedResponse.text();
        console.error('Failed to fetch detailed slots:', detailedResponse.status, errorData);
      }
      
      // Fetch booked slots BEFORE getting the week view
      const bookedResponse = await fetchWithAuth(
        `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK}/booked-slots?start_date=${mondayDate}`
      );
      
      if (bookedResponse.ok) {
        const bookedData = await bookedResponse.json();
        console.log('Booked slots data:', bookedData);
        setBookedSlots(bookedData.booked_slots || []);
      }
      
      // Then get the week view for display
      const response = await fetchWithAuth(
        `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK}?start_date=${mondayDate}`
      );
      
      if (!response.ok) throw new Error('Failed to fetch availability');
      const data = await response.json();
  
      console.log('Fetched week data:', data);
      console.log('Existing slots after fetch:', existingSlots);
      console.log('Data keys:', Object.keys(data));
      
      // DO NOT MERGE SLOTS - keep them as they come from the backend
      // The backend already handles merging appropriately
      const cleanedData: WeekSchedule = {};
      Object.entries(data).forEach(([date, slots]) => {
        if (Array.isArray(slots) && slots.length > 0) {
          // Simply use the slots as provided by the backend
          cleanedData[date] = slots as TimeSlot[];
        }
      });
  
      console.log('=== FETCH COMPLETE ===');
      console.log('Setting both states to:', JSON.stringify(cleanedData, null, 2));
      
      setWeekSchedule(cleanedData);
      setSavedWeekSchedule(cleanedData);
      setHasUnsavedChanges(false);
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to load availability. Please try again.' });
    } finally {
      setIsLoading(false);
    }
  };

  // Navigate weeks
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

  // Check if a time slot is within an availability range for a specific date
  const isHourInTimeRange = (date: string, hour: number): boolean => {
    const daySlots = weekSchedule[date] || [];
    return daySlots.some(range => {
      const startHour = parseInt(range.start_time.split(':')[0]);
      const endHour = parseInt(range.end_time.split(':')[0]);
      return hour >= startHour && hour < endHour && range.is_available;
    });
  };

  // Toggle time slot for a specific date
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
          
          // Only merge if:
          // 1. Slots are adjacent (no gap)
          // 2. There's no booking between them
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

  // Clear week confirmation
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

  // Apply preset to current week only
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
      console.error('Preset error:', error);
      setMessage({ type: 'error', text: `Failed to apply preset: ${error instanceof Error ? error.message : 'Unknown error'}` });
    }
  };

  // Save schedule for this week
  const saveWeekSchedule = async (skipValidation = false) => {
    setIsSaving(true);
      // If not skipping validation, validate first
      if (!skipValidation && hasUnsavedChanges) {
        setIsValidating(true);
        console.log('Starting validation...');
        try {
          const validation = await validateWeekChanges(
            weekSchedule,
            savedWeekSchedule,
            currentWeekStart
          );
          
          setValidationResults(validation);
          console.log('Validation results:', validation);
          setIsValidating(false);
          
          // If there are conflicts, show preview modal
          if (!validation.valid) {
            setShowValidationPreview(true);
            setIsSaving(false);
            return;
          }
          
          // If valid but has warnings, optionally show them
          if (validation.warnings.length > 0) {
            setMessage({
              type: 'info',
              text: `Note: ${validation.warnings.join('. ')}`
            });
          }
        } catch (error) {
          setIsValidating(false);
          setIsSaving(false);
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
      } else {
        console.log('=== SAVE OPERATION START ===');
        console.log('Current weekSchedule:', JSON.stringify(weekSchedule, null, 2));
        console.log('Current savedWeekSchedule:', JSON.stringify(savedWeekSchedule, null, 2));
        // First, fetch current existing slots to ensure we have the latest IDs
        const mondayDate = formatDateForAPI(currentWeekStart);
        const endDate = formatDateForAPI(new Date(currentWeekStart.getTime() + 6 * 24 * 60 * 60 * 1000));

        console.log('Fetching slots with date range:', mondayDate, 'to', endDate);

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
          console.log('Fetched existing slots:', JSON.stringify(currentExistingSlots, null, 2));
        } else {
          // Log the error details
          const errorData = await detailedResponse.text();
          console.error('Failed to fetch existing slots:', detailedResponse.status, errorData);
          // Don't fail the entire operation, just continue without slot IDs
          console.warn('Continuing without existing slot IDs - remove operations may not work');
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

          console.log(`Comparing ${dateStr}: current=${currentSlots.length}, saved=${savedSlots.length}`);
          
          // Skip past dates (but include today)
          if (dateInfo.fullDate !== today.toISOString().split('T')[0] && new Date(dateStr) < today) {
            console.log(`Skipping past date: ${dateStr}`);
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
              console.log('Looking for slot to remove:', dateStr, savedSlot);
              console.log('Available existing slots:', currentExistingSlots);
              
              // Debug: Show all slots for this date
              const slotsForDate = currentExistingSlots.filter(s => s.date === dateStr);
              console.log('All slots for this date:', slotsForDate);
              
              const existingSlot = currentExistingSlots.find(s => 
                s.date === dateStr &&
                s.start_time === savedSlot.start_time &&
                s.end_time === savedSlot.end_time
              );
              
              if (existingSlot) {
                console.log('Found slot to remove:', existingSlot);
                operations.push({
                  action: 'remove',
                  slot_id: existingSlot.id
                });
              } else {
                console.log('Could not find slot ID for removal');
                
                // Instead of exact match, find overlapping slots
                const overlappingSlots = currentExistingSlots.filter(s => {
                  if (s.date !== dateStr) return false;
                  
                  const slotStart = s.start_time;
                  const slotEnd = s.end_time;
                  const savedStart = savedSlot.start_time;
                  const savedEnd = savedSlot.end_time;
                  
                  // Check if there's any overlap
                  return slotStart < savedEnd && slotEnd > savedStart;
                });
                
                console.log('Overlapping slots found:', overlappingSlots);
                
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
              operations.push({
                action: 'add',
                date: dateStr,
                start_time: currentSlot.start_time,
                end_time: currentSlot.end_time
              });
            }
          });
        });
        
        console.log('Generated operations:', JSON.stringify(operations, null, 2));
        
        if (operations.length === 0) {
          setMessage({ type: 'info', text: 'No changes to save.' });
          setHasUnsavedChanges(false);
          return;
        }
        
        // Store operations for potential reuse
        setPendingOperations(operations);
      }
      
      // If not skipping validation, do the validation first
      if (!skipValidation) {
        const validationRequest: BulkUpdateRequest = {
          operations,
          validate_only: true
        };
        
        const validationResponse = await fetchWithAuth(
          API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_BULK_UPDATE,
          {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(validationRequest)
          }
        );
        
        if (!validationResponse.ok) {
          const error = await validationResponse.json();
          console.error('Validation error details:', error);
          
          // Handle Pydantic validation errors properly
          if (error.detail && Array.isArray(error.detail)) {
            // Pydantic validation errors come as an array
            const errorMessages = error.detail.map((err: any) => 
              `${err.loc?.join(' > ')}: ${err.msg}`
            ).join(', ');
            throw new Error(errorMessages);
          } else if (error.detail) {
            throw new Error(error.detail);
          } else {
            throw new Error('Validation failed');
          }
        }
        
        const validationResult: BulkUpdateResponse = await validationResponse.json();
        
        // Check if any operations would fail
        if (validationResult.failed > 0) {
          const failedOps = validationResult.results.filter(r => r.status === 'failed');
          const reasons = failedOps.map(op => op.reason).filter(Boolean).join(', ');
          
          setMessage({
            type: 'error',
            text: `Cannot save changes: ${reasons}`
          });
          return;
        }
        
        // Optional: Show preview modal (uncomment if you want to use it)
        // setValidationResults(validationResult);
        // setShowValidationPreview(true);
        // return;
      }
      
      // Apply the changes
      const applyRequest: BulkUpdateRequest = {
        operations,
        validate_only: false
      };
      
      const response = await fetchWithAuth(
        API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_BULK_UPDATE,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(applyRequest)
        });
      
      if (!response.ok) {
        const error = await response.json();
        console.error('Apply error details:', error);
        
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
      
      // Show detailed results
      if (result.successful === operations.length) {
        setMessage({ 
          type: 'success', 
          text: result.successful === 1 
            ? 'Successfully saved the change!' 
            : `Successfully saved all ${result.successful} changes!` 
        });
      } else if (result.successful > 0) {
        // Some succeeded, some failed - use 'info' instead of 'warning'
        const changeText = result.successful === 1 ? 'change' : 'changes';
        const failedText = result.failed === 1 ? 'failed' : 'failed';
        const skippedText = result.skipped === 1 ? 'skipped' : 'skipped';
        
        setMessage({ 
          type: 'info', 
          text: `Saved ${result.successful} ${changeText}. ${result.failed} ${failedText}, ${result.skipped} ${skippedText}.` 
        });
      } else {
        // All failed
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
      console.error('Save error:', error);
      setMessage({ 
        type: 'error', 
        text: error instanceof Error ? error.message : 'Failed to save schedule. Please try again.' 
      });
    } finally {
      setIsSaving(false);
      setPendingOperations([]); // Clear pending operations
    }
  };


// Copy from previous week
const copyFromPreviousWeek = async () => {
  setIsSaving(true);
  try {
    const previousWeek = new Date(currentWeekStart);
    previousWeek.setDate(previousWeek.getDate() - 7);
    
    console.log('Current week start:', currentWeekStart);
    console.log('Previous week start:', previousWeek);
    
    const response = await fetchWithAuth(
      `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK}?start_date=${formatDateForAPI(previousWeek)}`
    );
    
    if (!response.ok) throw new Error('Failed to fetch previous week');
    const previousWeekData = await response.json();
    
    console.log('Previous week data:', previousWeekData);
    
    // Get current week's booked slots to avoid modifying them
    await fetchBookedSlots(); // Ensure we have the latest booked slots
    
    // Start with the CURRENT week's schedule to preserve booked slots
    const copiedSchedule: WeekSchedule = {};
    const weekDates = getWeekDates();
    
    weekDates.forEach((dateInfo, index) => {
      const currentDateStr = dateInfo.fullDate;
      const prevDate = new Date(previousWeek);
      prevDate.setDate(prevDate.getDate() + index);
      const prevDateStr = formatDateForAPI(prevDate);
      
      console.log(`Mapping ${prevDateStr} to ${currentDateStr}`);
      
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
            // Preserve this slot as it contains bookings
            preservedSlots.push(slot);
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
              // Safe to add this slot from previous week
              preservedSlots.push(prevSlot);
            }
          });
        }
        
        // Sort and merge adjacent slots (but respect booking boundaries)
        copiedSchedule[currentDateStr] = mergeAdjacentSlots(preservedSlots, currentDateStr);
        
      } else {
        // No bookings on this date - safe to copy directly from previous week
        if (previousWeekData[prevDateStr] && previousWeekData[prevDateStr].length > 0) {
          copiedSchedule[currentDateStr] = previousWeekData[prevDateStr];
        } else {
          copiedSchedule[currentDateStr] = [];
        }
      }
    });
    
    console.log('Final copied schedule:', copiedSchedule);
    
    setWeekSchedule(copiedSchedule);
    setHasUnsavedChanges(true);
    setMessage({ type: 'success', text: 'Copied schedule from previous week. Booked time slots were preserved. Remember to save!' });
  } catch (error) {
    setMessage({ type: 'error', text: 'Failed to copy from previous week.' });
  } finally {
    setIsSaving(false);
  }
};

// Helper function to merge adjacent slots while respecting booking boundaries
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

  // Apply to future weeks
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
      <div className="bg-white rounded-lg shadow-lg p-6">
        <div className="mb-4">
          <h3 className="text-lg font-semibold">Week Schedule</h3>
          <p className="text-sm text-gray-600">Click time slots to toggle availability</p>
        </div>

        {/* Desktop Grid */}
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full table-fixed">
            <thead>
              <tr>
                <th className="text-left p-2 text-gray-600 w-24">Time</th>
                {weekDates.map((dateInfo, index) => (
                  <th key={index} className="text-center p-2 text-gray-600 w-32">
                    <div className="font-semibold capitalize">{dateInfo.dayOfWeek}</div>
                    <div className="text-sm font-normal">{dateInfo.dateStr}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
            {HOURS.map(hour => (
                <tr key={hour} className="border-t">
                  <td className="p-2 text-sm text-gray-600 w-24">
                    {hour % 12 || 12}:00 {hour < 12 ? 'AM' : 'PM'}
                  </td>
                  {weekDates.map((dateInfo) => {
                    const isPastSlot = isTimeSlotInPast(dateInfo.fullDate, hour);
                    const isAvailable = isHourInTimeRange(dateInfo.fullDate, hour);
                    const booking = getBookingForSlot(dateInfo.fullDate, hour);
                    const isBooked = !!booking;
                    const isFirstSlot = !!(booking && parseInt(booking.start_time.split(':')[0]) === hour);
                    
                    return (
                      <td key={`${dateInfo.fullDate}-${hour}`} className="p-1 w-32">
                        {isBooked && booking ? (
                          <BookedSlotCell
                            slot={booking}
                            isFirstSlot={isFirstSlot}
                            onClick={(e) => handleBookedSlotClick(booking.booking_id, e)}
                          />
                        ) : (
                          <TimeSlotButton
                            hour={hour}
                            isAvailable={isAvailable}
                            isBooked={isBooked}
                            isPast={isPastSlot}
                            onClick={() => toggleTimeSlot(dateInfo.fullDate, hour)}
                          />
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Mobile List View */}
        <div className="md:hidden space-y-4">
          {weekDates.map((dateInfo, index) => {
            const isPastDate = isDateInPast(dateInfo.fullDate);
            
            return (
              <div key={index} className={`border rounded-lg p-4 ${isPastDate ? 'bg-gray-50' : ''}`}>
                <h3 className="font-semibold capitalize mb-1">{dateInfo.dayOfWeek}</h3>
                <p className="text-sm text-gray-600 mb-3">
                  {dateInfo.dateStr}
                  {isPastDate && <span className="text-gray-500 ml-2">(Past date)</span>}
                </p>
                <div className="grid grid-cols-3 gap-2">
                {HOURS.map(hour => {
                    const isPastSlot = isTimeSlotInPast(dateInfo.fullDate, hour);
                    const isAvailable = isHourInTimeRange(dateInfo.fullDate, hour);
                    const booking = getBookingForSlot(dateInfo.fullDate, hour);
                    const isBooked = !!booking;
                    const isFirstSlot = !!(booking && parseInt(booking.start_time.split(':')[0]) === hour);
                    
                    return isBooked && booking ? (
                      <BookedSlotCell
                        key={`${dateInfo.fullDate}-${hour}`}
                        slot={booking}
                        isFirstSlot={isFirstSlot}
                        isMobile={true}
                        onClick={(e) => handleBookedSlotClick(booking.booking_id, e)}                      />
                    ) : (
                      <TimeSlotButton
                        key={`${dateInfo.fullDate}-${hour}`}
                        hour={hour}
                        isAvailable={isAvailable}
                        isBooked={isBooked}
                        isPast={isPastSlot}
                        onClick={() => toggleTimeSlot(dateInfo.fullDate, hour)}
                        isMobile={true}
                      />
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>

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
              setPreviewPosition(null);
            }}
            onViewFullDetails={() => {
              router.push(`/dashboard/instructor/bookings/${selectedBookingId}`);
            }}
            position={previewPosition || undefined}
            isMobile={isMobile()}
          />
        )}
    </div>
  );
}