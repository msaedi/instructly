/**
 * ConversationList - Sidebar with conversation entries
 *
 * Includes:
 * - Search input
 * - Compose button
 * - Filter buttons (All/Students/Platform/Archived/Trash)
 * - Scrollable conversation list
 */

import { Pencil, Search } from 'lucide-react';
import type { ConversationEntry, MessageWithAttachments, MessageDisplayMode } from '../types';
import { COMPOSE_THREAD_ID, FILTER_OPTIONS } from '../constants';
import { ConversationItem } from './ConversationItem';

export type ConversationListProps = {
  conversations: ConversationEntry[];
  selectedChat: string | null;
  searchQuery: string;
  typeFilter: 'all' | 'student' | 'platform';
  messageDisplay: MessageDisplayMode;
  isLoading: boolean;
  error: string | null;
  archivedMessagesByThread: Record<string, MessageWithAttachments[]>;
  trashMessagesByThread: Record<string, MessageWithAttachments[]>;
  onSearchChange: (query: string) => void;
  onTypeFilterChange: (filter: 'all' | 'student' | 'platform') => void;
  onMessageDisplayChange: (display: MessageDisplayMode) => void;
  onConversationSelect: (conversationId: string) => void;
  onConversationArchive?: (conversationId: string) => void;
  onConversationDelete?: (conversationId: string) => void;
};

export function ConversationList({
  conversations,
  selectedChat,
  searchQuery,
  typeFilter,
  messageDisplay,
  isLoading,
  error,
  archivedMessagesByThread,
  trashMessagesByThread,
  onSearchChange,
  onTypeFilterChange,
  onMessageDisplayChange,
  onConversationSelect,
  onConversationArchive,
  onConversationDelete,
}: ConversationListProps) {
  return (
    <aside className="w-full lg:w-80 xl:w-96 border-b border-gray-200 lg:border-b-0 lg:border-r flex flex-col min-h-0 max-h-full overflow-hidden">
      {/* Search and compose */}
      <div className="p-4 border-b border-gray-200 flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search conversations"
            className="w-full rounded-full border border-gray-300 bg-white pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-[#7E22CE]"
          />
        </div>
        <button
          type="button"
          onClick={() => onConversationSelect(COMPOSE_THREAD_ID)}
          className="inline-flex items-center justify-center rounded-full bg-purple-100 p-2 text-[#7E22CE] transition-colors hover:bg-purple-200"
          aria-label="Compose message"
        >
          <Pencil className="w-4 h-4" />
        </button>
      </div>

      {/* Filters */}
      <div className="px-4 py-3 border-b border-gray-200 flex flex-wrap gap-2 items-center">
        {FILTER_OPTIONS.map((option) => {
          const isActive = option.value === typeFilter && messageDisplay === 'inbox';
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => {
                onTypeFilterChange(option.value);
                onMessageDisplayChange('inbox');
              }}
              className={`text-xs font-medium rounded-full px-3 py-1 transition-colors ${
                isActive ? 'bg-[#7E22CE] text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {option.label}
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => onMessageDisplayChange('archived')}
          className={`text-xs font-medium rounded-full px-3 py-1 transition-colors ${
            messageDisplay === 'archived'
              ? 'bg-[#7E22CE] text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          Archived
        </button>
        <button
          type="button"
          onClick={() => onMessageDisplayChange('trash')}
          className={`text-xs font-medium rounded-full px-3 py-1 transition-colors ${
            messageDisplay === 'trash'
              ? 'bg-[#7E22CE] text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          Trash
        </button>
      </div>

      {/* Conversation list */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {isLoading && conversations.length === 0 ? (
          <div className="p-4 text-sm text-gray-500">Loading conversations...</div>
        ) : (
          <>
            {error && (
              <div className="px-4 py-2 text-xs text-red-500">{error}</div>
            )}
            {conversations.length > 0 ? (
              <ul className="divide-y divide-gray-100">
                {conversations.map((conversation) => (
                  <ConversationItem
                    key={conversation.id}
                    conversation={conversation}
                    isActive={conversation.id === selectedChat}
                    archivedCount={archivedMessagesByThread[conversation.id]?.length ?? 0}
                    trashCount={trashMessagesByThread[conversation.id]?.length ?? 0}
                    messageDisplay={messageDisplay}
                    onSelect={onConversationSelect}
                    onArchive={onConversationArchive}
                    onDelete={onConversationDelete}
                  />
                ))}
              </ul>
            ) : (
              <div className="p-4 text-sm text-gray-500">No conversations found.</div>
            )}
          </>
        )}
      </div>
    </aside>
  );
}
