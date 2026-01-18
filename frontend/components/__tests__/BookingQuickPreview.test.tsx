import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BookingQuickPreview from '../BookingQuickPreview';
import { fetchBookingPreview } from '@/lib/api';
import type { BookingPreview } from '@/features/shared/api/types';

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('@/lib/api', () => ({
  fetchBookingPreview: jest.fn(),
}));

jest.mock('@/lib/timezone/formatBookingTime', () => ({
  formatBookingDate: jest.fn(() => 'Monday, January 15, 2024'),
  formatBookingTimeRange: jest.fn(() => '10:00 AM - 11:00 AM'),
}));

jest.mock('@/types/booking', () => ({
  getLocationTypeIcon: jest.fn((type: string) => {
    const icons: Record<string, string> = {
      IN_HOME: '🏠',
      STUDIO: '🎹',
      VIRTUAL: '💻',
    };
    return icons[type] ?? '📍';
  }),
}));

jest.mock('@/components/Modal', () => {
  const MockModal = ({
    isOpen,
    onClose,
    title,
    children,
  }: {
    isOpen: boolean;
    onClose: () => void;
    title: string;
    children: React.ReactNode;
  }) =>
    isOpen ? (
      <div data-testid="modal">
        <h2>{title}</h2>
        <button onClick={onClose} aria-label="Close modal">
          ×
        </button>
        {children}
      </div>
    ) : null;
  MockModal.displayName = 'MockModal';
  return MockModal;
});

const mockFetchBookingPreview = fetchBookingPreview as jest.MockedFunction<
  typeof fetchBookingPreview
>;

const createMockBookingPreview = (overrides: Partial<BookingPreview> = {}): BookingPreview => ({
  booking_id: '01K2GY3VEVJWKZDVH5HMNXEVRD',
  student_first_name: 'John',
  student_last_name: 'D',
  instructor_first_name: 'Sarah',
  instructor_last_name: 'C',
  service_name: 'Piano Lesson',
  duration_minutes: 60,
  booking_date: '2024-01-15',
  start_time: '10:00',
  end_time: '11:00',
  total_price: 60,
  location_type: 'IN_HOME',
  location_type_display: 'In-Home Lesson',
  meeting_location: '123 Main St, New York, NY',
  service_area: null,
  student_note: null,
  status: 'CONFIRMED',
  ...overrides,
});

describe('BookingQuickPreview', () => {
  const defaultProps = {
    bookingId: '01K2GY3VEVJWKZDVH5HMNXEVRD',
    onClose: jest.fn(),
    onViewFullDetails: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Loading state', () => {
    it('shows loading skeleton while fetching', async () => {
      mockFetchBookingPreview.mockImplementation(
        () => new Promise(() => {}) // Never resolves
      );

      render(<BookingQuickPreview {...defaultProps} />);

      // Should show loading skeleton (pulse animation)
      const skeletons = screen.getAllByText('', { selector: '.animate-pulse' });
      expect(skeletons.length).toBeGreaterThan(0);
    });

    it('renders modal with title during loading', () => {
      mockFetchBookingPreview.mockImplementation(
        () => new Promise(() => {})
      );

      render(<BookingQuickPreview {...defaultProps} />);
      expect(screen.getByText('Booking Details')).toBeInTheDocument();
    });
  });

  describe('Error state', () => {
    it('shows error message when fetch fails', async () => {
      mockFetchBookingPreview.mockRejectedValue(new Error('Network error'));

      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('Failed to load booking details')).toBeInTheDocument();
      });
    });
  });

  describe('Success state', () => {
    beforeEach(() => {
      mockFetchBookingPreview.mockResolvedValue(createMockBookingPreview());
    });

    it('renders student name', async () => {
      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('John D.')).toBeInTheDocument();
      });
    });

    it('renders student name without dot for full last name', async () => {
      mockFetchBookingPreview.mockResolvedValue(
        createMockBookingPreview({ student_last_name: 'Doe' })
      );

      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('John Doe')).toBeInTheDocument();
      });
    });

    it('renders service name and duration', async () => {
      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('Piano Lesson - 60 minutes')).toBeInTheDocument();
      });
    });

    it('renders formatted date', async () => {
      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('Monday, January 15, 2024')).toBeInTheDocument();
      });
    });

    it('renders formatted time range', async () => {
      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('10:00 AM - 11:00 AM')).toBeInTheDocument();
      });
    });

    it('renders location type with icon', async () => {
      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('🏠')).toBeInTheDocument();
        expect(screen.getByText('In-Home Lesson')).toBeInTheDocument();
      });
    });

    it('renders meeting location when present', async () => {
      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('123 Main St, New York, NY')).toBeInTheDocument();
      });
    });

    it('does not render meeting location when not present', async () => {
      mockFetchBookingPreview.mockResolvedValue(
        createMockBookingPreview({ meeting_location: null })
      );

      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.queryByText('123 Main St')).not.toBeInTheDocument();
      });
    });

    it('renders student note when present', async () => {
      mockFetchBookingPreview.mockResolvedValue(
        createMockBookingPreview({ student_note: 'Please bring sheet music' })
      );

      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('Note from student')).toBeInTheDocument();
        expect(screen.getByText('"Please bring sheet music"')).toBeInTheDocument();
      });
    });

    it('does not render student note when not present', async () => {
      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.queryByText('Note from student')).not.toBeInTheDocument();
      });
    });

    it('renders total price formatted', async () => {
      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('$60.00')).toBeInTheDocument();
      });
    });

    it('renders View Full Details button', async () => {
      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('View Full Details →')).toBeInTheDocument();
      });
    });
  });

  describe('User interactions', () => {
    beforeEach(() => {
      mockFetchBookingPreview.mockResolvedValue(createMockBookingPreview());
    });

    it('calls onViewFullDetails when button is clicked', async () => {
      const user = userEvent.setup();
      const onViewFullDetails = jest.fn();

      render(
        <BookingQuickPreview {...defaultProps} onViewFullDetails={onViewFullDetails} />
      );

      await waitFor(() => {
        expect(screen.getByText('View Full Details →')).toBeInTheDocument();
      });

      await user.click(screen.getByText('View Full Details →'));
      expect(onViewFullDetails).toHaveBeenCalledTimes(1);
    });

    it('calls onClose when close button is clicked', async () => {
      const user = userEvent.setup();
      const onClose = jest.fn();

      render(<BookingQuickPreview {...defaultProps} onClose={onClose} />);

      await waitFor(() => {
        expect(screen.getByLabelText('Close modal')).toBeInTheDocument();
      });

      await user.click(screen.getByLabelText('Close modal'));
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  describe('API calls', () => {
    it('fetches booking preview with correct ID', async () => {
      mockFetchBookingPreview.mockResolvedValue(createMockBookingPreview());

      render(
        <BookingQuickPreview
          {...defaultProps}
          bookingId="01K2GY3VEVJWKZDVH5TESTID01"
        />
      );

      await waitFor(() => {
        expect(mockFetchBookingPreview).toHaveBeenCalledWith('01K2GY3VEVJWKZDVH5TESTID01');
      });
    });

    it('fetches again when bookingId changes', async () => {
      mockFetchBookingPreview.mockResolvedValue(createMockBookingPreview());

      const { rerender } = render(
        <BookingQuickPreview {...defaultProps} bookingId="booking-1" />
      );

      await waitFor(() => {
        expect(mockFetchBookingPreview).toHaveBeenCalledWith('booking-1');
      });

      rerender(<BookingQuickPreview {...defaultProps} bookingId="booking-2" />);

      await waitFor(() => {
        expect(mockFetchBookingPreview).toHaveBeenCalledWith('booking-2');
      });
    });
  });

  describe('Section labels', () => {
    beforeEach(() => {
      mockFetchBookingPreview.mockResolvedValue(createMockBookingPreview());
    });

    it('renders Student label', async () => {
      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('Student')).toBeInTheDocument();
      });
    });

    it('renders Service label', async () => {
      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('Service')).toBeInTheDocument();
      });
    });

    it('renders When label', async () => {
      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('When')).toBeInTheDocument();
      });
    });

    it('renders Location label', async () => {
      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('Location')).toBeInTheDocument();
      });
    });

    it('renders Total label', async () => {
      render(<BookingQuickPreview {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText('Total')).toBeInTheDocument();
      });
    });
  });
});
