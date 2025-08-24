'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { WeekDateInfo, WeekSchedule, TimeSlot } from '@/types/availability';
import { AVAILABILITY_CONSTANTS } from '@/types/availability';

type BookedPreview = {
  date: string; // YYYY-MM-DD
  start_time: string; // HH:MM:SS
  end_time: string; // HH:MM:SS
};

export interface InteractiveGridProps {
  weekDates: WeekDateInfo[];
  weekSchedule: WeekSchedule;
  bookedSlots?: BookedPreview[];
  startHour?: number;
  endHour?: number;
  isMobile?: boolean;
  activeDayIndex?: number;
  onActiveDayChange?: (index: number) => void;
  onScheduleChange: (schedule: WeekSchedule) => void;
  timezone?: string; // IANA timezone for rendering (e.g., "America/New_York")
}

const HALF_HOURS_PER_HOUR = 2;

function toCellIndex(hour: number, halfIndex: 0 | 1) {
  return hour * HALF_HOURS_PER_HOUR + halfIndex;
}

function parseHHMMSS(t: string) {
  const [h, m] = t.split(':').map((n) => parseInt(n, 10));
  return { h, m };
}

function toHHMMSS(hours: number, minutes: number): string {
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:00`;
}

function buildDayCellSet(slots: TimeSlot[], startHour: number, endHour: number): Set<number> {
  const set = new Set<number>();
  for (const slot of slots || []) {
    const { h: sh, m: sm } = parseHHMMSS(slot.start_time);
    const { h: eh, m: em } = parseHHMMSS(slot.end_time);

    // Clamp to grid
    const start = Math.max(startHour, sh);
    const end = Math.min(endHour, eh);

    let startIdx = (start - startHour) * HALF_HOURS_PER_HOUR + (sm >= 30 ? 1 : 0);
    let endIdx = (end - startHour) * HALF_HOURS_PER_HOUR + (em > 0 ? (em >= 30 ? 2 : 1) : 0);
    // Fill each half-hour cell
    for (let i = startIdx; i < endIdx; i++) set.add(i);
  }
  return set;
}

function cellsToSlots(cells: Set<number>, startHour: number): TimeSlot[] {
  if (cells.size === 0) return [];
  const indices = Array.from(cells).sort((a, b) => a - b);
  const result: TimeSlot[] = [];
  let runStart = indices[0];
  let prev = indices[0];
  for (let i = 1; i < indices.length; i++) {
    const idx = indices[i];
    if (idx !== prev + 1) {
      // flush
      const startH = Math.floor(runStart / HALF_HOURS_PER_HOUR) + startHour;
      const startM = runStart % 2 === 1 ? 30 : 0;
      const endCell = prev + 1;
      const endH = Math.floor(endCell / HALF_HOURS_PER_HOUR) + startHour;
      const endM = endCell % 2 === 1 ? 30 : 0;
      result.push({ start_time: toHHMMSS(startH, startM), end_time: toHHMMSS(endH, endM) });
      runStart = idx;
    }
    prev = idx;
  }
  // flush last
  const startH = Math.floor(runStart / HALF_HOURS_PER_HOUR) + startHour;
  const startM = runStart % 2 === 1 ? 30 : 0;
  const endCell = prev + 1;
  const endH = Math.floor(endCell / HALF_HOURS_PER_HOUR) + startHour;
  const endM = endCell % 2 === 1 ? 30 : 0;
  result.push({ start_time: toHHMMSS(startH, startM), end_time: toHHMMSS(endH, endM) });
  return result;
}

function isCellBooked(booked: BookedPreview[] | undefined, date: string, cellIdx: number, startHour: number) {
  if (!booked || booked.length === 0) return false;
  const startH = Math.floor(cellIdx / HALF_HOURS_PER_HOUR) + startHour;
  const startM = cellIdx % 2 === 1 ? 30 : 0;
  const start = toHHMMSS(startH, startM);
  const end = toHHMMSS(startM === 0 ? startH : startH + 1, startM === 0 ? 30 : 0);
  return booked.some((s) => s.date === date && !(end <= s.start_time || start >= s.end_time));
}

export default function InteractiveGrid({
  weekDates,
  weekSchedule,
  bookedSlots = [],
  startHour = AVAILABILITY_CONSTANTS.DEFAULT_START_HOUR,
  endHour = AVAILABILITY_CONSTANTS.DEFAULT_END_HOUR,
  isMobile = false,
  activeDayIndex = 0,
  onActiveDayChange,
  onScheduleChange,
  timezone,
}: InteractiveGridProps) {
  const hours = useMemo(() => Array.from({ length: endHour - startHour }, (_, i) => startHour + i), [startHour, endHour]);
  const rows = useMemo(() => (endHour - startHour) * HALF_HOURS_PER_HOUR, [startHour, endHour]);
  const [dragging, setDragging] = useState<null | { date: string; mode: 'add' | 'remove'; startCell: number; currentCell: number }>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const gridRef = useRef<HTMLDivElement | null>(null);

  // Accessibility: focused cell (roving tabindex)
  const [focusDay, setFocusDay] = useState<number>(0);
  const [focusRow, setFocusRow] = useState<number>(0);

  // Virtualization (window-based)
  const [rowHeight, setRowHeight] = useState<number>(0);
  const [visibleStart, setVisibleStart] = useState<number>(0);
  const [visibleEnd, setVisibleEnd] = useState<number>(rows - 1);
  const virtualizationEnabled = rows > 46; // enable for large ranges

  // Now-line positioning updates every 5 minutes
  const [nowTick, setNowTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setNowTick((x) => x + 1), 5 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  // Helpers to get "now" in a specific timezone (without external libs)
  const getNowInTimezone = useCallback(
    (tz?: string): { isoDate: string; hour: number; minute: number } => {
      const d = new Date();
      if (!tz) {
        const isoDate = d.toISOString().slice(0, 10);
        return { isoDate, hour: d.getHours(), minute: d.getMinutes() };
      }
      const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone: tz,
        hour12: false,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      }).formatToParts(d);
      const get = (type: string) => parts.find((p) => p.type === type)?.value || '';
      const isoDate = `${get('year')}-${get('month')}-${get('day')}`;
      const hour = parseInt(get('hour') || '0', 10);
      const minute = parseInt(get('minute') || '0', 10);
      return { isoDate, hour, minute };
    },
    []
  );

  const todayIdx = useMemo(() => {
    const { isoDate } = getNowInTimezone(timezone);
    return weekDates.findIndex((d) => d.fullDate === isoDate);
  }, [weekDates, nowTick, timezone, getNowInTimezone]);

  const nowLine = useMemo(() => {
    if (todayIdx < 0) return null;
    const { hour, minute } = getNowInTimezone(timezone);
    const halfCells = (hour - startHour) * HALF_HOURS_PER_HOUR + (minute >= 30 ? 1 : 0) + (minute % 30) / 30;
    const perc = Math.max(0, Math.min(halfCells / rows, 1));
    return { column: todayIdx, topPercent: perc * 100 };
  }, [todayIdx, startHour, rows, nowTick, timezone, getNowInTimezone]);

  const isPastCell = (date: string, cellIdx: number) => {
    const { isoDate, hour, minute } = getNowInTimezone(timezone);
    // Compare dates first
    if (date < isoDate) return true;
    if (date > isoDate) return false;
    // Same date: compare end of cell vs now
    const cellEndHour = Math.floor((cellIdx + 1) / HALF_HOURS_PER_HOUR) + startHour;
    const cellEndMin = (cellIdx + 1) % 2 === 1 ? 30 : 0;
    if (cellEndHour < hour) return true;
    if (cellEndHour > hour) return false;
    return cellEndMin <= minute;
  };

  // Keyboard interactions
  const toggleSingleCell = useCallback((date: string, cellIdx: number) => {
    const currentSet = buildDayCellSet(weekSchedule[date] || [], startHour, endHour);
    const nextSet = new Set(currentSet);
    if (nextSet.has(cellIdx)) nextSet.delete(cellIdx);
    else nextSet.add(cellIdx);
    const nextSlots = cellsToSlots(nextSet, startHour);
    onScheduleChange({ ...weekSchedule, [date]: nextSlots });
  }, [weekSchedule, onScheduleChange, startHour, endHour]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>, dayIdx: number, rowIdx: number, date: string) => {
    let nextDay = dayIdx;
    let nextRow = rowIdx;
    if (e.key === 'ArrowRight') {
      nextDay = Math.min(weekDates.length - 1, dayIdx + 1);
      e.preventDefault();
    } else if (e.key === 'ArrowLeft') {
      nextDay = Math.max(0, dayIdx - 1);
      e.preventDefault();
    } else if (e.key === 'ArrowDown') {
      nextRow = Math.min(rows - 1, rowIdx + 1);
      e.preventDefault();
    } else if (e.key === 'ArrowUp') {
      nextRow = Math.max(0, rowIdx - 1);
      e.preventDefault();
    } else if (e.key === ' ' || e.key === 'Enter') {
      toggleSingleCell(date, rowIdx);
      e.preventDefault();
    }

    if (nextDay !== dayIdx || nextRow !== rowIdx) {
      setFocusDay(nextDay);
      setFocusRow(nextRow);
      // Scroll cell into view if virtualized
      if (virtualizationEnabled && gridRef.current && rowHeight > 0) {
        const topPx = nextRow * rowHeight;
        const bottomPx = topPx + rowHeight;
        const rect = gridRef.current.getBoundingClientRect();
        const viewportTop = Math.max(0, -rect.top);
        const viewportBottom = viewportTop + window.innerHeight - Math.max(0, rect.top + rect.height - window.innerHeight);
        if (topPx < viewportTop + visibleStart * rowHeight || bottomPx > (visibleEnd + 1) * rowHeight) {
          // Force update range around target
          const buffer = 6;
          const start = Math.max(0, Math.floor(nextRow - buffer));
          const end = Math.min(rows - 1, Math.ceil(nextRow + buffer));
          setVisibleStart(start);
          setVisibleEnd(end);
        }
      }
    }
  };

  const handleMouseDown = (date: string, cellIdx: number) => {
    const existing = buildDayCellSet(weekSchedule[date] || [], startHour, endHour);
    const mode: 'add' | 'remove' = existing.has(cellIdx) ? 'remove' : 'add';
    setDragging({ date, mode, startCell: cellIdx, currentCell: cellIdx });
  };

  const handleMouseEnter = (date: string, cellIdx: number) => {
    setDragging((prev) => (prev && prev.date === date ? { ...prev, currentCell: cellIdx } : prev));
  };

  const handleMouseUp = () => {
    if (!dragging) return;
    const { date, mode } = dragging;
    const a = Math.min(dragging.startCell, dragging.currentCell);
    const b = Math.max(dragging.startCell, dragging.currentCell);
    const range = new Set<number>();
    for (let i = a; i <= b; i++) range.add(i);

    const currentSet = buildDayCellSet(weekSchedule[date] || [], startHour, endHour);
    const nextSet = new Set(currentSet);
    range.forEach((i) => {
      if (mode === 'add') nextSet.add(i);
      else nextSet.delete(i);
    });

    const nextSlots = cellsToSlots(nextSet, startHour);
    onScheduleChange({ ...weekSchedule, [date]: nextSlots });
    setDragging(null);
  };

  // Swipe handlers for mobile single-day view
  useEffect(() => {
    if (!isMobile || !containerRef.current || !onActiveDayChange) return;
    const el = containerRef.current;
    let startX = 0;
    let tracking = false;
    const onTouchStart = (e: TouchEvent) => {
      tracking = true;
      startX = e.touches[0].clientX;
    };
    const onTouchEnd = (e: TouchEvent) => {
      if (!tracking) return;
      const dx = (e.changedTouches[0].clientX || 0) - startX;
      if (Math.abs(dx) > 40) {
        const delta = dx > 0 ? -1 : 1;
        const idx = Math.max(0, Math.min(weekDates.length - 1, (activeDayIndex || 0) + delta));
        onActiveDayChange(idx);
      }
      tracking = false;
    };
    el.addEventListener('touchstart', onTouchStart);
    el.addEventListener('touchend', onTouchEnd);
    return () => {
      el.removeEventListener('touchstart', onTouchStart);
      el.removeEventListener('touchend', onTouchEnd);
    };
  }, [isMobile, activeDayIndex, onActiveDayChange, weekDates.length]);

  // Measure row height then compute visible range from window viewport
  useEffect(() => {
    if (!gridRef.current) return;
    // Try to measure from first rendered cell
    const el = gridRef.current.querySelector('[data-cell="0-0"]') as HTMLElement | null;
    if (el) {
      const h = el.getBoundingClientRect().height;
      if (h && Math.abs(h - rowHeight) > 0.5) setRowHeight(h);
    } else {
      // Fallback heuristics
      setRowHeight(isMobile ? 40 : 28);
    }
  }, [gridRef, isMobile, startHour, endHour]);

  useEffect(() => {
    if (!virtualizationEnabled || rowHeight <= 0) return;
    const updateVisible = () => {
      if (!gridRef.current) return;
      const rect = gridRef.current.getBoundingClientRect();
      const viewportTop = Math.max(0, -rect.top);
      const viewportBottom = Math.min(rect.height, window.innerHeight - rect.top);
      const bufferPx = rowHeight * 4;
      const startPx = Math.max(0, viewportTop - bufferPx);
      const endPx = Math.min(rect.height, viewportBottom + bufferPx);
      const start = Math.max(0, Math.floor(startPx / rowHeight));
      const end = Math.min(rows - 1, Math.ceil(endPx / rowHeight));
      setVisibleStart(start);
      setVisibleEnd(end);
    };
    updateVisible();
    window.addEventListener('scroll', updateVisible, { passive: true });
    window.addEventListener('resize', updateVisible);
    return () => {
      window.removeEventListener('scroll', updateVisible);
      window.removeEventListener('resize', updateVisible);
    };
  }, [virtualizationEnabled, rowHeight, rows]);

  const renderColumn = (dateInfo: WeekDateInfo, colIndex: number) => {
    const date = dateInfo.fullDate;
    const existing = buildDayCellSet(weekSchedule[date] || [], startHour, endHour);
    const dxActive = dragging && dragging.date === date ? dragging : null;
    const isLastColumn = isMobile ? true : colIndex === weekDates.length - 1;
    const startRow = virtualizationEnabled ? visibleStart : 0;
    const endRow = virtualizationEnabled ? visibleEnd : rows - 1;
    const topSpacer = virtualizationEnabled && rowHeight > 0 ? (
      <div style={{ height: `${startRow * rowHeight}px` }} />
    ) : null;
    const bottomSpacer = virtualizationEnabled && rowHeight > 0 ? (
      <div style={{ height: `${(rows - 1 - endRow) * rowHeight}px` }} />
    ) : null;
    return (
      <div className="relative" key={date}>
        <div role="grid" aria-label={`Availability for ${date}`}
             aria-rowcount={rows} aria-colcount={1}>
          {topSpacer}
          {Array.from({ length: endRow - startRow + 1 }).map((_, idx) => {
            const r = startRow + idx;
            const isHourLine = r % 2 === 0; // full hour rows
            const isSelected = existing.has(r);
            const inDragRange = dxActive ? r >= Math.min(dxActive.startCell, dxActive.currentCell) && r <= Math.max(dxActive.startCell, dxActive.currentCell) : false;
            const booked = isCellBooked(bookedSlots, date, r, startHour);
            const past = isPastCell(date, r);
            const isFirst = r === 0;
            const isLast = r === rows - 1;
            // Draw only bottom borders for consistency; first row adds a top border
            const bottomBorder = r % 2 === 1 ? 'border-b-2 border-gray-300' : 'border-b border-gray-200';
            const bookedTooltip = booked ? 'Booked: reservation stays; editing affects future availability' : undefined;
            const isFocused = focusDay === colIndex && focusRow === r;
            const labelHour = Math.floor(r / HALF_HOURS_PER_HOUR) + startHour;
            const labelMin = r % 2 === 1 ? '30' : '00';
            const ariaLabel = `${dateInfo.date.toLocaleDateString('en-US', { weekday: 'long' })} ${labelHour.toString().padStart(2, '0')}:${labelMin}`;
            return (
              <div
                key={r}
                onMouseDown={() => handleMouseDown(date, r)}
                onMouseEnter={() => handleMouseEnter(date, r)}
                onMouseUp={handleMouseUp}
                title={bookedTooltip}
                role="gridcell"
                aria-selected={isSelected}
                aria-label={ariaLabel}
                tabIndex={isFocused ? 0 : -1}
                onFocus={() => { setFocusDay(colIndex); setFocusRow(r); }}
                onKeyDown={(e) => handleKeyDown(e, colIndex, r, date)}
                data-cell={`${colIndex}-${r}`}
                className={`relative ${isMobile ? 'h-10' : 'h-6 sm:h-7 md:h-8'} border-l ${isLastColumn ? 'border-r' : ''} ${isFirst ? 'border-t-2 border-gray-300' : ''} ${bottomBorder} ${isSelected ? 'bg-[#EDE3FA]' : 'bg-white'} ${inDragRange ? 'ring-2 ring-[#D4B5F0] ring-inset' : ''} ${past ? 'opacity-70' : ''} cursor-pointer`}
              >
                {/* booked overlay */}
                {booked && (
                  <div className="h-full w-full bg-[repeating-linear-gradient(45deg,rgba(106,13,173,0.15),rgba(106,13,173,0.15)_6px,rgba(106,13,173,0.08)_6px,rgba(106,13,173,0.08)_12px)]"></div>
                )}
              </div>
            );
          })}
          {bottomSpacer}
        </div>
        {/* Now line */}
        {nowLine && nowLine.column === colIndex && nowLine.topPercent >= 0 && nowLine.topPercent <= 100 && (
          <div className="pointer-events-none absolute left-0 right-0" style={{ top: `${nowLine.topPercent}%` }}>
            <div className="h-px bg-red-500"></div>
            <div className="absolute -left-1 -top-2 h-2 w-2 rounded-full bg-red-500"></div>
          </div>
        )}
      </div>
    );
  };

  const dayColumns = useMemo(() => {
    if (isMobile) {
      const idx = activeDayIndex || 0;
      return [renderColumn(weekDates[idx], idx)];
    }
    return weekDates.map((d, i) => renderColumn(d, i));
  }, [weekDates, isMobile, activeDayIndex, weekSchedule, dragging, bookedSlots, nowLine]);

  return (
    <div ref={containerRef} className="relative w-full overflow-x-auto">
      <div ref={gridRef} className="grid" role="grid" aria-rowcount={rows} aria-colcount={isMobile ? 1 : weekDates.length}
           style={{ gridTemplateColumns: `60px repeat(${isMobile ? 1 : weekDates.length}, minmax(0, 1fr))` }}>
        {/* Time gutter header (no bottom border to avoid double lines) */}
        <div className="sticky left-0 top-0 z-20 bg-white/80 backdrop-blur px-2 py-1 text-sm font-medium text-gray-900">Time</div>
        {/* Day headers */}
        {weekDates.map((d, i) => (
          <div key={`hdr-${d.fullDate}`} className={`sticky top-0 z-20 bg-white/80 backdrop-blur px-2 py-1 ${isMobile && i !== (activeDayIndex || 0) ? 'hidden' : ''}`}>
            <div className="text-sm font-medium text-gray-900">{d.date.toLocaleDateString('en-US', { weekday: 'short' })}</div>
            <div className="text-xs text-gray-500">{d.dateStr}</div>
          </div>
        ))}

        {/* time rows (make the first selectable row start at top to avoid hidden row near headers) */}
        <div className="border-r border-gray-200">
          {hours.map((h, idx) => (
            <div key={h} className={`h-12 md:h-16 border-gray-200 ${idx === 0 ? 'border-t-2' : 'border-t-2'} ${idx === hours.length - 1 ? 'border-b' : ''}`}>
              <div className="text-xs text-gray-500 px-1 pt-1">{formatHour(h)}</div>
            </div>
          ))}
        </div>
        {dayColumns}
      </div>
    </div>
  );
}

function formatHour(h: number): string {
  const period = h >= 12 ? 'PM' : 'AM';
  const disp = h % 12 || 12;
  return `${disp}:00 ${period}`;
}
