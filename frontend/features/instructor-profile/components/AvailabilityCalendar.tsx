import { useState, useEffect } from 'react';
import { Calendar, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useInstructorAvailability } from '../hooks/useInstructorAvailability';
import { format, addDays } from 'date-fns';
import { logger } from '@/lib/logger';

interface AvailabilityCalendarProps {
  instructorId: string;
  onSelectSlot?: (date: string, time: string) => void;
}

export function AvailabilityCalendar({ instructorId, onSelectSlot }: AvailabilityCalendarProps) {
  // Initialize with null to avoid hydration mismatch
  const [weekStart, setWeekStart] = useState<Date | null>(null);

  // Set the date on client side only - use current week starting from today
  useEffect(() => {
    setWeekStart(new Date());
  }, []);

  const { data, isLoading, error } = useInstructorAvailability(
    instructorId.toString(),
    weekStart ? format(weekStart, 'yyyy-MM-dd') : undefined
  );

  // Show loading state while weekStart is being initialized or data is loading
  if (!weekStart || isLoading) {
    return (
      <Card className="p-4">
        <div className="space-y-3">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="flex justify-between items-center">
              <Skeleton className="h-4 w-20" />
              <div className="flex gap-2">
                <Skeleton className="h-8 w-16" />
                <Skeleton className="h-8 w-16" />
                <Skeleton className="h-8 w-16" />
              </div>
            </div>
          ))}
        </div>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card className="p-4">
        <div className="text-center py-4">
          <p className="text-muted-foreground">Unable to load availability</p>
          <Button
            variant="outline"
            size="sm"
            className="mt-2"
            onClick={() => window.location.reload()}
          >
            Try Again
          </Button>
        </div>
      </Card>
    );
  }

  // Generate week days (only if weekStart is available)
  const weekDays = weekStart ? Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)) : [];

  return (
    <Card className="p-4">
      <div className="space-y-3">
        {weekDays.map((day) => {
          const dateStr = format(day, 'yyyy-MM-dd');
          const dayData = data.availability_by_date?.[dateStr];
          const availableSlots = dayData?.available_slots || [];
          const isBlackout = dayData?.is_blackout || false;

          return (
            <div key={dateStr} className="flex justify-between items-center py-2">
              <div>
                <div className="font-medium">{format(day, 'EEE d')}</div>
                <div className="text-xs text-muted-foreground">{format(day, 'MMM')}</div>
              </div>

              {!isBlackout && availableSlots.length > 0 ? (
                <div className="flex gap-1 flex-wrap justify-end">
                  {availableSlots.slice(0, 3).map((slot, idx) => (
                    <Button
                      key={idx}
                      variant="outline"
                      size="sm"
                      className="text-xs"
                      aria-label={`Select ${dateStr} at ${slot.start_time}`}
                      data-testid={`time-slot-${dateStr}-${slot.start_time}`}
                      onClick={() => {
                        if (onSelectSlot) {
                          onSelectSlot(dateStr, slot.start_time);
                        }
                      }}
                    >
                      {format(new Date(`2000-01-01T${slot.start_time}`), 'ha')}
                    </Button>
                  ))}
                  {availableSlots.length > 3 && (
                    <span className="text-xs text-muted-foreground self-center">
                      +{availableSlots.length - 3}
                    </span>
                  )}
                </div>
              ) : (
                <span className="text-sm text-muted-foreground">
                  {isBlackout ? 'Unavailable' : 'Fully Booked'}
                </span>
              )}
            </div>
          );
        })}
      </div>

      <Button
        variant="ghost"
        className="w-full mt-4 justify-between"
        onClick={() => {
          // TODO: Open full calendar view
          logger.info('View full calendar clicked');
        }}
      >
        <span className="flex items-center gap-2">
          <Calendar className="h-4 w-4" />
          View Full Calendar
        </span>
        <ChevronRight className="h-4 w-4" />
      </Button>
    </Card>
  );
}
