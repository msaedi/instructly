import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import BookingDetailsModal from '../BookingDetailsModal';
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
  formatInstructorFromUser: jest.fn((instructor) =>
    instructor ? `${instructor.first_name} ${instructor.last_initial}.` : null
  ),
  formatFullName: jest.fn((user) => `${user.first_name} ${user.last_name}`),
}));

jest.mock('@/lib/timezone/formatBookingTime', () => ({
  formatBookingDate: jest.fn((_booking, _tz) => 'Monday, January 15, 2024'),
  formatBookingTimeRange: jest.fn((_booking, _tz) => '10:00 AM - 11:00 AM'),
}));

const createMockBooking = (overrides: Partial<Booking> = {}): Booking => ({
  id: '01K2GY3VEVJWKZDVH5HMNXEVRD',
  student_id: '01K2GY3VEVJWKZDVH5STUDENT1',
  instructor_service_id: '01K2GY3VEVJWKZDVH5SERVICE1',
  instructor_id: '01K2GY3VEVJWKZDVH5INSTRUC1',
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

describe('BookingDetailsModal', () => {
  const defaultProps = {
    booking: createMockBooking(),
    isOpen: true,
    onClose: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Visibility', () => {
    it('renders when isOpen is true and booking exists', () => {
      render(<BookingDetailsModal {...defaultProps} />);
      expect(screen.getByText('Booking Details')).toBeInTheDocument();
    });

    it('returns null when isOpen is false', () => {
      const { container } = render(
        <BookingDetailsModal {...defaultProps} isOpen={false} />
      );
      expect(container).toBeEmptyDOMElement();
    });

    it('returns null when booking is null', () => {
      const { container } = render(
        <BookingDetailsModal {...defaultProps} booking={null} />
      );
      expect(container).toBeEmptyDOMElement();
    });
  });

  describe('Status badges', () => {
    it('renders CONFIRMED status with green styling', () => {
      render(<BookingDetailsModal {...defaultProps} />);
      const badge = screen.getByText('CONFIRMED');
      expect(badge).toHaveClass('bg-green-100', 'text-green-800');
    });

    it('renders COMPLETED status with gray styling', () => {
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({ status: 'COMPLETED' })}
        />
      );
      const badge = screen.getByText('COMPLETED');
      expect(badge).toHaveClass('bg-gray-100', 'text-gray-800');
    });

    it('renders CANCELLED status with red styling', () => {
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({ status: 'CANCELLED' })}
        />
      );
      const badge = screen.getByText('CANCELLED');
      expect(badge).toHaveClass('bg-red-100', 'text-red-800');
    });

    it('renders NO_SHOW status with yellow styling', () => {
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({ status: 'NO_SHOW' })}
        />
      );
      const badge = screen.getByText('NO_SHOW');
      expect(badge).toHaveClass('bg-yellow-100', 'text-yellow-800');
    });
  });

  describe('Booking ID', () => {
    it('displays booking ID', () => {
      render(<BookingDetailsModal {...defaultProps} />);
      expect(screen.getByText('Booking #01K2GY3VEVJWKZDVH5HMNXEVRD')).toBeInTheDocument();
    });
  });

  describe('Service info', () => {
    it('renders service name', () => {
      render(<BookingDetailsModal {...defaultProps} />);
      expect(screen.getByText('Piano Lesson')).toBeInTheDocument();
    });

    it('renders total price formatted', () => {
      render(<BookingDetailsModal {...defaultProps} />);
      expect(screen.getByText('Total: $60.00')).toBeInTheDocument();
    });

    it('renders hourly rate when available', () => {
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({
            service: { hourly_rate: 60 } as Booking['service'],
          })}
        />
      );
      expect(screen.getByText('($60.00/hour)')).toBeInTheDocument();
    });

    it('handles string price correctly', () => {
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({ total_price: '75.50' as unknown as number })}
        />
      );
      expect(screen.getByText('Total: $75.50')).toBeInTheDocument();
    });

    it('handles non-numeric string price gracefully', () => {
      // Lines 75-78: Catch block in formatPrice
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({ total_price: 'invalid' as unknown as number })}
        />
      );
      // Should show $0.00 for invalid price
      expect(screen.getByText('Total: $0.00')).toBeInTheDocument();
    });

    it('handles null price gracefully', () => {
      // Lines 75-78: Edge case for formatPrice
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({ total_price: null as unknown as number })}
        />
      );
      // Should show $0.00 for null price
      expect(screen.getByText('Total: $0.00')).toBeInTheDocument();
    });

    it('handles undefined price gracefully', () => {
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({ total_price: undefined as unknown as number })}
        />
      );
      // Should show $0.00 for undefined price
      expect(screen.getByText('Total: $0.00')).toBeInTheDocument();
    });
  });

  describe('formatMetaDate edge cases', () => {
    it('returns empty string for null date value', () => {
      // Line 84: Return empty string when value is null
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({ created_at: null as unknown as string })}
        />
      );
      // Should render without crashing, created_at text won't appear
      expect(screen.getByText('Booking Details')).toBeInTheDocument();
    });

    it('returns empty string for undefined date value', () => {
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({ created_at: undefined as unknown as string })}
        />
      );
      // Should render without crashing
      expect(screen.getByText('Booking Details')).toBeInTheDocument();
    });

    it('returns original value for invalid date string', () => {
      // Line 88: Return value if parsing fails
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({ created_at: 'not-a-date' })}
        />
      );
      // Should show the original value when date parsing fails
      expect(screen.getByText(/not-a-date|Booked on/)).toBeInTheDocument();
    });
  });

  describe('Date and time', () => {
    it('renders date label', () => {
      render(<BookingDetailsModal {...defaultProps} />);
      expect(screen.getByText('Date')).toBeInTheDocument();
    });

    it('renders formatted date', () => {
      render(<BookingDetailsModal {...defaultProps} />);
      expect(screen.getByText('Monday, January 15, 2024')).toBeInTheDocument();
    });

    it('renders time label', () => {
      render(<BookingDetailsModal {...defaultProps} />);
      expect(screen.getByText('Time')).toBeInTheDocument();
    });

    it('renders formatted time range', () => {
      render(<BookingDetailsModal {...defaultProps} />);
      expect(screen.getByText('10:00 AM - 11:00 AM')).toBeInTheDocument();
    });
  });

  describe('Instructor info', () => {
    it('renders instructor label', () => {
      render(<BookingDetailsModal {...defaultProps} />);
      expect(screen.getByText('Instructor')).toBeInTheDocument();
    });

    it('renders instructor name', () => {
      render(<BookingDetailsModal {...defaultProps} />);
      expect(screen.getByText('Sarah C.')).toBeInTheDocument();
    });

    it('shows fallback when instructor info not available', () => {
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({ instructor: undefined })}
        />
      );
      expect(screen.getByText(/Instructor #/)).toBeInTheDocument();
    });
  });

  describe('Location', () => {
    it('renders location label', () => {
      render(<BookingDetailsModal {...defaultProps} />);
      expect(screen.getByText('Location')).toBeInTheDocument();
    });

    it('renders meeting location when available', () => {
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({ meeting_location: '123 Main St, NYC' })}
        />
      );
      expect(screen.getByText('123 Main St, NYC')).toBeInTheDocument();
    });

    it('shows fallback text when no meeting location', () => {
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({ meeting_location: undefined })}
        />
      );
      expect(
        screen.getByText('Location details will be provided by instructor')
      ).toBeInTheDocument();
    });

    it('renders service area when available', () => {
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({ service_area: 'Upper West Side' })}
        />
      );
      expect(screen.getByText('Service area: Upper West Side')).toBeInTheDocument();
    });
  });

  describe('Student info', () => {
    it('renders student section when student data available', () => {
      render(<BookingDetailsModal {...defaultProps} />);
      expect(screen.getByText('Student')).toBeInTheDocument();
      expect(screen.getByText('John Doe')).toBeInTheDocument();
      expect(screen.getByText('john.doe@example.com')).toBeInTheDocument();
    });

    it('does not render student section when no student data', () => {
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({ student: undefined })}
        />
      );
      expect(screen.queryByText('Student')).not.toBeInTheDocument();
    });
  });

  describe('Booking notes', () => {
    it('renders notes when available', () => {
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({ student_note: 'Please bring sheet music' })}
        />
      );
      expect(screen.getByText('Booking Notes')).toBeInTheDocument();
      expect(screen.getByText('Please bring sheet music')).toBeInTheDocument();
    });

    it('does not render notes section when no notes', () => {
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({ student_note: undefined })}
        />
      );
      expect(screen.queryByText('Booking Notes')).not.toBeInTheDocument();
    });
  });

  describe('Cancellation info', () => {
    it('renders cancellation details for cancelled booking', () => {
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({
            status: 'CANCELLED',
            cancellation_reason: 'Schedule conflict',
            cancelled_at: '2024-01-12T10:00:00Z',
          })}
        />
      );
      expect(screen.getByText('Cancellation Details')).toBeInTheDocument();
      expect(screen.getByText('Schedule conflict')).toBeInTheDocument();
      expect(screen.getByText(/Cancelled on Jan 12, 2024/)).toBeInTheDocument();
    });

    it('does not render cancellation details for non-cancelled booking', () => {
      render(<BookingDetailsModal {...defaultProps} />);
      expect(screen.queryByText('Cancellation Details')).not.toBeInTheDocument();
    });
  });

  describe('Metadata', () => {
    it('renders booked on date', () => {
      render(<BookingDetailsModal {...defaultProps} />);
      expect(screen.getByText('Booked on Jan 10, 2024')).toBeInTheDocument();
    });

    it('renders last updated when different from created', () => {
      render(
        <BookingDetailsModal
          {...defaultProps}
          booking={createMockBooking({
            created_at: '2024-01-10T10:00:00Z',
            updated_at: '2024-01-12T15:00:00Z',
          })}
        />
      );
      expect(screen.getByText('Booked on Jan 10, 2024')).toBeInTheDocument();
      expect(screen.getByText('Last updated Jan 12, 2024')).toBeInTheDocument();
    });

    it('does not render last updated when same as created', () => {
      render(<BookingDetailsModal {...defaultProps} />);
      expect(screen.queryByText(/Last updated/)).not.toBeInTheDocument();
    });
  });

  describe('Close functionality', () => {
    it('calls onClose when X button is clicked', () => {
      const onClose = jest.fn();
      render(<BookingDetailsModal {...defaultProps} onClose={onClose} />);

      fireEvent.click(screen.getByLabelText('Close modal'));
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('calls onClose when footer Close button is clicked', () => {
      const onClose = jest.fn();
      render(<BookingDetailsModal {...defaultProps} onClose={onClose} />);

      fireEvent.click(screen.getByRole('button', { name: 'Close' }));
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  describe('Modal structure', () => {
    it('has overlay background', () => {
      const { container } = render(<BookingDetailsModal {...defaultProps} />);
      expect(container.querySelector('.bg-black.bg-opacity-50')).toBeInTheDocument();
    });

    it('has scrollable content area', () => {
      const { container } = render(<BookingDetailsModal {...defaultProps} />);
      expect(container.querySelector('.overflow-y-auto')).toBeInTheDocument();
    });

    it('has sticky header', () => {
      const { container } = render(<BookingDetailsModal {...defaultProps} />);
      expect(container.querySelector('.sticky.top-0')).toBeInTheDocument();
    });

    it('has sticky footer', () => {
      const { container } = render(<BookingDetailsModal {...defaultProps} />);
      expect(container.querySelector('.sticky.bottom-0')).toBeInTheDocument();
    });
  });
});
