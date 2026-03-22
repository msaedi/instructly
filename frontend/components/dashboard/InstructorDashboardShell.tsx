'use client';

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
  type ReactNode,
  type RefObject,
} from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { MessageSquare, type LucideIcon } from 'lucide-react';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { NotificationBell } from '@/components/notifications/NotificationBell';
import {
  INSTRUCTOR_DASHBOARD_NAV_ITEMS,
  type DashboardNavKey,
} from '@/lib/instructorDashboardNav';
import { fetchWithSessionRefresh } from '@/lib/auth/sessionRefresh';
import { withApiBase } from '@/lib/apiBase';
import { formatDisplayName } from '@/lib/format/displayName';
import type { ConversationListResponse } from '@/types/conversation';
import { cn } from '@/lib/utils';

type InstructorDashboardShellProps = {
  activeNavKey: DashboardNavKey;
  children: ReactNode;
  contentClassName?: string;
};

function DashboardHeaderPopover({
  icon: Icon,
  label,
  isOpen,
  onToggle,
  children,
  containerRef,
  badgeCount,
}: {
  icon: LucideIcon;
  label: string;
  isOpen: boolean;
  onToggle: () => void;
  children: ReactNode;
  containerRef: RefObject<HTMLDivElement> | MutableRefObject<HTMLDivElement | null>;
  badgeCount: number;
}) {
  const hasBadge = badgeCount > 0;
  const badgeLabel = badgeCount > 9 ? '9+' : String(badgeCount);
  const computedLabel = hasBadge ? `${label} (${badgeLabel} unread)` : label;

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isOpen}
        aria-haspopup="menu"
        aria-label={computedLabel}
        className="group relative inline-flex h-10 w-10 items-center justify-center rounded-full text-[#7E22CE] transition-colors duration-150 focus:outline-none"
        title={label}
      >
        <Icon
          className="h-6 w-6 transition-colors group-hover:fill-current"
          style={{ fill: isOpen ? 'currentColor' : undefined }}
        />
        {hasBadge ? (
          <span className="absolute -right-0.5 -top-0.5 inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-[#7E22CE] px-1 text-[10px] font-semibold leading-none text-white">
            {badgeLabel}
          </span>
        ) : null}
      </button>
      {isOpen ? (
        <div role="menu" className="insta-header-dropdown absolute right-0 z-50 mt-2 w-80 rounded-lg">
          {children}
        </div>
      ) : null}
    </div>
  );
}

function getNavHref(item: (typeof INSTRUCTOR_DASHBOARD_NAV_ITEMS)[number]): string {
  if (item.key === 'dashboard') {
    return '/instructor/dashboard';
  }

  return `/instructor/dashboard?panel=${item.key}`;
}

export function InstructorDashboardShell({
  activeNavKey,
  children,
  contentClassName,
}: InstructorDashboardShellProps) {
  const router = useRouter();
  const msgRef = useRef<HTMLDivElement | null>(null);
  const notifRef = useRef<HTMLDivElement | null>(null);
  const [showMessages, setShowMessages] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [conversationList, setConversationList] = useState<ConversationListResponse['conversations']>(
    []
  );
  const [isMessagesLoading, setIsMessagesLoading] = useState(false);
  const [messagesError, setMessagesError] = useState<string | null>(null);

  const loadConversations = useCallback(async () => {
    setIsMessagesLoading(true);
    try {
      const response = await fetchWithSessionRefresh(
        withApiBase('/api/v1/conversations?state=active&limit=50'),
        {
          method: 'GET',
        }
      );
      if (!response.ok) {
        throw new Error('Failed to load messages');
      }
      const data = (await response.json()) as ConversationListResponse;
      setConversationList(data.conversations ?? []);
      setMessagesError(null);
    } catch (error) {
      setMessagesError(error instanceof Error ? error.message : 'Failed to load messages');
    } finally {
      setIsMessagesLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    if (showMessages) {
      void loadConversations();
    }
  }, [loadConversations, showMessages]);

  useEffect(() => {
    const onDocClick = (event: MouseEvent) => {
      const target = event.target as Node;
      const outsideNotif = !notifRef.current?.contains(target);
      const outsideMsg = !msgRef.current?.contains(target);

      if (outsideNotif && outsideMsg) {
        setShowNotifications(false);
        setShowMessages(false);
      }
    };

    document.addEventListener('click', onDocClick);
    return () => document.removeEventListener('click', onDocClick);
  }, []);

  const unreadConversations = useMemo(
    () => conversationList.filter(({ unread_count = 0 }) => unread_count > 0),
    [conversationList]
  );
  const unreadConversationsCount = unreadConversations.length;

  return (
    <div className="min-h-screen insta-dashboard-page" data-testid="instructor-dashboard-shell">
      <header className="insta-dashboard-header px-4 py-4 sm:px-6">
        <div className="flex max-w-full items-center justify-between">
          <Link href="/instructor/dashboard" className="inline-block">
            <span className="cursor-pointer pl-0 text-3xl font-bold text-[#7E22CE] transition-colors hover:text-purple-900 dark:hover:text-purple-300 sm:pl-4">
              iNSTAiNSTRU
            </span>
          </Link>
          <div className="flex items-center gap-2 pr-0 sm:pr-4">
            <DashboardHeaderPopover
              icon={MessageSquare}
              label="Messages"
              isOpen={showMessages}
              onToggle={() => {
                setShowMessages((prev) => !prev);
                setShowNotifications(false);
              }}
              containerRef={msgRef}
              badgeCount={unreadConversationsCount}
            >
              <ul className="max-h-80 space-y-2 overflow-auto p-2">
                {isMessagesLoading ? (
                  <li className="px-2 py-2 text-sm text-gray-600 dark:text-gray-400">
                    Loading messages...
                  </li>
                ) : messagesError ? (
                  <li className="px-2 py-2 text-sm text-red-600">{messagesError}</li>
                ) : unreadConversations.length === 0 ? (
                  <>
                    <li className="px-2 py-2 text-sm text-gray-600 dark:text-gray-400">
                      No unread messages.
                    </li>
                    <li>
                      <button
                        type="button"
                        className="w-full rounded px-2 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-700"
                        onClick={() => {
                          setShowMessages(false);
                          router.push('/instructor/dashboard?panel=messages');
                        }}
                      >
                        Open inbox
                      </button>
                    </li>
                  </>
                ) : (
                  unreadConversations.map((conversation) => {
                    const otherName = formatDisplayName(
                      conversation.other_user.first_name,
                      conversation.other_user.last_initial,
                      'Student'
                    );
                    const preview = conversation.last_message?.content || 'New message';

                    return (
                      <li key={conversation.id}>
                        <button
                          type="button"
                          onClick={() => {
                            setShowMessages(false);
                            router.push(
                              `/instructor/dashboard?panel=messages&conversation=${conversation.id}`
                            );
                          }}
                          className="w-full rounded-lg px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-700"
                        >
                          <p className="truncate text-sm font-medium text-gray-900 dark:text-gray-100">
                            {otherName}
                          </p>
                          <p className="truncate text-xs text-gray-500 dark:text-gray-400">
                            {preview}
                          </p>
                        </button>
                      </li>
                    );
                  })
                )}
              </ul>
            </DashboardHeaderPopover>
            <NotificationBell
              isOpen={showNotifications}
              onOpenChange={(open) => {
                setShowNotifications(open);
                setShowMessages(false);
              }}
              containerRef={notifRef}
            />
            <UserProfileDropdown hideDashboardItem />
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="grid grid-cols-12 gap-6">
          <aside
            className="col-span-12 hidden md:col-span-3 md:block"
            data-testid="instructor-dashboard-sidebar"
          >
            <div className="insta-surface-card p-4">
              <nav aria-label="Instructor dashboard navigation">
                <ul className="space-y-1">
                  {INSTRUCTOR_DASHBOARD_NAV_ITEMS.map((item) => {
                    const isActive = item.key === activeNavKey;

                    return (
                      <li key={item.key}>
                        <Link
                          href={getNavHref(item)}
                          aria-current={isActive ? 'page' : undefined}
                          className={cn(
                            'block rounded-md px-3 py-2 text-left transition-transform transition-colors duration-150',
                            isActive
                              ? 'border border-purple-200 bg-purple-50 font-semibold text-[#7E22CE] dark:border-purple-700 dark:bg-purple-900/30 dark:text-purple-300'
                              : 'text-gray-800 hover:scale-[1.02] hover:bg-purple-50 hover:text-purple-900 dark:text-gray-200 dark:hover:bg-purple-900/20 dark:hover:text-purple-300'
                          )}
                        >
                          {item.label}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </nav>
            </div>
          </aside>

          <section className={cn('col-span-12 md:col-span-9', contentClassName)}>{children}</section>
        </div>
      </div>
    </div>
  );
}
