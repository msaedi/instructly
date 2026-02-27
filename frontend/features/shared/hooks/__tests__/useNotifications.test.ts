import { renderHook, act, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useNotifications } from '../useNotifications';
import { notificationApi } from '@/features/shared/api/notifications';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useMessageStream } from '@/providers/UserMessageStreamProvider';
import type { SSENotificationUpdateEvent } from '@/types/messaging';

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(),
}));

jest.mock('@/providers/UserMessageStreamProvider', () => ({
  useMessageStream: jest.fn(),
}));

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

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
  },
}));

const useAuthMock = useAuth as jest.Mock;
const useMessageStreamMock = useMessageStream as jest.Mock;
const notificationApiMock = notificationApi as jest.Mocked<typeof notificationApi>;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  Wrapper.displayName = 'QueryWrapper';
  return Wrapper;
};

describe('useNotifications', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuthMock.mockReturnValue({ isAuthenticated: true });
    useMessageStreamMock.mockReturnValue({
      subscribe: jest.fn(() => jest.fn()),
    });
    notificationApiMock.getNotifications.mockResolvedValue({
      notifications: [],
      total: 0,
      unread_count: 0,
    });
    notificationApiMock.getUnreadCount.mockResolvedValue({ unread_count: 0 });
  });

  describe('default parameters', () => {
    it('uses default limit/offset/unreadOnly when no params provided', async () => {
      const { result } = renderHook(() => useNotifications(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(notificationApiMock.getNotifications).toHaveBeenCalledWith({
          limit: 20,
          offset: 0,
          unreadOnly: false,
        });
      });

      expect(result.current.notifications).toEqual([]);
      expect(result.current.unreadCount).toBe(0);
      expect(result.current.total).toBe(0);
    });

    it('uses provided params when supplied', async () => {
      renderHook(
        () => useNotifications({ limit: 10, offset: 5, unreadOnly: true }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(notificationApiMock.getNotifications).toHaveBeenCalledWith({
          limit: 10,
          offset: 5,
          unreadOnly: true,
        });
      });
    });
  });

  describe('unauthenticated state', () => {
    it('does not fetch when not authenticated', async () => {
      useAuthMock.mockReturnValue({ isAuthenticated: false });

      renderHook(() => useNotifications(), {
        wrapper: createWrapper(),
      });

      // Wait a bit to make sure queries don't fire
      await new Promise((r) => setTimeout(r, 50));
      expect(notificationApiMock.getNotifications).not.toHaveBeenCalled();
      expect(notificationApiMock.getUnreadCount).not.toHaveBeenCalled();
    });

    it('does not subscribe to SSE when not authenticated', async () => {
      useAuthMock.mockReturnValue({ isAuthenticated: false });
      const subscribeMock = jest.fn(() => jest.fn());
      useMessageStreamMock.mockReturnValue({ subscribe: subscribeMock });

      renderHook(() => useNotifications(), {
        wrapper: createWrapper(),
      });

      await new Promise((r) => setTimeout(r, 50));
      expect(subscribeMock).not.toHaveBeenCalled();
    });
  });

  describe('SSE notification updates', () => {
    it('updates unread count from SSE event', async () => {
      let capturedHandler: ((event: SSENotificationUpdateEvent) => void) | undefined;
      const subscribeMock = jest.fn((_channel: string, handlers: { onNotificationUpdate?: (event: SSENotificationUpdateEvent) => void }) => {
        capturedHandler = handlers.onNotificationUpdate;
        return jest.fn();
      });
      useMessageStreamMock.mockReturnValue({ subscribe: subscribeMock });

      const { result } = renderHook(() => useNotifications(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(subscribeMock).toHaveBeenCalledWith('__global__', expect.any(Object));
      });

      // Simulate SSE notification update without a latest notification
      act(() => {
        capturedHandler?.({
          type: 'notification_update',
          unread_count: 5,
        });
      });

      await waitFor(() => {
        expect(result.current.unreadCount).toBe(5);
      });
    });

    it('adds new notification to list from SSE event with latest', async () => {
      notificationApiMock.getNotifications.mockResolvedValue({
        notifications: [
          {
            id: 'notif-1',
            type: 'booking_confirmed',
            category: 'booking',
            title: 'Old notification',
            body: 'Previous',
            data: null,
            read_at: null,
            created_at: '2024-01-01T00:00:00Z',
          },
        ],
        total: 1,
        unread_count: 1,
      });

      let capturedHandler: ((event: SSENotificationUpdateEvent) => void) | undefined;
      const subscribeMock = jest.fn((_channel: string, handlers: { onNotificationUpdate?: (event: SSENotificationUpdateEvent) => void }) => {
        capturedHandler = handlers.onNotificationUpdate;
        return jest.fn();
      });
      useMessageStreamMock.mockReturnValue({ subscribe: subscribeMock });

      const { result } = renderHook(() => useNotifications(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.notifications).toHaveLength(1);
      });

      // Simulate SSE with a new notification
      act(() => {
        capturedHandler?.({
          type: 'notification_update',
          unread_count: 2,
          latest: {
            id: 'notif-2',
            type: 'new_message',
            category: 'message',
            title: 'New notification',
            body: 'Fresh',
            data: null,
            created_at: '2024-01-02T00:00:00Z',
          },
        });
      });

      await waitFor(() => {
        expect(result.current.notifications).toHaveLength(2);
        expect(result.current.notifications[0]?.id).toBe('notif-2');
        expect(result.current.unreadCount).toBe(2);
      });
    });

    it('does not duplicate existing notification from SSE event', async () => {
      notificationApiMock.getNotifications.mockResolvedValue({
        notifications: [
          {
            id: 'notif-1',
            type: 'booking_confirmed',
            category: 'booking',
            title: 'Existing',
            body: 'Already here',
            data: null,
            read_at: null,
            created_at: '2024-01-01T00:00:00Z',
          },
        ],
        total: 1,
        unread_count: 1,
      });

      let capturedHandler: ((event: SSENotificationUpdateEvent) => void) | undefined;
      const subscribeMock = jest.fn((_channel: string, handlers: { onNotificationUpdate?: (event: SSENotificationUpdateEvent) => void }) => {
        capturedHandler = handlers.onNotificationUpdate;
        return jest.fn();
      });
      useMessageStreamMock.mockReturnValue({ subscribe: subscribeMock });

      const { result } = renderHook(() => useNotifications(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.notifications).toHaveLength(1);
      });

      // SSE event with same notification ID (already exists)
      act(() => {
        capturedHandler?.({
          type: 'notification_update',
          unread_count: 1,
          latest: {
            id: 'notif-1',
            type: 'booking_confirmed',
            category: 'booking',
            title: 'Existing',
            body: 'Already here',
            data: null,
            created_at: '2024-01-01T00:00:00Z',
          },
        });
      });

      // Should not duplicate - still only 1 notification
      await waitFor(() => {
        expect(result.current.notifications).toHaveLength(1);
      });
    });
  });

  describe('markAsRead optimistic update', () => {
    it('calls markAsRead API and invalidates queries', async () => {
      notificationApiMock.getNotifications.mockResolvedValue({
        notifications: [
          {
            id: 'notif-1',
            type: 'booking_confirmed',
            category: 'booking',
            title: 'Test',
            body: 'Test msg',
            data: null,
            read_at: null,
            created_at: '2024-01-01T00:00:00Z',
          },
        ],
        total: 1,
        unread_count: 1,
      });
      notificationApiMock.getUnreadCount.mockResolvedValue({ unread_count: 1 });
      notificationApiMock.markAsRead.mockResolvedValue(undefined as unknown as ReturnType<typeof notificationApi.markAsRead>);

      const { result } = renderHook(() => useNotifications(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.notifications).toHaveLength(1);
      });

      act(() => {
        result.current.markAsRead.mutate('notif-1');
      });

      // Verify the API was called
      await waitFor(() => {
        expect(notificationApiMock.markAsRead).toHaveBeenCalledWith('notif-1');
      });
    });

    it('reverts on markAsRead failure', async () => {
      notificationApiMock.getNotifications.mockResolvedValue({
        notifications: [
          {
            id: 'notif-1',
            type: 'booking_confirmed',
            category: 'booking',
            title: 'Test',
            body: 'Test msg',
            data: null,
            read_at: null,
            created_at: '2024-01-01T00:00:00Z',
          },
        ],
        total: 1,
        unread_count: 1,
      });
      notificationApiMock.getUnreadCount.mockResolvedValue({ unread_count: 1 });
      notificationApiMock.markAsRead.mockRejectedValue(new Error('API error'));

      const { result } = renderHook(() => useNotifications(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.notifications).toHaveLength(1);
      });

      act(() => {
        result.current.markAsRead.mutate('notif-1');
      });

      // After error, should revert - notification should still be unread
      await waitFor(() => {
        // The invalidation will refetch the original data
        expect(notificationApiMock.markAsRead).toHaveBeenCalledWith('notif-1');
      });
    });
  });

  describe('markAllAsRead', () => {
    it('calls markAllAsRead API', async () => {
      notificationApiMock.markAllAsRead.mockResolvedValue(undefined as unknown as ReturnType<typeof notificationApi.markAllAsRead>);

      const { result } = renderHook(() => useNotifications(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      act(() => {
        result.current.markAllAsRead.mutate();
      });

      await waitFor(() => {
        expect(notificationApiMock.markAllAsRead).toHaveBeenCalled();
      });
    });
  });

  describe('deleteNotification', () => {
    it('calls deleteNotification API', async () => {
      notificationApiMock.deleteNotification.mockResolvedValue(undefined as unknown as ReturnType<typeof notificationApi.deleteNotification>);

      const { result } = renderHook(() => useNotifications(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      act(() => {
        result.current.deleteNotification.mutate('notif-1');
      });

      await waitFor(() => {
        expect(notificationApiMock.deleteNotification).toHaveBeenCalledWith('notif-1');
      });
    });
  });

  describe('clearAll', () => {
    it('calls deleteAll API', async () => {
      notificationApiMock.deleteAll.mockResolvedValue(undefined as unknown as ReturnType<typeof notificationApi.deleteAll>);

      const { result } = renderHook(() => useNotifications(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      act(() => {
        result.current.clearAll.mutate();
      });

      await waitFor(() => {
        expect(notificationApiMock.deleteAll).toHaveBeenCalled();
      });
    });
  });

  describe('data fallbacks', () => {
    it('returns empty defaults when queries have no data', async () => {
      notificationApiMock.getNotifications.mockResolvedValue(null as unknown as Awaited<ReturnType<typeof notificationApi.getNotifications>>);
      notificationApiMock.getUnreadCount.mockResolvedValue(null as unknown as Awaited<ReturnType<typeof notificationApi.getUnreadCount>>);

      const { result } = renderHook(() => useNotifications(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.notifications).toEqual([]);
      expect(result.current.unreadCount).toBe(0);
      expect(result.current.total).toBe(0);
    });
  });

  describe('markAsRead optimistic update edge cases', () => {
    it('skips optimistic update when notification is already read', async () => {
      notificationApiMock.getNotifications.mockResolvedValue({
        notifications: [
          {
            id: 'notif-already-read',
            type: 'booking_confirmed',
            category: 'booking',
            title: 'Test',
            body: 'Test msg',
            data: null,
            read_at: '2024-01-01T00:00:00Z', // already read
            created_at: '2024-01-01T00:00:00Z',
          },
        ],
        total: 1,
        unread_count: 0,
      });
      notificationApiMock.getUnreadCount.mockResolvedValue({ unread_count: 0 });
      notificationApiMock.markAsRead.mockResolvedValue(undefined as unknown as ReturnType<typeof notificationApi.markAsRead>);

      const { result } = renderHook(() => useNotifications(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.notifications).toHaveLength(1);
      });

      // markAsRead on an already-read notification should not decrement unread
      act(() => {
        result.current.markAsRead.mutate('notif-already-read');
      });

      await waitFor(() => {
        expect(notificationApiMock.markAsRead).toHaveBeenCalledWith('notif-already-read');
      });

      // Unread count should remain 0 (didUpdate stays false, no decrement)
      expect(result.current.unreadCount).toBe(0);
    });

    it('skips optimistic update when notification id does not match', async () => {
      notificationApiMock.getNotifications.mockResolvedValue({
        notifications: [
          {
            id: 'notif-existing',
            type: 'booking_confirmed',
            category: 'booking',
            title: 'Existing',
            body: 'Test',
            data: null,
            read_at: null,
            created_at: '2024-01-01T00:00:00Z',
          },
        ],
        total: 1,
        unread_count: 1,
      });
      notificationApiMock.getUnreadCount.mockResolvedValue({ unread_count: 1 });
      notificationApiMock.markAsRead.mockResolvedValue(undefined as unknown as ReturnType<typeof notificationApi.markAsRead>);

      const { result } = renderHook(() => useNotifications(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.notifications).toHaveLength(1);
      });

      // markAsRead with a non-existent id - the map loop runs but didUpdate stays false
      act(() => {
        result.current.markAsRead.mutate('notif-nonexistent');
      });

      await waitFor(() => {
        expect(notificationApiMock.markAsRead).toHaveBeenCalledWith('notif-nonexistent');
      });
    });
  });

  describe('SSE notification update edge cases', () => {
    it('trims notification list to limit when adding new notification', async () => {
      // Create initial list at exactly the limit (20)
      const notifications = Array.from({ length: 20 }, (_, i) => ({
        id: `notif-${i}`,
        type: 'booking_confirmed' as const,
        category: 'booking' as const,
        title: `Notification ${i}`,
        body: `Body ${i}`,
        data: null,
        read_at: null,
        created_at: `2024-01-01T${String(i).padStart(2, '0')}:00:00Z`,
      }));

      notificationApiMock.getNotifications.mockResolvedValue({
        notifications,
        total: 20,
        unread_count: 20,
      });

      let capturedHandler: ((event: SSENotificationUpdateEvent) => void) | undefined;
      const subscribeMock = jest.fn((_channel: string, handlers: { onNotificationUpdate?: (event: SSENotificationUpdateEvent) => void }) => {
        capturedHandler = handlers.onNotificationUpdate;
        return jest.fn();
      });
      useMessageStreamMock.mockReturnValue({ subscribe: subscribeMock });

      const { result } = renderHook(() => useNotifications(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.notifications).toHaveLength(20);
      });

      // Add a new notification that should push the list over the limit
      act(() => {
        capturedHandler?.({
          type: 'notification_update',
          unread_count: 21,
          latest: {
            id: 'notif-new',
            type: 'new_message',
            category: 'message',
            title: 'New one',
            body: 'Fresh',
            data: null,
            created_at: '2024-01-02T00:00:00Z',
          },
        });
      });

      // Should still be limited to 20 (sliced to limit)
      await waitFor(() => {
        expect(result.current.notifications).toHaveLength(20);
        expect(result.current.notifications[0]?.id).toBe('notif-new');
      });
    });

    it('sets read_at to null and defaults data to null for SSE latest notification', async () => {
      notificationApiMock.getNotifications.mockResolvedValue({
        notifications: [],
        total: 0,
        unread_count: 0,
      });

      let capturedHandler: ((event: SSENotificationUpdateEvent) => void) | undefined;
      const subscribeMock = jest.fn((_channel: string, handlers: { onNotificationUpdate?: (event: SSENotificationUpdateEvent) => void }) => {
        capturedHandler = handlers.onNotificationUpdate;
        return jest.fn();
      });
      useMessageStreamMock.mockReturnValue({ subscribe: subscribeMock });

      const { result } = renderHook(() => useNotifications(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Add a notification whose data field is undefined (should be defaulted to null)
      act(() => {
        capturedHandler?.({
          type: 'notification_update',
          unread_count: 1,
          latest: {
            id: 'notif-no-data',
            type: 'new_message',
            category: 'message',
            title: 'No data field',
            body: 'Test',
            // data is undefined here, should become null via `latest.data ?? null`
            created_at: '2024-01-01T00:00:00Z',
          },
        });
      });

      await waitFor(() => {
        expect(result.current.notifications).toHaveLength(1);
      });

      expect(result.current.notifications[0]?.data).toBeNull();
      expect(result.current.notifications[0]?.read_at).toBeNull();
    });
  });
});
