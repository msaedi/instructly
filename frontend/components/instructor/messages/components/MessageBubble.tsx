/**
 * MessageBubble - Single message display component
 *
 * Pure UI component for rendering a chat message bubble with:
 * - Sender-appropriate styling (instructor/student/platform)
 * - Attachment previews
 * - Delivery status
 */

import { Paperclip, Check, CheckCheck, Pencil, Trash2, X } from 'lucide-react';
import { useState } from 'react';
import type { MessageWithAttachments } from '../types';

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
  onEdit?: () => void;
  onDelete?: () => void;
  canEdit?: boolean;
  canDelete?: boolean;
  isDeleting?: boolean;
  isEditing?: boolean;
  editValue?: string;
  onEditChange?: (value: string) => void;
  onSaveEdit?: () => void;
  onCancelEdit?: () => void;
  isSavingEdit?: boolean;
  showDeleteConfirm?: boolean;
  onConfirmDelete?: () => void;
  onCancelDelete?: () => void;
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
  onEdit,
  onDelete,
  canEdit = false,
  canDelete = false,
  isDeleting = false,
  isEditing = false,
  editValue,
  onEditChange,
  onSaveEdit,
  onCancelEdit,
  isSavingEdit = false,
  showDeleteConfirm = false,
  onConfirmDelete,
  onCancelDelete,
}: MessageBubbleProps) {
  const [isHovered, setIsHovered] = useState(false);
  const quickEmojis = ['👍', '❤️', '😊', '😮', '🎉'];
  const isDeleted = Boolean(message.isDeleted);
  const attachmentList = isDeleted ? [] : message.attachments || [];
  const displayText = isDeleted ? 'This message was deleted' : message.text?.trim();
  const isInstructorMessage = message.sender === 'instructor';

  const bubbleClasses =
    isDeleted
      ? 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-300 ring-1 ring-gray-200/60'
      : message.sender === 'instructor'
        ? 'bg-[#7E22CE] text-white'
        : message.sender === 'platform'
          ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-100'
          : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-white';

  const attachmentWrapper =
    message.sender === 'instructor'
      ? 'bg-white/10 border border-white/20'
      : 'bg-white border border-gray-200 dark:bg-gray-600 dark:border-gray-500';

  const formattedTime = (() => {
    const source =
      message.createdAt ||
      (message as { timestamp?: string }).timestamp ||
      null;
    if (!source) return '';
    const d = new Date(source);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  })();

  const timeLabel = formattedTime || message.timestamp || '';

  return (
    <div className={`flex ${message.sender === 'instructor' ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`relative flex flex-col ${message.sender === 'instructor' ? 'items-end pl-2' : 'items-start pr-2'}`}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        {/* Sender name */}
        {showSenderName && senderName && (
          <div className={`text-xs text-gray-500 mb-1 ${message.sender === 'instructor' ? 'mr-2' : 'ml-2'}`}>
            {senderName}
          </div>
        )}

        <div
          className={`group relative max-w-xs lg:max-w-md rounded-lg px-4 py-3 pr-14 ${bubbleClasses}`}
          data-testid="message-bubble"
        >
          {isEditing ? (
            <>
              <div className="flex items-start gap-2">
                <textarea
                  value={editValue ?? ''}
                  onChange={(e) => onEditChange?.(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      onSaveEdit?.();
                    } else if (e.key === 'Escape') {
                      e.preventDefault();
                      onCancelEdit?.();
                    }
                  }}
                  rows={1}
                  autoFocus
                  className={`w-full resize-none rounded-md border px-3 py-2 text-sm leading-5 focus:outline-none focus:ring-1 ${
                    isInstructorMessage
                      ? 'bg-white/10 border-white/30 text-white placeholder:text-white/70 focus:ring-white/60'
                      : 'bg-white border-gray-300 text-gray-900 dark:bg-gray-800 dark:border-gray-700 dark:text-white placeholder:text-gray-400 focus:ring-[#7E22CE]'
                  }`}
                  style={
                    isInstructorMessage
                      ? { color: 'white', caretColor: 'white', height: 'auto', overflowY: 'hidden' }
                      : { height: 'auto', overflowY: 'hidden' }
                  }
                  placeholder="Edit message"
                />
              </div>
            </>
          ) : (
            displayText && (
              <div className="flex items-start gap-2">
                <p className="text-sm whitespace-pre-line flex-1">{displayText}</p>
              </div>
            )
          )}

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

          <div className={`mt-2 flex items-center gap-2 text-xs ${message.sender === 'instructor' ? 'text-white/80' : 'text-gray-600 dark:text-gray-300'} justify-end`}>
            {isEditing ? (
              <div className="flex items-center gap-2">
                <span className="opacity-80">{isSavingEdit ? 'Saving…' : 'Save?'}</span>
                <button
                  type="button"
                  onClick={() => onSaveEdit?.()}
                  disabled={isSavingEdit || !editValue?.trim()}
                  className={`rounded-full p-1 ${message.sender === 'instructor' ? 'hover:bg-white/10 text-white' : 'hover:bg-gray-100 text-gray-700'} ${isSavingEdit || !editValue?.trim() ? 'opacity-50 cursor-not-allowed' : ''}`}
                  aria-label="Confirm edit"
                >
                  <Check className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={() => onCancelEdit?.()}
                  className={`rounded-full p-1 ${message.sender === 'instructor' ? 'hover:bg-white/10 text-white' : 'hover:bg-gray-100 text-gray-700'}`}
                  aria-label="Cancel edit"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : showDeleteConfirm ? (
              <div className="flex items-center gap-2">
                <span className="opacity-80">Delete?</span>
                <button
                  type="button"
                  onClick={() => onConfirmDelete?.()}
                  disabled={isDeleting}
                  className={`rounded-full p-1 ${message.sender === 'instructor' ? 'hover:bg-white/10 text-white' : 'hover:bg-gray-100 text-gray-700'} ${isDeleting ? 'opacity-50 cursor-not-allowed' : ''}`}
                  aria-label="Confirm delete"
                >
                  <Check className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={() => onCancelDelete?.()}
                  className={`rounded-full p-1 ${message.sender === 'instructor' ? 'hover:bg-white/10 text-white' : 'hover:bg-gray-100 text-gray-700'}`}
                  aria-label="Cancel delete"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <>
                {timeLabel && <span className="leading-none">{timeLabel}</span>}
                {(message.isEdited || message.editedAt) && (
                  <span className="text-[10px] opacity-80">edited</span>
                )}
                {showReadIndicator && message.sender === 'instructor' && (
                  <>
                    {readReceiptCount > 0 ? (
                      <CheckCheck className="w-3 h-3 text-blue-300" />
                    ) : hasDeliveredAt ? (
                      <CheckCheck className="w-3 h-3 text-white/60" />
                    ) : (
                      <Check className="w-3 h-3 text-white/60" />
                    )}
                  </>
                )}
                {isOwnMessage && !isDeleted && (canEdit || canDelete) && (
                  <div className="ml-1 flex items-center gap-2">
                    {canEdit && onEdit && (
                      <button
                        type="button"
                        onClick={onEdit}
                        className="text-white/80 hover:text-white dark:text-gray-200"
                        aria-label="Edit message"
                      >
                        <Pencil className="w-4 h-4" />
                      </button>
                    )}
                    {canDelete && onDelete && (
                      <button
                        type="button"
                        onClick={onDelete}
                        disabled={isDeleting}
                        className={`text-white/80 hover:text-white dark:text-gray-200 ${isDeleting ? 'opacity-60 cursor-not-allowed' : ''}`}
                        aria-label="Delete message"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* Inline read time for latest read own message (iMessage-style) */}
        {readTimestamp && message.sender === 'instructor' && (
          <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400 text-right pr-1">
            {readTimestamp}
          </div>
        )}

        {/* Reaction bar (counts) */}
        {!isDeleted && (() => {
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

        {/* Hover/press reaction bar (other user's messages only) */}
        {!isDeleted && onReactionClick && (isHovered || showReactionPicker) && (
          <div
            className={`absolute top-1/2 -translate-y-1/2 z-20 ${message.sender === 'instructor' ? 'right-full mr-1' : 'left-full ml-1'}`}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
            data-reaction-area="true"
          >
            {isHovered && !showReactionPicker && (
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  event.preventDefault();
                  onToggleReactionPicker?.();
                }}
                className="rounded-full bg-white px-2 py-1 text-sm text-gray-700 shadow ring-1 ring-gray-200 hover:bg-gray-50"
                aria-label="Add reaction"
                data-reaction-area="true"
              >
                😊
              </button>
            )}
            {showReactionPicker && (
              <div className="flex gap-1 rounded-full bg-white ring-1 ring-gray-200 shadow px-2 py-1">
                {quickEmojis.map((e) => {
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
                      data-reaction-area="true"
                    >
                      {e}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
        {/* Hover bridge to keep reaction visible while moving cursor */}
        {!isDeleted && (
          <div
            className={`absolute top-0 bottom-0 ${message.sender === 'instructor' ? 'right-full w-6' : 'left-full w-6'}`}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
            data-reaction-area="true"
          />
        )}
      </div>
    </div>
  );
}
