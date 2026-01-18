import { render, screen, fireEvent } from '@testing-library/react';
import { ConversationItem, type ConversationItemProps } from '../ConversationItem';
import { COMPOSE_THREAD_ID } from '../../constants';
import type { ConversationEntry } from '../../types';

// Mock the date formatter
jest.mock('@/components/messaging/formatters', () => ({
  formatShortDate: jest.fn((date: Date) => {
    const month = date.toLocaleString('default', { month: 'short' });
    const day = date.getDate();
    return `${month} ${day}`;
  }),
}));

describe('ConversationItem', () => {
  const mockConversation = {
    id: 'conv-123',
    name: 'John Doe',
    avatar: 'JD',
    type: 'student',
    lastMessage: 'Hey, when is our next lesson?',
    timestamp: '2h ago',
    unread: 0,
    latestMessageAt: Date.parse('2025-01-15T10:00:00Z'),
    bookingIds: [],
    primaryBookingId: null,
    studentId: 'student-1',
    instructorId: 'instructor-1',
  } as ConversationEntry;

  const defaultProps: ConversationItemProps = {
    conversation: mockConversation,
    isActive: false,
    archivedCount: 0,
    trashCount: 0,
    messageDisplay: 'inbox',
    onSelect: jest.fn(),
    onArchive: jest.fn(),
    onDelete: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('regular conversation', () => {
    it('renders conversation name', () => {
      render(<ConversationItem {...defaultProps} />);

      expect(screen.getByText('John Doe')).toBeInTheDocument();
    });

    it('renders avatar initials', () => {
      render(<ConversationItem {...defaultProps} />);

      expect(screen.getByText('JD')).toBeInTheDocument();
    });

    it('renders last message preview', () => {
      render(<ConversationItem {...defaultProps} />);

      expect(screen.getByText('Hey, when is our next lesson?')).toBeInTheDocument();
    });

    it('renders formatted date', () => {
      render(<ConversationItem {...defaultProps} />);

      expect(screen.getByText('Jan 15')).toBeInTheDocument();
    });

    it('calls onSelect when clicked', () => {
      const onSelect = jest.fn();
      render(<ConversationItem {...defaultProps} onSelect={onSelect} />);

      // Click the main conversation button (first button)
      fireEvent.click(screen.getAllByRole('button')[0]!);

      expect(onSelect).toHaveBeenCalledWith('conv-123');
    });

    it('applies active styles when selected', () => {
      render(<ConversationItem {...defaultProps} isActive={true} />);

      // Get the main conversation button (first button)
      const button = screen.getAllByRole('button')[0]!;
      expect(button).toHaveClass('bg-purple-50');
    });

    it('applies student avatar colors', () => {
      const { container } = render(<ConversationItem {...defaultProps} />);

      // Find the avatar element with the initials - it's the div with the rounded-full class
      const avatar = container.querySelector('.bg-purple-100.text-purple-600');
      expect(avatar).toBeInTheDocument();
      expect(avatar).toHaveTextContent('JD');
    });

    it('applies platform avatar colors', () => {
      const platformConversation = { ...mockConversation, type: 'platform' as const };
      const { container } = render(
        <ConversationItem {...defaultProps} conversation={platformConversation} />
      );

      // Find the avatar element with platform colors
      const avatar = container.querySelector('.bg-blue-100.text-blue-600');
      expect(avatar).toBeInTheDocument();
      expect(avatar).toHaveTextContent('JD');
    });
  });

  describe('unread indicator', () => {
    it('shows unread dot when unread > 0', () => {
      const unreadConversation = { ...mockConversation, unread: 3 };
      render(
        <ConversationItem {...defaultProps} conversation={unreadConversation} />
      );

      expect(screen.getByText('3 unread messages')).toBeInTheDocument();
    });

    it('shows singular unread message text for 1 unread', () => {
      const unreadConversation = { ...mockConversation, unread: 1 };
      render(
        <ConversationItem {...defaultProps} conversation={unreadConversation} />
      );

      expect(screen.getByText('1 unread message')).toBeInTheDocument();
    });

    it('does not show unread dot when unread is 0', () => {
      render(<ConversationItem {...defaultProps} />);

      expect(screen.queryByText(/unread message/)).not.toBeInTheDocument();
    });
  });

  describe('archive and trash counts', () => {
    it('shows archived count when > 0', () => {
      render(<ConversationItem {...defaultProps} archivedCount={5} />);

      expect(screen.getByText('5')).toBeInTheDocument();
    });

    it('shows trash count when > 0', () => {
      render(<ConversationItem {...defaultProps} trashCount={2} />);

      expect(screen.getByText('2')).toBeInTheDocument();
    });

    it('does not show counts when 0', () => {
      const { container } = render(<ConversationItem {...defaultProps} />);

      // No archive or trash icons should be visible
      const counts = container.querySelectorAll('.flex.items-center.gap-1 span');
      expect(counts.length).toBe(0);
    });
  });

  describe('hover actions', () => {
    it('renders archive and delete buttons in inbox view', () => {
      render(<ConversationItem {...defaultProps} />);

      expect(screen.getByRole('button', { name: /archive conversation/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /delete conversation/i })).toBeInTheDocument();
    });

    it('does not render actions in archived view', () => {
      render(<ConversationItem {...defaultProps} messageDisplay="archived" />);

      expect(screen.queryByRole('button', { name: /archive conversation/i })).not.toBeInTheDocument();
    });

    it('does not render actions in trash view', () => {
      render(<ConversationItem {...defaultProps} messageDisplay="trash" />);

      expect(screen.queryByRole('button', { name: /delete conversation/i })).not.toBeInTheDocument();
    });

    it('calls onArchive when archive button clicked', () => {
      const onArchive = jest.fn();
      render(<ConversationItem {...defaultProps} onArchive={onArchive} />);

      fireEvent.click(screen.getByRole('button', { name: /archive conversation/i }));

      expect(onArchive).toHaveBeenCalledWith('conv-123');
    });

    it('calls onDelete when delete button clicked', () => {
      const onDelete = jest.fn();
      render(<ConversationItem {...defaultProps} onDelete={onDelete} />);

      fireEvent.click(screen.getByRole('button', { name: /delete conversation/i }));

      expect(onDelete).toHaveBeenCalledWith('conv-123');
    });

    it('stops propagation on action button clicks', () => {
      const onSelect = jest.fn();
      const onArchive = jest.fn();
      render(
        <ConversationItem {...defaultProps} onSelect={onSelect} onArchive={onArchive} />
      );

      fireEvent.click(screen.getByRole('button', { name: /archive conversation/i }));

      expect(onArchive).toHaveBeenCalled();
      expect(onSelect).not.toHaveBeenCalled();
    });
  });

  describe('compose thread', () => {
    const composeConversation = {
      id: COMPOSE_THREAD_ID,
      name: 'Compose',
      avatar: '',
      type: 'student',
      lastMessage: '',
      timestamp: '',
      unread: 0,
      latestMessageAt: 0,
      bookingIds: [],
      primaryBookingId: null,
      studentId: null,
      instructorId: null,
    } as ConversationEntry;

    it('renders "New Message" text for compose thread', () => {
      render(
        <ConversationItem {...defaultProps} conversation={composeConversation} />
      );

      expect(screen.getByText('New Message')).toBeInTheDocument();
    });

    it('renders "Draft a message" as preview', () => {
      render(
        <ConversationItem {...defaultProps} conversation={composeConversation} />
      );

      expect(screen.getByText('Draft a message')).toBeInTheDocument();
    });

    it('does not render action buttons for compose', () => {
      render(
        <ConversationItem {...defaultProps} conversation={composeConversation} />
      );

      expect(screen.queryByRole('button', { name: /archive/i })).not.toBeInTheDocument();
    });

    it('does not show unread indicator for compose', () => {
      const composeWithUnread = { ...composeConversation, unread: 5 };
      render(
        <ConversationItem {...defaultProps} conversation={composeWithUnread} />
      );

      expect(screen.queryByText(/unread/)).not.toBeInTheDocument();
    });

    it('applies compose avatar styles', () => {
      const { container } = render(
        <ConversationItem {...defaultProps} conversation={composeConversation} />
      );

      const avatar = container.querySelector('.bg-\\[\\#7E22CE\\]');
      expect(avatar).toBeInTheDocument();
    });
  });
});
