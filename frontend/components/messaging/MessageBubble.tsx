import React, { useMemo, useState } from 'react';
import { Check, CheckCheck, Pencil, Trash2, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { NormalizedMessage, NormalizedReaction } from './types';
import { ReactionTrigger } from './ReactionTrigger';

interface MessageBubbleProps {
  message: NormalizedMessage;
  canEdit?: boolean;
  canDelete?: boolean;
  canReact?: boolean;
  showReadReceipt?: boolean;
  onEdit?: (messageId: string, newContent: string) => Promise<void> | void;
  onDelete?: (messageId: string) => Promise<void> | void;
  onReact?: (messageId: string, emoji: string) => Promise<void> | void;
  reactionBusy?: boolean;
  renderAttachments?: ((attachments: NonNullable<NormalizedMessage['attachments']>) => React.ReactNode) | undefined;
  side?: 'left' | 'right';
  quickEmojis?: string[];
}

export function MessageBubble({
  message,
  canEdit = false,
  canDelete = false,
  canReact = true,
  showReadReceipt = false,
  onEdit,
  onDelete,
  onReact,
  reactionBusy = false,
  renderAttachments,
  side,
  quickEmojis,
}: MessageBubbleProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(message.content);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isReactionOpen, setIsReactionOpen] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const bubbleSide: 'left' | 'right' = side ?? (message.isOwn ? 'right' : 'left');

  const reactions: NormalizedReaction[] = useMemo(() => message.reactions || [], [message.reactions]);

  const handleSave = async () => {
    if (!onEdit) {
      setIsEditing(false);
      return;
    }
    const trimmed = draft.trim();
    if (!trimmed || trimmed === message.content.trim()) {
      setIsEditing(false);
      setDraft(message.content);
      return;
    }
    await onEdit(message.id, trimmed);
    setIsEditing(false);
  };

  const handleDelete = async () => {
    if (!onDelete) return;
    setIsDeleting(true);
    await onDelete(message.id);
    setIsDeleting(false);
  };

  const showEditedTag = message.isEdited && !message.isDeleted;

  const readIcon = () => {
    if (!showReadReceipt) return null;
    if (message.readStatus === 'read') return <CheckCheck className="w-3 h-3 text-blue-500" />;
    if (message.readStatus === 'delivered') return <CheckCheck className="w-3 h-3 text-gray-400" />;
    return <Check className="w-3 h-3 text-gray-400" />;
  };

  // Footer row: reactions position based on bubble side
  // - Own messages (right): reactions on left, read timestamp on right
  // - Other's messages (left): reactions on right
  const renderFooter = () => {
    const hasReactions = reactions.length > 0;
    const hasReadTimestamp = message.isOwn && message.readTimestampLabel && message.readStatus === 'read';

    if (!hasReactions && !hasReadTimestamp) return null;

    const reactionButtons = reactions.map((r) => (
      <button
        key={r.emoji}
        type="button"
        disabled={reactionBusy}
        className={cn(
          'rounded-full px-2 py-0.5 text-xs ring-1 transition',
          r.isMine ? 'bg-[#7E22CE] text-white ring-[#7E22CE]' : 'bg-gray-50 text-gray-700 ring-gray-200',
          reactionBusy && 'cursor-default opacity-50'
        )}
        onClick={async () => {
          if (reactionBusy || !onReact) return;
          await onReact(message.id, r.emoji);
        }}
      >
        {r.emoji} {r.count}
      </button>
    ));

    // For own messages (right side): reactions left, read timestamp right
    // For other's messages (left side): reactions right
    if (bubbleSide === 'right') {
      return (
        <div className="mt-1 flex items-center gap-3 w-full px-1">
          <div className="flex gap-1 flex-shrink-0">{reactionButtons}</div>
          <div className="flex-1" />
          {hasReadTimestamp && (
            <span className="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0">
              {message.readTimestampLabel}
            </span>
          )}
        </div>
      );
    }

    // Left side bubbles: reactions on right
    return (
      <div className="mt-1 flex items-center justify-end w-full px-1">
        <div className="flex gap-1 flex-shrink-0">{reactionButtons}</div>
      </div>
    );
  };

  const timeAndActions = (
    <div
      className={cn(
        'mt-2 flex items-center gap-2 text-xs justify-end',
        bubbleSide === 'right' ? 'text-white/80' : 'text-gray-600 dark:text-gray-300'
      )}
    >
      {message.timestampLabel && <span className="leading-none">{message.timestampLabel}</span>}
      {showEditedTag && <span className="text-[10px] opacity-80">edited</span>}
      {showReadReceipt && readIcon()}
      {message.isOwn && !message.isDeleted && (
        <>
          {isEditing ? (
            <>
              <span className="opacity-80">Save?</span>
              <button
                type="button"
                onClick={handleSave}
                disabled={!draft.trim()}
                className="rounded-full p-1 hover:bg-white/10 text-white disabled:opacity-50"
                aria-label="Confirm edit"
              >
                <Check className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsEditing(false);
                  setDraft(message.content);
                }}
                className="rounded-full p-1 hover:bg-white/10 text-white"
                aria-label="Cancel edit"
              >
                <X className="w-4 h-4" />
              </button>
            </>
          ) : isDeleting ? (
            <>
              <span className="opacity-80">Delete?</span>
              <button
                type="button"
                onClick={handleDelete}
                className="rounded-full p-1 hover:bg-white/10 text-white"
                aria-label="Confirm delete"
              >
                <Check className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => setIsDeleting(false)}
                className="rounded-full p-1 hover:bg-white/10 text-white"
                aria-label="Cancel delete"
              >
                <X className="w-4 h-4" />
              </button>
            </>
          ) : (
            <>
              {canEdit && onEdit && (
                <button
                  type="button"
                  onClick={() => setIsEditing(true)}
                  className="rounded-full p-1 hover:bg-white/10 text-white"
                  aria-label="Edit message"
                >
                  <Pencil className="w-4 h-4" />
                </button>
              )}
              {canDelete && onDelete && (
                <button
                  type="button"
                  onClick={() => setIsDeleting(true)}
                  className="rounded-full p-1 hover:bg-white/10 text-white"
                  aria-label="Delete message"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </>
          )}
        </>
      )}
    </div>
  );

  return (
    <div className={cn('flex', bubbleSide === 'right' ? 'justify-end' : 'justify-start')}>
      <div
        className={cn('relative flex flex-col', bubbleSide === 'right' ? 'items-end pl-2' : 'items-start pr-2')}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        <div
          className={cn(
            'relative max-w-xs lg:max-w-md rounded-2xl px-3.5 py-2 break-words shadow-sm select-text text-[15px] leading-5 sm:text-sm',
            bubbleSide === 'right'
              ? 'bg-gradient-to-tr from-purple-700 to-purple-600 text-white ring-1 ring-[#7E22CE]/10'
              : 'bg-white text-gray-900 ring-1 ring-gray-200 dark:bg-gray-800 dark:text-gray-100 dark:ring-gray-700'
          )}
        >
      {message.isDeleted ? (
        <p className="whitespace-pre-wrap italic text-gray-500">This message was deleted</p>
      ) : isEditing ? (
        <textarea
          value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void handleSave();
                } else if (e.key === 'Escape') {
                  e.preventDefault();
                  setIsEditing(false);
                  setDraft(message.content);
                }
              }}
              rows={1}
              autoFocus
              className={cn(
                'w-full resize-none rounded-md px-2 py-1 text-[15px] leading-5 outline-none focus:ring-[#7E22CE] focus:border-purple-500',
                bubbleSide === 'right'
                  ? 'bg-transparent text-white placeholder:text-blue-100'
                  : 'bg-transparent text-gray-900 placeholder:text-gray-400'
              )}
              style={{
                overflowY: 'hidden',
                height: 'auto',
                color: bubbleSide === 'right' ? 'white' : undefined,
                caretColor: bubbleSide === 'right' ? 'white' : undefined,
              }}
            />
          ) : (
            <p className={cn('whitespace-pre-wrap', message.isDeleted && 'italic text-gray-500')}>
              {message.isDeleted ? 'This message was deleted' : message.content}
            </p>
          )}

          {renderAttachments && message.attachments && message.attachments.length > 0 && (
            <div className="mt-2">{renderAttachments(message.attachments)}</div>
          )}

          {timeAndActions}
        </div>

        {renderFooter()}

        {/* Hover bridge - extends hover area to cover reaction trigger position */}
        {canReact && !message.isDeleted && onReact && (
          <div
            className={cn(
              'absolute top-0 bottom-0 w-10',
              bubbleSide === 'right' ? 'right-full' : 'left-full'
            )}
            aria-hidden="true"
          />
        )}

        {canReact && !message.isDeleted && onReact && (
          <ReactionTrigger
            messageId={message.id}
            side={bubbleSide === 'right' ? 'right' : 'left'}
            isOpen={isReactionOpen}
            isHovered={isHovered}
            onOpen={() => setIsReactionOpen(true)}
            onClose={() => setIsReactionOpen(false)}
            onSelect={(emoji) => onReact(message.id, emoji)}
            currentEmoji={message.currentUserReaction ?? null}
            emojis={quickEmojis ?? undefined}
            disabled={reactionBusy}
          />
        )}
      </div>
    </div>
  );
}
