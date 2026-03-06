import { at } from '@/lib/ts/safe';

export interface CalendarTimeSlot {
  start_time: string;
  end_time: string;
  is_available: boolean;
}

export interface CalendarAvailabilityDay {
  date: string;
  slots: CalendarTimeSlot[];
}

interface NextDayLike {
  date?: string | null;
}

interface AvailabilityByDateLike {
  [date: string]: {
    available_slots?: Array<{
      start_time: string;
      end_time: string;
    }>;
  };
}

export const buildAvailabilityDays = (
  nextDays: NextDayLike[],
  availabilityByDate?: AvailabilityByDateLike | null,
): CalendarAvailabilityDay[] => {
  if (!availabilityByDate) {
    return nextDays.map((day) => ({ date: day.date ?? '', slots: [] }));
  }

  const availabilityMap = new Map<string, CalendarTimeSlot[]>();
  Object.entries(availabilityByDate).forEach(([date, dayData]) => {
    const slots = dayData.available_slots
      ? dayData.available_slots.map((slot) => ({
          start_time: slot.start_time,
          end_time: slot.end_time,
          is_available: true,
        }))
      : [];
    availabilityMap.set(date, slots);
  });

  return nextDays
    .map((day) => {
      const date = day?.date;
      if (!date) return { date: '', slots: [] };
      return {
        date,
        slots: availabilityMap.get(date) || [],
      };
    })
    .filter((day) => day.date !== '');
};

export const getFutureAvailableSlots = (
  availability: CalendarAvailabilityDay[],
  date: string,
  now = new Date(),
): CalendarTimeSlot[] => {
  const dayAvailability = availability.find((day) => day.date === date);
  const allSlots = dayAvailability?.slots.filter((slot) => slot.is_available) || [];

  return allSlots.filter((slot) => {
    const slotDateTime = new Date(`${date}T${slot.start_time}`);
    return slotDateTime > now;
  });
};

export const groupSlotsByTimeOfDay = (slots: CalendarTimeSlot[]) => {
  const morning = slots.filter((slot) => {
    const timeParts = slot.start_time.split(':');
    const hourStr = at(timeParts, 0);
    if (!hourStr) return false;
    const hour = parseInt(hourStr, 10);
    return hour < 12;
  });

  const afternoon = slots.filter((slot) => {
    const timeParts = slot.start_time.split(':');
    const hourStr = at(timeParts, 0);
    if (!hourStr) return false;
    const hour = parseInt(hourStr, 10);
    return hour >= 12 && hour < 17;
  });

  const evening = slots.filter((slot) => {
    const timeParts = slot.start_time.split(':');
    const hourStr = at(timeParts, 0);
    if (!hourStr) return false;
    const hour = parseInt(hourStr, 10);
    return hour >= 17;
  });

  return { morning, afternoon, evening };
};

export const formatAvailabilityTime = (time: string) => {
  const timeParts = time.split(':');
  const hours = at(timeParts, 0);
  const minutes = at(timeParts, 1);
  if (!hours || !minutes) return '';
  const hour = parseInt(hours, 10);
  const ampm = hour >= 12 ? 'PM' : 'AM';
  const displayHour = hour % 12 || 12;
  return `${displayHour}:${minutes}${ampm}`;
};
