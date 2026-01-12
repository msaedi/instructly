import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useNotifications } from '@/features/shared/hooks/useNotifications';
import { notificationApi } from '@/features/shared/api/notifications';
import type { SSENotificationUpdateEvent } from '@/types/messaging';

let lastHandlers: { onNotificationUpdate?: (event: SSENotificationUpdateEvent) => void } | null = null;

jest.mock('@/features/shared/api/notifications', () => ({
  notificationApi: {
    getNotifications: jest.fn(),
    getUnreadCount: jest.fn(),
    markAsRead: jest.fn(),
    markAllAsRead: jest.fn(),
    deleteNotification: jest.fn(),
  },
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));

jest.mock('@/providers/UserMessageStreamProvider', () => ({
  useMessageStream: () => ({
    subscribe: (_id: string, handlers: { onNotificationUpdate?: (event: { unread_count: number; latest?: { id: string } }) => void }) => {
      lastHandlers = handlers;
      return () => {};
    },
  }),
}));

describe('useNotifications', () => {
  const mockedApi = notificationApi as jest.Mocked<typeof notificationApi>;

  const createWrapper = () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const Wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    Wrapper.displayName = 'NotificationsTestWrapper';
    return Wrapper;
  };

  beforeEach(() => {
    lastHandlers = null;
    jest.clearAllMocks();
  });

  it('loads notifications and unread count', async () => {
    mockedApi.getNotifications.mockResolvedValue({
      notifications: [],
      total: 0,
      unread_count: 0,
    });
    mockedApi.getUnreadCount.mockResolvedValue({ unread_count: 1 });

    const { result } = renderHook(() => useNotifications(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.unreadCount).toBe(1);
    });

    expect(result.current.notifications).toEqual([]);
  });

  it('handles SSE notification updates', async () => {
    mockedApi.getNotifications.mockResolvedValue({
      notifications: [
        {
          id: 'notif-1',
          title: 'First',
          body: 'Body',
          category: 'lesson_updates',
          type: 'booking_confirmed',
          data: null,
          read_at: null,
          created_at: '2024-01-01T00:00:00Z',
        },
      ],
      total: 1,
      unread_count: 1,
    });
    mockedApi.getUnreadCount.mockResolvedValue({ unread_count: 1 });

    const { result } = renderHook(() => useNotifications(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.notifications.length).toBe(1);
    });
    expect(lastHandlers).not.toBeNull();

    act(() => {
      lastHandlers?.onNotificationUpdate?.({
        type: 'notification_update',
        unread_count: 2,
        latest: {
          id: 'notif-2',
          title: 'Second',
          body: 'Body',
          category: 'messages',
          type: 'new_message',
          data: null,
          created_at: '2024-01-02T00:00:00Z',
        },
      });
    });

    await waitFor(() => {
      expect(result.current.unreadCount).toBe(2);
      expect(result.current.notifications[0]?.id).toBe('notif-2');
    });
  });
});
