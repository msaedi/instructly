// frontend/components/calendar/WeekView.tsx

import { useCallback, useMemo } from 'react';
import type { WeekSchedule, WeekDateInfo } from '@/types/availability';
import type { BookedSlotPreview } from '@/types/booking';
import InteractiveGrid from '@/components/availability/InteractiveGrid';
import { normalizeSchedule } from '@/lib/calendar/normalize';

interface WeekViewProps {
  weekDates: WeekDateInfo[];
  schedule: WeekSchedule;
  bookedSlots?: BookedSlotPreview[];
  onScheduleChange: (schedule: WeekSchedule) => void;
  startHour?: number;
  endHour?: number;
  timezone?: string;
  isMobile?: boolean;
  activeDayIndex?: number;
  onActiveDayChange?: (index: number) => void;
}

function schedulesEqual(a: WeekSchedule, b: WeekSchedule): boolean {
  const aKeys = Object.keys(a);
  const bKeys = Object.keys(b);
  if (aKeys.length !== bKeys.length) return false;
  for (const key of aKeys) {
    const aSlots = a[key] || [];
    const bSlots = b[key] || [];
    if (aSlots.length !== bSlots.length) return false;
    for (let i = 0; i < aSlots.length; i += 1) {
      const aSlot = aSlots[i];
      const bSlot = bSlots[i];
      if (
        !aSlot ||
        !bSlot ||
        aSlot.start_time !== bSlot.start_time ||
        aSlot.end_time !== bSlot.end_time
      ) {
        return false;
      }
    }
  }
  return true;
}

const WeekView = ({
  weekDates,
  schedule,
  bookedSlots,
  onScheduleChange,
  startHour,
  endHour,
  timezone,
  isMobile,
  activeDayIndex,
  onActiveDayChange,
}: WeekViewProps) => {
  const normalizedSchedule = useMemo(() => {
    const normalized = normalizeSchedule(schedule, timezone);
    return schedulesEqual(normalized, schedule) ? schedule : normalized;
  }, [schedule, timezone]);

  const handleScheduleChange = useCallback(
    (next: WeekSchedule) => {
      const normalized = normalizeSchedule(next, timezone);
      onScheduleChange(schedulesEqual(normalized, next) ? next : normalized);
    },
    [onScheduleChange, timezone]
  );

  return (
    <InteractiveGrid
      weekDates={weekDates}
      weekSchedule={normalizedSchedule}
      {...(bookedSlots ? { bookedSlots } : {})}
      {...(startHour !== undefined ? { startHour } : {})}
      {...(endHour !== undefined ? { endHour } : {})}
      {...(timezone ? { timezone } : {})}
      {...(isMobile !== undefined ? { isMobile } : {})}
      {...(activeDayIndex !== undefined ? { activeDayIndex } : {})}
      {...(onActiveDayChange ? { onActiveDayChange } : {})}
      onScheduleChange={handleScheduleChange}
    />
  );
};

export default WeekView;
