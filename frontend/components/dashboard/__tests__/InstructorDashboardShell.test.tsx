/**
 * @jest-environment jsdom
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { InstructorDashboardShell } from '../InstructorDashboardShell';
import { fetchWithSessionRefresh } from '@/lib/auth/sessionRefresh';

const mockPush = jest.fn();
const mockFetchWithSessionRefresh = fetchWithSessionRefresh as jest.MockedFunction<
  typeof fetchWithSessionRefresh
>;

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('@/components/UserProfileDropdown', () => {
  const MockUserProfileDropdown = () => <div data-testid="user-dropdown" />;
  MockUserProfileDropdown.displayName = 'MockUserProfileDropdown';
  return {
    __esModule: true,
    default: MockUserProfileDropdown,
  };
});

jest.mock('@/components/notifications/NotificationBell', () => ({
  NotificationBell: ({
    onOpenChange,
    isOpen,
  }: {
    onOpenChange?: (open: boolean) => void;
    isOpen?: boolean;
  }) => (
    <button
      type="button"
      data-testid="notification-bell"
      aria-label="Notifications"
      onClick={() => onOpenChange?.(!isOpen)}
    >
      Notifications
    </button>
  ),
}));

jest.mock('@/lib/auth/sessionRefresh', () => ({
  fetchWithSessionRefresh: jest.fn(),
}));

function renderShell() {
  return render(
    <InstructorDashboardShell activeNavKey="bookings">
      <div>Shell content</div>
    </InstructorDashboardShell>
  );
}

function createConversationResponse(conversations: Array<{
  id: string;
  unread_count?: number | undefined;
  first_name?: string;
  last_initial?: string;
  content?: string | undefined;
}> = []) {
  return {
    ok: true,
    json: async () => ({
      conversations: conversations.map((conversation) => ({
        id: conversation.id,
        unread_count: conversation.unread_count ?? 0,
        other_user: {
          first_name: conversation.first_name ?? 'Emma',
          last_initial: conversation.last_initial ?? 'J.',
        },
        last_message: {
          content: conversation.content ?? 'New message',
        },
      })),
    }),
  } as Response;
}

describe('InstructorDashboardShell', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders the full dashboard header and routes empty inbox states to the messages panel', async () => {
    const user = userEvent.setup();
    mockFetchWithSessionRefresh.mockResolvedValue({
      ok: true,
      json: async () => ({}),
    } as Response);

    renderShell();

    expect(screen.getByText('iNSTAiNSTRU')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Messages' })).toBeInTheDocument();
    expect(screen.getByTestId('notification-bell')).toBeInTheDocument();
    expect(screen.getByTestId('user-dropdown')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Messages' }));

    await waitFor(() => {
      expect(screen.getByText('No unread messages.')).toBeInTheDocument();
    });
    expect(mockFetchWithSessionRefresh).toHaveBeenCalledTimes(2);

    await user.click(screen.getByRole('button', { name: 'Open inbox' }));

    expect(mockPush).toHaveBeenCalledWith('/instructor/dashboard?panel=messages');
  });

  it('renders unread conversations, shows a capped badge label, and opens the selected thread', async () => {
    const user = userEvent.setup();
    mockFetchWithSessionRefresh.mockResolvedValue(
      createConversationResponse(
        Array.from({ length: 11 }, (_, index) => ({
          id: `conversation-${index + 1}`,
          unread_count: index === 10 ? undefined : 1,
          first_name: index === 0 ? 'Sophia' : `Student${index + 1}`,
          last_initial: index === 0 ? 'B.' : 'L.',
          content:
            index === 0
              ? undefined
              : index === 1
                ? 'See you soon'
                : 'New message',
        }))
      )
    );

    renderShell();

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'Messages (9+ unread)' })
      ).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'Messages (9+ unread)' }));

    await waitFor(() => {
      expect(screen.getByText('Sophia B.')).toBeInTheDocument();
      expect(screen.getAllByText('New message').length).toBeGreaterThan(0);
      expect(screen.getByText('See you soon')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /Sophia B\./i }));

    expect(mockPush).toHaveBeenCalledWith(
      '/instructor/dashboard?panel=messages&conversation=conversation-1'
    );
  });

  it('shows the loading state while refreshing the inbox menu', async () => {
    const user = userEvent.setup();
    mockFetchWithSessionRefresh
      .mockResolvedValueOnce(createConversationResponse())
      .mockImplementationOnce(
        () =>
          new Promise<Response>(() => {
            // Intentionally unresolved to keep the loading state visible.
          })
      );

    renderShell();

    await user.click(screen.getByRole('button', { name: 'Messages' }));

    expect(await screen.findByText('Loading messages...')).toBeInTheDocument();
  });

  it('shows an explicit error when the conversations request returns a non-ok response', async () => {
    const user = userEvent.setup();
    mockFetchWithSessionRefresh.mockResolvedValue({
      ok: false,
      json: async () => ({}),
    } as Response);

    renderShell();

    await user.click(screen.getByRole('button', { name: 'Messages' }));

    expect(await screen.findByText('Failed to load messages')).toBeInTheDocument();
  });

  it('falls back to a generic error string when the fetch rejects with a non-Error value', async () => {
    const user = userEvent.setup();
    mockFetchWithSessionRefresh.mockRejectedValue('boom' as never);

    renderShell();

    await user.click(screen.getByRole('button', { name: 'Messages' }));

    expect(await screen.findByText('Failed to load messages')).toBeInTheDocument();
  });

  it('closes the messages popover when notifications are opened or when clicking outside', async () => {
    const user = userEvent.setup();
    mockFetchWithSessionRefresh.mockResolvedValue(createConversationResponse());

    renderShell();

    await user.click(screen.getByRole('button', { name: 'Messages' }));
    expect(await screen.findByText('No unread messages.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Notifications' }));
    await waitFor(() => {
      expect(screen.queryByText('No unread messages.')).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'Notifications' }));

    await user.click(screen.getByRole('button', { name: 'Messages' }));
    expect(await screen.findByText('No unread messages.')).toBeInTheDocument();

    await user.click(document.body);
    await waitFor(() => {
      expect(screen.queryByText('No unread messages.')).not.toBeInTheDocument();
    });
  });
});
