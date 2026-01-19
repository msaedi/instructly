import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Calendar from '../Calendar';

describe('Calendar', () => {
  const defaultProps = {
    currentMonth: new Date('2024-01-15'),
    selectedDate: null,
    availableDates: ['2024-01-15', '2024-01-16', '2024-01-20', '2024-01-25'],
    onDateSelect: jest.fn(),
    onMonthChange: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    // Mock today as Jan 10, 2024
    jest.useFakeTimers().setSystemTime(new Date('2024-01-10T12:00:00Z'));
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('Month display', () => {
    it('renders current month and year', () => {
      render(<Calendar {...defaultProps} />);
      expect(screen.getByText('January 2024')).toBeInTheDocument();
    });

    it('renders day headers', () => {
      render(<Calendar {...defaultProps} />);
      expect(screen.getByText('SUN')).toBeInTheDocument();
      expect(screen.getByText('MON')).toBeInTheDocument();
      expect(screen.getByText('TUE')).toBeInTheDocument();
      expect(screen.getByText('WED')).toBeInTheDocument();
      expect(screen.getByText('THU')).toBeInTheDocument();
      expect(screen.getByText('FRI')).toBeInTheDocument();
      expect(screen.getByText('SAT')).toBeInTheDocument();
    });
  });

  describe('Month navigation', () => {
    it('navigates to next month when next button clicked', () => {
      const onMonthChange = jest.fn();
      render(<Calendar {...defaultProps} onMonthChange={onMonthChange} />);

      fireEvent.click(screen.getByLabelText('Next month'));
      expect(onMonthChange).toHaveBeenCalledTimes(1);

      const newMonth = onMonthChange.mock.calls[0][0] as Date;
      expect(newMonth.getMonth()).toBe(1); // February
      expect(newMonth.getFullYear()).toBe(2024);
    });

    it('navigates to previous month when previous button clicked', () => {
      const onMonthChange = jest.fn();
      render(<Calendar {...defaultProps} onMonthChange={onMonthChange} />);

      fireEvent.click(screen.getByLabelText('Previous month'));
      expect(onMonthChange).toHaveBeenCalledTimes(1);

      const newMonth = onMonthChange.mock.calls[0][0] as Date;
      expect(newMonth.getMonth()).toBe(11); // December
      expect(newMonth.getFullYear()).toBe(2023);
    });

    it('disables previous button when current month is in the past', () => {
      jest.useFakeTimers().setSystemTime(new Date('2024-02-15T12:00:00Z'));

      render(
        <Calendar {...defaultProps} currentMonth={new Date('2024-01-15')} />
      );

      const prevButton = screen.getByLabelText('Previous month');
      expect(prevButton).toBeDisabled();
    });

    it('enables previous button when current month is current', () => {
      render(<Calendar {...defaultProps} />);
      const prevButton = screen.getByLabelText('Previous month');
      expect(prevButton).not.toBeDisabled();
    });
  });

  describe('Date rendering', () => {
    it('renders dates of the month', () => {
      render(<Calendar {...defaultProps} />);
      // Check some specific dates
      expect(screen.getByTestId('cal-day-2024-01-15')).toHaveTextContent('15');
      expect(screen.getByTestId('cal-day-2024-01-20')).toHaveTextContent('20');
    });

    it('highlights available dates', () => {
      render(<Calendar {...defaultProps} />);
      const availableDate = screen.getByTestId('cal-day-2024-01-15');
      expect(availableDate).not.toBeDisabled();
    });

    it('disables unavailable dates', () => {
      render(<Calendar {...defaultProps} />);
      const unavailableDate = screen.getByTestId('cal-day-2024-01-17');
      expect(unavailableDate).toBeDisabled();
    });

    it('disables past dates', () => {
      render(
        <Calendar
          {...defaultProps}
          availableDates={['2024-01-05', '2024-01-15']}
        />
      );
      const pastDate = screen.getByTestId('cal-day-2024-01-05');
      expect(pastDate).toBeDisabled();
    });
  });

  describe('Date selection', () => {
    it('calls onDateSelect when available date is clicked', () => {
      const onDateSelect = jest.fn();
      render(<Calendar {...defaultProps} onDateSelect={onDateSelect} />);

      fireEvent.click(screen.getByTestId('cal-day-2024-01-15'));
      expect(onDateSelect).toHaveBeenCalledWith('2024-01-15');
    });

    it('does not call onDateSelect when unavailable date is clicked', () => {
      const onDateSelect = jest.fn();
      render(<Calendar {...defaultProps} onDateSelect={onDateSelect} />);

      fireEvent.click(screen.getByTestId('cal-day-2024-01-17'));
      expect(onDateSelect).not.toHaveBeenCalled();
    });

    it('does not call onDateSelect when past date is clicked', () => {
      const onDateSelect = jest.fn();
      render(
        <Calendar
          {...defaultProps}
          availableDates={['2024-01-05', '2024-01-15']}
          onDateSelect={onDateSelect}
        />
      );

      fireEvent.click(screen.getByTestId('cal-day-2024-01-05'));
      expect(onDateSelect).not.toHaveBeenCalled();
    });

    it('highlights selected date', () => {
      render(<Calendar {...defaultProps} selectedDate="2024-01-15" />);
      const selectedDate = screen.getByTestId('cal-day-2024-01-15');
      expect(selectedDate).toHaveClass('bg-[#7E22CE]');
      expect(selectedDate).toHaveAttribute('aria-pressed', 'true');
    });

    it('sets aria-current on selected date', () => {
      render(<Calendar {...defaultProps} selectedDate="2024-01-15" />);
      const selectedDate = screen.getByTestId('cal-day-2024-01-15');
      expect(selectedDate).toHaveAttribute('aria-current', 'date');
    });
  });

  describe('Pre-selected date', () => {
    it('auto-selects pre-selected date if available', async () => {
      const onDateSelect = jest.fn();
      render(
        <Calendar
          {...defaultProps}
          preSelectedDate="2024-01-15"
          selectedDate={null}
          onDateSelect={onDateSelect}
        />
      );

      await waitFor(() => {
        expect(onDateSelect).toHaveBeenCalledWith('2024-01-15');
      });
    });

    it('does not auto-select if pre-selected date is not available', async () => {
      const onDateSelect = jest.fn();
      render(
        <Calendar
          {...defaultProps}
          preSelectedDate="2024-01-17"
          selectedDate={null}
          onDateSelect={onDateSelect}
        />
      );

      await waitFor(() => {
        expect(onDateSelect).not.toHaveBeenCalled();
      });
    });

    it('does not auto-select if date is already selected', async () => {
      const onDateSelect = jest.fn();
      render(
        <Calendar
          {...defaultProps}
          preSelectedDate="2024-01-15"
          selectedDate="2024-01-20"
          onDateSelect={onDateSelect}
        />
      );

      await waitFor(() => {
        expect(onDateSelect).not.toHaveBeenCalled();
      });
    });
  });

  describe('Today styling', () => {
    it('applies bold styling to today', () => {
      render(<Calendar {...defaultProps} />);
      const today = screen.getByTestId('cal-day-2024-01-10');
      expect(today).toHaveClass('font-bold');
    });
  });

  describe('Different months', () => {
    it('renders February correctly', () => {
      render(
        <Calendar
          {...defaultProps}
          currentMonth={new Date('2024-02-15')}
          availableDates={['2024-02-14', '2024-02-15']}
        />
      );
      expect(screen.getByText('February 2024')).toBeInTheDocument();
    });

    it('renders December correctly', () => {
      render(
        <Calendar
          {...defaultProps}
          currentMonth={new Date('2024-12-15')}
          availableDates={['2024-12-15', '2024-12-25']}
        />
      );
      expect(screen.getByText('December 2024')).toBeInTheDocument();
    });
  });
});
