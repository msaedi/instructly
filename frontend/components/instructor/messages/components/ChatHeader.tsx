/**
 * ChatHeader - Header for the chat area
 *
 * Displays recipient info for regular chats or compose recipient selector for new messages.
 * Phase 5: Now shows booking context (next booking, upcoming booking count).
 */

import { useRef, useState, useEffect } from 'react';
import { MoreVertical, X, Calendar } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import type { ConversationEntry, ConversationBooking } from '../types';

export type ChatHeaderProps = {
  isComposeView: boolean;
  activeConversation: ConversationEntry | null;
  composeRecipient: ConversationEntry | null;
  composeRecipientQuery: string;
  composeSuggestions: ConversationEntry[];
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
  try {
    const [hoursStr, minutesStr] = timeStr.split(':');
    const hours = parseInt(hoursStr ?? '0', 10);
    const minutes = parseInt(minutesStr ?? '0', 10);

    const period = hours < 12 ? 'am' : 'pm';
    let hour12 = hours % 12;
    if (hour12 === 0) hour12 = 12;

    if (minutes === 0) {
      return `${hour12}${period}`;
    }
    return `${hour12}:${minutesStr}${period}`;
  } catch {
    return timeStr;
  }
}

/**
 * Format booking info for display
 */
function formatBookingInfo(booking: ConversationBooking): string {
  try {
    const formattedDate = formatDateShort(booking.date);
    const formattedTime = formatTime12h(booking.start_time);
    return `${booking.service_name} on ${formattedDate}, ${formattedTime}`;
  } catch {
    return `${booking.service_name} - ${booking.date}`;
  }
}

export function ChatHeader({
  isComposeView,
  activeConversation,
  composeRecipient,
  composeRecipientQuery,
  composeSuggestions,
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
      <div className="flex-shrink-0 p-4 border-b border-gray-200">
        <div className="flex flex-col gap-3">
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
            <span className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">To:</span>
            {composeRecipient ? (
              <span className="inline-flex items-center gap-2 rounded-full bg-purple-50 border border-purple-200 px-3 py-1 text-sm text-[#7E22CE]">
                {composeRecipient.name}
                <button
                  type="button"
                  className="text-[#7E22CE] hover:text-purple-800"
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
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-[#7E22CE]"
                />
                {composeRecipientQuery && (
                  <ul className="absolute z-40 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg">
                    {composeSuggestions.length > 0 ? (
                      composeSuggestions.map((suggestion) => (
                        <li key={suggestion.id}>
                          <button
                            type="button"
                            onClick={() => onComposeRecipientSelect(suggestion)}
                            className="w-full px-3 py-2 text-left text-sm hover:bg-purple-50"
                          >
                            <span className="font-medium text-gray-900 dark:text-gray-100">{suggestion.name}</span>
                            <span className="block text-xs text-gray-500 dark:text-gray-400">
                              {suggestion.type === 'platform' ? 'Platform' : 'Student'}
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
  // Get all bookings except the next one for the expandable list
  const remainingBookings = nextBooking
    ? upcomingBookings.filter((b) => b.id !== nextBooking.id)
    : upcomingBookings;

  return (
    <div className="flex-shrink-0 p-4 border-b border-gray-200">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
              activeConversation?.type === 'platform'
                ? 'bg-blue-100 text-blue-600'
                : 'bg-purple-100 text-purple-600'
            }`}
          >
            {activeConversation?.avatar}
          </div>
          <div>
            <h3 className="font-medium text-gray-900 dark:text-gray-100">{activeConversation?.name}</h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {activeConversation?.type === 'platform' ? 'Platform' : 'Student'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Booking context badge */}
          {nextBooking && (
            <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 bg-purple-50 border border-purple-200 rounded-full text-xs text-purple-700">
              <Calendar className="w-3 h-3" />
              <span className="truncate max-w-[220px]">{formatBookingInfo(nextBooking)}</span>
              {upcomingCount > 1 && (
                <span className="text-purple-500">+{upcomingCount - 1} more</span>
              )}
            </div>
          )}
          {activeConversation && (
            <div className="relative" ref={threadMenuRef}>
              <button
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
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
                  className="absolute right-0 mt-2 w-56 bg-white border border-gray-200 rounded-lg shadow-lg z-40"
                >
                  <div className="p-3 border-b border-gray-100">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100">Booking Info</p>
                  </div>
                  <div className="p-3">
                    {nextBooking ? (
                      <div className="space-y-3">
                        {/* Header row with NEXT BOOKING label and Upcoming tag */}
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-[#7E22CE] uppercase tracking-wide">Next Booking</span>
                          <span className="px-2 py-0.5 text-xs font-medium text-[#7E22CE] border border-[#7E22CE] rounded-full">
                            Upcoming
                          </span>
                        </div>

                        {/* Next booking details in purple container */}
                        <div className="p-3 bg-purple-50 rounded-lg border border-purple-200">
                          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{nextBooking.service_name}</p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">{formatDateShort(nextBooking.date)}, {formatTime12h(nextBooking.start_time)}</p>
                          <p className="text-[10px] text-gray-400 dark:text-gray-400 font-mono mt-1 truncate">{nextBooking.id}</p>
                        </div>

                        {/* Expand/collapse for more bookings */}
                        {upcomingCount > 1 && (
                          <button
                            type="button"
                            onClick={() => setShowUpcomingBookings((v) => !v)}
                            className="text-xs text-[#7E22CE] flex items-center justify-between gap-1 hover:text-purple-800 w-full text-left pt-1"
                          >
                            <span>
                              +{upcomingCount - 1} more upcoming {upcomingCount - 1 === 1 ? 'booking' : 'bookings'}
                            </span>
                            <span aria-hidden="true" className={`transition-transform ${showUpcomingBookings ? 'rotate-180' : ''}`}>^</span>
                          </button>
                        )}

                        {/* Expanded upcoming bookings */}
                        {showUpcomingBookings && remainingBookings.length > 0 && (
                          <div className="space-y-2 pt-2">
                            {remainingBookings.map((booking) => (
                              <div key={booking.id} className="p-2.5 bg-gray-50 rounded-lg border border-gray-200">
                                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{booking.service_name}</p>
                                <p className="text-xs text-gray-500 dark:text-gray-400">{formatDateShort(booking.date)}, {formatTime12h(booking.start_time)}</p>
                                <p className="text-[10px] text-gray-400 dark:text-gray-400 font-mono mt-1 truncate">{booking.id}</p>
                              </div>
                            ))}
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
