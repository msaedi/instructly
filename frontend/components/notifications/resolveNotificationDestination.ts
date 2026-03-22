import type { NotificationItem as NotificationItemType } from '@/features/shared/api/notifications';

const BOOKING_NOTIFICATION_TYPES = new Set([
  'booking_confirmed',
  'booking_cancelled',
  'booking_reminder_24h',
  'booking_reminder_1h',
]);

function getNotificationDataString(
  notification: NotificationItemType,
  key: string
): string | null {
  const value = notification.data?.[key];
  return typeof value === 'string' && value.trim().length > 0 ? value : null;
}

export function resolveNotificationDestination(
  notification: NotificationItemType
): string | null {
  const bookingId = getNotificationDataString(notification, 'booking_id');
  if (bookingId && BOOKING_NOTIFICATION_TYPES.has(notification.type)) {
    return `/instructor/bookings/${bookingId}`;
  }

  const explicitUrl = getNotificationDataString(notification, 'url');
  if (explicitUrl) {
    return explicitUrl;
  }

  const conversationId = getNotificationDataString(notification, 'conversation_id');
  if (notification.type === 'booking_new_message') {
    const params = new URLSearchParams({ panel: 'messages' });

    if (conversationId) {
      params.set('conversation', conversationId);
    }

    return `/instructor/dashboard?${params.toString()}`;
  }

  if (BOOKING_NOTIFICATION_TYPES.has(notification.type)) {
    return '/instructor/dashboard?panel=bookings';
  }

  const reviewId = getNotificationDataString(notification, 'review_id');
  if (notification.type === 'new_review' || notification.category === 'reviews' || reviewId) {
    return '/instructor/dashboard?panel=reviews';
  }

  return null;
}
