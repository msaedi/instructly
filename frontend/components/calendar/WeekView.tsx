// frontend/components/calendar/WeekView.tsx

import type { WeekBits, WeekDateInfo, WeekTags } from '@/types/availability';
import type { EditableFormatTag } from '@/components/availability/calendarSettings';
import type { BookedSlotPreview } from '@/types/booking';
import InteractiveGrid from '@/components/availability/InteractiveGrid';

interface WeekViewProps {
  weekDates: WeekDateInfo[];
  weekBits: WeekBits;
  weekTags?: WeekTags;
  onBitsChange: (next: WeekBits | ((prev: WeekBits) => WeekBits)) => void;
  onTagsChange?: (next: WeekTags | ((prev: WeekTags) => WeekTags)) => void;
  availableTagOptions?: EditableFormatTag[];
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
  weekTags,
  onBitsChange,
  onTagsChange,
  availableTagOptions,
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
      {...(weekTags ? { weekTags } : {})}
      onBitsChange={onBitsChange}
      {...(onTagsChange ? { onTagsChange } : {})}
      {...(availableTagOptions ? { availableTagOptions } : {})}
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
