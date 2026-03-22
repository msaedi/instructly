import { render, screen } from '@testing-library/react';
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

    const emptyState = screen.getByTestId('booking-list-empty');
    expect(emptyState).toBeInTheDocument();
    expect(emptyState).toHaveClass('border-dashed', 'insta-surface-card');
    expect(screen.getByText(/no bookings/i)).toBeInTheDocument();
  });

  it('handles null data by showing the empty state', () => {
    render(
      <BookingList
        data={null as unknown as []}
        emptyTitle="Nothing here"
        emptyDescription="Check back soon"
      />
    );

    expect(screen.getByText('Nothing here')).toBeInTheDocument();
    expect(screen.getByText('Check back soon')).toBeInTheDocument();
  });

  it('uses a custom data-testid for the rendered state', () => {
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

  it('renders instructor booking cards for each booking', () => {
    render(
      <BookingList
        data={[
          {
            id: 'booking-1',
            booking_date: '2026-03-14',
            start_time: '14:45:00',
            end_time: '15:30:00',
            status: 'CONFIRMED',
            service_name: 'Piano',
            duration_minutes: 45,
            location_type: 'student_location',
            student: {
              id: 'student-1',
              first_name: 'David',
              last_initial: 'M',
            },
          },
          {
            id: 'booking-2',
            booking_date: '2026-03-15',
            start_time: '10:00:00',
            end_time: '10:45:00',
            status: 'COMPLETED',
            service_name: 'Voice',
            duration_minutes: 45,
            location_type: 'online',
            student: {
              id: 'student-2',
              first_name: 'Ari',
              last_initial: 'L',
            },
          },
        ]}
        emptyTitle="No bookings"
        emptyDescription="Come back later"
      />
    );

    expect(screen.getAllByTestId('booking-card')).toHaveLength(2);
    expect(screen.getByText('David M.')).toBeInTheDocument();
    expect(screen.getByText('Ari L.')).toBeInTheDocument();
  });
});
