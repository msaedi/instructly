/**
 * ChatHeader - Header for the chat area
 *
 * Displays recipient info for regular chats or compose recipient selector for new messages.
 * Phase 5: Now shows booking context (next booking, upcoming booking count).
 */

import { useRef, useState, useEffect } from 'react';
import Link from 'next/link';
import { MoreVertical, X, Calendar } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import type { ConversationEntry, ConversationBooking } from '../types';
import { shortenBookingId } from '@/lib/bookingId';
import { getBookingStatusBadgeClasses } from '@/lib/bookingStatus';

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

/**
 * Format a date string (YYYY-MM-DD) to "Dec 8" format
 */
function formatDateShort(dateStr: string): string {
  try {
    const date = parseISO(dateStr);
    return format(date, 'MMM d');
  } catch {
    return dateStr;
  }
}

/**
 * Format a 24-hour time string (HH:MM) to 12-hour format (e.g., "9am", "5:30pm")
 */
function formatTime12h(timeStr: string): string {
  const [hoursStr, minutesStr] = timeStr.split(':');
  const hours = parseInt(hoursStr ?? '0', 10);
  const minutes = parseInt(minutesStr ?? '0', 10);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes) || !minutesStr) {
    return timeStr;
  }

  const period = hours < 12 ? 'am' : 'pm';
  let hour12 = hours % 12;
  if (hour12 === 0) hour12 = 12;

  if (minutes === 0) {
    return `${hour12}${period}`;
  }
  return `${hour12}:${minutesStr}${period}`;
}

/**
 * Format booking info for display
 */
function formatBookingInfo(booking: ConversationBooking): string {
  const formattedDate = formatDateShort(booking.date);
  const formattedTime = formatTime12h(booking.start_time);
  return formattedDate === booking.date && formattedTime === booking.start_time
    ? `${booking.service_name} - ${booking.date}`
    : `${booking.service_name} on ${formattedDate}, ${formattedTime}`;
}

function getBookingTimestamp(booking: ConversationBooking): number {
  const parsed = Date.parse(`${booking.date}T${booking.start_time}`);
  if (Number.isFinite(parsed)) {
    return parsed;
  }

  const fallback = Date.parse(booking.date);
  return Number.isFinite(fallback) ? fallback : Number.POSITIVE_INFINITY;
}

function getExplicitBookingStatus(booking: ConversationBooking): string | null {
  return typeof booking.status === 'string' && booking.status.trim()
    ? booking.status.trim().toUpperCase()
    : null;
}

function getBookingStatus(booking: ConversationBooking): string {
  const explicitStatus = getExplicitBookingStatus(booking);
  if (explicitStatus) {
    return explicitStatus;
  }

  return getBookingTimestamp(booking) < Date.now() ? 'COMPLETED' : 'CONFIRMED';
}

function getBookingStatusLabel(status: string): string {
  switch (status) {
    case 'CONFIRMED':
      return 'Confirmed';
    case 'COMPLETED':
      return 'Completed';
    case 'CANCELLED':
      return 'Cancelled';
    case 'NO_SHOW':
      return 'No Show';
    case 'IN_PROGRESS':
      return 'In Progress';
    default:
      return status
        .toLowerCase()
        .split('_')
        .filter(Boolean)
        .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
        .join(' ');
  }
}

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
              <span className="inline-flex items-center gap-2 rounded-full bg-purple-50 border border-purple-200 px-3 py-1 text-sm text-[#7E22CE]">
                {composeRecipient.name}
                <button
                  type="button"
                  className="text-[#7E22CE] hover:text-purple-800 dark:hover:text-purple-200"
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
                  className="w-full rounded-lg border border-gray-300 dark:border-gray-700 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-[#7E22CE]"
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

  // Get booking context from conversation
  const nextBooking = activeConversation?.nextBooking;
  const upcomingCount = activeConversation?.upcomingBookingCount ?? 0;
  const upcomingBookings = activeConversation?.upcomingBookings ?? [];
  const hasUpcomingBookings = Boolean(nextBooking || upcomingBookings.length > 0);
  const primaryBooking = hasUpcomingBookings
    ? nextBooking ?? upcomingBookings[0] ?? null
    : fallbackBookings[0] ?? null;
  const remainingBookings = hasUpcomingBookings
    ? (primaryBooking
        ? upcomingBookings.filter((booking) => booking.id !== primaryBooking.id)
        : upcomingBookings)
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

  const renderBookingCard = (booking: ConversationBooking, isPrimary: boolean) => {
    const status = getBookingStatus(booking);
    const statusLabel = getBookingStatusLabel(status);
    const statusClassName = getBookingStatusBadgeClasses(status);
    const isCompletedBooking = status === 'COMPLETED';
    const cardClassName = isPrimary && !isCompletedBooking
      ? 'border-[#E5D7FE] bg-[#F3E8FF] hover:bg-[#EEE4FE] dark:border-[#5B21B6] dark:bg-[#2A114A] dark:hover:bg-[#34145B]'
      : isCompletedBooking
        ? 'border-gray-200 bg-gray-100 hover:bg-gray-200 dark:border-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700'
        : 'border-gray-200 bg-white hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:hover:bg-gray-800';

    return (
      <Link
        key={booking.id}
        href={bookingHrefForId(booking.id)}
        data-testid={`chat-header-booking-card-${booking.id}`}
        className={`block rounded-xl border p-3 transition-colors ${cardClassName}`}
      >
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{booking.service_name}</p>
          <span
            className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${statusClassName}`}
          >
            {statusLabel}
          </span>
        </div>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {formatDateShort(booking.date)}, {formatTime12h(booking.start_time)}
        </p>
        <p className="mt-2 text-[10px] font-mono uppercase tracking-[0.18em] text-gray-400 dark:text-gray-300">
          #{shortenBookingId(booking.id)}
        </p>
      </Link>
    );
  };

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
                {formatBookingInfo(primaryBooking)} · #{shortenBookingId(primaryBooking.id)}
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
                  className="absolute right-0 mt-2 w-56 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-40"
                >
                  <div className="p-3">
                    {primaryBooking ? (
                      <div className="space-y-3">
                        {renderBookingCard(primaryBooking, true)}

                        {/* Expand/collapse for more bookings */}
                        {remainingBookingCount > 0 && (
                          hasExpandableBookingDetails ? (
                            <button
                              type="button"
                              onClick={() => {
                                setShowUpcomingBookings((v) => !v);
                              }}
                              className="text-xs text-[#7E22CE] flex items-center justify-between gap-1 hover:text-purple-800 dark:hover:text-purple-200 w-full text-left pt-1"
                              data-testid="chat-header-booking-expander"
                            >
                              <span>{remainingBookingsLabel}</span>
                              <span aria-hidden="true" className={`transition-transform ${showUpcomingBookings ? 'rotate-180' : ''}`}>^</span>
                            </button>
                          ) : (
                            <span
                              className="block w-full pt-1 text-xs text-[#7E22CE]"
                              data-testid="chat-header-booking-summary-count"
                            >
                              {remainingBookingsLabel}
                            </span>
                          )
                        )}

                        {/* Expanded upcoming bookings */}
                        {showUpcomingBookings && hasExpandableBookingDetails && (
                          <div className="space-y-2 pt-2">
                            {remainingBookings.map((booking) => renderBookingCard(booking, false))}
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
