import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ApplyToFutureWeeksModal from '../ApplyToFutureWeeksModal';

// Mock the date helpers
jest.mock('@/lib/availability/dateHelpers', () => ({
  formatDateForAPI: jest.fn((date: Date) => date.toISOString().split('T')[0]),
  getEndDateForOption: jest.fn((option: string, customDate: string) => {
    if (option === 'end-of-year') return '2025-12-31';
    if (option === 'indefinitely') return '2026-01-15';
    return customDate;
  }),
}));

// Mock the logger
jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
  },
}));

describe('ApplyToFutureWeeksModal', () => {
  const currentWeekStart = new Date('2025-01-15');

  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    onConfirm: jest.fn(),
    hasAvailability: true,
    currentWeekStart,
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders when open', () => {
    render(<ApplyToFutureWeeksModal {...defaultProps} />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('does not render when isOpen is false', () => {
    render(<ApplyToFutureWeeksModal {...defaultProps} isOpen={false} />);

    expect(screen.queryByText('Apply Schedule to Future Weeks')).not.toBeInTheDocument();
  });

  it('shows copy message when hasAvailability is true', () => {
    render(<ApplyToFutureWeeksModal {...defaultProps} />);

    expect(
      screen.getByText(/copy the current week's schedule/i)
    ).toBeInTheDocument();
  });

  it('shows clear message when hasAvailability is false', () => {
    render(<ApplyToFutureWeeksModal {...defaultProps} hasAvailability={false} />);

    expect(
      screen.getByText(/clear the schedule for future weeks/i)
    ).toBeInTheDocument();
  });

  it('shows booking preservation note', () => {
    render(<ApplyToFutureWeeksModal {...defaultProps} />);

    expect(
      screen.getByText(/Existing bookings in future weeks will be preserved/i)
    ).toBeInTheDocument();
  });

  it('has end-of-year option selected by default', () => {
    render(<ApplyToFutureWeeksModal {...defaultProps} />);

    const endOfYearRadio = screen.getByLabelText(/until end of this year/i);
    expect(endOfYearRadio).toBeChecked();
  });

  it('allows selecting specific date option', async () => {
    const user = userEvent.setup();
    render(<ApplyToFutureWeeksModal {...defaultProps} />);

    const specificDateRadio = screen.getByLabelText(/until specific date/i);
    await user.click(specificDateRadio);

    expect(specificDateRadio).toBeChecked();
    expect(screen.getByLabelText(/select end date/i)).toBeInTheDocument();
  });

  it('allows selecting indefinitely option', async () => {
    const user = userEvent.setup();
    render(<ApplyToFutureWeeksModal {...defaultProps} />);

    const indefinitelyRadio = screen.getByLabelText(/apply indefinitely/i);
    await user.click(indefinitelyRadio);

    expect(indefinitelyRadio).toBeChecked();
  });

  it('calls onConfirm with correct date for end-of-year option', async () => {
    const user = userEvent.setup();
    render(<ApplyToFutureWeeksModal {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: /apply & save/i }));

    expect(defaultProps.onConfirm).toHaveBeenCalledWith('2025-12-31');
  });

  it('calls onConfirm with correct date for indefinitely option', async () => {
    const user = userEvent.setup();
    render(<ApplyToFutureWeeksModal {...defaultProps} />);

    const indefinitelyRadio = screen.getByLabelText(/apply indefinitely/i);
    await user.click(indefinitelyRadio);
    await user.click(screen.getByRole('button', { name: /apply & save/i }));

    expect(defaultProps.onConfirm).toHaveBeenCalledWith('2026-01-15');
  });

  it('calls onClose after confirm', async () => {
    const user = userEvent.setup();
    render(<ApplyToFutureWeeksModal {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: /apply & save/i }));

    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('calls onClose when Cancel button is clicked', async () => {
    const user = userEvent.setup();
    render(<ApplyToFutureWeeksModal {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('resets option to default on close', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<ApplyToFutureWeeksModal {...defaultProps} />);

    // Change to indefinitely
    await user.click(screen.getByLabelText(/apply indefinitely/i));
    expect(screen.getByLabelText(/apply indefinitely/i)).toBeChecked();

    // Close and reopen
    await user.click(screen.getByRole('button', { name: /cancel/i }));
    rerender(<ApplyToFutureWeeksModal {...defaultProps} isOpen={false} />);
    rerender(<ApplyToFutureWeeksModal {...defaultProps} isOpen={true} />);

    // Should reset to default
    expect(screen.getByLabelText(/until end of this year/i)).toBeChecked();
  });

  it('shows date picker when specific date option is selected', async () => {
    const user = userEvent.setup();
    render(<ApplyToFutureWeeksModal {...defaultProps} />);

    // Date picker should not be visible initially
    expect(screen.queryByLabelText(/select end date/i)).not.toBeInTheDocument();

    // Select specific date option
    await user.click(screen.getByLabelText(/until specific date/i));

    // Date picker should now be visible
    expect(screen.getByLabelText(/select end date/i)).toBeInTheDocument();
  });

  it('allows changing custom date when date option is selected', async () => {
    const user = userEvent.setup();
    render(<ApplyToFutureWeeksModal {...defaultProps} />);

    await user.click(screen.getByLabelText(/until specific date/i));

    const dateInput = screen.getByLabelText(/select end date/i);
    fireEvent.change(dateInput, { target: { value: '2025-06-15' } });

    await user.click(screen.getByRole('button', { name: /apply & save/i }));

    expect(defaultProps.onConfirm).toHaveBeenCalledWith('2025-06-15');
  });

  it('triggers end-of-year onChange when switching back from another option', async () => {
    const user = userEvent.setup();
    render(<ApplyToFutureWeeksModal {...defaultProps} />);

    // First switch away from end-of-year to indefinitely
    const indefinitelyRadio = screen.getByLabelText(/apply indefinitely/i);
    await user.click(indefinitelyRadio);
    expect(indefinitelyRadio).toBeChecked();

    // Now explicitly click back to end-of-year, triggering the onChange handler
    const endOfYearRadio = screen.getByLabelText(/until end of this year/i);
    await user.click(endOfYearRadio);
    expect(endOfYearRadio).toBeChecked();

    // Verify the option was applied by confirming with the end-of-year date
    await user.click(screen.getByRole('button', { name: /apply & save/i }));
    expect(defaultProps.onConfirm).toHaveBeenCalledWith('2025-12-31');
  });

  describe('getMinDate', () => {
    it('sets date picker min to 7 days after currentWeekStart', async () => {
      const user = userEvent.setup();
      // currentWeekStart is Jan 15
      render(<ApplyToFutureWeeksModal {...defaultProps} />);

      await user.click(screen.getByLabelText(/until specific date/i));

      const dateInput = screen.getByLabelText(/select end date/i);
      // min should be Jan 15 + 7 days = Jan 22, formatted as 2025-01-22
      expect(dateInput).toHaveAttribute('min', '2025-01-22');
    });

    it('handles month boundary crossing (Jan 28 -> Feb 4)', async () => {
      const user = userEvent.setup();
      const weekStart = new Date('2025-01-28');
      render(
        <ApplyToFutureWeeksModal {...defaultProps} currentWeekStart={weekStart} />
      );

      await user.click(screen.getByLabelText(/until specific date/i));

      const dateInput = screen.getByLabelText(/select end date/i);
      // Jan 28 + 7 = Feb 4
      expect(dateInput).toHaveAttribute('min', '2025-02-04');
    });

    it('handles year boundary crossing (Dec 29 -> Jan 5)', async () => {
      const user = userEvent.setup();
      const weekStart = new Date('2025-12-29');
      render(
        <ApplyToFutureWeeksModal {...defaultProps} currentWeekStart={weekStart} />
      );

      await user.click(screen.getByLabelText(/until specific date/i));

      const dateInput = screen.getByLabelText(/select end date/i);
      // Dec 29 + 7 = Jan 5 next year
      expect(dateInput).toHaveAttribute('min', '2026-01-05');
    });

    it('handles leap year boundary (Feb 22 -> Mar 1 in non-leap year)', async () => {
      const user = userEvent.setup();
      // 2025 is not a leap year, so Feb has 28 days
      const weekStart = new Date('2025-02-22');
      render(
        <ApplyToFutureWeeksModal {...defaultProps} currentWeekStart={weekStart} />
      );

      await user.click(screen.getByLabelText(/until specific date/i));

      const dateInput = screen.getByLabelText(/select end date/i);
      // Feb 22 + 7 = Mar 1 (in non-leap year)
      expect(dateInput).toHaveAttribute('min', '2025-03-01');
    });

    it('handles leap year correctly (Feb 22 -> Feb 29 in leap year)', async () => {
      const user = userEvent.setup();
      // 2024 is a leap year
      const weekStart = new Date('2024-02-22');
      render(
        <ApplyToFutureWeeksModal {...defaultProps} currentWeekStart={weekStart} />
      );

      await user.click(screen.getByLabelText(/until specific date/i));

      const dateInput = screen.getByLabelText(/select end date/i);
      // Feb 22 + 7 = Feb 29 (leap year)
      expect(dateInput).toHaveAttribute('min', '2024-02-29');
    });
  });
});
