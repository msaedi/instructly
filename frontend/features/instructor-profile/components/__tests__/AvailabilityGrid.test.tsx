import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AvailabilityGrid } from '../AvailabilityGrid';
import { useInstructorAvailability } from '@/hooks/queries/useInstructorAvailability';

jest.mock('@/hooks/queries/useInstructorAvailability', () => ({
  useInstructorAvailability: jest.fn(),
}));

const mockUseInstructorAvailability = useInstructorAvailability as jest.Mock;

describe('AvailabilityGrid', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders a loading skeleton when weekStart is missing', () => {
    mockUseInstructorAvailability.mockReturnValue({ data: null, isLoading: true, error: null });

    const { container } = render(
      <AvailabilityGrid
        instructorId="1"
        weekStart={null}
        onWeekChange={jest.fn()}
        selectedSlot={null}
        onSelectSlot={jest.fn()}
      />
    );

    expect(screen.getByText(/availability/i)).toBeInTheDocument();
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });

  it('falls back to mock availability when the query errors', async () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date(2025, 0, 6, 7, 0, 0));
    const onSelectSlot = jest.fn();
    mockUseInstructorAvailability.mockReturnValue({ data: null, isLoading: false, error: new Error('fail') });

    const { container } = render(
      <AvailabilityGrid
        instructorId="1"
        weekStart={new Date(2025, 0, 6)}
        onWeekChange={jest.fn()}
        selectedSlot={null}
        onSelectSlot={onSelectSlot}
      />
    );

    const button = container.querySelector('[data-testid="time-slot-Mon-8am"]') as HTMLButtonElement | null;
    expect(button).toBeInTheDocument();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    await user.click(button!);

    expect(onSelectSlot).toHaveBeenCalledWith('2025-01-06', '8am', 60, 120);
    jest.useRealTimers();
  });

  it('selects real availability slots and calculates duration', async () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date(2025, 0, 6, 8, 0, 0));
    const onSelectSlot = jest.fn();
    mockUseInstructorAvailability.mockReturnValue({
      data: {
        availability_by_date: {
          '2025-01-06': { available_slots: [{ start_time: '10:00', end_time: '12:00' }] },
        },
      },
      isLoading: false,
      error: null,
    });

    render(
      <AvailabilityGrid
        instructorId="1"
        weekStart={new Date(2025, 0, 6)}
        onWeekChange={jest.fn()}
        selectedSlot={null}
        onSelectSlot={onSelectSlot}
      />
    );

    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    await user.click(screen.getByLabelText(/select mon at 10am/i));

    expect(onSelectSlot).toHaveBeenCalledWith('2025-01-06', '10:00', 60, 120);
    jest.useRealTimers();
  });

  it('hides slots that violate minimum advance booking hours', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date(2025, 0, 6, 10, 30, 0));
    mockUseInstructorAvailability.mockReturnValue({
      data: {
        availability_by_date: {
          '2025-01-06': { available_slots: [{ start_time: '11:00', end_time: '12:00' }] },
        },
      },
      isLoading: false,
      error: null,
    });

    const { container } = render(
      <AvailabilityGrid
        instructorId="1"
        weekStart={new Date(2025, 0, 6)}
        onWeekChange={jest.fn()}
        selectedSlot={null}
        onSelectSlot={jest.fn()}
        minAdvanceBookingHours={2}
      />
    );

    expect(container.querySelector('[data-testid="time-slot-Mon-11am"]')).not.toBeInTheDocument();
    jest.useRealTimers();
  });

  it('navigates weeks with the next button and disables previous at today', async () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date(2025, 0, 6, 9, 0, 0));
    const onWeekChange = jest.fn();
    mockUseInstructorAvailability.mockReturnValue({
      data: { availability_by_date: {} },
      isLoading: false,
      error: null,
    });

    render(
      <AvailabilityGrid
        instructorId="1"
        weekStart={new Date(2025, 0, 6)}
        onWeekChange={onWeekChange}
        selectedSlot={null}
        onSelectSlot={jest.fn()}
      />
    );

    expect(screen.getByRole('button', { name: /prev/i })).toBeDisabled();

    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    await user.click(screen.getByRole('button', { name: /next/i }));

    expect(onWeekChange).toHaveBeenCalledWith(new Date(2025, 0, 13));
    jest.useRealTimers();
  });

  it('auto-aligns to the earliest available date when out of range', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date(2025, 1, 10, 9, 0, 0));
    const onWeekChange = jest.fn();
    mockUseInstructorAvailability.mockReturnValue({
      data: { availability_by_date: { '2025-01-20': { available_slots: [] } } },
      isLoading: false,
      error: null,
    });

    render(
      <AvailabilityGrid
        instructorId="1"
        weekStart={new Date(2025, 1, 10)}
        onWeekChange={onWeekChange}
        selectedSlot={null}
        onSelectSlot={jest.fn()}
      />
    );

    expect(onWeekChange).toHaveBeenCalledWith(new Date(2025, 0, 20));
    jest.useRealTimers();
  });
});
