import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { BookingCard } from '../BookingCard';
import type { Booking, BookingStatus } from '@/types/booking';

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('@/utils/nameDisplay', () => ({
  formatInstructorFromUser: jest.fn((instructor) => `${instructor.first_name} ${instructor.last_initial}.`),
}));

jest.mock('@/lib/timezone/formatBookingTime', () => ({
  formatBookingDate: jest.fn(() => 'Monday, January 15, 2024'),
  formatBookingTimeRange: jest.fn(() => '10:00 AM - 11:00 AM'),
}));

const createMockBooking = (overrides: Partial<Booking> = {}): Booking => ({
  id: '01K2GY3VEVJWKZDVH5HMNXEVRD',
  student_id: '01K2GY3VEVJWKZDVH5STUDENT1',
  instructor_id: '01K2GY3VEVJWKZDVH5INSTRUC1',
  instructor_service_id: '01K2GY3VEVJWKZDVH5SERVICE1',
  booking_date: '2024-01-15',
  start_time: '10:00',
  end_time: '11:00',
  status: 'CONFIRMED' as BookingStatus,
  total_price: 60,
  duration_minutes: 60,
  hourly_rate: 60,
  service_name: 'Piano Lesson',
  instructor: {
    id: '01K2GY3VEVJWKZDVH5INSTRUC1',
    first_name: 'Sarah',
    last_initial: 'C',
  },
  student: {
    id: '01K2GY3VEVJWKZDVH5STUDENT1',
    first_name: 'John',
    last_name: 'Doe',
    email: 'john.doe@example.com',
  },
  created_at: '2024-01-10T10:00:00Z',
  updated_at: '2024-01-10T10:00:00Z',
  ...overrides,
});

describe('BookingCard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Set a fixed date for testing
    jest.useFakeTimers().setSystemTime(new Date('2024-01-20T12:00:00Z'));
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('Basic rendering', () => {
    it('renders service name', () => {
      render(<BookingCard booking={createMockBooking()} />);
      expect(screen.getByText('Piano Lesson')).toBeInTheDocument();
    });

    it('renders instructor name', () => {
      render(<BookingCard booking={createMockBooking()} />);
      expect(screen.getByText('with Sarah C.')).toBeInTheDocument();
    });

    it('renders formatted date', () => {
      render(<BookingCard booking={createMockBooking()} />);
      expect(screen.getByText('Monday, January 15, 2024')).toBeInTheDocument();
    });

    it('renders formatted time range', () => {
      render(<BookingCard booking={createMockBooking()} />);
      expect(screen.getByText('10:00 AM - 11:00 AM')).toBeInTheDocument();
    });

    it('renders price', () => {
      render(<BookingCard booking={createMockBooking({ total_price: 75 })} />);
      expect(screen.getByText('$75')).toBeInTheDocument();
    });

    it('applies custom className', () => {
      const { container } = render(
        <BookingCard booking={createMockBooking()} className="custom-class" />
      );
      expect(container.firstChild).toHaveClass('custom-class');
    });
  });

  describe('Status badges', () => {
    it('renders PENDING status badge', () => {
      render(<BookingCard booking={createMockBooking({ status: 'PENDING' })} />);
      const badge = screen.getByText('Pending');
      expect(badge).toHaveClass('bg-yellow-100', 'text-yellow-800');
    });

    it('renders CONFIRMED status badge', () => {
      render(<BookingCard booking={createMockBooking({ status: 'CONFIRMED' })} />);
      const badge = screen.getByText('Confirmed');
      expect(badge).toHaveClass('bg-green-100', 'text-green-800');
    });

    it('renders COMPLETED status badge', () => {
      render(<BookingCard booking={createMockBooking({ status: 'COMPLETED' })} />);
      const badge = screen.getByText('Completed');
      expect(badge).toHaveClass('bg-blue-100', 'text-blue-800');
    });

    it('renders CANCELLED status badge', () => {
      render(<BookingCard booking={createMockBooking({ status: 'CANCELLED' })} />);
      const badge = screen.getByText('Cancelled');
      expect(badge).toHaveClass('bg-red-100', 'text-red-800');
    });

    it('renders NO_SHOW status badge', () => {
      render(<BookingCard booking={createMockBooking({ status: 'NO_SHOW' })} />);
      const badge = screen.getByText('No Show');
      expect(badge).toHaveClass('bg-gray-100', 'text-gray-800');
    });
  });

  describe('Student notes', () => {
    it('renders student note when present', () => {
      render(
        <BookingCard
          booking={createMockBooking({ student_note: 'Please bring sheet music' })}
        />
      );
      expect(screen.getByText('Notes:')).toBeInTheDocument();
      expect(screen.getByText('Please bring sheet music')).toBeInTheDocument();
    });

    it('does not render notes section when note is not present', () => {
      render(<BookingCard booking={createMockBooking({ student_note: undefined })} />);
      expect(screen.queryByText('Notes:')).not.toBeInTheDocument();
    });
  });

  describe('Cancellation reason', () => {
    it('renders cancellation reason when present', () => {
      render(
        <BookingCard
          booking={createMockBooking({
            status: 'CANCELLED',
            cancellation_reason: 'Schedule conflict',
          })}
        />
      );
      expect(screen.getByText('Cancellation reason:')).toBeInTheDocument();
      expect(screen.getByText('Schedule conflict')).toBeInTheDocument();
    });

    it('does not render cancellation section when reason is not present', () => {
      render(
        <BookingCard booking={createMockBooking({ cancellation_reason: undefined })} />
      );
      expect(screen.queryByText('Cancellation reason:')).not.toBeInTheDocument();
    });
  });

  describe('Action buttons', () => {
    it('renders View Details button when callback provided', () => {
      const onViewDetails = jest.fn();
      render(<BookingCard booking={createMockBooking()} onViewDetails={onViewDetails} />);
      expect(screen.getByText('View Details')).toBeInTheDocument();
    });

    it('does not render View Details button when callback not provided', () => {
      render(<BookingCard booking={createMockBooking()} />);
      expect(screen.queryByText('View Details')).not.toBeInTheDocument();
    });

    it('calls onViewDetails when button is clicked', () => {
      const onViewDetails = jest.fn();
      render(<BookingCard booking={createMockBooking()} onViewDetails={onViewDetails} />);
      fireEvent.click(screen.getByText('View Details'));
      expect(onViewDetails).toHaveBeenCalledTimes(1);
    });

    it('renders Cancel button for confirmed future booking', () => {
      const onCancel = jest.fn();
      // Set booking in the future
      render(
        <BookingCard
          booking={createMockBooking({
            status: 'CONFIRMED',
            booking_date: '2024-01-25',
            booking_end_utc: '2024-01-25T12:00:00Z',
          })}
          onCancel={onCancel}
        />
      );
      expect(screen.getByText('Cancel Booking')).toBeInTheDocument();
    });

    it('does not render Cancel button for past booking', () => {
      const onCancel = jest.fn();
      render(
        <BookingCard
          booking={createMockBooking({
            status: 'CONFIRMED',
            booking_date: '2024-01-10',
            booking_end_utc: '2024-01-10T12:00:00Z',
          })}
          onCancel={onCancel}
        />
      );
      expect(screen.queryByText('Cancel Booking')).not.toBeInTheDocument();
    });

    it('does not render Cancel button for non-confirmed booking', () => {
      const onCancel = jest.fn();
      render(
        <BookingCard
          booking={createMockBooking({
            status: 'PENDING',
            booking_date: '2024-01-25',
            booking_end_utc: '2024-01-25T12:00:00Z',
          })}
          onCancel={onCancel}
        />
      );
      expect(screen.queryByText('Cancel Booking')).not.toBeInTheDocument();
    });

    it('calls onCancel when button is clicked', () => {
      const onCancel = jest.fn();
      render(
        <BookingCard
          booking={createMockBooking({
            status: 'CONFIRMED',
            booking_date: '2024-01-25',
            booking_end_utc: '2024-01-25T12:00:00Z',
          })}
          onCancel={onCancel}
        />
      );
      fireEvent.click(screen.getByText('Cancel Booking'));
      expect(onCancel).toHaveBeenCalledTimes(1);
    });

    it('renders Mark Complete button for past confirmed booking', () => {
      const onComplete = jest.fn();
      render(
        <BookingCard
          booking={createMockBooking({
            status: 'CONFIRMED',
            booking_date: '2024-01-10',
            booking_end_utc: '2024-01-10T12:00:00Z',
          })}
          onComplete={onComplete}
        />
      );
      expect(screen.getByText('Mark Complete')).toBeInTheDocument();
    });

    it('does not render Mark Complete button for future booking', () => {
      const onComplete = jest.fn();
      render(
        <BookingCard
          booking={createMockBooking({
            status: 'CONFIRMED',
            booking_date: '2024-01-25',
            booking_end_utc: '2024-01-25T12:00:00Z',
          })}
          onComplete={onComplete}
        />
      );
      expect(screen.queryByText('Mark Complete')).not.toBeInTheDocument();
    });

    it('calls onComplete when button is clicked', () => {
      const onComplete = jest.fn();
      render(
        <BookingCard
          booking={createMockBooking({
            status: 'CONFIRMED',
            booking_date: '2024-01-10',
            booking_end_utc: '2024-01-10T12:00:00Z',
          })}
          onComplete={onComplete}
        />
      );
      fireEvent.click(screen.getByText('Mark Complete'));
      expect(onComplete).toHaveBeenCalledTimes(1);
    });
  });

  describe('Booking state determination', () => {
    it('uses booking_end_utc when available to determine past status', () => {
      const onComplete = jest.fn();
      const onCancel = jest.fn();
      // booking_end_utc is in the past
      render(
        <BookingCard
          booking={createMockBooking({
            status: 'CONFIRMED',
            booking_date: '2024-01-15',
            start_time: '10:00',
            end_time: '11:00',
            booking_end_utc: '2024-01-15T12:00:00Z', // Past
          })}
          onComplete={onComplete}
          onCancel={onCancel}
        />
      );
      // Should show Mark Complete (past) instead of Cancel
      expect(screen.getByText('Mark Complete')).toBeInTheDocument();
      expect(screen.queryByText('Cancel Booking')).not.toBeInTheDocument();
    });

    it('falls back to booking_date + end_time when booking_end_utc is not available', () => {
      const onCancel = jest.fn();
      // Use future date without booking_end_utc
      render(
        <BookingCard
          booking={createMockBooking({
            status: 'CONFIRMED',
            booking_date: '2024-01-25',
            start_time: '10:00',
            end_time: '11:00',
          })}
          onCancel={onCancel}
        />
      );
      // Should show Cancel (future)
      expect(screen.getByText('Cancel Booking')).toBeInTheDocument();
    });
  });

  describe('Variant prop', () => {
    it('accepts upcoming variant', () => {
      render(<BookingCard booking={createMockBooking()} variant="upcoming" />);
      expect(screen.getByText('Piano Lesson')).toBeInTheDocument();
    });

    it('accepts past variant', () => {
      render(<BookingCard booking={createMockBooking()} variant="past" />);
      expect(screen.getByText('Piano Lesson')).toBeInTheDocument();
    });

    it('accepts detailed variant', () => {
      render(<BookingCard booking={createMockBooking()} variant="detailed" />);
      expect(screen.getByText('Piano Lesson')).toBeInTheDocument();
    });

    it('defaults to upcoming variant', () => {
      render(<BookingCard booking={createMockBooking()} />);
      expect(screen.getByText('Piano Lesson')).toBeInTheDocument();
    });
  });
});
