'use client';

import { useCallback, useMemo, useRef } from 'react';
import clsx from 'clsx';

import type { WeekBits, WeekDateInfo } from '@/types/availability';
import type { DayBits } from '@/lib/calendar/bitset';
import { idx, newEmptyBits, toggle } from '@/lib/calendar/bitset';
import type { BookedSlotPreview } from '@/types/booking';

interface InteractiveGridProps {
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
}

const HALF_HOURS_PER_HOUR = 2;

const HOURS_LABEL = (hour: number) => {
  if (hour === 24) return '12:00 AM (+1d)';
  const period = hour >= 12 ? 'PM' : 'AM';
  const display = hour % 12 || 12;
  return `${display}:00 ${period}`;
};

const isSlotSelected = (bits: DayBits | undefined, slotIndex: number): boolean => {
  if (!bits) return false;
  const byte = Math.floor(slotIndex / 8);
  const bit = slotIndex % 8;
  return ((bits[byte] ?? 0) & (1 << bit)) > 0;
};

const isSlotBooked = (
  booked: BookedSlotPreview[] | undefined,
  date: string,
  slotIndex: number,
  startHour: number
): boolean => {
  if (!booked?.length) return false;
  const hour = startHour + Math.floor(slotIndex / HALF_HOURS_PER_HOUR);
  const minute = slotIndex % 2 === 1 ? 30 : 0;
  const nextMinutes = minute === 0 ? 30 : 0;
  const nextHour = minute === 0 ? hour : hour + 1;
  const start = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:00`;
  const end = `${String(nextHour).padStart(2, '0')}:${String(nextMinutes).padStart(2, '0')}:00`;
  return booked.some(
    (slot) => slot.date === date && !(end <= slot.start_time || start >= slot.end_time)
  );
};

const getNowInTimezone = (tz?: string) => {
  const now = new Date();
  if (!tz) {
    return {
      isoDate: now.toISOString().slice(0, 10),
      minutes: now.getHours() * 60 + now.getMinutes(),
    };
  }
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: tz,
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
  const parts = formatter.formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '0';
  const isoDate = `${get('year')}-${get('month')}-${get('day')}`;
  const minutes = parseInt(get('hour'), 10) * 60 + parseInt(get('minute'), 10);
  return { isoDate, minutes };
};

const getSlotIndex = (startHour: number, row: number) => {
  const hour = startHour + Math.floor(row / HALF_HOURS_PER_HOUR);
  const minute = row % 2 === 1 ? 30 : 0;
  return idx(hour, minute);
};

export default function InteractiveGrid({
  weekDates,
  weekBits,
  onBitsChange,
  bookedSlots = [],
  startHour = 6,
  endHour = 22,
  timezone,
  isMobile = false,
  activeDayIndex = 0,
  onActiveDayChange,
}: InteractiveGridProps) {
  const rows = useMemo(() => (endHour - startHour) * HALF_HOURS_PER_HOUR, [startHour, endHour]);
  const dragRef = useRef<{ date: string; turningOn: boolean } | null>(null);

  const displayDates = useMemo(() => {
    if (!isMobile) return weekDates;
    const dateInfo = weekDates[activeDayIndex] ?? weekDates[0];
    return dateInfo ? [dateInfo] : [];
  }, [isMobile, activeDayIndex, weekDates]);

  const applyToggle = useCallback(
    (date: string, slotIndex: number, turnOn: boolean) => {
      onBitsChange((prev) => {
        const current = prev[date] ?? newEmptyBits();
        if (isSlotSelected(current, slotIndex) === turnOn) {
          return prev;
        }
        return {
          ...prev,
          [date]: toggle(current, slotIndex, turnOn),
        };
      });
    },
    [onBitsChange]
  );

  const beginDrag = useCallback(
    (date: string, slotIndex: number) => {
      const turningOn = !isSlotSelected(weekBits[date], slotIndex);
      applyToggle(date, slotIndex, turningOn);
      dragRef.current = { date, turningOn };
    },
    [applyToggle, weekBits]
  );

  const updateDrag = useCallback(
    (date: string, slotIndex: number) => {
      const state = dragRef.current;
      if (!state || state.date !== date) return;
      applyToggle(date, slotIndex, state.turningOn);
    },
    [applyToggle]
  );

  const endDrag = useCallback(() => {
    dragRef.current = null;
  }, []);

  const { isoDate: todayIso, minutes: nowMinutes } = useMemo(
    () => getNowInTimezone(timezone),
    [timezone]
  );

  const isPastSlot = useCallback(
    (date: string, slotIndex: number) => {
      if (date < todayIso) return true;
      if (date > todayIso) return false;
      const slotEndMinutes =
        (startHour + Math.floor((slotIndex + 1) / HALF_HOURS_PER_HOUR)) * 60 +
        ((slotIndex + 1) % 2 === 1 ? 30 : 0);
      return slotEndMinutes <= nowMinutes;
    },
    [nowMinutes, startHour, todayIso]
  );

  const handlePointerDown = useCallback(
    (event: React.PointerEvent<HTMLButtonElement>, date: string, slotIndex: number) => {
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      beginDrag(date, slotIndex);
    },
    [beginDrag]
  );

  const handlePointerEnter = useCallback(
    (event: React.PointerEvent<HTMLButtonElement>, date: string, slotIndex: number) => {
      if (event.buttons !== 1 || !dragRef.current) return;
      updateDrag(date, slotIndex);
    },
    [updateDrag]
  );

  const handlePointerUp = useCallback((event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.currentTarget.releasePointerCapture(event.pointerId);
    endDrag();
  }, [endDrag]);

  const handleKeyToggle = useCallback(
    (event: React.KeyboardEvent<HTMLButtonElement>, date: string, slotIndex: number) => {
      if (event.key !== ' ' && event.key !== 'Enter') return;
      event.preventDefault();
      const next = !isSlotSelected(weekBits[date], slotIndex);
      applyToggle(date, slotIndex, next);
    },
    [applyToggle, weekBits]
  );

  return (
    <div className="w-full overflow-x-auto">
      <div
        className="grid"
        style={{
          gridTemplateColumns: `80px repeat(${displayDates.length}, minmax(0, 1fr))`,
          columnGap: '0px',
          rowGap: '8px',
        }}
      >
        {/* Corner spacer */}
        <div />
        {displayDates.map((info, idx) => {
          const isToday = info.fullDate === todayIso;
          const dateObj = info.date;
          const dow = dateObj.toLocaleDateString('en-US', { weekday: 'short' });
          const dayNum = dateObj.getDate();
          const headerClasses = clsx(
            'sticky top-0 z-10 flex flex-col items-center gap-1 bg-white/85 px-2 py-2 backdrop-blur',
            isToday ? 'text-[#7E22CE]' : 'text-gray-700'
          );
          const isPastDate = info.fullDate < todayIso;
          return (
            <div key={info.fullDate} className={headerClasses}>
              <span className={clsx('text-xs uppercase tracking-wide', isPastDate ? 'text-gray-400' : 'text-gray-500')}>
                {dow}
              </span>
              <button
                type="button"
                className={clsx(
                  'flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold',
                  isToday ? 'border-2 border-[#7E22CE] text-[#111827]' : 'border border-gray-200 text-gray-800'
                )}
                onClick={() => {
                  if (!isMobile || !onActiveDayChange) return;
                  onActiveDayChange(idx);
                }}
              >
                {dayNum}
              </button>
            </div>
          );
        })}

        {/* Time gutter */}
        <div className="sticky left-0 z-10 flex flex-col bg-white/85 px-2 py-1 backdrop-blur">
          {Array.from({ length: rows }, (_, row) => {
            const showLabel = row % HALF_HOURS_PER_HOUR === 0;
            const labelHour = Math.floor(row / HALF_HOURS_PER_HOUR) + startHour;
            return (
              <div
                key={`time-${row}`}
                className={clsx(
                  'flex items-center border-b border-gray-200 text-xs text-gray-500',
                  'min-h-[32px]'
                )}
              >
                {showLabel ? HOURS_LABEL(labelHour) : ''}
              </div>
            );
          })}
        </div>

        {/* Day grids */}
        {displayDates.map((info) => {
          const date = info.fullDate;
          const dayBits = weekBits[date] ?? newEmptyBits();
          return (
            <div key={date} className="flex flex-col">
              {Array.from({ length: rows }, (_, row) => {
                const slotIndex = getSlotIndex(startHour, row);
                const booked = isSlotBooked(bookedSlots, date, row, startHour);
                const past = isPastSlot(date, slotIndex);
                const selected = isSlotSelected(dayBits, slotIndex);
                const labelHour = startHour + Math.floor(row / HALF_HOURS_PER_HOUR);
                const labelMinute = row % 2 === 1 ? '30' : '00';
                const weekdayLabel = info.date.toLocaleDateString('en-US', { weekday: 'long' });
                const ariaLabel = `${weekdayLabel} ${String(labelHour).padStart(2, '0')}:${labelMinute}`;
                return (
                  <button
                    key={`${date}-${row}`}
                    type="button"
                    className={clsx(
                      'group relative flex-1 min-h-[32px] border-b border-gray-200 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-0 focus-visible:ring-[#7E22CE]',
                      selected ? 'bg-[#EDE3FA]' : 'bg-white',
                      past && !selected && 'bg-gray-50 opacity-80'
                    )}
                    role="gridcell"
                    aria-selected={selected}
                    aria-label={ariaLabel}
                    onPointerDown={(event) => handlePointerDown(event, date, slotIndex)}
                    onPointerEnter={(event) => handlePointerEnter(event, date, slotIndex)}
                    onPointerUp={handlePointerUp}
                    onPointerLeave={(event) => {
                      if (event.buttons === 0) endDrag();
                    }}
                    onKeyDown={(event) => handleKeyToggle(event, date, slotIndex)}
                  >
                    {booked && (
                      <span className="pointer-events-none absolute inset-0 rounded-sm bg-[repeating-linear-gradient(45deg,rgba(124,58,237,0.18),rgba(124,58,237,0.18)_6px,rgba(124,58,237,0.08)_6px,rgba(124,58,237,0.08)_12px)]" />
                    )}
                    <span className="sr-only">
                      {info.date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
                    </span>
                    <span className="absolute inset-x-1 bottom-1 text-[10px] text-gray-400 opacity-0 transition-opacity group-hover:opacity-100">
                      {selected ? 'Selected' : booked ? 'Booked' : 'Available'}
                    </span>
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
