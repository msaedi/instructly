'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatRelativeTimestamp } from '@/components/messaging/formatters';
import type { NotificationItem as NotificationItemType } from '@/features/shared/api/notifications';
import { NotificationIcon } from './NotificationIcon';

interface NotificationItemProps {
  notification: NotificationItemType;
  onRead: () => void;
  onDelete: () => void;
}

export function NotificationItem({ notification, onRead, onDelete }: NotificationItemProps) {
  const router = useRouter();
  const [isHovered, setIsHovered] = useState(false);
  const isUnread = !notification.read_at;
  const timestamp = formatRelativeTimestamp(notification.created_at);
  const dataUrl = notification.data?.['url'];
  const url = typeof dataUrl === 'string' ? dataUrl : null;

  const handleClick = () => {
    if (isUnread) {
      onRead();
    }
    if (url) {
      router.push(url);
    }
  };

  return (
    <div
      role="menuitem"
      tabIndex={0}
      data-notification-item="true"
      aria-label={`${notification.title}${isUnread ? ' (unread)' : ''}`}
      onClick={handleClick}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          handleClick();
        }
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={cn(
        'flex items-start gap-3 px-3 py-3 text-left transition-colors hover:bg-gray-50 cursor-pointer',
        isUnread && 'bg-blue-50/40'
      )}
    >
      <div className="mt-0.5 shrink-0">
        <NotificationIcon category={notification.category} />
      </div>
      <div className="min-w-0 flex-1">
        <p className={cn('text-sm text-gray-900', isUnread && 'font-medium')}>
          {notification.title}
        </p>
        {notification.body && (
          <p className="text-sm text-gray-500 truncate">{notification.body}</p>
        )}
        <p className="mt-1 text-xs text-gray-400">{timestamp}</p>
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
          className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
          aria-label="Delete notification"
        >
          <X className="h-4 w-4" />
        </button>
      )}
      {isUnread && <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-blue-500" />}
    </div>
  );
}
