import { useEffect } from 'react';
import { cn } from '@/lib/utils';

interface ReactionTriggerProps {
  messageId: string;
  side: 'left' | 'right';
  isOpen: boolean;
  /** Whether the parent bubble is being hovered - controls trigger visibility */
  isHovered: boolean;
  onOpen: () => void;
  onClose: () => void;
  onSelect: (emoji: string) => void;
  currentEmoji?: string | null;
  emojis?: string[] | undefined;
  disabled?: boolean;
}

const DEFAULT_EMOJIS = ['👍', '❤️', '😊', '😮', '🎉'];

export function ReactionTrigger({
  messageId,
  side,
  isOpen,
  isHovered,
  onOpen,
  onClose,
  onSelect,
  currentEmoji,
  emojis = DEFAULT_EMOJIS,
  disabled = false,
}: ReactionTriggerProps) {
  // Close when clicking outside the reaction area
  useEffect(() => {
    if (!isOpen) return;
    const handler = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && target.closest(`[data-reaction-area="${messageId}"]`)) return;
      onClose();
    };
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, [isOpen, messageId, onClose]);

  if (disabled) return null;

  // Show nothing if not hovered and not open
  if (!isHovered && !isOpen) return null;

  return (
    <>
      {/* Emoji picker (shown when open) */}
      {isOpen && (
        <div
          className={cn(
            'absolute top-1/2 -translate-y-1/2 z-20',
            side === 'right' ? 'right-full mr-1' : 'left-full ml-1'
          )}
          data-reaction-area={messageId}
        >
          <div className="flex gap-1 rounded-full bg-white ring-1 ring-gray-200 shadow px-2 py-1 dark:bg-gray-900 dark:ring-gray-700">
            {emojis.map((e) => {
              const isCurrent = currentEmoji === e;
              return (
                <button
                  key={e}
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    event.preventDefault();
                    onSelect(e);
                    onClose();
                  }}
                  className={cn(
                    'text-xl leading-none transition',
                    'hover:scale-110',
                    isCurrent && 'bg-purple-100 rounded-full px-1'
                  )}
                  data-reaction-area={messageId}
                >
                  {e}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Trigger button (shown on hover, hidden when picker is open) */}
      {!isOpen && (
        <div
          className={cn(
            'absolute top-1/2 -translate-y-1/2 z-10',
            side === 'right' ? 'right-full mr-1' : 'left-full ml-1'
          )}
          data-reaction-area={messageId}
        >
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              event.preventDefault();
              onOpen();
            }}
            className="rounded-full bg-white text-gray-700 shadow ring-1 ring-gray-200 px-2 py-1 text-sm hover:bg-gray-50"
            aria-label="Add reaction"
            data-reaction-area={messageId}
          >
            😊
          </button>
        </div>
      )}
    </>
  );
}
