'use client';

/**
 * Instructor Messages Page - Main Orchestrator
 *
 * Composes the messaging interface using extracted components and hooks.
 * This file should remain ~200-300 lines as the main coordinator.
 */

import { useState, useRef, useEffect, useMemo, useCallback, startTransition, type KeyboardEvent, Fragment } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { format, isToday, isYesterday } from 'date-fns';
import { MessageSquare, ChevronDown, Undo2 } from 'lucide-react';
import {
  useAddReaction,
  useRemoveReaction,
  useEditMessage,
  useDeleteMessage,
  useMessageConfig,
} from '@/src/api/services/messages';
import { sendTypingIndicator as sendConversationTypingIndicator } from '@/src/api/services/conversations';
import { useAuthStatus } from '@/hooks/queries/useAuth';
import { useMessageStream } from '@/providers/UserMessageStreamProvider';
import { logger } from '@/lib/logger';
import { SectionHeroCard } from '@/components/dashboard/SectionHeroCard';
import { useEmbedded } from '../_embedded/EmbeddedContext';

// Extracted components and hooks
import {
  type ConversationEntry,
  type MessageDisplayMode,
  type MailSection,
  type SSEMessageWithOwnership,
  type MessageWithAttachments,
  COMPOSE_THREAD_ID,
} from '@/components/instructor/messages';

import {
  useConversations,
  useUpdateConversationState,
  useMessageDrafts,
  useMessageThread,
  useTemplates,
} from '@/components/instructor/messages/hooks';

import {
  ChatHeader,
  ConversationList,
  MessageInput,
  TemplateEditor,
} from '@/components/instructor/messages/components';
import { MessageBubble as SharedMessageBubble, normalizeInstructorMessage, formatRelativeTimestamp, useReactions, useReadReceipts, useLiveTimestamp, useSSEHandlers, type NormalizedMessage, type NormalizedReaction, type ReactionMutations, type ReadReceiptEntry } from '@/components/messaging';

// Helper to convert messageDisplay to API filter parameters
function getFiltersForDisplay(
  messageDisplay: MessageDisplayMode,
  typeFilter: 'all' | 'student' | 'platform'
): { stateFilter: 'archived' | 'trashed' | null; apiTypeFilter: 'student' | 'platform' | null } {
  let stateFilter: 'archived' | 'trashed' | null = null;

  if (messageDisplay === 'archived') {
    stateFilter = 'archived';
  } else if (messageDisplay === 'trash') {
    stateFilter = 'trashed';
  }

  const apiTypeFilter = typeFilter === 'all' ? null : typeFilter;

  return { stateFilter, apiTypeFilter };
}

export type MessagesViewerRole = 'instructor' | 'student';

type MessagesPanelContentProps = {
  viewerRole?: MessagesViewerRole;
};

export function MessagesPanelContent({
  viewerRole = 'instructor',
}: MessagesPanelContentProps) {
  const searchParams = useSearchParams();
  const { user: currentUser, isLoading: isLoadingUser } = useAuthStatus();
  const embedded = useEmbedded();
  const counterpartLabel = viewerRole === 'student' ? 'Instructor' : 'Student';
  const counterpartPluralLabel = viewerRole === 'student' ? 'Instructors' : 'Students';
  const dashboardSubtitle = viewerRole === 'student'
    ? 'Communicate with instructors and platform.'
    : 'Communicate with students and platform.';
  const bookingHrefForId = useCallback(
    (bookingId: string) => (
      viewerRole === 'student'
        ? `/student/lessons/${bookingId}`
        : `/instructor/bookings/${bookingId}`
    ),
    [viewerRole],
  );

  // Read conversation ID from URL parameter (for deep linking from MessageInstructorButton)
  const conversationFromUrl = searchParams.get('conversation');

  // Core UI state
  const [selectedChat, setSelectedChat] = useState<string | null>(conversationFromUrl);
  const [messageText, setMessageText] = useState('');
  const [pendingAttachments, setPendingAttachments] = useState<File[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<'all' | 'student' | 'platform'>('all');
  const [mailSection, setMailSection] = useState<MailSection>('inbox');
  const [messageDisplay, setMessageDisplay] = useState<MessageDisplayMode>('inbox');
  const [composeRecipient, setComposeRecipient] = useState<ConversationEntry | null>(null);
  const [composeRecipientQuery, setComposeRecipientQuery] = useState('');

  // Auto-scroll ref
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  // Calculate filters for backend
  const { stateFilter, apiTypeFilter } = getFiltersForDisplay(messageDisplay, typeFilter);

  // Extracted hooks
  const {
    conversations,
    setConversations,
    isLoading: isLoadingConversations,
    error: conversationError,
  } = useConversations({
    currentUserId: currentUser?.id,
    isLoadingUser,
    stateFilter,
    typeFilter: apiTypeFilter,
    counterpartFallbackLabel: counterpartLabel,
  });

  // Mutation hook for conversation state management
  const updateStateMutation = useUpdateConversationState();

  const { draftsByThread, updateDraft, clearDraft, getDraftKey } = useMessageDrafts();

  const {
    templates,
    setTemplates,
    selectedTemplateId,
    setSelectedTemplateId,
    templateDrafts,
    setTemplateDrafts,
    handleTemplateSubjectChange,
    handleTemplateDraftChange,
  } = useTemplates();

  const {
    threadMessages,
    archivedMessagesByThread,
    trashMessagesByThread,
    loadThreadMessages,
    handleSSEMessage,
    handleSendMessage: sendMessage,
    setThreadMessagesForDisplay,
    updateThreadMessage,
    invalidateConversationCache,
  } = useMessageThread({
    currentUserId: currentUser?.id,
    conversations,
    setConversations,
  });

  const { data: messageConfig } = useMessageConfig();
  const editWindowMinutes = messageConfig?.edit_window_minutes ?? 5;
  const editMessageMutation = useEditMessage();
  const deleteMessageMutation = useDeleteMessage();

  // Track previous conversation IDs to detect reappearances (auto-restored conversations)
  const previousConversationIds = useRef<Set<string>>(new Set());
  const prevSelectedChatRef = useRef<string | null>(null);

  // Track if selection was intentionally cleared (archive/trash) to prevent auto-select
  const intentionallyClearedRef = useRef(false);

  // Handle conversation selection from URL parameter (deep linking)
  useEffect(() => {
    if (conversationFromUrl && conversations.length > 0) {
      // Check if the conversation exists in the current list
      const conversationExists = conversations.some((c) => c.id === conversationFromUrl);
      if (conversationExists) {
        startTransition(() => {
          setSelectedChat(conversationFromUrl);
          // Ensure we're in inbox view to see the conversation
          setMessageDisplay('inbox');
        });
      }
    }
  }, [conversationFromUrl, conversations]);

  useEffect(() => {
    if (conversations) {
      const currentIds = new Set(conversations.map((c) => c.id));

      // Find conversations that just appeared (weren't in previous list)
      for (const conv of conversations) {
        if (!previousConversationIds.current.has(conv.id)) {
          // This conversation just appeared - invalidate its cache
          // This handles auto-restored conversations (were archived/trashed, now active)
          invalidateConversationCache(conv.id);

          // ALWAYS clear prevSelectedChatRef to force reload when this conversation is selected
          // Don't check if it's currently selected - it will be auto-selected soon
          prevSelectedChatRef.current = null;
        }
      }

      previousConversationIds.current = currentIds;
    }
  }, [conversations, invalidateConversationCache]);

  // Backend-powered archive/trash handlers
  const handleArchiveConversation = useCallback((conversationId: string) => {
    // If archiving the currently selected conversation, clear selection
    if (selectedChat === conversationId) {
      intentionallyClearedRef.current = true;
      setSelectedChat(null);
    }
    updateStateMutation.mutate({ conversationId, state: 'archived' });
  }, [updateStateMutation, selectedChat]);

  const handleDeleteConversation = useCallback((conversationId: string) => {
    // If trashing the currently selected conversation, clear selection
    if (selectedChat === conversationId) {
      intentionallyClearedRef.current = true;
      setSelectedChat(null);
    }
    updateStateMutation.mutate({ conversationId, state: 'trashed' });
  }, [updateStateMutation, selectedChat]);

  const handleRestoreConversation = useCallback((conversationId: string) => {
    // Restore conversation to active state
    updateStateMutation.mutate(
      { conversationId, state: 'active' },
      {
        onSuccess: () => {
          // After cache is invalidated, clear selection and switch back to inbox
          setSelectedChat(null);
          setMessageDisplay('inbox');
        }
      }
    );
  }, [updateStateMutation]);

  // Derived state
  const isComposeView = selectedChat === COMPOSE_THREAD_ID;
  const activeConversation = useMemo(
    () => selectedChat && !isComposeView
      ? conversations.find((conv) => conv.id === selectedChat) ?? null
      : null,
    [selectedChat, isComposeView, conversations]
  );

  // Typing indicator
  const typingDebounceRef = useRef<NodeJS.Timeout | null>(null);

  const handleTyping = useCallback(() => {
    if (!selectedChat || selectedChat === COMPOSE_THREAD_ID) return;
    void sendConversationTypingIndicator(selectedChat).catch(() => {});
  }, [selectedChat]);

  // Reaction mutations and shared hook
  const addReactionMutation = useAddReaction();
  const removeReactionMutation = useRemoveReaction();

  const reactionMutations: ReactionMutations = useMemo(
    () => ({
      addReaction: (params) => addReactionMutation.mutateAsync(params),
      removeReaction: (params) => removeReactionMutation.mutateAsync(params),
    }),
    [addReactionMutation, removeReactionMutation]
  );

  const {
    userReactions,
    processingReaction,
    handleReaction: handleAddReaction,
  } = useReactions({
    messages: threadMessages,
    mutations: reactionMutations,
    debug: false,
  });

  // Auto-scroll to bottom
  const scrollToBottom = useCallback(() => {
    // Double RAF ensures DOM is fully painted before scrolling
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (messagesContainerRef.current) {
          messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
        }
      });
    });
  }, []);

  // SSE connection (Phase 4: per-user inbox)
  const { subscribe } = useMessageStream();

  // Shared SSE handlers for typing and read receipts
  const {
    typingStatus: sseTypingStatus,
    sseReadReceipts,
    handleSSETyping,
    handleSSEReadReceipt,
  } = useSSEHandlers();

  // Shared read receipt management hook
  const { mergedReadReceipts, lastReadMessageId: lastInstructorReadMessageId } = useReadReceipts({
    messages: threadMessages,
    sseReadReceipts,
    currentUserId: currentUser?.id ?? '',
    getReadBy: (m) => m.read_by as ReadReceiptEntry[] | null | undefined,
    isOwnMessage: (m) => m.sender === 'instructor' || m.senderId === currentUser?.id,
    getCreatedAt: (m) => m.createdAt ? new Date(m.createdAt) : null,
  });

  // Live timestamp ticker - triggers re-render every minute for relative timestamps
  const tick = useLiveTimestamp();
  const relativeNow = useMemo(() => new Date(tick * 60000), [tick]);
  const nowMs = tick * 60000;

  // Use ref to store latest handleSSEMessage to avoid re-render loop
  const handleSSEMessageRef = useRef(handleSSEMessage);
  useEffect(() => {
    handleSSEMessageRef.current = handleSSEMessage;
  }, [handleSSEMessage]);

  // Store latest values in refs to avoid recreating subscription
  const selectedChatRef = useRef(selectedChat);
  const activeConversationRef = useRef(activeConversation);
  const currentUserIdRef = useRef(currentUser?.id);

  useEffect(() => {
    selectedChatRef.current = selectedChat;
    activeConversationRef.current = activeConversation;
    currentUserIdRef.current = currentUser?.id;
  }, [selectedChat, activeConversation, currentUser?.id]);

  // Extract SSE handlers to useCallback for stable references (fixes re-render loop)
  const handleSSEMessageWrapper = useCallback((message: { id: string; content: string; sender_id: string | null; sender_name: string | null; created_at: string; booking_id?: string; delivered_at?: string | null }, isMine: boolean) => {
    if (!selectedChatRef.current || !activeConversationRef.current || !currentUserIdRef.current) return;
    const sseMessage: SSEMessageWithOwnership = {
      ...message,
      booking_id: message.booking_id ?? null,
      delivered_at: message.delivered_at ?? null,
      is_deleted: false,
      is_mine: isMine,
    };
    handleSSEMessageRef.current(sseMessage, selectedChatRef.current, activeConversationRef.current);
  }, []);

  const handleReaction = useCallback((messageId: string, emoji: string, action: 'added' | 'removed', userId: string) => {
    // Update threadMessages reactions locally when SSE event is received
    updateThreadMessage(messageId, (msg) => {
      // Update reactions object
      const updatedReactions = { ...(msg.reactions || {}) };
      const currentCount = updatedReactions[emoji] || 0;
      const newCount = action === 'added' ? currentCount + 1 : Math.max(0, currentCount - 1);

      if (newCount === 0) {
        delete updatedReactions[emoji];
      } else {
        updatedReactions[emoji] = newCount;
      }

      // Update my_reactions if it's the current user
      let updatedMyReactions = msg.my_reactions || [];
      if (userId === currentUser?.id) {
        if (action === 'added') {
          // Add emoji if not already there
          if (!updatedMyReactions.includes(emoji)) {
            updatedMyReactions = [emoji]; // Users can only have one reaction
          }
        } else {
          // Remove emoji
          updatedMyReactions = updatedMyReactions.filter((e) => e !== emoji);
        }
      }

      return {
        ...msg,
        reactions: updatedReactions,
        my_reactions: updatedMyReactions,
      };
    });
  }, [currentUser?.id, updateThreadMessage]);

  const handleMessageEdited = useCallback((messageId: string, newContent: string, _editorId: string) => {
    // DEBUG: Log entry
    logger.debug('[MSG-DEBUG] handleMessageEdited CALLED (instructor)', {
      messageId,
      newContent,
      selectedChat,
    });

    // Update threadMessages when message edited via SSE
    // Note: MessageWithAttachments uses 'text' field, not 'content'
    updateThreadMessage(messageId, (msg) => {
      logger.debug('[MSG-DEBUG] handleMessageEdited updating message', {
        oldText: msg.text,
        newContent,
      });
      return {
        ...msg,
        text: newContent,
        isEdited: true,
        editedAt: new Date().toISOString(),
      };
    });
  }, [updateThreadMessage, selectedChat]);

  const handleMessageDeleted = useCallback((messageId: string, deletedBy: string) => {
    logger.debug('[MSG-DEBUG] handleMessageDeleted CALLED (instructor)', {
      messageId,
      deletedBy,
    });

    updateThreadMessage(messageId, (msg) => ({
      ...msg,
      isDeleted: true,
      text: 'This message was deleted',
      deletedBy,
      deletedAt: new Date().toISOString(),
    }));
  }, [updateThreadMessage]);

  const canModifyMessage = useCallback((message: MessageWithAttachments): boolean => {
    if (!currentUser?.id) return false;
    if (message.senderId !== currentUser.id) return false;
    if (message.isDeleted) return false;
    const created = message.createdAt ? new Date(message.createdAt).getTime() : undefined;
    if (!created) return false;
    const diffMinutes = (nowMs - created) / 60000;
    return diffMinutes <= editWindowMinutes;
  }, [currentUser, editWindowMinutes, nowMs]);

  // Subscribe to active conversation's events using conversation_id (NOT booking_id!)
  // Phase 7: SSE must use conversation_id because one conversation spans multiple bookings.
  // Using booking_id would cause messages to not be delivered when viewing chat via different bookings.
  useEffect(() => {
    if (!selectedChat || isComposeView || messageDisplay !== 'inbox') {
      return;
    }

    const unsubscribe = subscribe(selectedChat, {
      onMessage: handleSSEMessageWrapper,
      onTyping: handleSSETyping,
      onReadReceipt: handleSSEReadReceipt,
      onReaction: handleReaction,
      onMessageEdited: handleMessageEdited,
      onMessageDeleted: handleMessageDeleted,
    });

    return unsubscribe;
  }, [selectedChat, isComposeView, messageDisplay, subscribe, handleSSEMessageWrapper, handleSSETyping, handleSSEReadReceipt, handleReaction, handleMessageEdited, handleMessageDeleted]);

  // Filter conversations (backend now handles state/type filtering, we just filter by search text)
  const filteredConversations = useMemo(() => {
    return conversations.filter((conv) => {
      const matchesText = conv.name.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesText;
    });
  }, [conversations, searchQuery]);

  // Compose list entry
  const composeListEntry: ConversationEntry = useMemo(() => ({
    id: COMPOSE_THREAD_ID,
    name: 'New Message',
    lastMessage: composeRecipient ? `Draft to ${composeRecipient.name}` : 'Draft a message',
    timestamp: '',
    unread: 0,
    avatar: '',
    type: 'platform',
    bookingIds: [],
    primaryBookingId: null,
    studentId: null,
    instructorId: currentUser?.id ?? null,
    latestMessageAt: tick * 60000,
    latestMessageId: null,
  }), [composeRecipient, currentUser?.id, tick]);

  const conversationSource = useMemo(() => {
    if (messageDisplay === 'inbox') {
      return [composeListEntry, ...filteredConversations];
    }
    return filteredConversations;
  }, [composeListEntry, filteredConversations, messageDisplay]);

  // Compose suggestions
  const composeSuggestions = useMemo(() => {
    if (!composeRecipientQuery.trim()) return [];
    const query = composeRecipientQuery.toLowerCase();
    return conversations
      .filter((conv) => conv.id !== composeRecipient?.id && conv.name.toLowerCase().includes(query))
      .slice(0, 5);
  }, [composeRecipientQuery, composeRecipient?.id, conversations]);

  const normalizedThreadMessages = useMemo<NormalizedMessage[]>(() => {
    return threadMessages.map((message) => {
      const readReceiptCount = mergedReadReceipts[message.id]?.length ?? 0;
      const hasDeliveredAt = !!message.delivered_at;
      const isOwnMessage = message.sender === 'instructor';
      const currentReaction: string | null =
        message.id in userReactions ? userReactions[message.id]! : (message.my_reactions?.[0] ?? null);

      const timestampLabel = formatRelativeTimestamp(message.createdAt, relativeNow);
      const isLastRead = message.id === lastInstructorReadMessageId;
      const readTimestampLabel =
        isLastRead && readReceiptCount > 0
          ? (() => {
              const firstReceipt = mergedReadReceipts[message.id]?.[0];
              const readAt = new Date(firstReceipt?.read_at || '');
              if (isToday(readAt)) return `Read at ${format(readAt, 'h:mm a')}`;
              if (isYesterday(readAt)) return `Read yesterday at ${format(readAt, 'h:mm a')}`;
              return `Read on ${format(readAt, 'MMM d')} at ${format(readAt, 'h:mm a')}`;
            })()
          : undefined;

      const reactionsRaw = message.reactions || {};
      const displayReactions: Record<string, number> = { ...reactionsRaw };
      const reactions: NormalizedReaction[] = Object.entries(displayReactions)
        .filter(([, c]) => c > 0)
        .map(([emoji, count]) => ({
          emoji,
          count,
          isMine: currentReaction === emoji,
        }));

      const attachments =
        message.attachments?.map((attachment, index) => ({
          id: `${message.id}-att-${index}`,
          url: attachment.dataUrl || '',
          type: attachment.type,
          name: attachment.name,
        })) ?? [];

      return normalizeInstructorMessage(message, currentUser?.id ?? '', {
        reactions,
        currentUserReaction: currentReaction,
        timestampLabel,
        readStatus: isOwnMessage ? (readReceiptCount > 0 ? 'read' : hasDeliveredAt ? 'delivered' : 'sent') : undefined,
        readTimestampLabel,
        attachments,
      });
    });
  }, [threadMessages, mergedReadReceipts, lastInstructorReadMessageId, userReactions, currentUser?.id, relativeNow]);

  // Get primary booking ID for a thread
  const getPrimaryBookingId = useCallback((threadId: string | null) => {
    if (!threadId) return null;
    const conv = conversations.find((c) => c.id === threadId);
    return conv?.primaryBookingId ?? (conv?.bookingIds[0] ?? null);
  }, [conversations]);

  // Auto-select first conversation (but only if current selection is valid)
  useEffect(() => {
    if (mailSection !== 'inbox' || filteredConversations.length === 0) return;

    // Don't auto-select if user just archived/trashed a conversation
    if (intentionallyClearedRef.current) {
      intentionallyClearedRef.current = false;
      return;
    }

    // Only auto-select if:
    // 1. Nothing is selected, OR
    // 2. Current selection is not in the list (conversation was archived/trashed)
    const isCurrentSelectionValid = selectedChat && filteredConversations.some(c => c.id === selectedChat);

    if (!selectedChat || !isCurrentSelectionValid) {
      startTransition(() => {
        setSelectedChat(filteredConversations[0]?.id ?? null);
      });
    }
  }, [filteredConversations, selectedChat, mailSection]);

  // Track previous messageDisplay to detect actual changes
  const prevMessageDisplayRef = useRef<MessageDisplayMode>(messageDisplay);

  // Clear selection when switching display modes to allow auto-select to pick first conversation
  useEffect(() => {
    if (messageDisplay !== prevMessageDisplayRef.current) {
      startTransition(() => {
        setSelectedChat(null);
      });
    }
  }, [messageDisplay]);

  // Load messages when conversation selected OR when switching between All/Archived/Trash views
  useEffect(() => {
    const conversationChanged = selectedChat !== prevSelectedChatRef.current;
    const displayModeChanged = messageDisplay !== prevMessageDisplayRef.current;

    // Load messages when:
    // 1. Conversation changed to a new one, OR
    // 2. Display mode changed (All -> Archived, etc.) and a conversation is selected
    if (
      selectedChat &&
      selectedChat !== COMPOSE_THREAD_ID &&
      activeConversation &&
      (conversationChanged || displayModeChanged)
    ) {
      // Invalidate cache to force fresh fetch when switching conversations or display modes
      // This ensures new messages (shown in sidebar via inbox polling) appear immediately
      invalidateConversationCache(selectedChat);
      loadThreadMessages(selectedChat, activeConversation, messageDisplay);
      prevSelectedChatRef.current = selectedChat;
      prevMessageDisplayRef.current = messageDisplay;
    }
  }, [selectedChat, activeConversation, messageDisplay, loadThreadMessages, invalidateConversationCache]);

  // Update thread messages on display mode change
  useEffect(() => {
    if (selectedChat && selectedChat !== COMPOSE_THREAD_ID) {
      setThreadMessagesForDisplay(selectedChat, messageDisplay);
    }
  }, [messageDisplay, selectedChat, setThreadMessagesForDisplay]);

  // Auto-scroll to bottom when messages change OR when conversation changes
  useEffect(() => {
    if (threadMessages.length > 0) {
      scrollToBottom();
    }
  }, [threadMessages.length, selectedChat, messageDisplay, scrollToBottom]);

  // Load draft when switching conversations
  useEffect(() => {
    const draftValue = draftsByThread[getDraftKey(selectedChat)] ?? '';
    if (draftValue !== messageText) {
      startTransition(() => {
        setMessageText(draftValue);
      });
    }
  }, [selectedChat, draftsByThread, getDraftKey, messageText]);

  // Handlers
  const handleConversationSelect = useCallback((conversationId: string) => {
    // Save current draft
    updateDraft(selectedChat, messageText);
    setPendingAttachments([]);

    if (conversationId === COMPOSE_THREAD_ID) {
      setMessageDisplay('inbox');
      setComposeRecipient(null);
      setComposeRecipientQuery('');
      setMailSection('compose');
    } else {
      if (mailSection !== 'inbox') setMailSection('inbox');
      setComposeRecipient(null);
      setComposeRecipientQuery('');
      // Clear unread for selected conversation
      setConversations((prev) =>
        prev.map((conv) => conv.id === conversationId ? { ...conv, unread: 0 } : conv)
      );
    }

    setSelectedChat(conversationId);
    const draftValue = draftsByThread[getDraftKey(conversationId)] ?? '';
    setMessageText(draftValue);
  }, [selectedChat, messageText, mailSection, draftsByThread, getDraftKey, updateDraft, setConversations]);

  const handleMessageChange = useCallback((value: string) => {
    setMessageText(value);
    updateDraft(selectedChat, value);

    // Typing indicator debounce
    if (typingDebounceRef.current) clearTimeout(typingDebounceRef.current);
    typingDebounceRef.current = setTimeout(() => handleTyping(), 300);
  }, [selectedChat, updateDraft, handleTyping]);

  const handleSend = useCallback(async () => {
    // Cancel typing indicator
    if (typingDebounceRef.current) {
      clearTimeout(typingDebounceRef.current);
      typingDebounceRef.current = null;
    }

    await sendMessage({
      selectedChat,
      messageText,
      pendingAttachments,
      composeRecipient,
      conversations,
      getPrimaryBookingId,
      onSuccess: (targetThreadId, switchingFromCompose) => {
        setMessageText('');
        setPendingAttachments([]);
        clearDraft(selectedChat);

        if (switchingFromCompose) {
          clearDraft(COMPOSE_THREAD_ID);
          setComposeRecipient(null);
          setComposeRecipientQuery('');
          setMailSection('inbox');
          setSelectedChat(targetThreadId);
        }
      },
    });
  }, [selectedChat, messageText, pendingAttachments, composeRecipient, conversations, getPrimaryBookingId, sendMessage, clearDraft]);

  const handleKeyPress = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.repeat) return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (selectedChat === COMPOSE_THREAD_ID && !composeRecipient) return;
      void handleSend();
    }
  }, [selectedChat, composeRecipient, handleSend]);

  const isSendDisabled = messageDisplay !== 'inbox'
    || (isComposeView && (!composeRecipient || !currentUser?.id))
    || (!messageText.trim() && pendingAttachments.length === 0);

  const typingUserName = sseTypingStatus && sseTypingStatus.userId !== currentUser?.id
    ? activeConversation?.name ?? 'Someone'
    : null;

  return (
    <div className="flex h-full min-h-[calc(100vh-12rem)] flex-col">
        <SectionHeroCard
          id={embedded ? 'messages-first-card' : undefined}
          icon={MessageSquare}
          title="Messages"
          subtitle={dashboardSubtitle}
        />

        <div className="mb-4 insta-surface-card p-4">
          <button
            type="button"
            onClick={() => setMailSection(mailSection === 'templates' ? 'inbox' : 'templates')}
            className="flex w-full items-center justify-between text-left"
          >
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Communication templates
              </h2>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Access saved templates for quick replies.
              </p>
            </div>
            <ChevronDown
              className={`h-5 w-5 text-gray-500 transition-transform dark:text-gray-400 ${mailSection === 'templates' ? 'rotate-180' : ''}`}
            />
          </button>
        </div>

        {mailSection === 'templates' ? (
          <TemplateEditor
            templates={templates}
            selectedTemplateId={selectedTemplateId}
            templateDrafts={templateDrafts}
            onTemplateSelect={setSelectedTemplateId}
            onTemplateCreate={() => {
              const newId = `template-${Date.now()}`;
              setTemplates((prev) => [
                ...prev,
                { id: newId, subject: 'Untitled template', preview: '', body: '' },
              ]);
              setTemplateDrafts((prev) => ({ ...prev, [newId]: '' }));
              setSelectedTemplateId(newId);
            }}
            onTemplateSubjectChange={handleTemplateSubjectChange}
            onTemplateDraftChange={handleTemplateDraftChange}
            onTemplatesUpdate={setTemplates}
          />
        ) : (
          <div className="flex min-h-[680px] flex-1 flex-col overflow-hidden insta-surface-card">
            <div className="flex flex-1 flex-col overflow-hidden lg:flex-row">
              {/* Sidebar */}
              <ConversationList
                conversations={conversationSource}
                selectedChat={selectedChat}
                searchQuery={searchQuery}
                typeFilter={typeFilter}
                messageDisplay={messageDisplay}
                isLoading={isLoadingConversations}
                error={conversationError}
                counterpartPluralLabel={counterpartPluralLabel}
                archivedMessagesByThread={archivedMessagesByThread}
                trashMessagesByThread={trashMessagesByThread}
                onSearchChange={setSearchQuery}
                onTypeFilterChange={setTypeFilter}
                onMessageDisplayChange={setMessageDisplay}
                onConversationSelect={handleConversationSelect}
                onConversationArchive={handleArchiveConversation}
                onConversationDelete={handleDeleteConversation}
              />

              {/* Chat area */}
              <div className="flex-1 flex flex-col overflow-hidden">
                {selectedChat ? (
                  <>
                    <ChatHeader
                      isComposeView={isComposeView}
                      activeConversation={activeConversation}
                      composeRecipient={composeRecipient}
                      composeRecipientQuery={composeRecipientQuery}
                      composeSuggestions={composeSuggestions}
                      counterpartLabel={counterpartLabel}
                      bookingHrefForId={bookingHrefForId}
                      onComposeRecipientQueryChange={setComposeRecipientQuery}
                      onComposeRecipientSelect={(conv) => { setComposeRecipient(conv); setComposeRecipientQuery(''); }}
                      onComposeRecipientClear={() => { setComposeRecipient(null); setComposeRecipientQuery(''); }}
                    />

                    {/* Restore button for archived/trashed conversations */}
                    {(messageDisplay === 'archived' || messageDisplay === 'trash') && selectedChat && (
                      <div className="flex items-center justify-between px-4 py-2 bg-amber-50 border-b border-amber-200">
                        <span className="text-sm text-amber-800">
                          {messageDisplay === 'archived' ? 'Archived' : 'Trashed'} messages are read-only
                        </span>
                        <button
                          type="button"
                          onClick={() => handleRestoreConversation(selectedChat)}
                          className="insta-secondary-btn inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors"
                        >
                          <Undo2 className="h-4 w-4" />
                          Restore to Inbox
                        </button>
                      </div>
                    )}

                    {/* Messages */}
                    <div ref={messagesContainerRef} className="flex-1 overflow-y-auto overflow-x-hidden p-4 space-y-4">
                      {isComposeView && threadMessages.length === 0 && (
                        <div className="flex items-center justify-center py-12">
                          <p className="text-sm text-gray-500 dark:text-gray-400">Draft your message and choose who to send it to.</p>
                        </div>
                      )}
                      {normalizedThreadMessages.map((message) => {
                        const raw = message._raw as MessageWithAttachments | undefined;
                        const canModify = messageDisplay === 'inbox' && raw ? canModifyMessage(raw) : false;

                        const renderAttachments = (attachments: NonNullable<NormalizedMessage['attachments']>) => (
                          <div className="mt-2 flex flex-col gap-2">
                            {attachments.map((attachment) => {
                              const isImage = attachment.type.startsWith('image/') && attachment.url;
                              if (isImage) {
                                return (
                                  <div key={attachment.id} className="overflow-hidden rounded-lg bg-white/10 border border-white/20">
                                    <img
                                      src={attachment.url}
                                      alt={attachment.name ?? 'attachment'}
                                      className="max-w-[240px] rounded-md object-cover"
                                    />
                                    {attachment.name && <p className="text-xs opacity-80 mt-1 truncate px-2 pb-1">{attachment.name}</p>}
                                  </div>
                                );
                              }
                              return (
                                <div
                                  key={attachment.id}
                                  className="flex items-center gap-2 rounded-lg px-3 py-2 bg-white border border-gray-200 dark:bg-gray-600 dark:border-gray-500"
                                >
                                  <span className="text-xs truncate max-w-[12rem]" title={attachment.name}>
                                    {attachment.name || 'File'}
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        );

                        return (
                          <Fragment key={message.id}>
                            <SharedMessageBubble
                              message={message}
                              side={message.isOwn ? 'right' : 'left'}
                              canEdit={canModify && !message.isDeleted}
                              canDelete={canModify && !message.isDeleted}
                              canReact={!message.isOwn && !message.isDeleted}
                              showReadReceipt={message.isOwn}
                              onEdit={async (messageId, newContent) => {
                                const target = threadMessages.find((m) => m.id === messageId);
                                if (!target || !canModifyMessage(target)) return;
                                await editMessageMutation.mutateAsync({
                                  messageId,
                                  data: { content: newContent },
                                });
                                updateThreadMessage(messageId, (msg) => ({
                                  ...msg,
                                  text: newContent,
                                  isEdited: true,
                                  editedAt: new Date().toISOString(),
                                }));
                              }}
                              onDelete={async (messageId) => {
                                const target = threadMessages.find((m) => m.id === messageId);
                                if (!target || !canModifyMessage(target)) return;
                                await deleteMessageMutation.mutateAsync({ messageId });
                                updateThreadMessage(messageId, (msg) => ({
                                  ...msg,
                                  isDeleted: true,
                                  text: 'This message was deleted',
                                  deletedAt: new Date().toISOString(),
                                  deletedBy: currentUser?.id ?? null,
                                }));
                              }}
                              onReact={async (messageId, emoji) => {
                                if (processingReaction !== null) return;
                                await handleAddReaction(messageId, emoji);
                              }}
                              reactionBusy={processingReaction !== null}
                              quickEmojis={['👍', '❤️', '😊', '😮', '🎉']}
                              renderAttachments={message.attachments && message.attachments.length > 0 ? renderAttachments : undefined}
                            />
                          </Fragment>
                        );
                      })}
                    </div>

                    <div className="flex-shrink-0">
                      <MessageInput
                        messageText={messageText}
                        pendingAttachments={pendingAttachments}
                        isSendDisabled={isSendDisabled}
                        typingUserName={typingUserName}
                        messageDisplay={messageDisplay}
                        hasUpcomingBookings={isComposeView || activeConversation?.type === 'platform' || (activeConversation?.upcomingBookingCount ?? 0) > 0}
                        onMessageChange={handleMessageChange}
                        onKeyPress={handleKeyPress}
                        onSend={handleSend}
                        onAttachmentAdd={(files) => files && setPendingAttachments((prev) => [...prev, ...Array.from(files)])}
                        onAttachmentRemove={(index) => setPendingAttachments((prev) => prev.filter((_, i) => i !== index))}
                      />
                    </div>
                  </>
                ) : (
                  <div className="flex-1 flex items-center justify-center text-gray-500 dark:text-gray-400">
                    <div className="text-center">
                      <MessageSquare className="w-12 h-12 mx-auto mb-4 text-gray-300" />
                      <p className="text-lg font-medium">Select a conversation</p>
                      <p className="text-sm">Choose a conversation from the list to start messaging</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
  );
}

export default function MessagesPage() {
  const embedded = useEmbedded();
  const router = useRouter();
  const searchParams = useSearchParams();
  const dashboardHref = useMemo(() => {
    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.set('panel', 'messages');
    return `/instructor/dashboard?${nextParams.toString()}`;
  }, [searchParams]);

  useEffect(() => {
    if (!embedded) {
      router.replace(dashboardHref, { scroll: false });
    }
  }, [dashboardHref, embedded, router]);

  if (!embedded) {
    return null;
  }

  return <MessagesPanelContent />;
}
