import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BookingList } from '../BookingList';

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
});
