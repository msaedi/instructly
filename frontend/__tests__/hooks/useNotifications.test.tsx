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
    deleteAll: jest.fn(),
  },
}));

const mockUseAuth = jest.fn().mockReturnValue({ isAuthenticated: true });
jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => mockUseAuth(),
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
    mockUseAuth.mockReturnValue({ isAuthenticated: true });
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

  it('handles SSE update when notification already exists', async () => {
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

    // Send SSE update with same notification ID
    act(() => {
      lastHandlers?.onNotificationUpdate?.({
        type: 'notification_update',
        unread_count: 0,
        latest: {
          id: 'notif-1', // Same ID - should not duplicate
          title: 'First',
          body: 'Body',
          category: 'lesson_updates',
          type: 'booking_confirmed',
          data: null,
          created_at: '2024-01-01T00:00:00Z',
        },
      });
    });

    await waitFor(() => {
      expect(result.current.unreadCount).toBe(0);
    });
    // Should still have only 1 notification
    expect(result.current.notifications.length).toBe(1);
  });

  it('handles SSE update without latest notification', async () => {
    mockedApi.getNotifications.mockResolvedValue({
      notifications: [],
      total: 0,
      unread_count: 0,
    });
    mockedApi.getUnreadCount.mockResolvedValue({ unread_count: 0 });

    const { result } = renderHook(() => useNotifications(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    // Send SSE update without latest
    act(() => {
      lastHandlers?.onNotificationUpdate?.({
        type: 'notification_update',
        unread_count: 1,
        // No latest property - triggers invalidateQueries
      });
    });

    await waitFor(() => {
      expect(result.current.unreadCount).toBe(1);
    });
  });

  it('handles markAsRead mutation with optimistic update', async () => {
    // First return unread notification, after mutation return updated version
    mockedApi.getNotifications
      .mockResolvedValueOnce({
        notifications: [
          {
            id: 'notif-1',
            title: 'Unread',
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
      })
      .mockResolvedValue({
        notifications: [
          {
            id: 'notif-1',
            title: 'Unread',
            body: 'Body',
            category: 'lesson_updates',
            type: 'booking_confirmed',
            data: null,
            read_at: '2024-01-02T00:00:00Z',
            created_at: '2024-01-01T00:00:00Z',
          },
        ],
        total: 1,
        unread_count: 0,
      });
    mockedApi.getUnreadCount
      .mockResolvedValueOnce({ unread_count: 1 })
      .mockResolvedValue({ unread_count: 0 });
    mockedApi.markAsRead.mockResolvedValue(undefined);

    const { result } = renderHook(() => useNotifications(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.notifications.length).toBe(1);
    });

    await act(async () => {
      await result.current.markAsRead.mutateAsync('notif-1');
    });

    // After mutation, should have updated read_at (from refetch in onSettled)
    await waitFor(() => {
      expect(result.current.notifications[0]?.read_at).toBeTruthy();
    });
    expect(mockedApi.markAsRead).toHaveBeenCalledWith('notif-1');
  });

  it('handles markAsRead for already read notification', async () => {
    mockedApi.getNotifications.mockResolvedValue({
      notifications: [
        {
          id: 'notif-1',
          title: 'Already Read',
          body: 'Body',
          category: 'lesson_updates',
          type: 'booking_confirmed',
          data: null,
          read_at: '2024-01-01T00:00:00Z', // Already read
          created_at: '2024-01-01T00:00:00Z',
        },
      ],
      total: 1,
      unread_count: 0,
    });
    mockedApi.getUnreadCount.mockResolvedValue({ unread_count: 0 });
    mockedApi.markAsRead.mockResolvedValue(undefined);

    const { result } = renderHook(() => useNotifications(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.notifications.length).toBe(1);
    });

    await act(async () => {
      await result.current.markAsRead.mutateAsync('notif-1');
    });

    // API should still be called even if already read
    expect(mockedApi.markAsRead).toHaveBeenCalledWith('notif-1');
  });

  it('handles markAsRead error with rollback', async () => {
    mockedApi.getNotifications.mockResolvedValue({
      notifications: [
        {
          id: 'notif-1',
          title: 'Unread',
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
    mockedApi.markAsRead.mockRejectedValue(new Error('Server error'));

    const { result } = renderHook(() => useNotifications(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.notifications.length).toBe(1);
    });

    await act(async () => {
      try {
        await result.current.markAsRead.mutateAsync('notif-1');
      } catch {
        // Expected to fail
      }
    });

    // Should rollback optimistic update
    await waitFor(() => {
      expect(result.current.notifications[0]?.read_at).toBeNull();
    });
  });

  it('handles markAllAsRead mutation', async () => {
    mockedApi.getNotifications.mockResolvedValue({
      notifications: [
        {
          id: 'notif-1',
          title: 'Unread',
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
    mockedApi.markAllAsRead.mockResolvedValue(undefined);

    const { result } = renderHook(() => useNotifications(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.unreadCount).toBe(1);
    });

    await act(async () => {
      await result.current.markAllAsRead.mutateAsync();
    });

    expect(mockedApi.markAllAsRead).toHaveBeenCalled();
  });

  it('handles deleteNotification mutation', async () => {
    mockedApi.getNotifications.mockResolvedValue({
      notifications: [
        {
          id: 'notif-1',
          title: 'To Delete',
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
    mockedApi.deleteNotification.mockResolvedValue(undefined);

    const { result } = renderHook(() => useNotifications(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.notifications.length).toBe(1);
    });

    await act(async () => {
      await result.current.deleteNotification.mutateAsync('notif-1');
    });

    expect(mockedApi.deleteNotification).toHaveBeenCalledWith('notif-1');
  });

  it('handles clearAll mutation', async () => {
    mockedApi.getNotifications.mockResolvedValue({
      notifications: [
        {
          id: 'notif-1',
          title: 'To Clear',
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
    mockedApi.deleteAll.mockResolvedValue(undefined);

    const { result } = renderHook(() => useNotifications(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.notifications.length).toBe(1);
    });

    await act(async () => {
      await result.current.clearAll.mutateAsync();
    });

    expect(mockedApi.deleteAll).toHaveBeenCalled();
  });

  it('does not subscribe when not authenticated', async () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: false });

    const { result } = renderHook(() => useNotifications(), { wrapper: createWrapper() });

    // Should not subscribe to SSE
    expect(lastHandlers).toBeNull();
    // Queries should be disabled
    expect(result.current.isLoading).toBe(false);
  });

  it('uses custom query params', async () => {
    mockedApi.getNotifications.mockResolvedValue({
      notifications: [],
      total: 0,
      unread_count: 0,
    });
    mockedApi.getUnreadCount.mockResolvedValue({ unread_count: 0 });

    renderHook(() => useNotifications({ limit: 10, offset: 5, unreadOnly: true }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(mockedApi.getNotifications).toHaveBeenCalledWith({
        limit: 10,
        offset: 5,
        unreadOnly: true,
      });
    });
  });

  it('exposes total and error from query', async () => {
    mockedApi.getNotifications.mockResolvedValue({
      notifications: [
        {
          id: 'notif-1',
          title: 'Test',
          body: 'Body',
          category: 'lesson_updates',
          type: 'booking_confirmed',
          data: null,
          read_at: null,
          created_at: '2024-01-01T00:00:00Z',
        },
      ],
      total: 50,
      unread_count: 10,
    });
    mockedApi.getUnreadCount.mockResolvedValue({ unread_count: 10 });

    const { result } = renderHook(() => useNotifications(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.total).toBe(50);
    });
    expect(result.current.error).toBeNull();
  });

  it('exposes refetch function', async () => {
    mockedApi.getNotifications.mockResolvedValue({
      notifications: [],
      total: 0,
      unread_count: 0,
    });
    mockedApi.getUnreadCount.mockResolvedValue({ unread_count: 0 });

    const { result } = renderHook(() => useNotifications(), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    await act(async () => {
      await result.current.refetch();
    });

    // getNotifications should have been called at least twice (initial + refetch)
    expect(mockedApi.getNotifications).toHaveBeenCalledTimes(2);
  });
});
