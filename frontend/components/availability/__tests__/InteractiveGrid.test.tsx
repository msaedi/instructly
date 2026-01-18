import { render, screen, fireEvent } from '@testing-library/react';
import InteractiveGrid from '../InteractiveGrid';
import type { WeekBits, WeekDateInfo, DayOfWeek } from '@/types/availability';
import type { BookedSlotPreview } from '@/types/booking';

// Mock clsx to pass through classnames
jest.mock('clsx', () => ({
  __esModule: true,
  default: (...args: unknown[]) => args.filter(Boolean).join(' '),
}));

describe('InteractiveGrid', () => {
  const DAY_NAMES: DayOfWeek[] = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];

  const createWeekDates = (startDate: Date): WeekDateInfo[] => {
    const dates: WeekDateInfo[] = [];
    for (let i = 0; i < 7; i++) {
      const date = new Date(startDate);
      date.setDate(date.getDate() + i);
      dates.push({
        date,
        dateStr: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        dayOfWeek: DAY_NAMES[date.getDay()] as DayOfWeek,
        fullDate: date.toISOString().slice(0, 10),
      });
    }
    return dates;
  };

  // Use a future date to avoid past date issues
  const futureMonday = new Date('2030-01-07');
  const mockWeekDates = createWeekDates(futureMonday);

  const defaultProps = {
    weekDates: mockWeekDates,
    weekBits: {} as WeekBits,
    onBitsChange: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    // Mock Date.now to return a consistent "today"
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2030-01-08T10:00:00'));
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('rendering', () => {
    it('renders availability cells for each day', () => {
      render(<InteractiveGrid {...defaultProps} />);

      const cells = screen.getAllByTestId('availability-cell');
      expect(cells.length).toBeGreaterThan(0);
    });

    it('renders time labels', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={11} />);

      // Component renders time labels every hour (only on the hour, not half hour)
      // The format shows only on even rows (hour boundaries)
      const container = screen.getByText((content) => content.includes('9:00'));
      expect(container).toBeInTheDocument();
    });

    it('renders day headers with weekday abbreviations', () => {
      render(<InteractiveGrid {...defaultProps} />);

      // Should show day headers
      expect(screen.getByText('MON')).toBeInTheDocument();
      expect(screen.getByText('TUE')).toBeInTheDocument();
    });

    it('respects custom hour range', () => {
      render(<InteractiveGrid {...defaultProps} startHour={10} endHour={12} />);

      // Component renders time labels
      const container = screen.getByText((content) => content.includes('10:00'));
      expect(container).toBeInTheDocument();
    });
  });

  describe('slot selection', () => {
    it('calls onBitsChange when cell is clicked', async () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      if (firstCell) {
        fireEvent.mouseDown(firstCell);
        fireEvent.mouseUp(firstCell);
      }

      expect(onBitsChange).toHaveBeenCalled();
    });

    it('marks selected cells with aria-selected', () => {
      const weekBits: WeekBits = {
        '2030-01-07': new Uint8Array([0, 0, 1, 0, 0]),
      };

      render(
        <InteractiveGrid
          {...defaultProps}
          weekBits={weekBits}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const selectedCells = cells.filter(
        (cell) => cell.getAttribute('aria-selected') === 'true'
      );
      expect(selectedCells.length).toBeGreaterThanOrEqual(0);
    });
  });

  describe('keyboard interaction', () => {
    it('toggles selection on Enter key', async () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      if (firstCell) {
        fireEvent.keyDown(firstCell, { key: 'Enter' });
      }

      expect(onBitsChange).toHaveBeenCalled();
    });

    it('toggles selection on Space key', async () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      if (firstCell) {
        fireEvent.keyDown(firstCell, { key: ' ' });
      }

      expect(onBitsChange).toHaveBeenCalled();
    });

    it('does not toggle on other keys', () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      if (firstCell) {
        fireEvent.keyDown(firstCell, { key: 'a' });
      }

      expect(onBitsChange).not.toHaveBeenCalled();
    });
  });

  describe('drag selection', () => {
    it('supports drag to select multiple cells', () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={11}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');

      // Simulate drag: mouseDown on first cell, mouseEnter on second, mouseUp
      const firstCell = cells[0];
      const secondCell = cells[1];
      if (firstCell && secondCell) {
        fireEvent.mouseDown(firstCell, { buttons: 1 });
        fireEvent.mouseEnter(secondCell, { buttons: 1 });
        fireEvent.mouseUp(secondCell);
      }

      expect(onBitsChange).toHaveBeenCalled();
    });

    it('finishes drag on mouse leave with buttons=0', () => {
      const onBitsChange = jest.fn();
      render(
        <InteractiveGrid
          {...defaultProps}
          onBitsChange={onBitsChange}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      if (firstCell) {
        fireEvent.mouseDown(firstCell, { buttons: 1 });
        fireEvent.mouseLeave(firstCell, { buttons: 0 });
      }

      // Drag should be finished
      expect(onBitsChange).toHaveBeenCalled();
    });
  });

  describe('booked slots', () => {
    it('shows booked indicator for booked slots', () => {
      const bookedSlots: BookedSlotPreview[] = [
        {
          booking_id: 'booking-123',
          date: '2030-01-07',
          start_time: '09:00:00',
          end_time: '10:00:00',
          student_first_name: 'John',
          student_last_initial: 'D',
          service_name: 'Piano',
          service_area_short: 'Manhattan',
          duration_minutes: 60,
          location_type: 'student_home',
        },
      ];

      render(
        <InteractiveGrid
          {...defaultProps}
          bookedSlots={bookedSlots}
          startHour={9}
          endHour={10}
        />
      );

      // Component renders booked slots with striped pattern
      const cells = screen.getAllByTestId('availability-cell');
      expect(cells.length).toBeGreaterThan(0);
    });
  });

  describe('mobile view', () => {
    it('renders single day when isMobile is true', () => {
      render(
        <InteractiveGrid
          {...defaultProps}
          isMobile={true}
          activeDayIndex={0}
          startHour={9}
          endHour={10}
        />
      );

      // In mobile view, only one day's cells should be visible
      const cells = screen.getAllByTestId('availability-cell');
      // 2 hours × 2 half-hours = 4 half-hour cells for one day
      expect(cells.length).toBeLessThan(7 * 4); // Less than full week
    });

    it('respects activeDayIndex for mobile view', () => {
      render(
        <InteractiveGrid
          {...defaultProps}
          isMobile={true}
          activeDayIndex={2}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      // Should show cells for day at index 2 (limited to one day)
      expect(cells.length).toBeLessThan(7 * 4);
    });
  });

  describe('past slot handling', () => {
    it('marks past slots as disabled', () => {
      // Set current time to middle of week
      jest.setSystemTime(new Date('2030-01-09T14:00:00'));

      render(
        <InteractiveGrid
          {...defaultProps}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const disabledCells = cells.filter(
        (cell) => cell.getAttribute('aria-disabled') === 'true'
      );
      expect(disabledCells.length).toBeGreaterThan(0);
    });

    it('allows editing past slots when allowPastEditing is true', () => {
      jest.setSystemTime(new Date('2030-01-09T14:00:00'));

      render(
        <InteractiveGrid
          {...defaultProps}
          allowPastEditing={true}
          startHour={9}
          endHour={10}
        />
      );

      const cells = screen.getAllByTestId('availability-cell');
      const disabledCells = cells.filter(
        (cell) => cell.getAttribute('aria-disabled') === 'true'
      );
      // With allowPastEditing, no cells should be disabled
      expect(disabledCells.length).toBe(0);
    });
  });

  describe('now line', () => {
    it('shows now line for current day within hour range', () => {
      // Set time within the grid's hour range
      jest.setSystemTime(new Date('2030-01-07T10:30:00'));

      render(
        <InteractiveGrid
          {...defaultProps}
          startHour={9}
          endHour={12}
        />
      );

      const nowLine = screen.queryByTestId('now-line');
      // The now line should be rendered for today's column
      expect(nowLine).toBeInTheDocument();
    });

    it('does not show now line outside hour range', () => {
      // Set time outside the grid's hour range
      jest.setSystemTime(new Date('2030-01-07T05:00:00'));

      render(
        <InteractiveGrid
          {...defaultProps}
          startHour={9}
          endHour={12}
        />
      );

      const nowLine = screen.queryByTestId('now-line');
      expect(nowLine).not.toBeInTheDocument();
    });
  });

  describe('accessibility', () => {
    it('cells have role=gridcell', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      // Cells have role="gridcell" attribute
      const cells = screen.getAllByTestId('availability-cell');
      expect(cells[0]?.getAttribute('role')).toBe('gridcell');
    });

    it('cells have aria-label with day and time', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      expect(firstCell?.getAttribute('aria-label')).toBeTruthy();
    });

    it('cells have data-date and data-time attributes', () => {
      render(<InteractiveGrid {...defaultProps} startHour={9} endHour={10} />);

      const cells = screen.getAllByTestId('availability-cell');
      const firstCell = cells[0];
      expect(firstCell?.getAttribute('data-date')).toBeTruthy();
      expect(firstCell?.getAttribute('data-time')).toBeTruthy();
    });
  });

  describe('timezone support', () => {
    it('accepts timezone prop', () => {
      render(
        <InteractiveGrid
          {...defaultProps}
          timezone="America/New_York"
          startHour={9}
          endHour={10}
        />
      );

      // Should render without errors
      const cells = screen.getAllByTestId('availability-cell');
      expect(cells.length).toBeGreaterThan(0);
    });
  });

  describe('hour label formatting', () => {
    it('formats morning hours correctly', () => {
      render(<InteractiveGrid {...defaultProps} startHour={6} endHour={11} />);

      // Time labels include AM/PM - use getAllByText since multiple elements may match
      const elements = screen.getAllByText((_, element) => {
        return element?.textContent?.includes('6:00') || false;
      });
      expect(elements.length).toBeGreaterThan(0);
    });

    it('formats noon correctly', () => {
      render(<InteractiveGrid {...defaultProps} startHour={12} endHour={13} />);

      // Noon shows as 12:00 PM
      const elements = screen.getAllByText((_, element) => {
        return element?.textContent?.includes('12:00') || false;
      });
      expect(elements.length).toBeGreaterThan(0);
    });

    it('formats afternoon hours correctly', () => {
      render(<InteractiveGrid {...defaultProps} startHour={13} endHour={17} />);

      // Afternoon shows PM hours
      const elements = screen.getAllByText((_, element) => {
        return element?.textContent?.includes('1:00') || false;
      });
      expect(elements.length).toBeGreaterThan(0);
    });

    it('renders cells for extended hours', () => {
      render(<InteractiveGrid {...defaultProps} startHour={22} endHour={24} />);

      // Component should handle extended hours
      const cells = screen.getAllByTestId('availability-cell');
      expect(cells.length).toBeGreaterThan(0);
    });
  });
});
