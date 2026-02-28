'use client';

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type MutableRefObject,
  type RefObject,
} from 'react';
import { Bell } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useNotifications } from '@/features/shared/hooks/useNotifications';
import { NotificationItem } from './NotificationItem';

type NotificationBellProps = {
  isOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  containerRef?: RefObject<HTMLDivElement> | MutableRefObject<HTMLDivElement | null>;
  className?: string;
};

export function NotificationBell({
  isOpen,
  onOpenChange,
  containerRef,
  className,
}: NotificationBellProps) {
  const {
    notifications,
    unreadCount,
    isLoading,
    error,
    markAllAsRead,
    markAsRead,
    deleteNotification,
    clearAll,
  } = useNotifications();
  const [internalOpen, setInternalOpen] = useState(false);
  const isControlled = typeof isOpen === 'boolean' && typeof onOpenChange === 'function';
  const open = isControlled ? (isOpen as boolean) : internalOpen;
  const setOpen = useCallback(
    (next: boolean) => {
      if (isControlled) {
        onOpenChange?.(next);
      } else {
        setInternalOpen(next);
      }
    },
    [isControlled, onOpenChange]
  );

  const localRef = useRef<HTMLDivElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const rootRef = (containerRef ?? localRef) as RefObject<HTMLDivElement>;

  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (rootRef.current && !rootRef.current.contains(target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open, rootRef, setOpen]);

  const badgeLabel = unreadCount > 9 ? '9+' : String(unreadCount);
  const errorMessage = error instanceof Error ? error.message : null;

  const handleMenuKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setOpen(false);
        buttonRef.current?.focus();
        return;
      }

      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') {
        return;
      }

      const items = menuRef.current?.querySelectorAll<HTMLElement>(
        '[data-notification-item="true"]'
      );
      if (!items || items.length === 0) {
        return;
      }

      event.preventDefault();
      const activeElement = document.activeElement as HTMLElement | null;
      const currentIndex = activeElement ? Array.from(items).indexOf(activeElement) : -1;
      const nextIndex =
        event.key === 'ArrowDown'
          ? (currentIndex + 1 + items.length) % items.length
          : (currentIndex - 1 + items.length) % items.length;

      items[nextIndex]?.focus();
    },
    [setOpen]
  );

  const listContent = useMemo(() => {
    if (isLoading) {
      return <p className="px-3 py-4 text-sm text-gray-500">Loading notifications...</p>;
    }
    if (errorMessage) {
      return <p className="px-3 py-4 text-sm text-red-600">{errorMessage}</p>;
    }
    if (notifications.length === 0) {
      return <p className="px-3 py-4 text-sm text-gray-500">No notifications yet.</p>;
    }
    return notifications.map((notification) => (
      <NotificationItem
        key={notification.id}
        notification={notification}
        onRead={() => markAsRead.mutate(notification.id)}
        onDelete={() => deleteNotification.mutate(notification.id)}
      />
    ));
  }, [deleteNotification, errorMessage, isLoading, markAsRead, notifications]);

  return (
    <div ref={rootRef} className={cn('relative', className)}>
      <button
        type="button"
        ref={buttonRef}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={unreadCount > 0 ? `Notifications (${badgeLabel} unread)` : 'Notifications'}
        title="Notifications"
        className="group relative inline-flex items-center justify-center h-10 w-10 rounded-full text-[#7E22CE] transition-colors duration-150"
      >
        <Bell
          className="h-6 w-6 transition-colors group-hover:fill-current"
          style={{ fill: open ? 'currentColor' : undefined }}
        />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-[#7E22CE] px-1 text-[10px] font-semibold leading-none text-white">
            {badgeLabel}
          </span>
        )}
      </button>

      {open && (
        <div
          ref={menuRef}
          role="menu"
          aria-live="polite"
          aria-label="Notifications"
          onKeyDown={handleMenuKeyDown}
          className="insta-header-dropdown absolute right-0 mt-2 w-80 rounded-lg z-50"
        >
          <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2">
            <h3 className="text-sm font-semibold text-gray-900">Notifications</h3>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={() => markAllAsRead.mutate()}
                disabled={markAllAsRead.isPending}
                className="text-xs text-[#7E22CE] hover:text-[#6B21A8] disabled:opacity-60"
              >
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">{listContent}</div>
          {notifications.length > 0 && (
            <div className="border-t border-gray-100 p-2">
              <button
                type="button"
                onClick={() => clearAll.mutate()}
                disabled={clearAll.isPending}
                className="w-full rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:text-destructive disabled:opacity-60"
              >
                Clear all
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
