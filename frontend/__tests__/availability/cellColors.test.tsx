import { render, screen } from '@testing-library/react';
import React from 'react';
import InteractiveGrid from '@/components/availability/InteractiveGrid';
import type { WeekBits, WeekDateInfo } from '@/types/availability';
import { formatDateForAPI } from '@/lib/availability/dateHelpers';

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

describe('Availability cell colors', () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  it('uses the purple fills for past and future cells', () => {
    jest.useFakeTimers();
    const current = new Date('2025-05-07T12:00:00Z'); // Wednesday
    jest.setSystemTime(current);

    const monday = new Date('2025-05-05T00:00:00Z');
    const weekDates = createWeekDates(monday);
    const weekBits: WeekBits = {};

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
    const futureCell = screen.getByRole('gridcell', { name: /Thursday 06:00/ });

    expect(pastCell.className).toContain('bg-[#EDE9FE]');
    expect(futureCell.className).toContain('bg-[#F5F3FF]');
  });
});
