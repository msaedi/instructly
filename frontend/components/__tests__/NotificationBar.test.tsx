import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NotificationBar } from '../NotificationBar';
import { useAuth } from '@/features/shared/hooks/useAuth';

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(),
}));

const useAuthMock = useAuth as jest.Mock;

const setupSessionStorage = (initial: Record<string, number> = {}) => {
  const storage: Record<string, string> = {
    dismissedNotifications: JSON.stringify(initial),
  };
  Object.defineProperty(window, 'sessionStorage', {
    value: {
      getItem: jest.fn((key: string) => storage[key] ?? null),
      setItem: jest.fn((key: string, value: string) => {
        storage[key] = value;
      }),
    },
    configurable: true,
  });
};

describe('NotificationBar', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setupSessionStorage();
  });

  it('returns null when unauthenticated', () => {
    useAuthMock.mockReturnValue({ user: null, isAuthenticated: false });

    const { container } = render(<NotificationBar />);

    expect(container.firstChild).toBeNull();
  });

  it('shows credits notification with highest priority', async () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-10T10:00:00Z'));
    useAuthMock.mockReturnValue({
      user: { credits_balance: 25, created_at: '2025-01-09T10:00:00Z' },
      isAuthenticated: true,
    });

    render(<NotificationBar />);

    jest.runOnlyPendingTimers();
    await waitFor(() => {
      expect(screen.getByText(/You have \$25 in credits!/i)).toBeInTheDocument();
    });
    jest.useRealTimers();
  });

  it('shows welcome notification for new users when no credits', async () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-10T10:00:00Z'));
    useAuthMock.mockReturnValue({
      user: { credits_balance: 0, created_at: '2025-01-09T10:00:00Z' },
      isAuthenticated: true,
    });

    render(<NotificationBar />);

    jest.runOnlyPendingTimers();
    await waitFor(() => {
      expect(screen.getByText(/welcome to instainstru/i)).toBeInTheDocument();
    });
    jest.useRealTimers();
  });

  it('dismisses the current notification and stores it', async () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-10T10:00:00Z'));
    useAuthMock.mockReturnValue({
      user: { credits_balance: 10, created_at: '2025-01-01T10:00:00Z' },
      isAuthenticated: true,
    });

    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    const { container } = render(<NotificationBar />);

    jest.runOnlyPendingTimers();
    await waitFor(() => expect(screen.getByText(/credits/i)).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /dismiss notification/i }));

    expect(window.sessionStorage.setItem).toHaveBeenCalled();
    expect(container.firstChild).toBeNull();
    jest.useRealTimers();
  });

  it('hides dismissed notifications within 24 hours', async () => {
    jest.useFakeTimers();
    const now = new Date('2025-01-10T10:00:00Z').getTime();
    jest.setSystemTime(new Date(now));
    setupSessionStorage({ credits: now - 60 * 60 * 1000 });
    useAuthMock.mockReturnValue({
      user: { credits_balance: 10, created_at: '2025-01-01T10:00:00Z' },
      isAuthenticated: true,
    });

    const { container } = render(<NotificationBar />);
    jest.runOnlyPendingTimers();

    await waitFor(() => {
      expect(container.firstChild).toBeNull();
    });
    jest.useRealTimers();
  });

  it('shows notifications again after 24 hours', async () => {
    jest.useFakeTimers();
    const now = new Date('2025-01-10T10:00:00Z').getTime();
    jest.setSystemTime(new Date(now));
    setupSessionStorage({ credits: now - 25 * 60 * 60 * 1000 });
    useAuthMock.mockReturnValue({
      user: { credits_balance: 10, created_at: '2025-01-01T10:00:00Z' },
      isAuthenticated: true,
    });

    render(<NotificationBar />);
    jest.runOnlyPendingTimers();

    await waitFor(() => {
      expect(screen.getByText(/credits/i)).toBeInTheDocument();
    });
    jest.useRealTimers();
  });
});
