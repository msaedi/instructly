// frontend/components/calendar/WeekView.tsx

import type { WeekBits, WeekDateInfo } from '@/types/availability';
import type { BookedSlotPreview } from '@/types/booking';
import InteractiveGrid from '@/components/availability/InteractiveGrid';

interface WeekViewProps {
  weekDates: WeekDateInfo[];
  weekBits: WeekBits;
  onBitsChange: (next: WeekBits | ((prev: WeekBits) => WeekBits)) => void;
  bookedSlots?: BookedSlotPreview[];
  startHour?: number;
  endHour?: number;
  timezone?: string;
  isMobile?: boolean;
  activeDayIndex?: number;
  onActiveDayChange?: (index: number) => void;
  allowPastEditing?: boolean;
}

const WeekView = ({
  weekDates,
  weekBits,
  onBitsChange,
  bookedSlots,
  startHour,
  endHour,
  timezone,
  isMobile,
  activeDayIndex,
  onActiveDayChange,
  allowPastEditing,
}: WeekViewProps) => {
  return (
    <InteractiveGrid
      weekDates={weekDates}
      weekBits={weekBits}
      onBitsChange={onBitsChange}
      {...(bookedSlots ? { bookedSlots } : {})}
      {...(startHour !== undefined ? { startHour } : {})}
      {...(endHour !== undefined ? { endHour } : {})}
      {...(timezone ? { timezone } : {})}
      {...(isMobile !== undefined ? { isMobile } : {})}
      {...(activeDayIndex !== undefined ? { activeDayIndex } : {})}
      {...(onActiveDayChange ? { onActiveDayChange } : {})}
      {...(allowPastEditing !== undefined ? { allowPastEditing } : {})}
    />
  );
};

export default WeekView;
