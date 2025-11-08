import { render, screen } from '@testing-library/react';
import React from 'react';
import InteractiveGrid from '@/components/availability/InteractiveGrid';
import type { WeekBits, WeekDateInfo } from '@/types/availability';
import { AVAILABILITY_CONSTANTS } from '@/types/availability';
import { formatDateForAPI } from '@/lib/availability/dateHelpers';

const createWeekDates = (weekStart: Date): WeekDateInfo[] => {
  return Array.from({ length: 7 }, (_value, index) => {
    const date = new Date(weekStart);
    date.setDate(weekStart.getDate() + index);
    return {
      date,
      dateStr: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      dayOfWeek: AVAILABILITY_CONSTANTS.DAYS_OF_WEEK[index] as WeekDateInfo['dayOfWeek'],
      fullDate: formatDateForAPI(date),
    };
  });
};

const defaultProps = {
  weekBits: {} as WeekBits,
  onBitsChange: jest.fn(),
  bookedSlots: [],
  startHour: 6,
  endHour: 22,
  allowPastEditing: true,
};

describe('InteractiveGrid now indicator', () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  it('renders the now line when current time is within the teaching window', () => {
    jest.useFakeTimers();
    const monday = new Date('2025-05-05T00:00:00Z');
    jest.setSystemTime(new Date('2025-05-05T12:15:00Z'));

    render(
      <InteractiveGrid
        weekDates={createWeekDates(monday)}
        {...defaultProps}
        timezone="UTC"
      />
    );

    expect(screen.getByTestId('now-line')).toBeInTheDocument();
  });

  it('hides the now line when outside the teaching window', () => {
    jest.useFakeTimers();
    const monday = new Date('2025-05-05T00:00:00Z');
    jest.setSystemTime(new Date('2025-05-05T02:00:00Z'));

    render(
      <InteractiveGrid
        weekDates={createWeekDates(monday)}
        {...defaultProps}
        timezone="UTC"
      />
    );

    expect(screen.queryByTestId('now-line')).toBeNull();
  });
});
