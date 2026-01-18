import { render, screen, fireEvent } from '@testing-library/react';
import { ConversationList, type ConversationListProps } from '../ConversationList';
import { COMPOSE_THREAD_ID } from '../../constants';
import type { ConversationEntry } from '../../types';

// Mock ConversationItem to simplify testing
jest.mock('../ConversationItem', () => ({
  ConversationItem: ({ conversation, onSelect }: { conversation: ConversationEntry; onSelect: (id: string) => void }) => (
    <li data-testid={`conversation-${conversation.id}`}>
      <button onClick={() => onSelect(conversation.id)}>{conversation.name}</button>
    </li>
  ),
}));

describe('ConversationList', () => {
  const mockConversations = [
    {
      id: 'conv-1',
      name: 'John Doe',
      avatar: 'JD',
      type: 'student',
      lastMessage: 'Hello',
      timestamp: '2h',
      unread: 1,
      latestMessageAt: Date.parse('2025-01-15T10:00:00Z'),
      bookingIds: [],
      primaryBookingId: null,
      studentId: 'student-1',
      instructorId: 'instructor-1',
    },
    {
      id: 'conv-2',
      name: 'Platform Support',
      avatar: 'PS',
      type: 'platform',
      lastMessage: 'Welcome!',
      timestamp: '1d',
      unread: 0,
      latestMessageAt: Date.parse('2025-01-14T09:00:00Z'),
      bookingIds: [],
      primaryBookingId: null,
      studentId: null,
      instructorId: 'instructor-1',
    },
  ] as ConversationEntry[];

  const defaultProps: ConversationListProps = {
    conversations: mockConversations,
    selectedChat: null,
    searchQuery: '',
    typeFilter: 'all',
    messageDisplay: 'inbox',
    isLoading: false,
    error: null,
    archivedMessagesByThread: {},
    trashMessagesByThread: {},
    onSearchChange: jest.fn(),
    onTypeFilterChange: jest.fn(),
    onMessageDisplayChange: jest.fn(),
    onConversationSelect: jest.fn(),
    onConversationArchive: jest.fn(),
    onConversationDelete: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('search functionality', () => {
    it('renders search input', () => {
      render(<ConversationList {...defaultProps} />);

      expect(screen.getByPlaceholderText('Search conversations')).toBeInTheDocument();
    });

    it('displays current search query', () => {
      render(<ConversationList {...defaultProps} searchQuery="John" />);

      const input = screen.getByPlaceholderText('Search conversations');
      expect(input).toHaveValue('John');
    });

    it('calls onSearchChange when typing', () => {
      const onSearchChange = jest.fn();
      render(<ConversationList {...defaultProps} onSearchChange={onSearchChange} />);

      const input = screen.getByPlaceholderText('Search conversations');
      fireEvent.change(input, { target: { value: 'test' } });

      expect(onSearchChange).toHaveBeenCalledWith('test');
    });
  });

  describe('compose button', () => {
    it('renders compose button', () => {
      render(<ConversationList {...defaultProps} />);

      expect(screen.getByRole('button', { name: /compose message/i })).toBeInTheDocument();
    });

    it('calls onConversationSelect with COMPOSE_THREAD_ID when clicked', () => {
      const onSelect = jest.fn();
      render(<ConversationList {...defaultProps} onConversationSelect={onSelect} />);

      fireEvent.click(screen.getByRole('button', { name: /compose message/i }));

      expect(onSelect).toHaveBeenCalledWith(COMPOSE_THREAD_ID);
    });
  });

  describe('filter buttons', () => {
    it('renders All filter button', () => {
      render(<ConversationList {...defaultProps} />);

      expect(screen.getByRole('button', { name: /^all$/i })).toBeInTheDocument();
    });

    it('renders Students filter button', () => {
      render(<ConversationList {...defaultProps} />);

      expect(screen.getByRole('button', { name: /students/i })).toBeInTheDocument();
    });

    it('renders Platform filter button', () => {
      render(<ConversationList {...defaultProps} />);

      // Use exact match to distinguish from "Platform Support" conversation
      expect(screen.getByRole('button', { name: /^platform$/i })).toBeInTheDocument();
    });

    it('renders Archived button', () => {
      render(<ConversationList {...defaultProps} />);

      expect(screen.getByRole('button', { name: /archived/i })).toBeInTheDocument();
    });

    it('renders Trash button', () => {
      render(<ConversationList {...defaultProps} />);

      expect(screen.getByRole('button', { name: /trash/i })).toBeInTheDocument();
    });

    it('highlights active type filter', () => {
      render(<ConversationList {...defaultProps} typeFilter="student" />);

      const studentsButton = screen.getByRole('button', { name: /students/i });
      expect(studentsButton).toHaveClass('bg-[#7E22CE]', 'text-white');
    });

    it('highlights archived when in archived mode', () => {
      render(<ConversationList {...defaultProps} messageDisplay="archived" />);

      const archivedButton = screen.getByRole('button', { name: /archived/i });
      expect(archivedButton).toHaveClass('bg-[#7E22CE]', 'text-white');
    });

    it('calls onTypeFilterChange and onMessageDisplayChange when clicking filter', () => {
      const onTypeFilterChange = jest.fn();
      const onMessageDisplayChange = jest.fn();

      render(
        <ConversationList
          {...defaultProps}
          onTypeFilterChange={onTypeFilterChange}
          onMessageDisplayChange={onMessageDisplayChange}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /students/i }));

      expect(onTypeFilterChange).toHaveBeenCalledWith('student');
      expect(onMessageDisplayChange).toHaveBeenCalledWith('inbox');
    });

    it('calls onMessageDisplayChange when clicking Archived', () => {
      const onMessageDisplayChange = jest.fn();

      render(
        <ConversationList {...defaultProps} onMessageDisplayChange={onMessageDisplayChange} />
      );

      fireEvent.click(screen.getByRole('button', { name: /archived/i }));

      expect(onMessageDisplayChange).toHaveBeenCalledWith('archived');
    });

    it('calls onMessageDisplayChange when clicking Trash', () => {
      const onMessageDisplayChange = jest.fn();

      render(
        <ConversationList {...defaultProps} onMessageDisplayChange={onMessageDisplayChange} />
      );

      fireEvent.click(screen.getByRole('button', { name: /trash/i }));

      expect(onMessageDisplayChange).toHaveBeenCalledWith('trash');
    });
  });

  describe('conversation list', () => {
    it('renders conversation items', () => {
      render(<ConversationList {...defaultProps} />);

      expect(screen.getByText('John Doe')).toBeInTheDocument();
      expect(screen.getByText('Platform Support')).toBeInTheDocument();
    });

    it('shows loading state when loading and no conversations', () => {
      render(
        <ConversationList {...defaultProps} isLoading={true} conversations={[]} />
      );

      expect(screen.getByText('Loading conversations...')).toBeInTheDocument();
    });

    it('shows empty state when no conversations', () => {
      render(<ConversationList {...defaultProps} conversations={[]} />);

      expect(screen.getByText('No conversations found.')).toBeInTheDocument();
    });

    it('shows error message when error exists', () => {
      render(
        <ConversationList {...defaultProps} error="Failed to load conversations" />
      );

      expect(screen.getByText('Failed to load conversations')).toBeInTheDocument();
    });
  });
});
