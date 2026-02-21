import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BookingList } from '../BookingList';

jest.mock('@/components/lessons/video/JoinLessonButton', () => ({
  JoinLessonButton: (props: Record<string, unknown>) => (
    <div data-testid="join-lesson-button" data-booking-id={props.bookingId} />
  ),
}));

describe('BookingList', () => {
  it('renders loading cards when loading', () => {
    render(
      <BookingList
        data={[]}
        isLoading
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    expect(screen.getByTestId('booking-list-loading')).toBeInTheDocument();
  });

  it('renders an empty state when no bookings are present', () => {
    render(
      <BookingList
        data={[]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    expect(screen.getByTestId('booking-list-empty')).toBeInTheDocument();
    expect(screen.getByText(/no bookings/i)).toBeInTheDocument();
  });

  it('shows in-progress status and formatted times', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-06T10:30:00'));

    render(
      <BookingList
        data={[
          {
            id: 'b1',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            end_time: '11:00:00',
            status: 'CONFIRMED',
            service_name: 'Piano',
            total_price: 85,
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    expect(screen.getByText(/in progress/i)).toBeInTheDocument();
    expect(screen.getByText('$85.00')).toBeInTheDocument();
    expect(screen.getByText(/mon, jan 6/i)).toBeInTheDocument();
    expect(screen.getByText(/10:00 am/i)).toBeInTheDocument();

    jest.useRealTimers();
  });

  it('shows action buttons for past confirmed bookings', async () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-06T12:30:00'));
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    const onComplete = jest.fn();
    const onNoShow = jest.fn();

    render(
      <BookingList
        data={[
          {
            id: 'b2',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            end_time: '11:00:00',
            status: 'CONFIRMED',
            service_name: 'Guitar',
            student: { first_name: 'Ava', last_name: 'Lee' },
            instructor: { first_name: 'Sam', last_initial: 'Q' },
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
        onComplete={onComplete}
        onNoShow={onNoShow}
      />
    );

    await user.click(screen.getByTestId('mark-complete-button'));
    await user.click(screen.getByTestId('report-no-show-button'));

    expect(onComplete).toHaveBeenCalledWith('b2');
    expect(onNoShow).toHaveBeenCalledWith('b2');
    jest.useRealTimers();
  });

  it('disables action buttons when an action is pending', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-06T12:30:00'));

    render(
      <BookingList
        data={[
          {
            id: 'b3',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            end_time: '11:00:00',
            status: 'CONFIRMED',
            service_name: 'Yoga',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
        onComplete={jest.fn()}
        onNoShow={jest.fn()}
        isActionPending
      />
    );

    expect(screen.getByTestId('mark-complete-button')).toBeDisabled();
    expect(screen.getByTestId('report-no-show-button')).toBeDisabled();
    jest.useRealTimers();
  });

  it('falls back to raw date strings when parsing fails', () => {
    render(
      <BookingList
        data={[
          {
            id: 'b4',
            booking_date: 'not-a-date',
            start_time: 'invalid',
            status: 'CONFIRMED',
            service_name: 'Voice',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    expect(screen.getByText('not-a-date')).toBeInTheDocument();
    expect(screen.getByText('invalid')).toBeInTheDocument();
  });

  it('falls back to raw status when STATUS_LABELS has no match', () => {
    render(
      <BookingList
        data={[
          {
            id: 'b5',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            status: 'UNKNOWN_STATUS',
            service_name: 'Piano',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    // STATUS_LABELS has no 'UNKNOWN_STATUS', so falls back to booking.status
    expect(screen.getByText('UNKNOWN_STATUS')).toBeInTheDocument();
  });

  it('falls back to "Pending" when status is null/undefined', () => {
    render(
      <BookingList
        data={[
          {
            id: 'b6',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            status: null as unknown as string,
            service_name: 'Piano',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    // STATUS_LABELS[null] is undefined, booking.status is null, so ?? 'Pending'
    expect(screen.getByText('Pending')).toBeInTheDocument();
  });

  it('falls back to default badge style for unknown status', () => {
    render(
      <BookingList
        data={[
          {
            id: 'b7',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            status: 'WEIRD_STATUS',
            service_name: 'Guitar',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    const badge = screen.getByText('WEIRD_STATUS');
    expect(badge).toHaveClass('bg-gray-100', 'text-gray-700');
  });

  it('shows first name only when last_name is missing', () => {
    render(
      <BookingList
        data={[
          {
            id: 'b8',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            status: 'CONFIRMED',
            service_name: 'Voice',
            student: { first_name: 'Alice', last_name: null },
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    expect(screen.getByText('Alice')).toBeInTheDocument();
  });

  it('shows "Student" when student has no first_name', () => {
    render(
      <BookingList
        data={[
          {
            id: 'b9',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            status: 'CONFIRMED',
            service_name: 'Drums',
            student: { first_name: null, last_name: null },
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    expect(screen.getByText('Student')).toBeInTheDocument();
  });

  it('shows "Student" when student object is undefined', () => {
    render(
      <BookingList
        data={[
          {
            id: 'b10',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            status: 'CONFIRMED',
            service_name: 'Trumpet',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    expect(screen.getByText('Student')).toBeInTheDocument();
  });

  it('shows "You" when instructor is not provided', () => {
    render(
      <BookingList
        data={[
          {
            id: 'b11',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            status: 'CONFIRMED',
            service_name: 'Bass',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    expect(screen.getByText('You')).toBeInTheDocument();
  });

  it('shows instructor name without last_initial when missing', () => {
    render(
      <BookingList
        data={[
          {
            id: 'b12',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            status: 'CONFIRMED',
            service_name: 'Sax',
            instructor: { first_name: 'Maria', last_initial: null },
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    expect(screen.getByText('Maria')).toBeInTheDocument();
    // Should NOT show "Maria ." or "Maria null."
    expect(screen.queryByText(/Maria\s+\./)).not.toBeInTheDocument();
  });

  it('shows instructor with last_initial when provided', () => {
    render(
      <BookingList
        data={[
          {
            id: 'b13',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            status: 'CONFIRMED',
            service_name: 'Cello',
            instructor: { first_name: 'Sam', last_initial: 'Q' },
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    expect(screen.getByText('Sam Q.')).toBeInTheDocument();
  });

  it('does not show action buttons when callbacks are not provided', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-06T12:30:00'));

    render(
      <BookingList
        data={[
          {
            id: 'b14',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            end_time: '11:00:00',
            status: 'CONFIRMED',
            service_name: 'Piano',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    // Past booking but no onComplete/onNoShow callbacks
    expect(screen.queryByTestId('mark-complete-button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('report-no-show-button')).not.toBeInTheDocument();
    expect(screen.queryByText('Action Required')).not.toBeInTheDocument();

    jest.useRealTimers();
  });

  it('shows only mark complete button when onNoShow is not provided', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-06T12:30:00'));

    render(
      <BookingList
        data={[
          {
            id: 'b15',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            end_time: '11:00:00',
            status: 'CONFIRMED',
            service_name: 'Piano',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
        onComplete={jest.fn()}
      />
    );

    expect(screen.getByTestId('mark-complete-button')).toBeInTheDocument();
    expect(screen.queryByTestId('report-no-show-button')).not.toBeInTheDocument();

    jest.useRealTimers();
  });

  it('shows only report no-show button when onComplete is not provided', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-06T12:30:00'));

    render(
      <BookingList
        data={[
          {
            id: 'b16',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            end_time: '11:00:00',
            status: 'CONFIRMED',
            service_name: 'Piano',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
        onNoShow={jest.fn()}
      />
    );

    expect(screen.queryByTestId('mark-complete-button')).not.toBeInTheDocument();
    expect(screen.getByTestId('report-no-show-button')).toBeInTheDocument();

    jest.useRealTimers();
  });

  it('shows "Pending rate" when total_price is null', () => {
    render(
      <BookingList
        data={[
          {
            id: 'b17',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            status: 'CONFIRMED',
            service_name: 'Piano',
            total_price: null,
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    expect(screen.getByText('Pending rate')).toBeInTheDocument();
  });

  it('shows "Pending rate" when total_price is 0 (falsy)', () => {
    render(
      <BookingList
        data={[
          {
            id: 'b18',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            status: 'CONFIRMED',
            service_name: 'Piano',
            total_price: 0,
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    // 0 is falsy, so it shows "Pending rate"
    expect(screen.getByText('Pending rate')).toBeInTheDocument();
  });

  it('does not show in-progress for CONFIRMED booking without end_time', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-06T10:30:00'));

    render(
      <BookingList
        data={[
          {
            id: 'b19',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            status: 'CONFIRMED',
            service_name: 'Piano',
            // no end_time
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    // isInProgress returns false when end_time is missing
    expect(screen.getByText('Confirmed')).toBeInTheDocument();
    expect(screen.queryByText(/in progress/i)).not.toBeInTheDocument();

    jest.useRealTimers();
  });

  it('does not show action buttons for non-CONFIRMED status even if past', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-06T12:30:00'));

    render(
      <BookingList
        data={[
          {
            id: 'b20',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            end_time: '11:00:00',
            status: 'COMPLETED',
            service_name: 'Piano',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
        onComplete={jest.fn()}
        onNoShow={jest.fn()}
      />
    );

    // needsAction returns false for COMPLETED
    expect(screen.queryByText('Action Required')).not.toBeInTheDocument();

    jest.useRealTimers();
  });

  it('handles data as null by showing empty state', () => {
    render(
      <BookingList
        data={null as unknown as []}
        emptyTitle="Nothing here"
        emptyDescription="Check back soon"
      />
    );

    expect(screen.getByText('Nothing here')).toBeInTheDocument();
  });

  it('uses custom data-testid', () => {
    render(
      <BookingList
        data={[]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
        data-testid="custom-list"
      />
    );

    expect(screen.getByTestId('custom-list-empty')).toBeInTheDocument();
  });

  it('does not show in-progress for future CONFIRMED booking', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-06T08:00:00'));

    render(
      <BookingList
        data={[
          {
            id: 'b21',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            end_time: '11:00:00',
            status: 'CONFIRMED',
            service_name: 'Guitar',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    // Future booking, not in-progress yet
    expect(screen.getByText('Confirmed')).toBeInTheDocument();
    expect(screen.queryByText(/in progress/i)).not.toBeInTheDocument();

    jest.useRealTimers();
  });

  it('does not show needsAction buttons for CONFIRMED booking without end_time', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-06T12:30:00'));

    render(
      <BookingList
        data={[
          {
            id: 'b22',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            status: 'CONFIRMED',
            service_name: 'Violin',
            // no end_time
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
        onComplete={jest.fn()}
        onNoShow={jest.fn()}
      />
    );

    // needsAction returns false when end_time is missing
    expect(screen.queryByText('Action Required')).not.toBeInTheDocument();

    jest.useRealTimers();
  });

  it('calls onViewDetails when a booking card is clicked', async () => {
    const onViewDetails = jest.fn();
    const user = userEvent.setup();

    render(
      <BookingList
        data={[
          {
            id: 'b-click',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            status: 'CONFIRMED',
            service_name: 'Piano',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
        onViewDetails={onViewDetails}
      />
    );

    await user.click(screen.getByTestId('booking-card'));
    expect(onViewDetails).toHaveBeenCalledWith('b-click');
  });

  it('does not call onViewDetails when action buttons are clicked', async () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-06T12:30:00'));
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    const onViewDetails = jest.fn();
    const onComplete = jest.fn();

    render(
      <BookingList
        data={[
          {
            id: 'b-stop',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            end_time: '11:00:00',
            status: 'CONFIRMED',
            service_name: 'Guitar',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
        onViewDetails={onViewDetails}
        onComplete={onComplete}
      />
    );

    await user.click(screen.getByTestId('mark-complete-button'));
    expect(onComplete).toHaveBeenCalledWith('b-stop');
    expect(onViewDetails).not.toHaveBeenCalled();

    jest.useRealTimers();
  });

  it('renders JoinLessonButton when join_opens_at is provided', () => {
    render(
      <BookingList
        data={[
          {
            id: 'b23',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            end_time: '11:00:00',
            status: 'CONFIRMED',
            service_name: 'Piano',
            join_opens_at: '2025-01-06T09:55:00Z',
            join_closes_at: '2025-01-06T10:15:00Z',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    expect(screen.getByTestId('join-lesson-button')).toBeInTheDocument();
  });

  it('does not render JoinLessonButton when join_opens_at is null', () => {
    render(
      <BookingList
        data={[
          {
            id: 'b24',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            end_time: '11:00:00',
            status: 'CONFIRMED',
            service_name: 'Guitar',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    expect(screen.queryByTestId('join-lesson-button')).not.toBeInTheDocument();
  });

  it('does not call onViewDetails when JoinLessonButton area is clicked', async () => {
    const onViewDetails = jest.fn();
    const user = userEvent.setup();

    render(
      <BookingList
        data={[
          {
            id: 'b-join-stop',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            end_time: '11:00:00',
            status: 'CONFIRMED',
            service_name: 'Piano',
            join_opens_at: '2025-01-06T09:55:00Z',
            join_closes_at: '2025-01-06T10:15:00Z',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
        onViewDetails={onViewDetails}
      />
    );

    await user.click(screen.getByTestId('join-lesson-button'));
    expect(onViewDetails).not.toHaveBeenCalled();
  });

  it('renders JoinLessonButton alongside action buttons', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-06T12:30:00'));

    render(
      <BookingList
        data={[
          {
            id: 'b25',
            booking_date: '2025-01-06',
            start_time: '10:00:00',
            end_time: '11:00:00',
            status: 'CONFIRMED',
            service_name: 'Drums',
            join_opens_at: '2025-01-06T09:55:00Z',
            join_closes_at: '2025-01-06T10:15:00Z',
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
        onComplete={jest.fn()}
        onNoShow={jest.fn()}
      />
    );

    expect(screen.getByTestId('join-lesson-button')).toBeInTheDocument();
    expect(screen.getByTestId('mark-complete-button')).toBeInTheDocument();

    jest.useRealTimers();
  });
});
