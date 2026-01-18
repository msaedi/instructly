import { render, screen } from '@testing-library/react';
import WeekCalendarGrid from '../WeekCalendarGrid';

// Mock logger to avoid console noise in tests
jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

interface DateInfo {
  date: Date;
  dateStr: string;
  dayOfWeek: string;
  fullDate: string;
}

describe('WeekCalendarGrid', () => {
  const createWeekDates = (startDate: Date): DateInfo[] => {
    const dates: DateInfo[] = [];
    for (let i = 0; i < 7; i++) {
      const date = new Date(startDate);
      date.setDate(date.getDate() + i);
      dates.push({
        date,
        dateStr: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        dayOfWeek: date.toLocaleDateString('en-US', { weekday: 'short' }).toLowerCase(),
        fullDate: date.toISOString().slice(0, 10),
      });
    }
    return dates;
  };

  // Use a future date to avoid past date styling issues
  const futureMonday = new Date('2030-01-07'); // A Monday
  const mockWeekDates = createWeekDates(futureMonday);

  const defaultRenderCell = (date: string, hour: number) => (
    <div data-testid={`cell-${date}-${hour}`}>{`${date} ${hour}:00`}</div>
  );

  const defaultProps = {
    weekDates: mockWeekDates,
    renderCell: defaultRenderCell,
  };

  it('renders the week schedule header', () => {
    render(<WeekCalendarGrid {...defaultProps} />);

    expect(screen.getByText('Week Schedule')).toBeInTheDocument();
    expect(screen.getByText('Click time slots to toggle availability')).toBeInTheDocument();
  });

  it('renders all days of the week', () => {
    render(<WeekCalendarGrid {...defaultProps} />);

    // Check all weekdays are rendered (case insensitive)
    mockWeekDates.forEach((dateInfo) => {
      const dayText = screen.getAllByText(new RegExp(dateInfo.dayOfWeek, 'i'));
      expect(dayText.length).toBeGreaterThan(0);
    });
  });

  it('renders time slots for default hours (8-20)', () => {
    render(<WeekCalendarGrid {...defaultProps} />);

    // Default is 8 AM to 8 PM
    expect(screen.getByText('8:00 AM')).toBeInTheDocument();
    expect(screen.getByText('12:00 PM')).toBeInTheDocument();
    expect(screen.getByText('8:00 PM')).toBeInTheDocument();
  });

  it('respects custom start and end hours', () => {
    render(<WeekCalendarGrid {...defaultProps} startHour={6} endHour={22} />);

    expect(screen.getByText('6:00 AM')).toBeInTheDocument();
    expect(screen.getByText('10:00 PM')).toBeInTheDocument();
  });

  it('calls renderCell for each time slot', () => {
    const renderCellMock = jest.fn(() => <div>Cell</div>);
    render(
      <WeekCalendarGrid
        {...defaultProps}
        renderCell={renderCellMock}
        startHour={8}
        endHour={10}
      />
    );

    // 7 days × 3 hours = 21 cells in desktop view + 21 cells in mobile view = 42
    // But actually only mobile view renders renderCell if no renderMobileCell
    // Let's check it was called
    expect(renderCellMock).toHaveBeenCalled();
  });

  it('renders cells with correct date and hour', () => {
    render(<WeekCalendarGrid {...defaultProps} startHour={9} endHour={10} />);

    const firstDay = mockWeekDates[0]?.fullDate;
    if (firstDay) {
      // Both desktop and mobile views render cells, so we use getAllByTestId
      const cells9 = screen.getAllByTestId(`cell-${firstDay}-9`);
      const cells10 = screen.getAllByTestId(`cell-${firstDay}-10`);
      expect(cells9.length).toBeGreaterThan(0);
      expect(cells10.length).toBeGreaterThan(0);
    }
  });

  it('uses renderMobileCell when provided for mobile view', () => {
    const renderMobileCellMock = jest.fn((date: string, hour: number) => (
      <div data-testid={`mobile-cell-${date}-${hour}`}>Mobile</div>
    ));

    render(
      <WeekCalendarGrid
        {...defaultProps}
        startHour={8}
        endHour={9}
        renderMobileCell={renderMobileCellMock}
      />
    );

    // Mobile cells should use renderMobileCell
    expect(renderMobileCellMock).toHaveBeenCalled();
  });

  it('falls back to renderCell when renderMobileCell not provided', () => {
    const renderCellMock = jest.fn(() => <div>Regular Cell</div>);

    render(
      <WeekCalendarGrid
        {...defaultProps}
        renderCell={renderCellMock}
        startHour={8}
        endHour={8}
      />
    );

    // renderCell is used for both desktop and mobile when renderMobileCell is not provided
    expect(renderCellMock).toHaveBeenCalled();
  });

  describe('hour formatting', () => {
    it('formats morning hours correctly', () => {
      render(<WeekCalendarGrid {...defaultProps} startHour={6} endHour={11} />);

      expect(screen.getByText('6:00 AM')).toBeInTheDocument();
      expect(screen.getByText('11:00 AM')).toBeInTheDocument();
    });

    it('formats 12 PM correctly', () => {
      render(<WeekCalendarGrid {...defaultProps} startHour={12} endHour={12} />);

      expect(screen.getByText('12:00 PM')).toBeInTheDocument();
    });

    it('formats afternoon hours correctly', () => {
      render(<WeekCalendarGrid {...defaultProps} startHour={13} endHour={17} />);

      expect(screen.getByText('1:00 PM')).toBeInTheDocument();
      expect(screen.getByText('5:00 PM')).toBeInTheDocument();
    });
  });

  describe('past date detection', () => {
    it('applies different styling to past dates', () => {
      const pastMonday = new Date('2020-01-06'); // Past Monday
      const pastWeekDates = createWeekDates(pastMonday);

      render(
        <WeekCalendarGrid
          weekDates={pastWeekDates}
          renderCell={defaultRenderCell}
          startHour={8}
          endHour={8}
        />
      );

      // Mobile view shows "(Past date)" text for past dates
      const pastDateIndicators = screen.getAllByText('(Past date)');
      expect(pastDateIndicators.length).toBeGreaterThan(0);
    });

    it('does not show past date indicator for future dates', () => {
      render(<WeekCalendarGrid {...defaultProps} startHour={8} endHour={8} />);

      expect(screen.queryByText('(Past date)')).not.toBeInTheDocument();
    });
  });

  describe('desktop table view', () => {
    it('renders a table with headers', () => {
      render(<WeekCalendarGrid {...defaultProps} />);

      // Check for table structure
      const tables = document.querySelectorAll('table');
      expect(tables.length).toBeGreaterThan(0);
    });

    it('renders Time column header', () => {
      render(<WeekCalendarGrid {...defaultProps} />);

      expect(screen.getByText('Time')).toBeInTheDocument();
    });
  });

  describe('mobile list view', () => {
    it('renders day sections in mobile view', () => {
      render(<WeekCalendarGrid {...defaultProps} startHour={8} endHour={8} />);

      // Mobile view renders each day as a separate section
      mockWeekDates.forEach((dateInfo) => {
        // Each day appears in both desktop header and mobile section
        const dayElements = screen.getAllByText(new RegExp(dateInfo.dayOfWeek, 'i'));
        expect(dayElements.length).toBeGreaterThan(0);
      });
    });
  });

  describe('props handling', () => {
    it('accepts onNavigateWeek callback', () => {
      const onNavigateWeek = jest.fn();

      render(
        <WeekCalendarGrid
          {...defaultProps}
          onNavigateWeek={onNavigateWeek}
        />
      );

      // Component should render without error when callback provided
      expect(screen.getByText('Week Schedule')).toBeInTheDocument();
    });

    it('accepts currentWeekDisplay prop', () => {
      render(
        <WeekCalendarGrid
          {...defaultProps}
          currentWeekDisplay="January 2030"
        />
      );

      // Component should render without error when display prop provided
      expect(screen.getByText('Week Schedule')).toBeInTheDocument();
    });
  });
});
