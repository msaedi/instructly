import React from 'react';
import { render, screen } from '@testing-library/react';
import WeekView from '../WeekView';
import type { WeekBits, WeekDateInfo, DayOfWeek } from '@/types/availability';
import type { BookedSlotPreview, LocationType } from '@/types/booking';

// Mock InteractiveGrid
const mockInteractiveGrid = jest.fn();
jest.mock('@/components/availability/InteractiveGrid', () => {
  const MockInteractiveGrid = (props: Record<string, unknown>) => {
    mockInteractiveGrid(props);
    return <div data-testid="interactive-grid" />;
  };
  MockInteractiveGrid.displayName = 'MockInteractiveGrid';
  return MockInteractiveGrid;
});

// Mock bitset
jest.mock('@/lib/calendar/bitset', () => ({
  newEmptyBits: jest.fn(() => new Uint8Array(6)),
}));

describe('WeekView', () => {
  const createWeekDateInfo = (dayOfWeek: DayOfWeek, dateStr: string): WeekDateInfo => ({
    date: new Date(dateStr),
    dateStr: dateStr.substring(5), // e.g., "01-19"
    dayOfWeek,
    fullDate: dateStr,
  });

  const mockWeekDates: WeekDateInfo[] = [
    createWeekDateInfo('monday', '2026-01-19'),
    createWeekDateInfo('tuesday', '2026-01-20'),
    createWeekDateInfo('wednesday', '2026-01-21'),
    createWeekDateInfo('thursday', '2026-01-22'),
    createWeekDateInfo('friday', '2026-01-23'),
    createWeekDateInfo('saturday', '2026-01-24'),
    createWeekDateInfo('sunday', '2026-01-25'),
  ];

  const mockWeekBits: WeekBits = {
    monday: new Uint8Array(6),
    tuesday: new Uint8Array(6),
    wednesday: new Uint8Array(6),
    thursday: new Uint8Array(6),
    friday: new Uint8Array(6),
    saturday: new Uint8Array(6),
    sunday: new Uint8Array(6),
  };

  const defaultProps = {
    weekDates: mockWeekDates,
    weekBits: mockWeekBits,
    onBitsChange: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders InteractiveGrid component', () => {
    render(<WeekView {...defaultProps} />);
    expect(screen.getByTestId('interactive-grid')).toBeInTheDocument();
  });

  it('passes weekDates to InteractiveGrid', () => {
    render(<WeekView {...defaultProps} />);
    expect(mockInteractiveGrid).toHaveBeenCalledWith(
      expect.objectContaining({
        weekDates: mockWeekDates,
      })
    );
  });

  it('passes weekBits to InteractiveGrid', () => {
    render(<WeekView {...defaultProps} />);
    expect(mockInteractiveGrid).toHaveBeenCalledWith(
      expect.objectContaining({
        weekBits: mockWeekBits,
      })
    );
  });

  it('passes onBitsChange to InteractiveGrid', () => {
    const onBitsChange = jest.fn();
    render(<WeekView {...defaultProps} onBitsChange={onBitsChange} />);
    expect(mockInteractiveGrid).toHaveBeenCalledWith(
      expect.objectContaining({
        onBitsChange,
      })
    );
  });

  it('passes bookedSlots when provided', () => {
    const bookedSlots: BookedSlotPreview[] = [
      {
        booking_id: '01K2GY3VEVJWKZDVH5HMNXEVRD',
        date: '2026-01-20',
        start_time: '10:00',
        end_time: '11:00',
        student_first_name: 'John',
        student_last_initial: 'D',
        service_name: 'Piano Lesson',
        service_area_short: 'UWS',
        duration_minutes: 60,
        location_type: 'in_person' as LocationType,
      },
    ];
    render(<WeekView {...defaultProps} bookedSlots={bookedSlots} />);
    expect(mockInteractiveGrid).toHaveBeenCalledWith(
      expect.objectContaining({
        bookedSlots,
      })
    );
  });

  it('does not pass bookedSlots when not provided', () => {
    render(<WeekView {...defaultProps} />);
    const calledProps = mockInteractiveGrid.mock.calls[0]?.[0];
    expect(calledProps).not.toHaveProperty('bookedSlots');
  });

  it('passes startHour when provided', () => {
    render(<WeekView {...defaultProps} startHour={8} />);
    expect(mockInteractiveGrid).toHaveBeenCalledWith(
      expect.objectContaining({
        startHour: 8,
      })
    );
  });

  it('passes endHour when provided', () => {
    render(<WeekView {...defaultProps} endHour={20} />);
    expect(mockInteractiveGrid).toHaveBeenCalledWith(
      expect.objectContaining({
        endHour: 20,
      })
    );
  });

  it('passes timezone when provided', () => {
    render(<WeekView {...defaultProps} timezone="America/New_York" />);
    expect(mockInteractiveGrid).toHaveBeenCalledWith(
      expect.objectContaining({
        timezone: 'America/New_York',
      })
    );
  });

  it('passes isMobile when provided', () => {
    render(<WeekView {...defaultProps} isMobile={true} />);
    expect(mockInteractiveGrid).toHaveBeenCalledWith(
      expect.objectContaining({
        isMobile: true,
      })
    );
  });

  it('passes activeDayIndex when provided', () => {
    render(<WeekView {...defaultProps} activeDayIndex={2} />);
    expect(mockInteractiveGrid).toHaveBeenCalledWith(
      expect.objectContaining({
        activeDayIndex: 2,
      })
    );
  });

  it('passes onActiveDayChange when provided', () => {
    const onActiveDayChange = jest.fn();
    render(<WeekView {...defaultProps} onActiveDayChange={onActiveDayChange} />);
    expect(mockInteractiveGrid).toHaveBeenCalledWith(
      expect.objectContaining({
        onActiveDayChange,
      })
    );
  });

  it('passes allowPastEditing when provided', () => {
    render(<WeekView {...defaultProps} allowPastEditing={true} />);
    expect(mockInteractiveGrid).toHaveBeenCalledWith(
      expect.objectContaining({
        allowPastEditing: true,
      })
    );
  });

  it('does not pass optional props when not provided', () => {
    render(<WeekView {...defaultProps} />);
    const calledProps = mockInteractiveGrid.mock.calls[0]?.[0];
    expect(calledProps).not.toHaveProperty('startHour');
    expect(calledProps).not.toHaveProperty('endHour');
    expect(calledProps).not.toHaveProperty('timezone');
    expect(calledProps).not.toHaveProperty('isMobile');
    expect(calledProps).not.toHaveProperty('activeDayIndex');
    expect(calledProps).not.toHaveProperty('onActiveDayChange');
    expect(calledProps).not.toHaveProperty('allowPastEditing');
  });
});
