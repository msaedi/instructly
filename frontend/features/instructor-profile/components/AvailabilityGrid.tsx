import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ChevronLeft, ChevronRight, ChevronUp, ChevronDown } from 'lucide-react';
import { format, addDays, startOfWeek, addWeeks } from 'date-fns';
import { useInstructorAvailability } from '../hooks/useInstructorAvailability';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { logger } from '@/lib/logger';
import { useRef, useEffect, useState, useMemo } from 'react';

// Constants moved outside component to avoid recreation on each render
const ALL_TIME_SLOTS = [
  '6am', '7am', '8am', '9am', '10am', '11am',
  '12pm', '1pm', '2pm', '3pm', '4pm', '5pm',
  '6pm', '7pm', '8pm', '9pm', '10pm', '11pm'
];

const mockAvailability: Record<string, string[]> = {
  'Mon': ['8am', '9am', '10am', '2pm', '5pm'],
  'Tue': ['6am', '8am', '11am', '5pm'],
  'Wed': ['8am', '9am', '5pm'],
  'Thu': ['10am', '2pm'],
  'Fri': ['9am', '2pm', '5pm'],
  'Sat': [],
  'Sun': []
};

interface AvailabilityGridProps {
  instructorId: string;
  weekStart: Date | null;
  onWeekChange: (date: Date) => void;
  selectedSlot: { date: string; time: string; duration: number; availableDuration?: number } | null;
  onSelectSlot: (date: string, time: string, duration?: number, availableDuration?: number) => void;
  hideDuration?: boolean;
  minAdvanceBookingHours?: number; // Optional prop for minimum advance booking
}

export function AvailabilityGrid({
  instructorId,
  weekStart,
  onWeekChange,
  selectedSlot,
  onSelectSlot,
  minAdvanceBookingHours = 1, // Default to 1 hour if not provided
}: AvailabilityGridProps) {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [showScrollUp, setShowScrollUp] = useState(false);
  const [showScrollDown, setShowScrollDown] = useState(false);
  const VISIBLE_ROWS = 6;
  const { data, isLoading, error } = useInstructorAvailability(
    instructorId.toString(),
    weekStart ? format(weekStart, 'yyyy-MM-dd') : undefined
  );

  // Use rolling 7-day window starting from today
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  // If weekStart is not provided, use today as the start
  const actualStartDate = weekStart || today;

  // Generate 7 consecutive days starting from actualStartDate
  const weekDays = Array.from({ length: 7 }, (_, i) => addDays(actualStartDate, i));
  const weekLabel = `${format(weekDays[0], 'MMM d')} - ${format(weekDays[6], 'MMM d')}`;

  // Mock data fallback
  const useMockData = error || (!isLoading && !data?.availability_by_date);

  if (useMockData) {
    logger.info('Using mock availability data', { reason: error ? 'error' : 'no data' });
  }

  // Normalize time strings to HH:00 for consistent comparison
  const toTwentyFourHour = (label: string): string => {
    if (/^\d{2}:\d{2}$/.test(label)) return label; // already HH:MM
    const match = label.match(/(\d+)(am|pm)/i);
    if (!match) return label;
    let hour = parseInt(match[1]);
    const isPm = match[2].toLowerCase() === 'pm';
    if (isPm && hour !== 12) hour += 12;
    if (!isPm && hour === 12) hour = 0;
    return `${hour.toString().padStart(2, '0')}:00`;
  };

  // Calculate available duration from a selected time slot
  const calculateAvailableDuration = (dateStr: string, startTime: string): number => {
    if (useMockData) {
      // For mock data, just return 120 minutes as default
      return 120;
    }

    const dayData = data?.availability_by_date?.[dateStr];
    if (!dayData?.available_slots) return 60;

    // Parse the start hour from the time string (format: "HH:00")
    const startHour = parseInt(startTime.split(':')[0]);

    // Find the slot that contains this start time
    const containingSlot = dayData.available_slots.find((slot: any) => {
      const slotStart = parseInt(slot.start_time.split(':')[0]);
      const slotEnd = parseInt(slot.end_time.split(':')[0]);
      return startHour >= slotStart && startHour < slotEnd;
    });

    if (!containingSlot) return 60;

    // Calculate how many minutes are available from the start time to the end of the slot
    const slotEndHour = parseInt(containingSlot.end_time.split(':')[0]);
    const availableHours = slotEndHour - startHour;
    return availableHours * 60;
  };

  // Update scroll indicators
  const updateScrollIndicators = () => {
    if (!scrollContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
    setShowScrollUp(scrollTop > 5);
    setShowScrollDown(scrollTop + clientHeight < scrollHeight - 5);
  };

  // Calculate which slots are actually used
  const activeTimeSlots = useMemo(() => {
    const slotsWithData = new Set<string>();

    if (useMockData) {
      Object.values(mockAvailability).forEach(times => {
        times.forEach(time => slotsWithData.add(time));
      });
    } else if (data?.availability_by_date) {
      Object.values(data.availability_by_date).forEach((dayData: any) => {
        if (dayData.available_slots) {
          dayData.available_slots.forEach((slot: any) => {
            const startHour = parseInt(slot.start_time.split(':')[0]);
            const endHour = parseInt(slot.end_time.split(':')[0]);

            // Add all hours from start to end (exclusive)
            for (let hour = startHour; hour < endHour; hour++) {
              const timeLabel = hour === 0 ? '12am' : hour < 12 ? `${hour}am` : hour === 12 ? '12pm' : `${hour - 12}pm`;
              slotsWithData.add(timeLabel);
            }
          });
        }
      });
    }

    // Filter to only show times that have at least one slot
    return ALL_TIME_SLOTS.filter(time => {
      // Always show times from 8am to 6pm as the core hours
      const coreHours = ['8am', '9am', '10am', '11am', '12pm', '1pm', '2pm', '3pm', '4pm', '5pm', '6pm'];
      return coreHours.includes(time) || slotsWithData.has(time);
    });
  }, [data, useMockData]);

  // Auto-scroll to the most relevant time on mount
  useEffect(() => {
    if (!scrollContainerRef.current || activeTimeSlots.length === 0) return;

    const currentHour = new Date().getHours();
    const currentTimeLabel = currentHour === 0 ? '12am' : currentHour < 12 ? `${currentHour}am` : currentHour === 12 ? '12pm' : `${currentHour - 12}pm`;

    // Find the index of current time or nearest future time
    let targetIndex = activeTimeSlots.findIndex(time => time === currentTimeLabel);
    if (targetIndex === -1) {
      // Find the first time slot after current time
      targetIndex = activeTimeSlots.findIndex(time => {
        const slotHour = time.includes('pm') && time !== '12pm' ? parseInt(time) + 12 : parseInt(time);
        return slotHour >= currentHour;
      });
    }

    // If no future slots or very late, show the first available slot
    if (targetIndex === -1) targetIndex = 0;

    // Center the target time in the viewport (if possible)
    const rowHeight = 40; // Approximate height of each row
    const idealScroll = Math.max(0, (targetIndex - Math.floor(VISIBLE_ROWS / 2)) * rowHeight);
    scrollContainerRef.current.scrollTop = idealScroll;

    // Update indicators after scroll
    setTimeout(updateScrollIndicators, 100);
  }, [activeTimeSlots]);

  // Align the visible week to the earliest available date if current range has no data
  useEffect(() => {
    if (!onWeekChange || !data?.availability_by_date) return;
    const availableDates = Object.keys(data.availability_by_date);
    if (availableDates.length === 0) return;

    const hasAnyInRange = weekDays.some((d) => {
      const key = format(d, 'yyyy-MM-dd');
      return Boolean((data as any).availability_by_date?.[key]);
    });

    if (!hasAnyInRange) {
      const earliest = availableDates.sort()[0];
      const [y, m, d] = earliest.split('-').map(Number);
      const earliestDate = new Date(y, (m || 1) - 1, d || 1);
      onWeekChange(earliestDate);
    }
  }, [data, onWeekChange, weekDays]);

  // Handle loading and no weekStart cases
  if (!weekStart || isLoading) {
    return (
      <div>
        <h3 className="text-lg font-semibold mb-4 pb-2 border-b -mx-6 px-6">Availability</h3>
        <div className="space-y-3">
          {[0, 1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="space-y-2">
              <Skeleton className="h-4 w-20" />
              <div className="grid grid-cols-4 gap-1">
                {[0, 1, 2, 3].map((j) => (
                  <Skeleton key={j} className="h-8 w-full" />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div>
      <style jsx>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 3px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background-color: rgba(0, 0, 0, 0.2);
          border-radius: 2px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background-color: rgba(0, 0, 0, 0.3);
        }
        /* Hide scrollbar for Firefox */
        .custom-scrollbar {
          scrollbar-width: thin;
          scrollbar-color: rgba(0, 0, 0, 0.2) transparent;
        }
      `}</style>
      <h3 className="text-lg font-semibold mb-4 pb-2 border-b -mx-6 px-6">Availability</h3>

      {/* Week Navigation - Rolling 7-day window */}
      <div className="flex items-center justify-between mb-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            // Move back 7 days
            const prevWeekStart = addDays(actualStartDate, -7);
            // Only allow if the end of that week isn't entirely in the past
            const prevWeekEnd = addDays(prevWeekStart, 6);
            if (prevWeekEnd >= today) {
              onWeekChange(prevWeekStart);
            }
          }}
          disabled={(() => {
            // Can't go back if we're already showing today
            return actualStartDate <= today;
          })()}
          className="h-8 px-2 flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <ChevronLeft className="h-4 w-4" />
          <span className="text-sm">Prev</span>
        </Button>
        <span className="text-sm font-medium">{weekLabel}</span>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onWeekChange(addDays(actualStartDate, 7))}
          className="h-8 px-2 flex items-center gap-1"
        >
          <span className="text-sm">Next</span>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>

      {/* Calendar Grid with Scroll */}
      <div className="border rounded-lg overflow-hidden relative">
        {/* Scroll indicator - top */}
        {showScrollUp && (
          <div className="absolute top-12 left-0 right-0 h-8 bg-white border border-gray-200 border-t-0 rounded-b z-20 flex items-center justify-center shadow-sm">
            <div className="flex items-center gap-2 text-sm font-medium text-gray-900">
              <ChevronUp className="h-4 w-4 text-gray-600" />
              <span>Earlier times available</span>
            </div>
          </div>
        )}

        <div
          ref={scrollContainerRef}
          className="overflow-y-auto custom-scrollbar"
          style={{
            maxHeight: `${40 + VISIBLE_ROWS * 40}px`,
            scrollbarWidth: 'thin',
            scrollbarGutter: 'stable'
          }}
          onScroll={updateScrollIndicators}
        >
          <table className="w-full">
            <thead className="sticky top-0 bg-gray-50 z-20">
              <tr className="border-b">
                <th className="text-xs font-medium text-left p-2 w-16 bg-gray-50"></th>
                {weekDays.map((day) => {
                  const today = new Date();
                  today.setHours(0, 0, 0, 0);
                  const isPastDate = day < today;

                  const isToday = format(day, 'yyyy-MM-dd') === format(today, 'yyyy-MM-dd');

                  return (
                    <th key={format(day, 'yyyy-MM-dd')} className={cn(
                      "text-xs font-medium text-center p-2 bg-gray-50",
                      isPastDate && "opacity-50"
                    )}>
                      <div className={isPastDate ? "text-gray-400" : ""}>{format(day, 'EEE')}</div>
                      <div className={cn(
                        "inline-flex items-center justify-center w-6 h-6 rounded-full",
                        isToday && "bg-black text-white font-semibold",
                        !isToday && "text-muted-foreground",
                        isPastDate && "text-gray-300"
                      )}>{format(day, 'd')}</div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {activeTimeSlots.map((time) => (
              <tr key={time} className="border-b">
                <td className="text-xs text-muted-foreground p-2">{time}</td>
                {weekDays.map((day) => {
                  const dateStr = format(day, 'yyyy-MM-dd');
                  const dayName = format(day, 'EEE');

                  let hasSlot = false;
                  let timeStr = '';

                  if (useMockData) {
                    // Use mock data
                    hasSlot = mockAvailability[dayName]?.includes(time) || false;
                    timeStr = time;
                  } else {
                    // Use real data
                    const dayData = data?.availability_by_date?.[dateStr];
                    const availableSlots = dayData?.available_slots || [];
                    const isBlackout = dayData?.is_blackout || false;

                    // Convert display time to 24h format for comparison
                    const hour24 = time.includes('pm') && time !== '12pm'
                      ? parseInt(time) + 12
                      : parseInt(time);
                    const targetHour = hour24.toString().padStart(2, '0');

                    // Check if this hour falls within any available slot range
                    hasSlot = !isBlackout && availableSlots.some(s => {
                      // Parse start and end hours from the slots
                      const startHour = parseInt(s.start_time.split(':')[0]);
                      const endHour = parseInt(s.end_time.split(':')[0]);
                      const checkHour = parseInt(targetHour);

                      // Check if the current hour is within the slot range (inclusive of start, exclusive of end)
                      return checkHour >= startHour && checkHour < endHour;
                    });

                    // For selection purposes, use the hour in HH:00 format
                    timeStr = `${targetHour}:00`;
                  }

                  // Check if this slot is bookable
                  const now = new Date();
                  const timeForCheck = useMockData ? time : timeStr;

                  // Parse the hour correctly
                  let hour: number;
                  if (useMockData) {
                    // Handle format like "5pm" or "10am"
                    hour = time.includes('pm') && time !== '12pm'
                      ? parseInt(time) + 12
                      : parseInt(time);
                  } else {
                    // Handle format like "17:00"
                    hour = parseInt(timeForCheck.split(':')[0]);
                  }

                  // Create date from the string properly - dateStr is like "2025-08-04"
                  const [year, month, dayNum] = dateStr.split('-').map(Number);
                  const slotDateTime = new Date(year, month - 1, dayNum, hour, 0, 0);

                  const isPastDate = slotDateTime <= now;

                  // Check minimum advance booking time
                  const hoursUntilSlot = (slotDateTime.getTime() - now.getTime()) / (1000 * 60 * 60);
                  const isTooSoon = hoursUntilSlot < minAdvanceBookingHours;
                  const isBookable = !isPastDate && !isTooSoon;

                  const candidateTime = useMockData ? time : timeStr;
                  const isSelected = selectedSlot?.date === dateStr &&
                    toTwentyFourHour(selectedSlot?.time || '') === toTwentyFourHour(candidateTime);

                  return (
                    <td key={`${dateStr}-${time}`} className="p-1 text-center align-middle">
                      {hasSlot && isBookable ? (
                        <button
                          className={cn(
                            "w-8 h-8 rounded border text-xs transition-all relative",
                            isSelected
                              ? "bg-transparent border-black"
                              : "border-gray-300 hover:border-gray-400"
                          )}
                          onClick={() => {
                            const slotTime = useMockData ? time : timeStr;
                            const availableDuration = calculateAvailableDuration(dateStr, slotTime);
                            onSelectSlot(dateStr, slotTime, 60, availableDuration);
                          }}
                          aria-label={`Select ${dayName} at ${time}`}
                          data-testid={`time-slot-${dayName}-${time}`}
                          data-available="true"
                          data-date={dateStr}
                          data-time={useMockData ? time : timeStr}
                        >
                          {isSelected && (
                            <span className="absolute inset-0 flex items-center justify-center">
                              <span className="w-3 h-3 bg-black rounded-full"></span>
                            </span>
                          )}
                        </button>
                      ) : (
                        <span className="text-xs text-muted-foreground">-</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
            </tbody>
          </table>
        </div>

        {/* Scroll indicator - bottom */}
        {showScrollDown && (
          <div className="absolute bottom-10 left-0 right-0 h-8 bg-white border border-gray-200 border-b-0 rounded-t z-20 flex items-center justify-center shadow-sm">
            <div className="flex items-center gap-2 text-sm font-medium text-gray-900">
              <span>Later times available</span>
              <ChevronDown className="h-4 w-4 text-gray-600" />
            </div>
          </div>
        )}

        <div className="p-3 border-t bg-gray-50">
          <div className="flex items-center justify-center gap-6 text-sm">
            <span className="flex items-center gap-2">
              <span className="w-6 h-6 border border-gray-300 rounded bg-gray-50 inline-block"></span>
              <span className="text-gray-700">Available</span>
            </span>
            <span className="flex items-center gap-2">
              <span className="w-6 h-6 border border-gray-300 rounded bg-transparent inline-flex items-center justify-center relative">
                <span className="w-3 h-3 bg-black rounded-full"></span>
              </span>
              <span className="text-gray-700">Selected</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
