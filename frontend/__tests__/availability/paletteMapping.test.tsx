/**
 * Test suite to lock palette mapping behavior for availability grid cells.
 *
 * Locks the behavior that:
 * - past + selected → bg-[#EDE3FA] + fade opacity-70
 * - future + selected → bg-[#EDE3FA] without fade
 * - past + unselected → bg-gray-50 opacity-70
 * - future + unselected → bg-white
 * - These classes appear last in className so palette wins over earlier classes
 */

import { render, screen } from '@testing-library/react';
import React from 'react';
import InteractiveGrid from '@/components/availability/InteractiveGrid';
import type { WeekBits, WeekDateInfo } from '@/types/availability';
import { formatDateForAPI } from '@/lib/availability/dateHelpers';
import { fromWindows } from '@/lib/calendar/bitset';

const createWeekDates = (weekStart: Date): WeekDateInfo[] =>
  Array.from({ length: 7 }, (_value, index) => {
    const date = new Date(weekStart);
    date.setDate(weekStart.getDate() + index);
    return {
      date,
      dateStr: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      dayOfWeek: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'][index] as WeekDateInfo['dayOfWeek'],
      fullDate: formatDateForAPI(date),
    };
  });

describe('Availability palette mapping', () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  it('applies correct classes for past + selected cells', () => {
    jest.useFakeTimers();
    // Use local dates to match formatDateForAPI behavior
    const current = new Date(2025, 4, 7, 12, 0, 0); // May 7, 2025, Wednesday, 12:00 PM local
    jest.setSystemTime(current);

    const monday = new Date(2025, 4, 5, 0, 0, 0); // May 5, 2025, Monday (past)
    const weekDates = createWeekDates(monday);

    // Use the fullDate from weekDates to ensure exact match
    const mondayDateStr = weekDates[0]!.fullDate;

    // Set bits for Monday 06:00-07:00 (selected)
    // fromWindows('06:00:00') sets slot index 12 (6*2 + 0)
    // getSlotIndex(6, 0) = idx(6, 0) = 12, so they match
    const weekBits: WeekBits = {
      [mondayDateStr]: fromWindows([{ start_time: '06:00:00', end_time: '07:00:00' }]),
    };

    render(
      <InteractiveGrid
        weekDates={weekDates}
        weekBits={weekBits}
        onBitsChange={jest.fn()}
        timezone="UTC"
        startHour={6}
        endHour={7}
      />
    );

    // Find the Monday 06:00 cell (row 0 when startHour=6)
    const pastCell = screen.getByRole('gridcell', { name: /Monday 06:00/ });
    const className = pastCell.className;
    const ariaSelected = pastCell.getAttribute('aria-selected');

    // Note: Setting bits correctly requires matching the date format and slot calculation
    // This test documents the expected behavior: when a past cell IS selected,
    // it should have bg-[#EDE3FA] and opacity-70
    expect(ariaSelected).toBe('true');
    expect(className).toContain('bg-[#EDE3FA]');
    expect(className).toContain('opacity-70');
  });

  it('applies correct classes for future + selected cells', () => {
    jest.useFakeTimers();
    // Use local dates to match formatDateForAPI behavior
    const current = new Date(2025, 4, 7, 12, 0, 0); // May 7, 2025, Wednesday, 12:00 PM local
    jest.setSystemTime(current);

    const monday = new Date(2025, 4, 5, 0, 0, 0); // May 5, 2025, Monday
    const weekDates = createWeekDates(monday);

    // Use the fullDate from weekDates for Thursday (index 3) to ensure exact match
    const thursdayDateStr = weekDates[3]!.fullDate;

    // Set bits for Thursday 06:00-07:00 (future, selected)
    const weekBits: WeekBits = {
      [thursdayDateStr]: fromWindows([{ start_time: '06:00:00', end_time: '07:00:00' }]),
    };

    render(
      <InteractiveGrid
        weekDates={weekDates}
        weekBits={weekBits}
        onBitsChange={jest.fn()}
        timezone="UTC"
        startHour={6}
        endHour={7}
      />
    );

    const futureCell = screen.getByRole('gridcell', { name: /Thursday 06:00/ });
    const className = futureCell.className;
    const ariaSelected = futureCell.getAttribute('aria-selected');

    // Note: This test documents expected behavior for selected future cells
    expect(ariaSelected).toBe('true');
    expect(className).toContain('bg-[#EDE3FA]');
    expect(className).not.toContain('opacity-70');
  });

  it('applies correct classes for past + unselected cells', () => {
    jest.useFakeTimers();
    // Use local dates to match formatDateForAPI behavior
    const current = new Date(2025, 4, 7, 12, 0, 0); // May 7, 2025, Wednesday, 12:00 PM local
    jest.setSystemTime(current);

    const monday = new Date(2025, 4, 5, 0, 0, 0); // May 5, 2025, Monday (past)
    const weekDates = createWeekDates(monday);
    const weekBits: WeekBits = {}; // No bits = unselected

    render(
      <InteractiveGrid
        weekDates={weekDates}
        weekBits={weekBits}
        onBitsChange={jest.fn()}
        timezone="UTC"
        startHour={6}
        endHour={7}
      />
    );

    const pastCell = screen.getByRole('gridcell', { name: /Monday 06:00/ });
    const className = pastCell.className;

    // Should contain bg-gray-50
    expect(className).toContain('bg-gray-50');
    // Should contain opacity-70 for fade
    expect(className).toContain('opacity-70');
  });

  it('applies correct classes for future + unselected cells', () => {
    jest.useFakeTimers();
    // Use local dates to match formatDateForAPI behavior
    const current = new Date(2025, 4, 7, 12, 0, 0); // May 7, 2025, Wednesday, 12:00 PM local
    jest.setSystemTime(current);

    const monday = new Date(2025, 4, 5, 0, 0, 0); // May 5, 2025, Monday
    const weekDates = createWeekDates(monday);
    const weekBits: WeekBits = {}; // No bits = unselected

    render(
      <InteractiveGrid
        weekDates={weekDates}
        weekBits={weekBits}
        onBitsChange={jest.fn()}
        timezone="UTC"
        startHour={6}
        endHour={7}
      />
    );

    const futureCell = screen.getByRole('gridcell', { name: /Thursday 06:00/ });
    const className = futureCell.className;

    // Should contain bg-white
    expect(className).toContain('bg-white');
    // Should NOT contain opacity-70 (no fade for future)
    expect(className).not.toContain('opacity-70');
  });

  it('ensures palette classes appear last in className', () => {
    jest.useFakeTimers();
    // Use local dates to match formatDateForAPI behavior
    const current = new Date(2025, 4, 7, 12, 0, 0); // May 7, 2025, Wednesday, 12:00 PM local
    jest.setSystemTime(current);

    const monday = new Date(2025, 4, 5, 0, 0, 0); // May 5, 2025, Monday
    const weekDates = createWeekDates(monday);
    const thursdayDateStr = weekDates[3]!.fullDate; // Thursday (index 3)
    const weekBits: WeekBits = {
      [thursdayDateStr]: fromWindows([{ start_time: '06:00:00', end_time: '07:00:00' }]),
    };

    render(
      <InteractiveGrid
        weekDates={weekDates}
        weekBits={weekBits}
        onBitsChange={jest.fn()}
        timezone="UTC"
        startHour={6}
        endHour={7}
      />
    );

    const selectedCell = screen.getByRole('gridcell', { name: /Thursday 06:00/ });
    const className = selectedCell.className;
    const classes = className.split(/\s+/);

    // Find palette-related classes
    const paletteClasses = classes.filter((cls) =>
      cls.includes('bg-') || cls.includes('opacity-')
    );

    expect(paletteClasses.length).toBeGreaterThan(0);
    expect(classes.slice(-3)).toEqual(['bg-[#EDE3FA]', 'dark:bg-purple-500/25', 'opacity-100']);
  });
});
