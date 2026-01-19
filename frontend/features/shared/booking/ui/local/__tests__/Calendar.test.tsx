import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Calendar from '../Calendar';

// Helper to get date strings
const getDateString = (baseDate: Date, daysOffset: number): string => {
  const date = new Date(baseDate);
  date.setDate(date.getDate() + daysOffset);
  return date.toISOString().split('T')[0] ?? '';
};

describe('Calendar', () => {
  const baseDate = new Date('2024-12-15');

  const defaultProps = {
    currentMonth: baseDate,
    selectedDate: null,
    availableDates: [
      getDateString(baseDate, 0),
      getDateString(baseDate, 1),
      getDateString(baseDate, 5),
    ],
    onDateSelect: jest.fn(),
    onMonthChange: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('rendering', () => {
    it('renders month name and year', () => {
      render(<Calendar {...defaultProps} />);

      expect(screen.getByText('December 2024')).toBeInTheDocument();
    });

    it('renders prev and next month buttons', () => {
      render(<Calendar {...defaultProps} />);

      expect(screen.getByRole('button', { name: /prev/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /next/i })).toBeInTheDocument();
    });

    it('renders 14 day buttons', () => {
      render(<Calendar {...defaultProps} />);

      // Each day is a button with data-testid
      const dayButtons = screen.getAllByRole('button').filter((btn) =>
        btn.getAttribute('data-testid')?.startsWith('cal-day-')
      );
      expect(dayButtons).toHaveLength(14);
    });
  });

  describe('date selection', () => {
    it('calls onDateSelect when available date is clicked', async () => {
      const user = userEvent.setup();
      const onDateSelect = jest.fn();
      const availableDate = getDateString(baseDate, 0);

      render(
        <Calendar {...defaultProps} availableDates={[availableDate]} onDateSelect={onDateSelect} />
      );

      // Find and click the available date
      const dateButton = screen.getByTestId(`cal-day-${availableDate}`);
      await user.click(dateButton);

      expect(onDateSelect).toHaveBeenCalledWith(availableDate);
    });

    it('does not call onDateSelect for unavailable dates', async () => {
      const user = userEvent.setup();
      const onDateSelect = jest.fn();
      const unavailableDate = getDateString(baseDate, 10); // Not in availableDates

      render(
        <Calendar
          {...defaultProps}
          availableDates={[getDateString(baseDate, 0)]}
          onDateSelect={onDateSelect}
        />
      );

      // Find the unavailable date button
      const dateButton = screen.getByTestId(`cal-day-${unavailableDate}`);
      await user.click(dateButton);

      expect(onDateSelect).not.toHaveBeenCalled();
    });

    it('disables unavailable dates', () => {
      const unavailableDate = getDateString(baseDate, 10);

      render(<Calendar {...defaultProps} availableDates={[getDateString(baseDate, 0)]} />);

      const dateButton = screen.getByTestId(`cal-day-${unavailableDate}`);
      expect(dateButton).toBeDisabled();
    });
  });

  describe('selected date highlighting', () => {
    it('highlights selected date', () => {
      const selectedDate = getDateString(baseDate, 0);

      render(<Calendar {...defaultProps} selectedDate={selectedDate} />);

      const selectedButton = screen.getByTestId(`cal-day-${selectedDate}`);
      expect(selectedButton).toHaveClass('bg-blue-600', 'text-white');
    });

    it('highlights pre-selected date', () => {
      const preSelectedDate = getDateString(baseDate, 0);

      render(<Calendar {...defaultProps} preSelectedDate={preSelectedDate} />);

      const preSelectedButton = screen.getByTestId(`cal-day-${preSelectedDate}`);
      expect(preSelectedButton).toHaveClass('bg-blue-600', 'text-white');
    });
  });

  describe('month navigation', () => {
    it('calls onMonthChange with previous month when prev clicked', async () => {
      const user = userEvent.setup();
      const onMonthChange = jest.fn();

      render(<Calendar {...defaultProps} onMonthChange={onMonthChange} />);

      await user.click(screen.getByRole('button', { name: /prev/i }));

      expect(onMonthChange).toHaveBeenCalled();
      const newDate = onMonthChange.mock.calls[0][0] as Date;
      expect(newDate.getMonth()).toBe(10); // November (0-indexed)
    });

    it('calls onMonthChange with next month when next clicked', async () => {
      const user = userEvent.setup();
      const onMonthChange = jest.fn();

      render(<Calendar {...defaultProps} onMonthChange={onMonthChange} />);

      await user.click(screen.getByRole('button', { name: /next/i }));

      expect(onMonthChange).toHaveBeenCalled();
      const newDate = onMonthChange.mock.calls[0][0] as Date;
      expect(newDate.getMonth()).toBe(0); // January (0-indexed)
    });
  });

  describe('date display format', () => {
    it('displays dates in MM-DD format', () => {
      render(<Calendar {...defaultProps} />);

      // The component shows date.slice(5) which is MM-DD format
      // For December 15, it should show 12-15
      const dateButton = screen.getByTestId(`cal-day-${getDateString(baseDate, 0)}`);
      expect(dateButton.textContent).toMatch(/12-15/);
    });
  });

  describe('styling', () => {
    it('applies hover styles to available dates', () => {
      const availableDate = getDateString(baseDate, 0);

      render(<Calendar {...defaultProps} availableDates={[availableDate]} />);

      const dateButton = screen.getByTestId(`cal-day-${availableDate}`);
      expect(dateButton).toHaveClass('hover:bg-gray-50');
    });

    it('applies opacity to unavailable dates', () => {
      const unavailableDate = getDateString(baseDate, 10);

      render(<Calendar {...defaultProps} availableDates={[]} />);

      const dateButton = screen.getByTestId(`cal-day-${unavailableDate}`);
      expect(dateButton).toHaveClass('opacity-40', 'cursor-not-allowed');
    });
  });
});
