import { render, screen, fireEvent } from '@testing-library/react';
import { ChatHeader, type ChatHeaderProps } from '../ChatHeader';
import type { ConversationEntry } from '../../types';

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
      id: 'booking-123',
      service_name: 'Piano Lesson',
      date: '2025-01-20',
      start_time: '09:00',
    },
    upcomingBookingCount: 2,
    upcomingBookings: [
      {
        id: 'booking-123',
        service_name: 'Piano Lesson',
        date: '2025-01-20',
        start_time: '09:00',
      },
      {
        id: 'booking-456',
        service_name: 'Guitar Lesson',
        date: '2025-01-22',
        start_time: '14:30',
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

    it('toggles menu on button click', () => {
      render(<ChatHeader {...defaultProps} />);

      const menuButton = screen.getByRole('button', { expanded: false });
      fireEvent.click(menuButton);

      expect(screen.getByRole('menu')).toBeInTheDocument();
      expect(screen.getByText('Booking Info')).toBeInTheDocument();
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

    it('shows next booking in menu', () => {
      render(
        <ChatHeader
          {...defaultProps}
          activeConversation={mockConversationWithBooking}
        />
      );

      const menuButton = screen.getByRole('button', { expanded: false });
      fireEvent.click(menuButton);

      expect(screen.getByText('Next Booking')).toBeInTheDocument();
      expect(screen.getByText('Upcoming')).toBeInTheDocument();
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

      expect(screen.getByText(/\+1 more upcoming booking/)).toBeInTheDocument();
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

      // Click the expand button (the one with "upcoming booking" text)
      const expandButton = screen.getByText(/\+1 more upcoming booking/);
      fireEvent.click(expandButton);

      expect(screen.getByText('Guitar Lesson')).toBeInTheDocument();
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
