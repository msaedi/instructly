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
}: InteractiveGridProps) {
  const hours = useMemo(() => Array.from({ length: endHour - startHour }, (_, i) => startHour + i), [startHour, endHour]);
  const rows = useMemo(() => (endHour - startHour) * HALF_HOURS_PER_HOUR, [startHour, endHour]);
  const [dragging, setDragging] = useState<null | { date: string; mode: 'add' | 'remove'; startCell: number; currentCell: number }>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Now-line positioning updates every 5 minutes
  const [nowTick, setNowTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setNowTick((x) => x + 1), 5 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  const todayIdx = useMemo(() => {
    const todayISO = new Date().toISOString().slice(0, 10);
    return weekDates.findIndex((d) => d.fullDate === todayISO);
  }, [weekDates, nowTick]);

  const nowLine = useMemo(() => {
    if (todayIdx < 0) return null;
    const now = new Date();
    const hour = now.getHours();
    const minutes = now.getMinutes();
    const halfCells = (hour - startHour) * HALF_HOURS_PER_HOUR + (minutes >= 30 ? 1 : 0) + (minutes % 30) / 30;
    const perc = Math.max(0, Math.min(halfCells / rows, 1));
    return { column: todayIdx, topPercent: perc * 100 };
  }, [todayIdx, startHour, rows, nowTick]);

  const isPastCell = (date: string, cellIdx: number) => {
    const now = new Date();
    const [y, m, d] = date.split('-').map((n) => parseInt(n));
    const h = Math.floor(cellIdx / HALF_HOURS_PER_HOUR) + startHour;
    const min = cellIdx % 2 === 1 ? 30 : 0;
    const cellTime = new Date(y, m - 1, d, h, min, 0, 0);
    return cellTime < now;
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

  const renderColumn = (dateInfo: WeekDateInfo, colIndex: number) => {
    const date = dateInfo.fullDate;
    const existing = buildDayCellSet(weekSchedule[date] || [], startHour, endHour);
    const dxActive = dragging && dragging.date === date ? dragging : null;
    const isLastColumn = isMobile ? true : colIndex === weekDates.length - 1;
    return (
      <div className="relative" key={date}>
        <div role="grid" aria-label={`Availability for ${date}`}>
          {Array.from({ length: rows }).map((_, r) => {
            const isHourLine = r % 2 === 0; // full hour rows
            const isSelected = existing.has(r);
            const inDragRange = dxActive ? r >= Math.min(dxActive.startCell, dxActive.currentCell) && r <= Math.max(dxActive.startCell, dxActive.currentCell) : false;
            const booked = isCellBooked(bookedSlots, date, r, startHour);
            const past = isPastCell(date, r);
            const isFirst = r === 0;
            const isLast = r === rows - 1;
            // Draw only bottom borders for consistency; first row adds a top border
            const bottomBorder = r % 2 === 1 ? 'border-b-2 border-gray-300' : 'border-b border-gray-200';
            return (
              <div
                key={r}
                onMouseDown={() => handleMouseDown(date, r)}
                onMouseEnter={() => handleMouseEnter(date, r)}
                onMouseUp={handleMouseUp}
                className={`relative h-6 sm:h-7 md:h-8 border-l ${isLastColumn ? 'border-r' : ''} ${isFirst ? 'border-t-2 border-gray-300' : ''} ${bottomBorder} ${isSelected ? 'bg-[#EDE3FA]' : 'bg-white'} ${inDragRange ? 'ring-2 ring-[#D4B5F0] ring-inset' : ''} ${past ? 'opacity-70' : ''}`}
              >
                {/* booked overlay */}
                {booked && (
                  <div className="h-full w-full bg-[repeating-linear-gradient(45deg,rgba(106,13,173,0.12),rgba(106,13,173,0.12)_6px,rgba(106,13,173,0.06)_6px,rgba(106,13,173,0.06)_12px)]"></div>
                )}
              </div>
            );
          })}
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
      <div className="grid" style={{ gridTemplateColumns: `60px repeat(${isMobile ? 1 : weekDates.length}, minmax(0, 1fr))` }}>
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
