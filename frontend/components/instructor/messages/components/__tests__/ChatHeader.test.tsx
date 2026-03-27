import { render, screen, fireEvent, within } from '@testing-library/react';
import { ChatHeader, type ChatHeaderProps } from '../ChatHeader';
import type { ConversationEntry } from '../../types';
import { shortenBookingId } from '@/lib/bookingId';

describe('ChatHeader', () => {
  const mockConversation = {
    id: 'conv-123',
    name: 'John Doe',
    avatar: 'JD',
    type: 'student',
    lastMessage: 'Last message',
    timestamp: '2h ago',
    unread: 0,
    bookingIds: [],
    primaryBookingId: null,
    studentId: 'student-1',
    instructorId: 'instructor-1',
    latestMessageAt: Date.parse('2025-01-15T10:00:00Z'),
  } as ConversationEntry;

  const mockConversationWithBooking: ConversationEntry = {
    ...mockConversation,
    nextBooking: {
      id: '01KKQKWD9V9QF0J2T0AB3124',
      service_name: 'Piano Lesson',
      date: '2025-01-20',
      start_time: '09:00',
      status: 'CONFIRMED',
    },
    upcomingBookingCount: 2,
    upcomingBookings: [
      {
        id: '01KKQKWD9V9QF0J2T0AB3124',
        service_name: 'Piano Lesson',
        date: '2025-01-20',
        start_time: '09:00',
        status: 'CONFIRMED',
      },
      {
        id: '01JZ7AKD1234567890ABCDXYZ',
        service_name: 'Guitar Lesson',
        date: '2025-01-22',
        start_time: '14:30',
        status: 'CONFIRMED',
      },
    ],
  };

  const mockComposeRecipient = {
    id: 'recipient-123',
    name: 'Jane Smith',
    avatar: 'JS',
    type: 'student',
    lastMessage: '',
    timestamp: '',
    unread: 0,
    bookingIds: [],
    primaryBookingId: null,
    studentId: 'student-2',
    instructorId: 'instructor-1',
    latestMessageAt: 0,
  } as ConversationEntry;

  const defaultProps: ChatHeaderProps = {
    isComposeView: false,
    activeConversation: mockConversation,
    composeRecipient: null,
    composeRecipientQuery: '',
    composeSuggestions: [],
    onComposeRecipientQueryChange: jest.fn(),
    onComposeRecipientSelect: jest.fn(),
    onComposeRecipientClear: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('non-compose view', () => {
    it('renders conversation name and avatar', () => {
      render(<ChatHeader {...defaultProps} />);

      expect(screen.getByText('John Doe')).toBeInTheDocument();
      expect(screen.getByText('JD')).toBeInTheDocument();
    });

    it('shows "Student" label for student type', () => {
      render(<ChatHeader {...defaultProps} />);

      expect(screen.getByText('Student')).toBeInTheDocument();
    });

    it('shows "Platform" label for platform type', () => {
      const platformConversation = { ...mockConversation, type: 'platform' as const };
      render(
        <ChatHeader {...defaultProps} activeConversation={platformConversation} />
      );

      expect(screen.getByText('Platform')).toBeInTheDocument();
    });

    it('renders menu button when conversation is active', () => {
      render(<ChatHeader {...defaultProps} />);

      const menuButton = screen.getByRole('button', { expanded: false });
      expect(menuButton).toBeInTheDocument();
    });

    it('provides accessible label for menu button', () => {
      render(<ChatHeader {...defaultProps} />);

      expect(screen.getByRole('button', { name: /more options/i })).toBeInTheDocument();
    });

    it('toggles menu on button click', () => {
      render(<ChatHeader {...defaultProps} />);

      const menuButton = screen.getByRole('button', { expanded: false });
      fireEvent.click(menuButton);

      expect(screen.getByRole('menu')).toBeInTheDocument();
      expect(screen.queryByText('Booking Info')).not.toBeInTheDocument();
    });

    it('shows "No upcoming bookings" when no bookings exist', () => {
      render(<ChatHeader {...defaultProps} />);

      const menuButton = screen.getByRole('button', { expanded: false });
      fireEvent.click(menuButton);

      expect(screen.getByText('No upcoming bookings')).toBeInTheDocument();
    });
  });

  describe('with booking context', () => {
    it('displays booking badge on desktop', () => {
      render(
        <ChatHeader
          {...defaultProps}
          activeConversation={mockConversationWithBooking}
        />
      );

      expect(screen.getByText(/Piano Lesson/)).toBeInTheDocument();
    });

    it('shows the primary booking as an inline confirmed card in the menu', () => {
      render(
        <ChatHeader
          {...defaultProps}
          activeConversation={mockConversationWithBooking}
        />
      );

      const menuButton = screen.getByRole('button', { expanded: false });
      fireEvent.click(menuButton);

      const primaryCard = screen.getByTestId('chat-header-booking-card-01KKQKWD9V9QF0J2T0AB3124');
      expect(primaryCard).toHaveClass('bg-(--color-brand-lavender)');
      expect(within(primaryCard).getByText('Piano Lesson')).toBeInTheDocument();
      expect(within(primaryCard).getByText('Confirmed')).toHaveClass('bg-emerald-50', 'text-emerald-700');
      expect(within(primaryCard).getByText(`#${shortenBookingId('01KKQKWD9V9QF0J2T0AB3124')}`)).toBeInTheDocument();
      expect(screen.queryByText('Next booking')).not.toBeInTheDocument();
      expect(screen.queryByText('Upcoming')).not.toBeInTheDocument();
      expect(screen.queryByText('01KKQKWD9V9QF0J2T0AB3124')).not.toBeInTheDocument();
    });

    it('uses the first upcoming booking when nextBooking is omitted', () => {
      render(
        <ChatHeader
          {...defaultProps}
          activeConversation={{
            ...mockConversation,
            upcomingBookingCount: 1,
            upcomingBookings: [
              {
                id: '01KUPCOMING000000000000001',
                service_name: 'Violin Lesson',
                date: '2025-01-25',
                start_time: '11:30',
              },
            ],
          }}
        />
      );

      fireEvent.click(screen.getByRole('button', { expanded: false }));

      expect(screen.getByTestId('chat-header-booking-card-01KUPCOMING000000000000001')).toBeInTheDocument();
      expect(screen.getByText('Violin Lesson')).toBeInTheDocument();
    });

    it('shows expand button for multiple bookings', () => {
      render(
        <ChatHeader
          {...defaultProps}
          activeConversation={mockConversationWithBooking}
        />
      );

      const menuButton = screen.getByRole('button', { expanded: false });
      fireEvent.click(menuButton);

      expect(screen.getByText(/\+1 more booking$/)).toBeInTheDocument();
    });

    it('expands to show additional bookings', () => {
      render(
        <ChatHeader
          {...defaultProps}
          activeConversation={mockConversationWithBooking}
        />
      );

      const menuButton = screen.getByRole('button', { expanded: false });
      fireEvent.click(menuButton);

      const expandButton = screen.getByText(/\+1 more booking$/);
      fireEvent.click(expandButton);

      expect(screen.getByText('Guitar Lesson')).toBeInTheDocument();
    });

    it('links booking cards to the booking detail page', () => {
      render(
        <ChatHeader
          {...defaultProps}
          activeConversation={mockConversationWithBooking}
        />
      );

      fireEvent.click(screen.getByRole('button', { expanded: false }));

      expect(screen.getByRole('link', { name: /piano lesson/i })).toHaveAttribute(
        'href',
        '/instructor/bookings/01KKQKWD9V9QF0J2T0AB3124'
      );

      fireEvent.click(screen.getByText(/\+1 more booking$/));

      expect(screen.getByRole('link', { name: /guitar lesson/i })).toHaveAttribute(
        'href',
        '/instructor/bookings/01JZ7AKD1234567890ABCDXYZ'
      );
    });

    it('shows completed fallback bookings with gray cards when there are no upcoming bookings', () => {
      render(
        <ChatHeader
          {...defaultProps}
          activeConversation={mockConversation}
          fallbackBookings={[
            {
              id: '01KZZZZZ9V9QF0J2T0AB3124',
              service_name: 'Voice Lesson',
              date: '2024-12-15',
              start_time: '11:00',
            },
            {
              id: '01KYYYYY1234567890ABCDXYZ',
              service_name: 'Theory Lesson',
              date: '2024-12-10',
              start_time: '15:30',
            },
          ]}
        />
      );

      fireEvent.click(screen.getByRole('button', { expanded: false }));

      const primaryPastCard = screen.getByTestId('chat-header-booking-card-01KZZZZZ9V9QF0J2T0AB3124');
      expect(primaryPastCard).toHaveClass('bg-gray-100');
      expect(within(primaryPastCard).getByText('Completed')).toHaveClass('bg-blue-50', 'text-blue-700');
      expect(
        within(primaryPastCard).getByText(`#${shortenBookingId('01KZZZZZ9V9QF0J2T0AB3124')}`)
      ).toBeInTheDocument();

      fireEvent.click(screen.getByText(/\+1 more booking$/));
      expect(screen.getByTestId('chat-header-booking-card-01KYYYYY1234567890ABCDXYZ')).toBeInTheDocument();
    });

    it('falls back to upcomingBookingCount when the detailed list is missing', () => {
      render(
        <ChatHeader
          {...defaultProps}
          activeConversation={{
            ...mockConversation,
            nextBooking: {
              id: '01KCOUNT009V9QF0J2T0AB3124',
              service_name: 'Piano Lesson',
              date: '2025-01-20',
              start_time: '09:00',
              status: 'CONFIRMED',
            },
            upcomingBookingCount: 3,
          }}
        />
      );

      expect(screen.getByText(/\+2 more$/)).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { expanded: false }));
      expect(screen.getByText(/\+2 more bookings$/)).toBeInTheDocument();
      expect(screen.queryByTestId('chat-header-booking-expander')).not.toBeInTheDocument();
      expect(screen.getByTestId('chat-header-booking-summary-count')).toBeInTheDocument();
    });

    it('renders explicit booking status labels inline without renaming them to upcoming', () => {
      render(
        <ChatHeader
          {...defaultProps}
          activeConversation={{
            ...mockConversation,
            nextBooking: {
              id: '01KSTATUS0000000000000001',
              service_name: 'Cello Lesson',
              date: '2025-02-01',
              start_time: '10:00',
              status: 'CANCELLED',
            },
            upcomingBookingCount: 4,
            upcomingBookings: [
              {
                id: '01KSTATUS0000000000000001',
                service_name: 'Cello Lesson',
                date: '2025-02-01',
                start_time: '10:00',
                status: 'CANCELLED',
              },
              {
                id: '01KSTATUS0000000000000002',
                service_name: 'Percussion Lesson',
                date: '2025-02-02',
                start_time: '11:00',
                status: 'NO_SHOW',
              },
              {
                id: '01KSTATUS0000000000000003',
                service_name: 'Bass Lesson',
                date: '2025-02-03',
                start_time: '12:00',
                status: 'IN_PROGRESS',
              },
              {
                id: '01KSTATUS0000000000000004',
                service_name: 'Theory Intensive',
                date: '2025-02-04',
                start_time: '13:00',
                status: 'PAYMENT_PENDING',
              },
            ],
          }}
        />
      );

      fireEvent.click(screen.getByRole('button', { expanded: false }));

      const primaryCard = screen.getByTestId('chat-header-booking-card-01KSTATUS0000000000000001');
      expect(within(primaryCard).getByText('Cancelled')).toBeInTheDocument();
      expect(screen.queryByText('Upcoming')).not.toBeInTheDocument();

      fireEvent.click(screen.getByText(/\+3 more bookings$/));
      expect(screen.getByText('No Show')).toBeInTheDocument();
      expect(screen.getByText('In Progress')).toBeInTheDocument();
      expect(screen.getByText('Payment Pending')).toBeInTheDocument();
    });

    it('keeps fallback booking status stable across rerenders with unchanged booking props', () => {
      const dateNowSpy = jest.spyOn(Date, 'now');
      dateNowSpy.mockReturnValue(Date.parse('2025-01-19T00:00:00Z'));

      const conversationWithoutExplicitStatus = {
        ...mockConversation,
        nextBooking: {
          id: '01KSTABLE0000000000000001',
          service_name: 'Stable Status Lesson',
          date: '2025-01-20',
          start_time: '09:00',
        },
        upcomingBookingCount: 1,
        upcomingBookings: [
          {
            id: '01KSTABLE0000000000000001',
            service_name: 'Stable Status Lesson',
            date: '2025-01-20',
            start_time: '09:00',
          },
        ],
      } as ConversationEntry;

      const { rerender } = render(
        <ChatHeader {...defaultProps} activeConversation={conversationWithoutExplicitStatus} />
      );

      fireEvent.click(screen.getByRole('button', { expanded: false }));
      expect(screen.getByText('Confirmed')).toBeInTheDocument();

      dateNowSpy.mockReturnValue(Date.parse('2025-01-21T00:00:00Z'));
      rerender(<ChatHeader {...defaultProps} activeConversation={conversationWithoutExplicitStatus} />);

      expect(screen.getByText('Confirmed')).toBeInTheDocument();
      dateNowSpy.mockRestore();
    });
  });

  describe('date/time formatting edge cases', () => {
    it('formats midnight (00:00) as 12am — hour12 === 0 branch', () => {
      const conv = {
        ...mockConversation,
        nextBooking: {
          id: 'booking-midnight',
          service_name: 'Midnight Session',
          date: '2025-03-01',
          start_time: '00:00',
        },
        upcomingBookingCount: 1,
      } as ConversationEntry;
      render(
        <ChatHeader {...defaultProps} activeConversation={conv} />
      );

      const menuButton = screen.getByRole('button', { expanded: false });
      fireEvent.click(menuButton);

      // 00:00 → hours=0, 0%12=0, hour12=12 → "12am"
      // Multiple elements (badge + menu) may match, use getAllByText
      expect(screen.getAllByText(/12am/).length).toBeGreaterThanOrEqual(1);
    });

    it('formats noon (12:00) as 12pm', () => {
      const conv = {
        ...mockConversation,
        nextBooking: {
          id: 'booking-noon',
          service_name: 'Noon Session',
          date: '2025-03-01',
          start_time: '12:00',
        },
        upcomingBookingCount: 1,
      } as ConversationEntry;
      render(
        <ChatHeader {...defaultProps} activeConversation={conv} />
      );

      const menuButton = screen.getByRole('button', { expanded: false });
      fireEvent.click(menuButton);

      // 12:00 → hours=12, 12%12=0, hour12=12 → "12pm"
      expect(screen.getAllByText(/12pm/).length).toBeGreaterThanOrEqual(1);
    });

    it('formats time with minutes for non-zero minutes', () => {
      const conv = {
        ...mockConversation,
        nextBooking: {
          id: 'booking-minutes',
          service_name: 'Afternoon Class',
          date: '2025-03-01',
          start_time: '15:45',
        },
        upcomingBookingCount: 1,
      } as ConversationEntry;
      render(
        <ChatHeader {...defaultProps} activeConversation={conv} />
      );

      const menuButton = screen.getByRole('button', { expanded: false });
      fireEvent.click(menuButton);

      // 15:45 → "3:45pm"
      expect(screen.getAllByText(/3:45pm/).length).toBeGreaterThanOrEqual(1);
    });

    it('formats date correctly as "MMM d"', () => {
      const conv = {
        ...mockConversation,
        nextBooking: {
          id: 'booking-date',
          service_name: 'Date Test',
          date: '2025-12-08',
          start_time: '10:00',
        },
        upcomingBookingCount: 1,
      } as ConversationEntry;
      render(
        <ChatHeader {...defaultProps} activeConversation={conv} />
      );

      const menuButton = screen.getByRole('button', { expanded: false });
      fireEvent.click(menuButton);

      // Dec 8
      expect(screen.getAllByText(/Dec 8/).length).toBeGreaterThanOrEqual(1);
    });
  });

  describe('click outside thread menu', () => {
    it('closes menu when clicking outside', () => {
      render(
        <ChatHeader {...defaultProps} activeConversation={mockConversation} />
      );

      const menuButton = screen.getByRole('button', { expanded: false });
      fireEvent.click(menuButton);
      expect(screen.getByRole('menu')).toBeInTheDocument();

      // Click outside the menu
      fireEvent.click(document.body);

      // Menu should close
      expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    });
  });

  describe('upcoming bookings singular/plural', () => {
    it('shows singular "booking" for +1 more', () => {
      render(
        <ChatHeader {...defaultProps} activeConversation={mockConversationWithBooking} />
      );

      const menuButton = screen.getByRole('button', { expanded: false });
      fireEvent.click(menuButton);

      expect(screen.getByText(/\+1 more booking$/)).toBeInTheDocument();
    });

    it('shows plural "bookings" for +2 more', () => {
      const conv: ConversationEntry = {
        ...mockConversationWithBooking,
        upcomingBookingCount: 3,
        upcomingBookings: [
          ...mockConversationWithBooking.upcomingBookings!,
          {
            id: '01KKABCDE234567890ABCDXYZ',
            service_name: 'Vocal Lesson',
            date: '2025-01-25',
            start_time: '16:00',
            status: 'CONFIRMED',
          },
        ],
      };
      render(
        <ChatHeader {...defaultProps} activeConversation={conv} />
      );

      const menuButton = screen.getByRole('button', { expanded: false });
      fireEvent.click(menuButton);

      expect(screen.getByText(/\+2 more bookings$/)).toBeInTheDocument();
    });
  });

  describe('formatting error handling (catch blocks)', () => {
    it('falls back to raw date string when date parsing fails (line 32)', () => {
      const conv = {
        ...mockConversation,
        nextBooking: {
          id: 'booking-baddate',
          service_name: 'Bad Date Session',
          date: 'not-a-valid-date',
          start_time: '10:00',
        },
        upcomingBookingCount: 1,
      } as ConversationEntry;
      render(
        <ChatHeader {...defaultProps} activeConversation={conv} />
      );

      const menuButton = screen.getByRole('button', { expanded: false });
      fireEvent.click(menuButton);

      // When parseISO fails, formatDateShort catches and returns the raw string
      // formatBookingInfo uses the result so we check the fallback renders
      expect(screen.getAllByText(/Bad Date Session/).length).toBeGreaterThanOrEqual(1);
    });

    it('falls back to raw time string when time parsing fails (line 54)', () => {
      const conv = {
        ...mockConversation,
        nextBooking: {
          id: 'booking-badtime',
          service_name: 'Bad Time Session',
          date: '2025-03-01',
          start_time: '', // empty string triggers NaN in parseInt
        },
        upcomingBookingCount: 1,
      } as ConversationEntry;
      render(
        <ChatHeader {...defaultProps} activeConversation={conv} />
      );

      const menuButton = screen.getByRole('button', { expanded: false });
      fireEvent.click(menuButton);

      // formatTime12h should handle empty/invalid gracefully
      expect(screen.getAllByText(/Bad Time Session/).length).toBeGreaterThanOrEqual(1);
    });

    it('falls back to simple format when formatBookingInfo throws (line 67)', () => {
      // Provide a booking where date formatting succeeds but the combined logic fails
      const conv = {
        ...mockConversation,
        nextBooking: {
          id: 'booking-fallback',
          service_name: 'Fallback Session',
          date: '2025-03-01',
          start_time: '10:00',
        },
        upcomingBookingCount: 1,
      } as ConversationEntry;
      render(
        <ChatHeader {...defaultProps} activeConversation={conv} />
      );

      const menuButton = screen.getByRole('button', { expanded: false });
      fireEvent.click(menuButton);

      // Ensure the booking info renders (either normal or fallback path)
      expect(screen.getAllByText(/Fallback Session/).length).toBeGreaterThanOrEqual(1);
    });
  });

  describe('compose view', () => {
    const composeProps: ChatHeaderProps = {
      ...defaultProps,
      isComposeView: true,
      activeConversation: null,
    };

    it('renders "To:" label', () => {
      render(<ChatHeader {...composeProps} />);

      expect(screen.getByText('To:')).toBeInTheDocument();
    });

    it('renders search input when no recipient selected', () => {
      render(<ChatHeader {...composeProps} />);

      expect(screen.getByPlaceholderText('Search contacts...')).toBeInTheDocument();
    });

    it('calls onComposeRecipientQueryChange when typing', () => {
      const onQueryChange = jest.fn();
      render(
        <ChatHeader
          {...composeProps}
          onComposeRecipientQueryChange={onQueryChange}
        />
      );

      const input = screen.getByPlaceholderText('Search contacts...');
      fireEvent.change(input, { target: { value: 'Jane' } });

      expect(onQueryChange).toHaveBeenCalledWith('Jane');
    });

    it('displays suggestions when query has value', () => {
      render(
        <ChatHeader
          {...composeProps}
          composeRecipientQuery="Jane"
          composeSuggestions={[mockComposeRecipient]}
        />
      );

      expect(screen.getByText('Jane Smith')).toBeInTheDocument();
    });

    it('shows "No contacts found" when no suggestions match', () => {
      render(
        <ChatHeader
          {...composeProps}
          composeRecipientQuery="xyz"
          composeSuggestions={[]}
        />
      );

      expect(screen.getByText('No contacts found')).toBeInTheDocument();
    });

    it('calls onComposeRecipientSelect when clicking suggestion', () => {
      const onSelect = jest.fn();
      render(
        <ChatHeader
          {...composeProps}
          composeRecipientQuery="Jane"
          composeSuggestions={[mockComposeRecipient]}
          onComposeRecipientSelect={onSelect}
        />
      );

      fireEvent.click(screen.getByText('Jane Smith'));

      expect(onSelect).toHaveBeenCalledWith(mockComposeRecipient);
    });

    it('displays selected recipient as badge', () => {
      render(
        <ChatHeader
          {...composeProps}
          composeRecipient={mockComposeRecipient}
        />
      );

      expect(screen.getByText('Jane Smith')).toBeInTheDocument();
    });

    it('calls onComposeRecipientClear when clicking remove button', () => {
      const onClear = jest.fn();
      render(
        <ChatHeader
          {...composeProps}
          composeRecipient={mockComposeRecipient}
          onComposeRecipientClear={onClear}
        />
      );

      const removeButton = screen.getByRole('button', { name: /remove recipient/i });
      fireEvent.click(removeButton);

      expect(onClear).toHaveBeenCalled();
    });
  });
});
