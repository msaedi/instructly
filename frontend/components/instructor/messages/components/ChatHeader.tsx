/**
 * ChatHeader - Header for the chat area
 *
 * Displays recipient info for regular chats or compose recipient selector for new messages.
 * Phase 5: Now shows booking context (next booking, upcoming booking count).
 */

import { useRef, useState, useEffect } from 'react';
import { MoreVertical, X, Calendar } from 'lucide-react';
import type { ConversationEntry, ConversationBooking } from '../types';
import { ConversationBookingCard } from './ConversationBookingCard';
import { formatBookingInfo, getBookingStatus, getBookingStatusLabel } from '../utils';

export type ChatHeaderProps = {
  isComposeView: boolean;
  activeConversation: ConversationEntry | null;
  fallbackBookings?: ConversationBooking[] | undefined;
  composeRecipient: ConversationEntry | null;
  composeRecipientQuery: string;
  composeSuggestions: ConversationEntry[];
  counterpartLabel?: string | undefined;
  bookingHrefForId?: ((bookingId: string) => string) | undefined;
  onComposeRecipientQueryChange: (query: string) => void;
  onComposeRecipientSelect: (conversation: ConversationEntry) => void;
  onComposeRecipientClear: () => void;
};

export function ChatHeader({
  isComposeView,
  activeConversation,
  fallbackBookings = [],
  composeRecipient,
  composeRecipientQuery,
  composeSuggestions,
  counterpartLabel = 'Student',
  bookingHrefForId = (bookingId) => `/instructor/bookings/${bookingId}`,
  onComposeRecipientQueryChange,
  onComposeRecipientSelect,
  onComposeRecipientClear,
}: ChatHeaderProps) {
  const [showThreadMenu, setShowThreadMenu] = useState(false);
  const [showUpcomingBookings, setShowUpcomingBookings] = useState(false);
  const threadMenuRef = useRef<HTMLDivElement | null>(null);
  const bookingSnapshotRef = useRef('');
  const nowTimestampRef = useRef(Date.now());
  const nextBooking = activeConversation?.nextBooking;
  const upcomingCount = activeConversation?.upcomingBookingCount ?? 0;
  const upcomingBookings = activeConversation?.upcomingBookings ?? [];
  const hasUpcomingBookings = Boolean(nextBooking || upcomingBookings.length > 0);
  const primaryUpcomingBooking = nextBooking ?? upcomingBookings[0] ?? null;
  const primaryBooking = hasUpcomingBookings
    ? primaryUpcomingBooking
    : fallbackBookings[0] ?? null;
  const remainingBookings = hasUpcomingBookings
    ? upcomingBookings.filter((booking) => booking.id !== primaryUpcomingBooking?.id)
    : fallbackBookings.slice(1);
  const remainingBookingCount = hasUpcomingBookings
    ? remainingBookings.length > 0
      ? remainingBookings.length
      : primaryBooking && upcomingCount > 0
        ? Math.max(upcomingCount - 1, 0)
        : 0
    : remainingBookings.length;
  const hasExpandableBookingDetails = remainingBookings.length > 0;
  const remainingBookingsLabel = `+${remainingBookingCount} more ${remainingBookingCount === 1 ? 'booking' : 'bookings'}`;
  const bookingStatusSnapshot = [
    activeConversation?.id ?? '',
    primaryBooking ? `${primaryBooking.id}:${primaryBooking.status ?? ''}:${primaryBooking.date}:${primaryBooking.start_time}` : '',
    ...remainingBookings.map(
      (booking) => `${booking.id}:${booking.status ?? ''}:${booking.date}:${booking.start_time}`
    ),
  ].join('|');
  if (bookingSnapshotRef.current !== bookingStatusSnapshot) {
    bookingSnapshotRef.current = bookingStatusSnapshot;
    nowTimestampRef.current = Date.now();
  }
  const nowTimestamp = nowTimestampRef.current;
  const primaryBookingStatus = primaryBooking
    ? getBookingStatus(primaryBooking, nowTimestamp)
    : 'CONFIRMED';

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (threadMenuRef.current && e.target instanceof Node && !threadMenuRef.current.contains(e.target)) {
        setShowThreadMenu(false);
      }
    };
    document.addEventListener('click', onDocClick);
    return () => document.removeEventListener('click', onDocClick);
  }, []);

  if (isComposeView) {
    return (
      <div className="flex-shrink-0 p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="flex flex-col gap-3">
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
            <span className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">To:</span>
            {composeRecipient ? (
              <span className="inline-flex items-center gap-2 rounded-full bg-purple-50 border border-purple-200 px-3 py-1 text-sm text-(--color-brand-dark)">
                {composeRecipient.name}
                <button
                  type="button"
                  className="text-(--color-brand-dark) hover:text-purple-800 dark:hover:text-purple-200"
                  aria-label="Remove recipient"
                  onClick={onComposeRecipientClear}
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ) : (
              <div className="relative w-full sm:max-w-xs">
                <input
                  type="text"
                  value={composeRecipientQuery}
                  onChange={(event) => onComposeRecipientQueryChange(event.target.value)}
                  placeholder="Search contacts..."
                  className="w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-(--color-brand-dark)"
                />
                {composeRecipientQuery && (
                  <ul className="absolute z-40 mt-1 w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg">
                    {composeSuggestions.length > 0 ? (
                      composeSuggestions.map((suggestion) => (
                        <li key={suggestion.id}>
                          <button
                            type="button"
                            onClick={() => onComposeRecipientSelect(suggestion)}
                            className="w-full px-3 py-2 text-left text-sm hover:bg-purple-50 dark:hover:bg-purple-900/30"
                          >
                            <span className="font-medium text-gray-900 dark:text-gray-100">{suggestion.name}</span>
                            <span className="block text-xs text-gray-500 dark:text-gray-400">
                              {suggestion.type === 'platform' ? 'Platform' : counterpartLabel}
                            </span>
                          </button>
                        </li>
                      ))
                    ) : (
                      <li className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400">No contacts found</li>
                    )}
                  </ul>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-shrink-0 p-4 border-b border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
              activeConversation?.type === 'platform'
                ? 'bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-200'
                : 'bg-purple-100 text-purple-600'
            }`}
          >
            {activeConversation?.avatar}
          </div>
          <div>
            <h3 className="font-medium text-gray-900 dark:text-gray-100">{activeConversation?.name}</h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {activeConversation?.type === 'platform' ? 'Platform' : counterpartLabel}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Booking context badge */}
          {primaryBooking && (
            <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 bg-purple-50 border border-purple-200 rounded-full text-xs text-purple-700">
              <Calendar className="w-3 h-3" />
              <span className="truncate max-w-[220px]">
                {formatBookingInfo(primaryBooking)}
              </span>
              {remainingBookingCount > 0 && (
                <span className="text-purple-500">+{remainingBookingCount} more</span>
              )}
            </div>
          )}
          {activeConversation && (
            <div className="relative" ref={threadMenuRef}>
              <button
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                onClick={() => setShowThreadMenu((v) => !v)}
                aria-label="More options"
                aria-expanded={showThreadMenu}
                aria-haspopup="menu"
              >
                <MoreVertical className="w-4 h-4 text-gray-500 dark:text-gray-400" />
              </button>
              {showThreadMenu && (
                <div
                  role="menu"
                  className="absolute right-0 z-40 mt-2 max-h-[400px] w-56 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-800"
                >
                  <div className="p-3">
                    {primaryBooking ? (
                      <div className="space-y-3">
                        <ConversationBookingCard
                          booking={primaryBooking}
                          href={bookingHrefForId(primaryBooking.id)}
                          status={primaryBookingStatus}
                          statusLabel={getBookingStatusLabel(primaryBookingStatus)}
                          variant={primaryBookingStatus === 'COMPLETED' ? 'completed' : 'primary'}
                        />

                        {/* Expand/collapse for more bookings */}
                        {remainingBookingCount > 0 && !showUpcomingBookings && (
                          hasExpandableBookingDetails ? (
                            <button
                              type="button"
                              onClick={() => {
                                setShowUpcomingBookings((v) => !v);
                              }}
                              className="text-xs text-(--color-brand-dark) flex items-center justify-between gap-1 hover:text-purple-800 dark:hover:text-purple-200 w-full text-left pt-1"
                              data-testid="chat-header-booking-expander"
                            >
                              <span>{remainingBookingsLabel}</span>
                              <span aria-hidden="true" className={`transition-transform ${showUpcomingBookings ? 'rotate-180' : ''}`}>^</span>
                            </button>
                          ) : (
                            <span
                              className="block w-full pt-1 text-xs text-(--color-brand-dark)"
                              data-testid="chat-header-booking-summary-count"
                            >
                              {remainingBookingsLabel}
                            </span>
                          )
                        )}

                        {/* Expanded upcoming bookings */}
                        {showUpcomingBookings && hasExpandableBookingDetails && (
                          <div className="space-y-2 pt-2">
                            {remainingBookings.map((booking) => {
                              const status = getBookingStatus(booking, nowTimestamp);
                              return (
                                <ConversationBookingCard
                                  key={booking.id}
                                  booking={booking}
                                  href={bookingHrefForId(booking.id)}
                                  status={status}
                                  statusLabel={getBookingStatusLabel(status)}
                                  variant={status === 'COMPLETED' ? 'completed' : 'default'}
                                />
                              );
                            })}
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-gray-500 dark:text-gray-400">No upcoming bookings</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
