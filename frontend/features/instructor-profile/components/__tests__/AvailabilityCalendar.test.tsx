import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AvailabilityCalendar } from '../AvailabilityCalendar';
import { useInstructorAvailability } from '@/hooks/queries/useInstructorAvailability';
import { logger } from '@/lib/logger';

jest.mock('@/hooks/queries/useInstructorAvailability', () => ({
  useInstructorAvailability: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: { info: jest.fn() },
}));

const mockUseInstructorAvailability = useInstructorAvailability as jest.Mock;

describe('AvailabilityCalendar', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });
  afterEach(() => {
    jest.useRealTimers();
  });

  it('renders a loading skeleton', () => {
    mockUseInstructorAvailability.mockReturnValue({ data: null, isLoading: true, error: null });

    const { container } = render(<AvailabilityCalendar instructorId="1" />);

    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });

  it('shows an error state and reload action', async () => {
    mockUseInstructorAvailability.mockReturnValue({ data: null, isLoading: false, error: new Error('fail') });
    render(<AvailabilityCalendar instructorId="1" />);

    expect(screen.getByText(/unable to load availability/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('renders slots and handles selection', async () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date(2025, 0, 6, 9, 0, 0));
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    const onSelectSlot = jest.fn();
    mockUseInstructorAvailability.mockReturnValue({
      data: {
        availability_by_date: {
          '2025-01-06': {
            available_slots: [
              { start_time: '10:00', end_time: '11:00' },
              { start_time: '11:00', end_time: '12:00' },
              { start_time: '12:00', end_time: '13:00' },
              { start_time: '13:00', end_time: '14:00' },
            ],
          },
          '2025-01-07': { available_slots: [], is_blackout: true },
        },
      },
      isLoading: false,
      error: null,
    });

    render(<AvailabilityCalendar instructorId="1" onSelectSlot={onSelectSlot} />);

    await user.click(screen.getByTestId('time-slot-2025-01-06-10:00'));

    expect(onSelectSlot).toHaveBeenCalledWith('2025-01-06', '10:00');
    expect(screen.getByText('+1')).toBeInTheDocument();
    expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
  });

  it('logs when the full calendar button is clicked', async () => {
    const user = userEvent.setup();
    mockUseInstructorAvailability.mockReturnValue({
      data: { availability_by_date: {} },
      isLoading: false,
      error: null,
    });

    render(<AvailabilityCalendar instructorId="1" />);

    await user.click(screen.getByRole('button', { name: /view full calendar/i }));
    expect(logger.info).toHaveBeenCalledWith('View full calendar clicked');
  });
});
