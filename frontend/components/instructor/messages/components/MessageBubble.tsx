/**
 * MessageBubble - Single message display component
 *
 * Pure UI component for rendering a chat message bubble with:
 * - Sender-appropriate styling (instructor/student/platform)
 * - Attachment previews
 * - Delivery status
 */

import { Paperclip, Check, CheckCheck } from 'lucide-react';
import type { MessageWithAttachments } from '../types';
import { formatShortDate } from '../utils/formatters';

export type MessageBubbleProps = {
  message: MessageWithAttachments;
  isLastInstructor: boolean;
  showSenderName?: boolean;
  senderName?: string;
  showReadIndicator?: boolean;
  readReceiptCount?: number;
  hasDeliveredAt?: boolean;
  readTimestamp?: string;
  // Reaction props
  isOwnMessage?: boolean;
  currentReaction?: string | null;
  onReactionClick?: (emoji: string) => void;
  showReactionPicker?: boolean;
  onToggleReactionPicker?: () => void;
  processingReaction?: boolean;
};

export function MessageBubble({
  message,
  isLastInstructor: _isLastInstructor,
  showSenderName = false,
  senderName,
  showReadIndicator = false,
  readReceiptCount = 0,
  hasDeliveredAt = false,
  readTimestamp,
  // Reaction props
  isOwnMessage = false,
  currentReaction,
  onReactionClick,
  showReactionPicker = false,
  onToggleReactionPicker,
  processingReaction = false,
}: MessageBubbleProps) {
  const attachmentList = message.attachments || [];
  const displayText = message.text?.trim();

  const bubbleClasses =
    message.sender === 'instructor'
      ? 'bg-[#7E22CE] text-white'
      : message.sender === 'platform'
        ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-100'
        : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-white';

  const attachmentWrapper =
    message.sender === 'instructor'
      ? 'bg-white/10 border border-white/20'
      : 'bg-white border border-gray-200 dark:bg-gray-600 dark:border-gray-500';

  const shortDate =
    formatShortDate(message.createdAt) ||
    formatShortDate((message as { timestamp?: string }).timestamp ?? null) ||
    '';

  return (
    <div className={`flex ${message.sender === 'instructor' ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex flex-col ${message.sender === 'instructor' ? 'items-end' : 'items-start'}`}>
        {/* Sender name */}
        {showSenderName && senderName && (
          <div className={`text-xs text-gray-500 mb-1 ${message.sender === 'instructor' ? 'mr-2' : 'ml-2'}`}>
            {senderName}
          </div>
        )}

        <div
          className={`group relative max-w-xs lg:max-w-md rounded-lg px-4 pt-6 pb-3 pr-14 ${bubbleClasses}`}
        >
        {shortDate && (
          <div
            className={`absolute top-2 right-3 flex flex-col items-end text-[11px] ${
              message.sender === 'instructor'
                ? 'text-white/80'
                : message.sender === 'platform'
                  ? 'text-blue-700 dark:text-blue-300'
                  : 'text-gray-500 dark:text-gray-300'
            }`}
          >
            <span className="leading-none mb-2">{shortDate}</span>
          </div>
        )}

        {displayText && <p className="text-sm whitespace-pre-line">{displayText}</p>}

        {attachmentList.length > 0 && (
          <div className="mt-2 flex flex-col gap-2">
            {attachmentList.map((attachment, index) => {
              const isImage = attachment.type.startsWith('image/');
              if (isImage && attachment.dataUrl) {
                return (
                  <div
                    key={`${attachment.name}-${index}`}
                    className={`overflow-hidden rounded-lg ${attachmentWrapper}`}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={attachment.dataUrl}
                      alt={attachment.name}
                      className="max-w-[240px] rounded-md object-cover"
                    />
                    <p className="text-xs opacity-80 mt-1 truncate px-2 pb-1">{attachment.name}</p>
                  </div>
                );
              }
              return (
                <div
                  key={`${attachment.name}-${index}`}
                  className={`flex items-center gap-2 rounded-lg px-3 py-2 ${attachmentWrapper}`}
                >
                  <Paperclip className="w-4 h-4 opacity-80" />
                  <span className="text-xs truncate max-w-[12rem]" title={attachment.name}>
                    {attachment.name}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {!shortDate && <p className="text-xs opacity-70 mt-1">{message.timestamp}</p>}

        {showReadIndicator && message.sender === 'instructor' && (
          <div className="flex items-center justify-end mt-1">
            {readReceiptCount > 0 ? (
              <CheckCheck className="w-3 h-3 text-blue-300" />
            ) : hasDeliveredAt ? (
              <CheckCheck className="w-3 h-3 text-white/60" />
            ) : (
              <Check className="w-3 h-3 text-white/60" />
            )}
          </div>
        )}
        </div>

        {/* Inline read time for latest read own message (iMessage-style) */}
        {readTimestamp && message.sender === 'instructor' && (
          <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400 text-right pr-1">
            {readTimestamp}
          </div>
        )}

        {/* Reaction bar (counts) */}
        {(() => {
          const reactions = message.reactions || {};
          const displayReactions: Record<string, number> = { ...reactions };

          // Adjust counts based on local state changes
          const serverReaction = message.my_reactions?.[0];
          if (currentReaction !== undefined && currentReaction !== serverReaction) {
            if (serverReaction) {
              // Decrement old reaction
              displayReactions[serverReaction] = Math.max(0, (displayReactions[serverReaction] || 0) - 1);
              if (displayReactions[serverReaction] === 0) {
                delete displayReactions[serverReaction];
              }
            }
            if (currentReaction) {
              // Increment new reaction
              displayReactions[currentReaction] = (displayReactions[currentReaction] || 0) + 1;
            }
          }

          const entries = Object.entries(displayReactions).filter(([, c]) => c > 0);
          if (entries.length === 0) return null;

          return (
            <div className={`mt-1 flex gap-1 ${message.sender === 'instructor' ? 'justify-end pr-1' : 'justify-start pl-1'}`}>
              {entries.map(([emoji, count]) => {
                const mine = currentReaction === emoji || message.my_reactions?.[0] === emoji;
                return (
                  <button
                    type="button"
                    key={emoji}
                    onClick={() => {
                      if (isOwnMessage || !onReactionClick) return;
                      onReactionClick(emoji);
                    }}
                    disabled={isOwnMessage || processingReaction}
                    className={`rounded-full px-2 py-0.5 text-xs ring-1 transition ${
                      mine
                        ? 'bg-[#7E22CE] text-white ring-[#7E22CE]'
                        : message.sender === 'instructor'
                          ? 'bg-purple-50 text-[#7E22CE] ring-purple-200'
                          : 'bg-gray-50 text-gray-700 ring-gray-200'
                    } ${(isOwnMessage || processingReaction) && 'cursor-default'}`}
                  >
                    {emoji} {count}
                  </button>
                );
              })}
            </div>
          );
        })()}

        {/* Add reaction control (other user's messages only) */}
        {!isOwnMessage && onReactionClick && onToggleReactionPicker && (
          <div className={`mt-1 flex ${message.sender === 'instructor' ? 'justify-end pr-1' : 'justify-start pl-1'}`}>
            <button
              type="button"
              onClick={onToggleReactionPicker}
              disabled={processingReaction}
              className={`rounded-full px-2 py-0.5 text-xs ring-1 transition ${
                processingReaction
                  ? 'bg-gray-100 text-gray-400 ring-gray-200 cursor-not-allowed'
                  : 'bg-gray-50 text-gray-700 ring-gray-200 hover:bg-gray-100'
              }`}
            >
              +
            </button>
            {showReactionPicker && !processingReaction && (
              <div className="ml-2 flex gap-1 rounded-full bg-white ring-1 ring-gray-200 shadow px-2 py-1">
                {['👍', '❤️', '😊', '😮', '🎉'].map((e) => {
                  const isCurrentReaction = currentReaction === e;
                  return (
                    <button
                      key={e}
                      onClick={(event) => {
                        event.stopPropagation();
                        event.preventDefault();
                        if (processingReaction) return;
                        onReactionClick(e);
                      }}
                      disabled={processingReaction}
                      className={`text-xl leading-none transition ${
                        processingReaction ? 'opacity-50 cursor-not-allowed pointer-events-none' : 'hover:scale-110'
                      } ${isCurrentReaction && 'bg-purple-100 rounded-full px-1'}`}
                    >
                      {e}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
