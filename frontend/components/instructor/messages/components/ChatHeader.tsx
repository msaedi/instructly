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
 * Format booking info for display
 */
function formatBookingInfo(booking: ConversationBooking): string {
  try {
    const date = parseISO(booking.date);
    const formattedDate = format(date, 'MMM d');
    return `${booking.service_name} on ${formattedDate} at ${booking.start_time}`;
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
            <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">To:</span>
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
                            <span className="font-medium text-gray-900">{suggestion.name}</span>
                            <span className="block text-xs text-gray-500">
                              {suggestion.type === 'platform' ? 'Platform' : 'Student'}
                            </span>
                          </button>
                        </li>
                      ))
                    ) : (
                      <li className="px-3 py-2 text-xs text-gray-500">No contacts found</li>
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
            <h3 className="font-medium text-gray-900">{activeConversation?.name}</h3>
            <p className="text-xs text-gray-500">
              {activeConversation?.type === 'platform' ? 'Platform' : 'Student'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Booking context badge */}
          {nextBooking && (
            <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 bg-purple-50 border border-purple-200 rounded-full text-xs text-purple-700">
              <Calendar className="w-3 h-3" />
              <span className="truncate max-w-[180px]">{formatBookingInfo(nextBooking)}</span>
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
                aria-expanded={showThreadMenu}
                aria-haspopup="menu"
              >
                <MoreVertical className="w-4 h-4 text-gray-500" />
              </button>
              {showThreadMenu && (
                <div
                  role="menu"
                  className="absolute right-0 mt-2 w-56 bg-white border border-gray-200 rounded-lg shadow-lg z-40"
                >
                  <div className="p-3 border-b border-gray-100">
                    <p className="text-sm font-medium text-gray-900">Booking Info</p>
                  </div>
                  <div className="p-2">
                    {nextBooking ? (
                      <div className="px-2 py-2">
                        <p className="text-xs font-medium text-gray-700 mb-1">Next Booking</p>
                        <p className="text-sm text-gray-900">{nextBooking.service_name}</p>
                        <p className="text-xs text-gray-500">{nextBooking.date} at {nextBooking.start_time}</p>
                        {upcomingCount > 1 && (
                          <p className="text-xs text-purple-600 mt-1">
                            +{upcomingCount - 1} upcoming {upcomingCount - 1 === 1 ? 'booking' : 'bookings'}
                          </p>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-gray-500 px-2 py-1">No upcoming bookings</p>
                    )}
                  </div>
                  {(activeConversation.bookingIds || []).length > 0 && (
                    <>
                      <div className="border-t border-gray-100 p-3">
                        <p className="text-xs font-medium text-gray-500">Booking IDs</p>
                      </div>
                      <ul className="max-h-40 overflow-auto px-2 pb-2 space-y-1 text-xs">
                        {(activeConversation.bookingIds || []).map((bid) => (
                          <li key={bid} className="px-2 py-1 text-gray-600 font-mono truncate hover:bg-gray-50 rounded">
                            {bid}
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
