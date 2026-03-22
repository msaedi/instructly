'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatRelativeTimestamp } from '@/components/messaging/formatters';
import type { NotificationItem as NotificationItemType } from '@/features/shared/api/notifications';
import { NotificationIcon } from './NotificationIcon';
import { resolveNotificationDestination } from './resolveNotificationDestination';

interface NotificationItemProps {
  notification: NotificationItemType;
  onRead: () => Promise<void> | void;
  onDelete: () => void;
}

export function NotificationItem({ notification, onRead, onDelete }: NotificationItemProps) {
  const router = useRouter();
  const [isHovered, setIsHovered] = useState(false);
  const isUnread = !notification.read_at;
  const timestamp = formatRelativeTimestamp(notification.created_at);
  const destination = resolveNotificationDestination(notification);

  const handleClick = async () => {
    const markReadPromise = isUnread
      ? Promise.resolve(onRead()).catch(() => undefined)
      : Promise.resolve();

    if (destination) {
      router.push(destination);
    }

    await markReadPromise;
  };

  return (
    <div
      role="menuitem"
      tabIndex={0}
      data-notification-item="true"
      aria-label={`${notification.title}${isUnread ? ' (unread)' : ''}`}
      onClick={() => {
        void handleClick();
      }}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          void handleClick();
        }
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={cn(
        'flex items-start gap-3 px-3 py-3 text-left transition-colors hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer',
        isUnread && 'bg-blue-50/40'
      )}
    >
      <div className="mt-0.5 shrink-0">
        <NotificationIcon category={notification.category} />
      </div>
      <div className="min-w-0 flex-1">
        <p className={cn('text-sm text-gray-900 dark:text-gray-100', isUnread && 'font-medium')}>
          {notification.title}
        </p>
        {notification.body && (
          <p className="text-sm text-gray-500 dark:text-gray-400 truncate">{notification.body}</p>
        )}
        <p className="mt-1 text-xs text-gray-400 dark:text-gray-300">{timestamp}</p>
      </div>
      {isHovered && (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onDelete();
          }}
          onKeyDown={(event) => {
            event.stopPropagation();
          }}
          className="shrink-0 rounded p-1 text-gray-500 dark:text-gray-400 transition-colors hover:bg-red-600/10 hover:text-red-600 dark:hover:text-red-500"
          aria-label="Delete notification"
        >
          <X className="h-4 w-4" />
        </button>
      )}
      {isUnread && <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-blue-500" />}
    </div>
  );
}
