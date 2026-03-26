'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  KeyboardEvent as ReactKeyboardEvent,
  MouseEvent as ReactMouseEvent,
} from 'react';
import clsx from 'clsx';
import { MonitorCheck } from 'lucide-react';

import type { WeekBits, WeekDateInfo, WeekTags } from '@/types/availability';
import type { BookedSlotPreview } from '@/types/booking';
import type { DayBits, FormatTag } from '@/lib/calendar/bitset';
import {
  idx,
  newEmptyBits,
  newEmptyTags,
  toggleRange,
  isRangeSet,
  BITS_PER_CELL,
  AVAILABILITY_CELL_MINUTES,
  getRangeTag,
  setRangeTag,
  TAG_NONE,
  TAG_NO_TRAVEL,
  TAG_ONLINE_ONLY,
} from '@/lib/calendar/bitset';
import type {
  AvailabilityPaintMode,
  EditableFormatTag,
} from './calendarSettings';
import { formatTagLabel } from './calendarSettings';
import NoTravelIcon from './NoTravelIcon';

interface InteractiveGridProps {
  weekDates: WeekDateInfo[];
  weekBits: WeekBits;
  weekTags?: WeekTags;
  onBitsChange: (next: WeekBits | ((prev: WeekBits) => WeekBits)) => void;
  onTagsChange?: (next: WeekTags | ((prev: WeekTags) => WeekTags)) => void;
  availableTagOptions?: EditableFormatTag[];
  paintMode?: AvailabilityPaintMode;
  bookedSlots?: BookedSlotPreview[];
  startHour?: number;
  endHour?: number;
  timezone?: string;
  isMobile?: boolean;
  activeDayIndex?: number;
  onActiveDayChange?: (index: number) => void;
  allowPastEditing?: boolean;
}

type PaintInstruction =
  | { kind: 'toggle-availability'; desired: boolean }
  | { kind: 'apply-tag'; tag: EditableFormatTag }
  | { kind: 'clear-tag' };

const HALF_HOURS_PER_HOUR = 2;

const HOURS_LABEL = (hour: number) => {
  if (hour === 24) return '12:00 AM (+1d)';
  const period = hour >= 12 ? 'PM' : 'AM';
  const display = hour % 12 || 12;
  return `${display}:00 ${period}`;
};

const isCellSelected = (bits: DayBits | undefined, slotIndex: number): boolean => {
  return isRangeSet(bits, slotIndex, BITS_PER_CELL);
};

const isSlotBooked = (
  booked: BookedSlotPreview[] | undefined,
  date: string,
  row: number,
  startHour: number
): boolean => {
  if (!booked?.length) return false;
  const hour = startHour + Math.floor(row / HALF_HOURS_PER_HOUR);
  const minute = (row % HALF_HOURS_PER_HOUR) * AVAILABILITY_CELL_MINUTES;
  const nextMinutes = minute === 0 ? AVAILABILITY_CELL_MINUTES : 0;
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

const getCellBitmapStart = (startHour: number, row: number) => {
  const hour = startHour + Math.floor(row / HALF_HOURS_PER_HOUR);
  const minute = row % 2 === 1 ? 30 : 0;
  return idx(hour, minute);
};

function resolvePaintInstruction(
  selected: boolean,
  currentTag: FormatTag | null,
  paintMode: AvailabilityPaintMode
): PaintInstruction {
  if (paintMode === TAG_NONE) {
    return {
      kind: 'toggle-availability',
      desired: !selected,
    };
  }

  if (!selected) {
    return {
      kind: 'apply-tag',
      tag: paintMode,
    };
  }

  if (currentTag === paintMode) {
    return { kind: 'clear-tag' };
  }

  return {
    kind: 'apply-tag',
    tag: paintMode,
  };
}

export default function InteractiveGrid({
  weekDates,
  weekBits,
  weekTags = {},
  onBitsChange,
  onTagsChange,
  availableTagOptions = [],
  paintMode = TAG_NONE,
  bookedSlots = [],
  startHour = 6,
  endHour = 22,
  timezone,
  isMobile = false,
  activeDayIndex = 0,
  onActiveDayChange: _onActiveDayChange,
  allowPastEditing = false,
}: InteractiveGridProps) {
  const rows = useMemo(() => (endHour - startHour) * HALF_HOURS_PER_HOUR, [endHour, startHour]);
  const [activeCell, setActiveCell] = useState({ row: 0, col: 0 });
  const taggingEnabled = availableTagOptions.length > 0;
  const effectivePaintMode = taggingEnabled ? paintMode : TAG_NONE;
  const [isDragging, setIsDragging] = useState(false);
  const dragInstructionRef = useRef<PaintInstruction | null>(null);
  const lastHoverRowRef = useRef<{ date: string; row: number } | null>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const weekBitsRef = useRef(weekBits);
  const weekTagsRef = useRef(weekTags);

  const [nowInfo, setNowInfo] = useState(() => getNowInTimezone(timezone));

  useEffect(() => {
    weekBitsRef.current = weekBits;
  }, [weekBits]);

  useEffect(() => {
    weekTagsRef.current = weekTags;
  }, [weekTags]);

  useEffect(() => {
    const tick = () => setNowInfo(getNowInTimezone(timezone));
    tick();
    const interval = window.setInterval(tick, 60 * 1000);
    return () => window.clearInterval(interval);
  }, [timezone]);

  const finishDrag = useCallback(() => {
    setIsDragging(false);
    dragInstructionRef.current = null;
    lastHoverRowRef.current = null;
  }, []);

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
  }, [activeDayIndex, isMobile, weekDates]);

  const columnCount = displayDates.length;

  const clampedActiveCell = useMemo(() => {
    const maxRow = Math.max(rows - 1, 0);
    const maxCol = Math.max(columnCount - 1, 0);
    return {
      row: Math.min(Math.max(activeCell.row, 0), maxRow),
      col: Math.min(Math.max(activeCell.col, 0), maxCol),
    };
  }, [activeCell.col, activeCell.row, columnCount, rows]);

  const { isoDate: todayIso, minutes: nowMinutes } = nowInfo;

  const isPastSlot = useCallback(
    (date: string, row: number) => {
      if (allowPastEditing) return false;
      if (date < todayIso) return true;
      if (date > todayIso) return false;
      const cellEndMinutes =
        (startHour + Math.floor((row + 1) / HALF_HOURS_PER_HOUR)) * 60 +
        ((row + 1) % 2 === 1 ? 30 : 0);
      return cellEndMinutes <= nowMinutes;
    },
    [allowPastEditing, nowMinutes, startHour, todayIso]
  );

  const isPastForStyle = useCallback(
    (date: string, row: number) => {
      if (date < todayIso) return true;
      if (date > todayIso) return false;
      const cellEndMinutes =
        (startHour + Math.floor((row + 1) / HALF_HOURS_PER_HOUR)) * 60 +
        ((row + 1) % 2 === 1 ? 30 : 0);
      return cellEndMinutes <= nowMinutes;
    },
    [nowMinutes, startHour, todayIso]
  );

  const applyInstructionToCell = useCallback(
    (date: string, slotIndex: number, instruction: PaintInstruction) => {
      const currentBits = weekBitsRef.current[date] ?? newEmptyBits();
      const selected = isCellSelected(currentBits, slotIndex);
      const currentTags = weekTagsRef.current[date] ?? newEmptyTags();
      const currentTag = selected ? getRangeTag(currentTags, slotIndex, BITS_PER_CELL) : TAG_NONE;

      if (instruction.kind === 'toggle-availability') {
        if (selected === instruction.desired) {
          return;
        }

        onBitsChange((prev) => {
          const bits = prev[date] ?? newEmptyBits();
          if (isCellSelected(bits, slotIndex) === instruction.desired) {
            return prev;
          }
          return {
            ...prev,
            [date]: toggleRange(bits, slotIndex, BITS_PER_CELL, instruction.desired),
          };
        });

        if (onTagsChange) {
          onTagsChange((prev) => {
            const tags = prev[date] ?? newEmptyTags();
            const updated = setRangeTag(tags, slotIndex, BITS_PER_CELL, TAG_NONE);
            return {
              ...prev,
              [date]: updated,
            };
          });
        }
        return;
      }

      if (instruction.kind === 'clear-tag') {
        if (!selected || !onTagsChange || currentTag === TAG_NONE) {
          return;
        }

        onTagsChange((prev) => {
          const tags = prev[date] ?? newEmptyTags();
          const updated = setRangeTag(tags, slotIndex, BITS_PER_CELL, TAG_NONE);
          return {
            ...prev,
            [date]: updated,
          };
        });
        return;
      }

      if (!selected) {
        onBitsChange((prev) => {
          const bits = prev[date] ?? newEmptyBits();
          if (isCellSelected(bits, slotIndex)) {
            return prev;
          }
          return {
            ...prev,
            [date]: toggleRange(bits, slotIndex, BITS_PER_CELL, true),
          };
        });
      }

      if (!onTagsChange || currentTag === instruction.tag) {
        return;
      }

      onTagsChange((prev) => {
        const tags = prev[date] ?? newEmptyTags();
        const updated = setRangeTag(tags, slotIndex, BITS_PER_CELL, instruction.tag);
        return {
          ...prev,
          [date]: updated,
        };
      });
    },
    [onBitsChange, onTagsChange]
  );

  const focusGridCell = useCallback(
    (rowIndex: number, columnIndex: number) => {
      const maxRow = Math.max(rows - 1, 0);
      const maxCol = Math.max(columnCount - 1, 0);
      const nextRow = Math.min(Math.max(rowIndex, 0), maxRow);
      const nextCol = Math.min(Math.max(columnIndex, 0), maxCol);
      setActiveCell({ row: nextRow, col: nextCol });
      const targetCell = gridRef.current?.querySelector<HTMLButtonElement>(
        `[data-row-index="${nextRow}"][data-col-index="${nextCol}"]`
      );
      targetCell?.focus();
    },
    [columnCount, rows]
  );

  const handleMouseDown = useCallback(
    (
      event: ReactMouseEvent<HTMLButtonElement>,
      date: string,
      row: number,
      columnIndex: number,
      slotIndex: number,
      selected: boolean,
      cellTag: FormatTag | null,
      locked: boolean
    ) => {
      event.preventDefault();
      if (event.button !== 0 || locked) {
        return;
      }

      setActiveCell({ row, col: columnIndex });
      const instruction = resolvePaintInstruction(selected, cellTag, effectivePaintMode);
      dragInstructionRef.current = instruction;
      lastHoverRowRef.current = { date, row };
      setIsDragging(true);
      applyInstructionToCell(date, slotIndex, instruction);
    },
    [applyInstructionToCell, effectivePaintMode]
  );

  const handleMouseEnter = useCallback(
    (
      event: ReactMouseEvent<HTMLButtonElement>,
      date: string,
      row: number,
      slotIndex: number,
      locked: boolean
    ) => {
      const instruction = dragInstructionRef.current;
      if (!isDragging || !instruction || event.buttons === 0 || locked) {
        return;
      }

      const previous = lastHoverRowRef.current;
      if (!previous || previous.date !== date) {
        applyInstructionToCell(date, slotIndex, instruction);
        lastHoverRowRef.current = { date, row };
        return;
      }

      const delta = row - previous.row;
      if (delta === 0) {
        applyInstructionToCell(date, slotIndex, instruction);
      } else {
        const step = delta > 0 ? 1 : -1;
        for (let currentRow = previous.row + step; step > 0 ? currentRow <= row : currentRow >= row; currentRow += step) {
          applyInstructionToCell(date, getCellBitmapStart(startHour, currentRow), instruction);
        }
      }

      lastHoverRowRef.current = { date, row };
    },
    [applyInstructionToCell, isDragging, startHour]
  );

  const handleMouseUp = useCallback(
    (event: ReactMouseEvent<HTMLButtonElement>) => {
      event.preventDefault();
      finishDrag();
    },
    [finishDrag]
  );

  const handleCellKeyDown = useCallback(
    (
      event: ReactKeyboardEvent<HTMLButtonElement>,
      date: string,
      slotIndex: number,
      rowIndex: number,
      columnIndex: number,
      selected: boolean,
      cellTag: FormatTag | null,
      locked: boolean
    ) => {
      if (event.key === ' ' || event.key === 'Enter') {
        event.preventDefault();
        if (locked) return;
        const instruction = resolvePaintInstruction(selected, cellTag, effectivePaintMode);
        applyInstructionToCell(date, slotIndex, instruction);
        return;
      }

      let nextRowIndex = rowIndex;
      let nextColumnIndex = columnIndex;

      switch (event.key) {
        case 'ArrowLeft':
          nextColumnIndex = Math.max(0, columnIndex - 1);
          break;
        case 'ArrowRight':
          nextColumnIndex = Math.min(columnCount - 1, columnIndex + 1);
          break;
        case 'ArrowUp':
          nextRowIndex = Math.max(0, rowIndex - 1);
          break;
        case 'ArrowDown':
          nextRowIndex = Math.min(rows - 1, rowIndex + 1);
          break;
        case 'Home':
          nextColumnIndex = 0;
          break;
        case 'End':
          nextColumnIndex = Math.max(0, columnCount - 1);
          break;
        default:
          return;
      }

      event.preventDefault();
      if (nextRowIndex === rowIndex && nextColumnIndex === columnIndex) {
        return;
      }
      focusGridCell(nextRowIndex, nextColumnIndex);
    },
    [applyInstructionToCell, columnCount, effectivePaintMode, focusGridCell, rows]
  );

  return (
    <div className="w-full overflow-x-auto">
      <div
        ref={gridRef}
        role="grid"
        aria-label="Weekly availability editor. Use arrow keys to navigate between time slots."
        className="relative grid"
        style={{
          gridTemplateColumns: `80px repeat(${displayDates.length}, minmax(0, 1fr))`,
          columnGap: '0px',
        }}
      >
        <div role="row" className="contents">
          <div
            role="columnheader"
            aria-hidden="true"
            className="sticky left-0 top-0 z-20 border-r border-gray-200 bg-white/80 px-2 py-1 backdrop-blur dark:border-gray-700 dark:bg-gray-900/70"
          />
          {displayDates.map((info, index) => {
            const isToday = info.fullDate === todayIso;
            const isPastDate = info.fullDate < todayIso;
            const dayNum = info.date.getDate();
            const dayLabel = info.date.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase();

            return (
              <div
                key={info.fullDate}
                role="columnheader"
                className="relative sticky top-0 z-20 bg-white/80 px-2 pt-1 pb-0 text-center backdrop-blur dark:bg-gray-900/70"
              >
                {index > 0 ? (
                  <span
                    className="absolute bottom-0 left-0 w-px bg-gray-200 dark:bg-gray-700"
                    style={{ height: '50%' }}
                  />
                ) : null}
                {index === displayDates.length - 1 ? (
                  <span
                    className="absolute bottom-0 right-0 w-px bg-gray-200 dark:bg-gray-700"
                    style={{ height: '50%' }}
                  />
                ) : null}
                <div
                  className={clsx(
                    'text-[10px] uppercase tracking-wide',
                    isPastDate ? 'text-gray-400 dark:text-gray-300' : 'text-gray-500 dark:text-gray-400'
                  )}
                >
                  {dayLabel}
                </div>
                <div className="mt-0.5">
                  <span
                    className={clsx(
                      'inline-flex items-center justify-center px-1 py-0 text-2xl font-medium leading-none',
                      isToday
                        ? 'rounded-md border-2 border-[#7E22CE] text-[#111827] dark:text-white'
                        : isPastDate
                          ? 'text-gray-400 dark:text-gray-300'
                          : 'text-gray-900 dark:text-gray-100'
                    )}
                  >
                    {dayNum}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {Array.from({ length: rows }, (_, row) => (
          <div key={`grid-row-${row}`} role="row" className="contents">
            <div
              role="rowheader"
              className={clsx(
                'sticky left-0 z-10 flex items-center border-r border-b border-gray-200 bg-white/80 px-2 py-1 text-xs text-gray-500 backdrop-blur dark:border-gray-700 dark:bg-gray-900/70 dark:text-gray-400',
                isMobile ? 'h-10' : 'h-6 sm:h-7 md:h-8',
                row === 0 && 'border-t border-gray-200 dark:border-gray-700'
              )}
            >
              {row % HALF_HOURS_PER_HOUR === 0
                ? HOURS_LABEL(Math.floor(row / HALF_HOURS_PER_HOUR) + startHour)
                : ''}
            </div>
            {displayDates.map((info, columnIndex) => {
              const date = info.fullDate;
              const dayBits = weekBits[date] ?? newEmptyBits();
              const dayTags = weekTags[date] ?? newEmptyTags();
              const slotIndex = getCellBitmapStart(startHour, row);
              const booked = isSlotBooked(bookedSlots, date, row, startHour);
              const behaviourPast = isPastSlot(date, row);
              const visualPast = isPastForStyle(date, row);
              const locked = behaviourPast;
              const selected = isCellSelected(dayBits, slotIndex);
              const cellTag = selected ? getRangeTag(dayTags, slotIndex, BITS_PER_CELL) : TAG_NONE;
              const isLastColumn = columnIndex === displayDates.length - 1;
              const labelHour = startHour + Math.floor(row / HALF_HOURS_PER_HOUR);
              const labelMinute = row % 2 === 1 ? '30' : '00';
              const weekdayLabel = info.date.toLocaleDateString('en-US', { weekday: 'long' });
              const ariaLabel = `${weekdayLabel} ${String(labelHour).padStart(2, '0')}:${labelMinute}`;
              const isToday = date === todayIso;
              const windowStartMinutes = startHour * 60;
              const windowEndMinutes = endHour * 60;
              const withinWindow = nowMinutes >= windowStartMinutes && nowMinutes <= windowEndMinutes;
              const relativeMinutes = nowMinutes - windowStartMinutes;
              const nowRow = Math.floor(relativeMinutes / AVAILABILITY_CELL_MINUTES);
              const nowOffsetPercent =
                ((relativeMinutes % AVAILABILITY_CELL_MINUTES) / AVAILABILITY_CELL_MINUTES) * 100;
              const showNowMarker =
                isToday && withinWindow && row === Math.max(0, Math.min(rows - 1, nowRow));
              const fillClass = selected
                ? cellTag === TAG_ONLINE_ONLY
                  ? 'bg-[#D1FAE5] dark:bg-[#064E3B]/30'
                  : cellTag === TAG_NO_TRAVEL
                    ? 'bg-[#FFEDAF] dark:bg-[#78350F]/30'
                    : 'bg-[#EDE3FA] dark:bg-purple-500/25'
                : visualPast
                  ? 'bg-gray-50 dark:bg-gray-800/60'
                  : 'bg-white dark:bg-gray-900/60';
              const fadeClass = !selected && visualPast ? 'opacity-70' : 'opacity-100';
              const tagState = !selected
                ? 'inactive'
                : cellTag === TAG_ONLINE_ONLY
                  ? 'online_only'
                  : cellTag === TAG_NO_TRAVEL
                    ? 'no_travel'
                    : cellTag === null
                      ? 'mixed'
                      : 'none';

              return (
                <button
                  key={`${date}-${row}`}
                  type="button"
                  role="gridcell"
                  data-testid="availability-cell"
                  data-date={date}
                  data-time={`${String(labelHour).padStart(2, '0')}:${labelMinute}:00`}
                  data-row-index={row}
                  data-col-index={columnIndex}
                  data-tag-state={tagState}
                  aria-selected={selected}
                  aria-disabled={behaviourPast}
                  aria-label={ariaLabel}
                  tabIndex={
                    clampedActiveCell.row === row && clampedActiveCell.col === columnIndex ? 0 : -1
                  }
                  className={clsx(
                    'group relative w-full flex-none cursor-pointer border-l border-b border-gray-200 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE] focus-visible:ring-offset-0 dark:border-gray-700',
                    isLastColumn && 'border-r border-gray-200 dark:border-gray-700',
                    row === 0 && 'border-t border-gray-200 dark:border-gray-700',
                    isMobile ? 'h-10' : 'h-6 sm:h-7 md:h-8',
                    fillClass,
                    fadeClass
                  )}
                  onMouseDown={(event) =>
                    handleMouseDown(
                      event,
                      date,
                      row,
                      columnIndex,
                      slotIndex,
                      selected,
                      cellTag,
                      locked
                    )
                  }
                  onMouseEnter={(event) =>
                    handleMouseEnter(event, date, row, slotIndex, locked)
                  }
                  onMouseUp={handleMouseUp}
                  onMouseLeave={(event) => {
                    if (event.buttons === 0) {
                      finishDrag();
                    }
                  }}
                  onContextMenu={(event) => {
                    event.preventDefault();
                  }}
                  onFocus={() => setActiveCell({ row, col: columnIndex })}
                  onKeyDown={(event) =>
                    handleCellKeyDown(
                      event,
                      date,
                      slotIndex,
                      row,
                      columnIndex,
                      selected,
                      cellTag,
                      locked
                    )
                  }
                >
                  {booked ? (
                    <span className="pointer-events-none absolute inset-0 rounded-sm bg-[repeating-linear-gradient(45deg,rgba(156,163,175,0.35),rgba(156,163,175,0.35)_6px,rgba(156,163,175,0.2)_6px,rgba(156,163,175,0.2)_12px)]" />
                  ) : null}
                  {showNowMarker ? (
                    <>
                      <div
                        className="now-line"
                        data-testid="now-line"
                        style={{ top: `${nowOffsetPercent}%` }}
                      />
                      <span
                        className="now-dot"
                        style={{ top: `${nowOffsetPercent}%`, left: '0' }}
                      />
                    </>
                  ) : null}
                  {selected && !booked && cellTag === TAG_ONLINE_ONLY ? (
                    <span
                      data-testid="tag-indicator-online"
                      className="pointer-events-none absolute inset-0 flex items-center justify-center text-[#059669]"
                    >
                      <MonitorCheck className="h-3.5 w-3.5" />
                    </span>
                  ) : null}
                  {selected && !booked && cellTag === TAG_NO_TRAVEL ? (
                    <span className="pointer-events-none absolute inset-0 flex items-center justify-center text-[#92400E]">
                      <NoTravelIcon
                        className="h-3.5 w-3.5"
                        data-testid="tag-indicator-no-travel"
                      />
                    </span>
                  ) : null}
                  <span className="sr-only">
                    {info.date.toLocaleDateString('en-US', {
                      weekday: 'long',
                      month: 'long',
                      day: 'numeric',
                    })}
                  </span>
                  <span className="absolute inset-x-1 bottom-1 text-[10px] text-gray-400 opacity-0 transition-opacity group-hover:opacity-100 dark:text-gray-500">
                    {selected ? formatTagLabel(cellTag ?? TAG_NONE) : booked ? 'Booked' : 'Available'}
                  </span>
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
