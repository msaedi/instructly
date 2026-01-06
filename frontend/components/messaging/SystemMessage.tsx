/**
 * SystemMessage - Component for displaying system/platform messages
 *
 * Phase 5: Renders system messages with distinct styling:
 * - Centered layout
 * - Muted colors
 * - Emoji prefix based on message type
 */

import { cn } from '@/lib/utils';
import { formatRelativeTimestamp } from './formatters';

export type SystemMessageType =
  | 'system_booking_created'
  | 'system_booking_confirmed'
  | 'system_booking_cancelled'
  | 'system_booking_completed'
  | 'system_booking_rescheduled'
  | 'system_payment_received'
  | 'system_payment_refunded'
  | 'system_review_received'
  | 'system_generic'
  | string;

export interface SystemMessageProps {
  id: string;
  content: string;
  messageType: SystemMessageType;
  createdAt: string;
  bookingId?: string | null;
  className?: string;
}

// Map message types to emojis
const MESSAGE_TYPE_EMOJIS: Record<string, string> = {
  system_booking_created: '📅',
  system_booking_confirmed: '✅',
  system_booking_cancelled: '❌',
  system_booking_completed: '🎉',
  system_booking_rescheduled: '🔄',
  system_payment_received: '💰',
  system_payment_refunded: '💸',
  system_review_received: '⭐',
  system_generic: 'ℹ️',
};

// Get emoji for message type
function getEmojiForType(messageType: SystemMessageType): string {
  return MESSAGE_TYPE_EMOJIS[messageType] ?? MESSAGE_TYPE_EMOJIS['system_generic'] ?? 'ℹ️';
}

export function SystemMessage({
  content,
  messageType,
  createdAt,
  className,
}: SystemMessageProps) {
  const emoji = getEmojiForType(messageType);
  const timestamp = formatRelativeTimestamp(createdAt);

  return (
    <div className={cn('flex justify-center my-4', className)}>
      <div className="inline-flex flex-col items-center max-w-md px-4 py-2 rounded-full bg-gray-100 dark:bg-gray-800">
        <p className="text-sm text-gray-600 dark:text-gray-400 text-center">
          <span className="mr-1.5" role="img" aria-hidden="true">
            {emoji}
          </span>
          {content}
        </p>
        {timestamp && (
          <span className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            {timestamp}
          </span>
        )}
      </div>
    </div>
  );
}
