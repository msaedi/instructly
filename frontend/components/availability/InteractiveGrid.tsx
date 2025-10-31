'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { MouseEvent as ReactMouseEvent, KeyboardEvent as ReactKeyboardEvent } from 'react';
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

  const [isDragging, setIsDragging] = useState(false);
  const [dragValue, setDragValue] = useState<boolean | null>(null);
  const dragValueRef = useRef<boolean | null>(null);
  const pendingRef = useRef<Record<string, Set<number>>>({});
  const rafRef = useRef<number | null>(null);

  const applyImmediate = useCallback(
    (date: string, slotIndex: number, desired: boolean) => {
      onBitsChange((prev) => {
        const current = prev[date] ?? newEmptyBits();
        if (isSlotSelected(current, slotIndex) === desired) {
          return prev;
        }
        return {
          ...prev,
          [date]: toggle(current, slotIndex, desired),
        };
      });
    },
    [onBitsChange]
  );

  const flushPending = useCallback(() => {
    const desired = dragValueRef.current;
    if (desired === null) {
      pendingRef.current = {};
      return;
    }

    const payload = pendingRef.current;
    pendingRef.current = {};
    const dates = Object.keys(payload);
    if (!dates.length) {
      return;
    }

    onBitsChange((prev) => {
      let changed = false;
      const next: WeekBits = { ...prev };
      for (const date of dates) {
        const indices = Array.from(payload[date] ?? []);
        if (!indices.length) continue;
        const current = next[date] ?? newEmptyBits();
        let updated = current;
        indices.forEach((slotIndex) => {
          const selected = isSlotSelected(updated, slotIndex);
          if (selected !== desired) {
            updated = toggle(updated, slotIndex, desired);
          }
        });
        if (updated !== current) {
          next[date] = updated;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [onBitsChange]);

  const scheduleFlush = useCallback(() => {
    if (rafRef.current !== null) return;
    rafRef.current = window.requestAnimationFrame(() => {
      rafRef.current = null;
      flushPending();
    });
  }, [flushPending]);

  const cancelScheduledFlush = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const enqueueUpdate = useCallback(
    (date: string, slotIndex: number, desired: boolean) => {
      const currentBits = weekBits[date];
      if (isSlotSelected(currentBits, slotIndex) === desired) {
        return;
      }
      let setForDate = pendingRef.current[date];
      if (!setForDate) {
        setForDate = new Set<number>();
        pendingRef.current[date] = setForDate;
      }
      setForDate.add(slotIndex);
      scheduleFlush();
    },
    [scheduleFlush, weekBits]
  );

  const finishDrag = useCallback(() => {
    if (!isDragging) return;
    cancelScheduledFlush();
    flushPending();
    pendingRef.current = {};
    setIsDragging(false);
    setDragValue(null);
    dragValueRef.current = null;
  }, [cancelScheduledFlush, flushPending, isDragging]);

  useEffect(() => {
    dragValueRef.current = dragValue;
  }, [dragValue]);

  useEffect(() => {
    const handleWindowUp = () => {
      finishDrag();
    };
    window.addEventListener('mouseup', handleWindowUp);
    return () => window.removeEventListener('mouseup', handleWindowUp);
  }, [finishDrag]);

  const displayDates = useMemo(() => {
    if (!isMobile) return weekDates;
    const dateInfo = weekDates[activeDayIndex] ?? weekDates[0];
    return dateInfo ? [dateInfo] : [];
  }, [isMobile, activeDayIndex, weekDates]);

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

  const handleMouseDown = useCallback(
    (event: ReactMouseEvent<HTMLButtonElement>, date: string, slotIndex: number) => {
      event.preventDefault();
      const desired = !isSlotSelected(weekBits[date], slotIndex);
      pendingRef.current = {};
      setIsDragging(true);
      setDragValue(desired);
      dragValueRef.current = desired;
      applyImmediate(date, slotIndex, desired);
    },
    [applyImmediate, weekBits]
  );

  const handleMouseEnter = useCallback(
    (event: ReactMouseEvent<HTMLButtonElement>, date: string, slotIndex: number) => {
      if (!isDragging || dragValue === null || event.buttons === 0) return;
      enqueueUpdate(date, slotIndex, dragValue);
    },
    [enqueueUpdate, isDragging, dragValue]
  );

  const handleMouseUp = useCallback(
    (event: ReactMouseEvent<HTMLButtonElement>) => {
      event.preventDefault();
      finishDrag();
    },
    [finishDrag]
  );

  const handleKeyToggle = useCallback(
    (event: ReactKeyboardEvent<HTMLButtonElement>, date: string, slotIndex: number) => {
      if (event.key !== ' ' && event.key !== 'Enter') return;
      event.preventDefault();
      const desired = !isSlotSelected(weekBits[date], slotIndex);
      applyImmediate(date, slotIndex, desired);
    },
    [applyImmediate, weekBits]
  );

  return (
    <div className="w-full overflow-x-auto">
      <div
        className="grid"
        style={{
          gridTemplateColumns: `80px repeat(${displayDates.length}, minmax(0, 1fr))`,
          columnGap: '0px',
          rowGap: 'var(--slot-gap-y, 8px)',
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
                    onMouseDown={(event) => handleMouseDown(event, date, slotIndex)}
                    onMouseEnter={(event) => handleMouseEnter(event, date, slotIndex)}
                    onMouseUp={handleMouseUp}
                    onMouseLeave={(event) => {
                      if (event.buttons === 0) finishDrag();
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
