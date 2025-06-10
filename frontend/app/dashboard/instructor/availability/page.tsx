// app/dashboard/instructor/availability/page.tsx
"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { fetchWithAuth, API_ENDPOINTS } from "@/lib/api";
import { Calendar, Clock, Copy, Save, ChevronLeft, ChevronRight, AlertCircle, Trash2, CalendarDays } from "lucide-react";

type DayOfWeek = 'monday' | 'tuesday' | 'wednesday' | 'thursday' | 'friday' | 'saturday' | 'sunday';

interface TimeSlot {
  start_time: string;
  end_time: string;
  is_available: boolean;
}

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
    fetchWeekSchedule();
  }, [currentWeekStart]);

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
      const response = await fetchWithAuth(
        `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK}?start_date=${mondayDate}`
      );
      
      if (!response.ok) throw new Error('Failed to fetch availability');
      const data = await response.json();

      console.log('Fetched week data:', data);
      console.log('Data keys:', Object.keys(data));
      
      // Clean up duplicate slots by merging overlapping time ranges
      const cleanedData: WeekSchedule = {};
      Object.entries(data).forEach(([date, slots]) => {
        if (Array.isArray(slots) && slots.length > 0) {
          // Sort slots by start time
          const sortedSlots = (slots as TimeSlot[]).sort((a, b) => 
            a.start_time.localeCompare(b.start_time)
          );
          
          // Merge overlapping slots
          const mergedSlots: TimeSlot[] = [];
          sortedSlots.forEach((slot) => {
            if (mergedSlots.length === 0) {
              mergedSlots.push(slot);
            } else {
              const lastSlot = mergedSlots[mergedSlots.length - 1];
              // Check if slots overlap or are adjacent
              if (lastSlot.end_time >= slot.start_time) {
                // Merge slots by extending the end time if needed
                if (slot.end_time > lastSlot.end_time) {
                  lastSlot.end_time = slot.end_time;
                }
              } else {
                mergedSlots.push(slot);
              }
            }
          });
          
          cleanedData[date] = mergedSlots;
        }
      });
      
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
      
      // Merge adjacent slots
      const mergedSlots: TimeSlot[] = [];
      newSlots.forEach((slot, index) => {
        if (index === 0) {
          mergedSlots.push(slot);
        } else {
          const lastSlot = mergedSlots[mergedSlots.length - 1];
          if (lastSlot.end_time === slot.start_time && lastSlot.is_available === slot.is_available) {
            lastSlot.end_time = slot.end_time;
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
    setWeekSchedule({});
    setHasUnsavedChanges(true);
    setMessage({ type: 'info', text: 'Week cleared. Remember to save your changes.' });
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
  const saveWeekSchedule = async () => {
    setIsSaving(true);
    try {
      // Convert schedule to API format
      const scheduleData: any[] = [];
      const weekDates = getWeekDates();
      
      // IMPORTANT: Send ALL days, even empty ones
      weekDates.forEach(dateInfo => {
        const daySlots = weekSchedule[dateInfo.fullDate] || [];
        
        if (daySlots.length > 0) {
          // Day has slots
          daySlots.forEach(slot => {
            scheduleData.push({
              date: dateInfo.fullDate,
              start_time: slot.start_time,
              end_time: slot.end_time,
              is_available: slot.is_available
            });
          });
        }
      });
  
      console.log('Saving schedule:', {
        scheduleLength: scheduleData.length,
        isEmpty: Object.keys(weekSchedule).length === 0,
        scheduleData
      });
  
      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          schedule: scheduleData,
          clear_existing: true,
          week_start: formatDateForAPI(currentWeekStart)
        })
      });
  
      if (!response.ok) throw new Error('Failed to save schedule');
      
      setSavedWeekSchedule(weekSchedule);
      setHasUnsavedChanges(false);
      setMessage({ type: 'success', text: 'Schedule saved for this week.' });
      
      // Refresh to get the saved data
      await fetchWeekSchedule();
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to save schedule. Please try again.' });
    } finally {
      setIsSaving(false);
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
      
      // Start with ALL days having empty arrays
      const copiedSchedule: WeekSchedule = {};
      const weekDates = getWeekDates();
      
      // First, initialize all days with empty arrays
      weekDates.forEach(dateInfo => {
        copiedSchedule[dateInfo.fullDate] = [];
      });
      
      // Then copy actual data where it exists
      weekDates.forEach((dateInfo, index) => {
        const prevDate = new Date(previousWeek);
        prevDate.setDate(prevDate.getDate() + index);
        const prevDateStr = formatDateForAPI(prevDate);
        
        console.log(`Mapping ${prevDateStr} to ${dateInfo.fullDate}`);
        
        if (previousWeekData[prevDateStr] && previousWeekData[prevDateStr].length > 0) {
          // Copy the actual slots
          copiedSchedule[dateInfo.fullDate] = previousWeekData[prevDateStr];
          console.log(`Copied slots from ${prevDateStr} to ${dateInfo.fullDate}`);
        }
        // Days without data remain as empty arrays
      });
      
      console.log('Final copied schedule:', copiedSchedule);
      
      setWeekSchedule(copiedSchedule);
      setHasUnsavedChanges(true);
      setMessage({ type: 'success', text: 'Copied schedule from previous week. Remember to save!' });
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to copy from previous week.' });
    } finally {
      setIsSaving(false);
    }
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
          onClick={saveWeekSchedule}
          disabled={isSaving || !hasUnsavedChanges}
          className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
        >
          <Save className="w-4 h-4" />
          Save This Week
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
                  {weekDates.map((dateInfo) => (
                    <td key={`${dateInfo.fullDate}-${hour}`} className="p-1 w-32">
                      <button
                        onClick={() => toggleTimeSlot(dateInfo.fullDate, hour)}
                        className={`w-full h-10 rounded transition-colors ${
                          isHourInTimeRange(dateInfo.fullDate, hour)
                            ? 'bg-green-500 hover:bg-green-600 text-white'
                            : 'bg-gray-200 hover:bg-gray-300'
                        }`}
                      >
                        {isHourInTimeRange(dateInfo.fullDate, hour) ? '✓' : ''}
                      </button>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Mobile List View */}
        <div className="md:hidden space-y-4">
          {weekDates.map((dateInfo, index) => (
            <div key={index} className="border rounded-lg p-4">
              <h3 className="font-semibold capitalize mb-1">{dateInfo.dayOfWeek}</h3>
              <p className="text-sm text-gray-600 mb-3">{dateInfo.dateStr}</p>
              <div className="grid grid-cols-3 gap-2">
                {HOURS.map(hour => (
                  <button
                    key={`${dateInfo.fullDate}-${hour}`}
                    onClick={() => toggleTimeSlot(dateInfo.fullDate, hour)}
                    className={`p-2 rounded text-sm ${
                      isHourInTimeRange(dateInfo.fullDate, hour)
                        ? 'bg-green-500 text-white'
                        : 'bg-gray-200'
                    }`}
                  >
                    {hour % 12 || 12}:00
                  </button>
                ))}
              </div>
            </div>
          ))}
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
    </div>
  );
}