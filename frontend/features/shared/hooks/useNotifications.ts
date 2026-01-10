'use client';

import { useCallback, useEffect, useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/features/shared/hooks/useAuth';
import {
  notificationApi,
  type NotificationItem,
  type NotificationQueryParams,
} from '@/features/shared/api/notifications';
import { useMessageStream } from '@/providers/UserMessageStreamProvider';
import type { SSENotificationUpdateEvent } from '@/types/messaging';

type NotificationListData = Awaited<ReturnType<typeof notificationApi.getNotifications>>;

export function useNotifications(params?: NotificationQueryParams) {
  const { isAuthenticated } = useAuth();
  const { subscribe } = useMessageStream();
  const queryClient = useQueryClient();

  const queryParams = useMemo(
    () => ({
      limit: params?.limit ?? 20,
      offset: params?.offset ?? 0,
      unreadOnly: params?.unreadOnly ?? false,
    }),
    [params?.limit, params?.offset, params?.unreadOnly]
  );

  const listQueryKey = useMemo(() => ['notifications', queryParams], [queryParams]);
  const unreadQueryKey = useMemo(() => ['notifications', 'unread-count'], []);

  const notificationsQuery = useQuery({
    queryKey: listQueryKey,
    queryFn: () => notificationApi.getNotifications(queryParams),
    enabled: isAuthenticated,
    staleTime: 30_000,
  });

  const unreadQuery = useQuery({
    queryKey: unreadQueryKey,
    queryFn: () => notificationApi.getUnreadCount(),
    enabled: isAuthenticated,
    refetchInterval: 60_000,
  });

  const handleNotificationUpdate = useCallback(
    (event: SSENotificationUpdateEvent) => {
      queryClient.setQueryData(unreadQueryKey, { unread_count: event.unread_count });

      const latest = event.latest;
      if (latest) {
        queryClient.setQueryData<NotificationListData | undefined>(listQueryKey, (prev) => {
          if (!prev) return prev;
          const exists = prev.notifications.some((item) => item.id === latest.id);
          if (exists) {
            return {
              ...prev,
              unread_count: event.unread_count,
            };
          }

          const nextItem: NotificationItem = {
            ...latest,
            data: latest.data ?? null,
            read_at: null,
          };
          const limit = queryParams.limit ?? 20;
          const nextNotifications = [nextItem, ...prev.notifications].slice(0, limit);

          return {
            ...prev,
            notifications: nextNotifications,
            total: prev.total + 1,
            unread_count: event.unread_count,
          };
        });
      } else {
        void queryClient.invalidateQueries({ queryKey: listQueryKey });
      }
    },
    [listQueryKey, queryClient, queryParams.limit, unreadQueryKey]
  );

  useEffect(() => {
    if (!isAuthenticated) {
      return undefined;
    }

    const unsubscribe = subscribe('__global__', {
      onNotificationUpdate: handleNotificationUpdate,
    });

    return unsubscribe;
  }, [handleNotificationUpdate, isAuthenticated, subscribe]);

  const markAsRead = useMutation({
    mutationFn: (notificationId: string) => notificationApi.markAsRead(notificationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: listQueryKey });
      void queryClient.invalidateQueries({ queryKey: unreadQueryKey });
    },
  });

  const markAllAsRead = useMutation({
    mutationFn: () => notificationApi.markAllAsRead(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: listQueryKey });
      void queryClient.invalidateQueries({ queryKey: unreadQueryKey });
    },
  });

  const deleteNotification = useMutation({
    mutationFn: (notificationId: string) => notificationApi.deleteNotification(notificationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: listQueryKey });
      void queryClient.invalidateQueries({ queryKey: unreadQueryKey });
    },
  });

  const clearAll = useMutation({
    mutationFn: () => notificationApi.deleteAll(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: listQueryKey });
      void queryClient.invalidateQueries({ queryKey: unreadQueryKey });
    },
  });

  return {
    notifications: notificationsQuery.data?.notifications ?? [],
    unreadCount: unreadQuery.data?.unread_count ?? 0,
    total: notificationsQuery.data?.total ?? 0,
    isLoading: notificationsQuery.isLoading,
    error: notificationsQuery.error,
    markAsRead,
    markAllAsRead,
    deleteNotification,
    clearAll,
    refetch: notificationsQuery.refetch,
  };
}
