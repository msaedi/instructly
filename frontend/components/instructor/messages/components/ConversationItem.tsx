/**
 * ConversationItem - Single conversation row in the sidebar
 *
 * Pure UI component for rendering a conversation entry with:
 * - Avatar with unread indicator
 * - Name and last message preview
 * - Timestamp and archive/trash counts
 * - Archive/delete actions on hover
 */

import type { MouseEvent as ReactMouseEvent } from 'react';
import { Archive, Pencil, Trash2 } from 'lucide-react';
import type { ConversationEntry } from '../types';
import { COMPOSE_THREAD_ID } from '../constants';
import { formatShortDate } from '../utils/formatters';

export type ConversationItemProps = {
  conversation: ConversationEntry;
  isActive: boolean;
  archivedCount: number;
  trashCount: number;
  messageDisplay: 'inbox' | 'archived' | 'trash';
  onSelect: (conversationId: string) => void;
  onArchive?: ((conversationId: string) => void) | undefined;
  onDelete?: ((conversationId: string) => void) | undefined;
};

export function ConversationItem({
  conversation,
  isActive,
  archivedCount,
  trashCount,
  messageDisplay,
  onSelect,
  onArchive,
  onDelete,
}: ConversationItemProps) {
  const isCompose = conversation.id === COMPOSE_THREAD_ID;

  const conversationDate =
    !isCompose && conversation.latestMessageAt
      ? formatShortDate(new Date(conversation.latestMessageAt))
      : '';

  const avatarClasses = isCompose
    ? 'bg-[#7E22CE] text-white'
    : conversation.type === 'platform'
      ? 'bg-blue-100 text-blue-600'
      : 'bg-purple-100 text-purple-600';

  const unreadDot =
    conversation.unread > 0 && !isCompose ? (
      <span
        aria-hidden="true"
        className="pointer-events-none absolute left-0 top-1/2 inline-flex h-1.5 w-1.5 rounded-full bg-[#7E22CE]"
        style={{ transform: 'translate(calc(-100% - 6px), -50%)' }}
      />
    ) : null;

  // Show archive/delete actions only in inbox view and for non-compose items
  const showActions = !isCompose && messageDisplay === 'inbox';

  const handleArchiveClick = (event: ReactMouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    onArchive?.(conversation.id);
  };

  const handleDeleteClick = (event: ReactMouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    onDelete?.(conversation.id);
  };

  return (
    <li className="group relative">
      <button
        type="button"
        onClick={() => onSelect(conversation.id)}
        className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${
          isActive ? 'bg-purple-50' : 'hover:bg-gray-50'
        }`}
      >
        <div className="relative">
          <div
            className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium ${avatarClasses}`}
          >
            {isCompose ? <Pencil className="w-4 h-4" /> : conversation.avatar}
          </div>
          {unreadDot}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-900 truncate">
            {isCompose ? 'New Message' : conversation.name}
          </p>
          <p className="text-xs text-gray-500 truncate">
            {conversation.lastMessage || (isCompose ? 'Draft a message' : '')}
          </p>
        </div>
        {!isCompose && (
          <div className="flex flex-col items-end gap-1 text-xs text-gray-400">
            {conversationDate ? (
              <span className="text-[11px] text-gray-500 leading-none">
                {conversationDate}
              </span>
            ) : (
              conversation.timestamp && <span>{conversation.timestamp}</span>
            )}
            <div className="flex items-center gap-2">
              {archivedCount > 0 && (
                <span className="inline-flex items-center gap-1">
                  <Archive className="w-3 h-3" aria-hidden="true" />
                  <span>{archivedCount}</span>
                </span>
              )}
              {trashCount > 0 && (
                <span className="inline-flex items-center gap-1">
                  <Trash2 className="w-3 h-3" aria-hidden="true" />
                  <span>{trashCount}</span>
                </span>
              )}
            </div>
            {conversation.unread > 0 && (
              <span className="sr-only">
                {conversation.unread === 1
                  ? '1 unread message'
                  : `${conversation.unread} unread messages`}
              </span>
            )}
          </div>
        )}
      </button>

      {/* Hover actions - Archive and Delete buttons */}
      {showActions && (
        <div className="absolute right-2 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center gap-1 bg-white rounded-lg shadow-sm border border-gray-200 p-1">
          <button
            type="button"
            aria-label="Archive conversation"
            title="Archive conversation"
            onClick={handleArchiveClick}
            className="inline-flex h-7 w-7 items-center justify-center rounded text-gray-500 transition-colors hover:bg-purple-50 hover:text-[#7E22CE]"
          >
            <Archive className="w-4 h-4" />
          </button>
          <button
            type="button"
            aria-label="Delete conversation"
            title="Delete conversation"
            onClick={handleDeleteClick}
            className="inline-flex h-7 w-7 items-center justify-center rounded text-gray-500 transition-colors hover:bg-red-50 hover:text-red-600"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      )}
    </li>
  );
}
