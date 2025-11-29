'use client';

/**
 * Instructor Messages Page - Main Orchestrator
 *
 * Composes the messaging interface using extracted components and hooks.
 * This file should remain ~200-300 lines as the main coordinator.
 */

import { useState, useRef, useEffect, useMemo, useCallback, type KeyboardEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Bell, MessageSquare, ChevronDown } from 'lucide-react';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { useSendTypingIndicator } from '@/src/api/services/messages';
import { useAuthStatus } from '@/hooks/queries/useAuth';
import { useMessageStream } from '@/providers/UserMessageStreamProvider';

// Extracted components and hooks
import {
  type ConversationEntry,
  type MessageDisplayMode,
  type MailSection,
  type SSEMessageWithOwnership,
  COMPOSE_THREAD_ID,
} from '@/components/instructor/messages';

import {
  useConversations,
  useMessageDrafts,
  useMessageThread,
  useTemplates,
} from '@/components/instructor/messages/hooks';

import {
  ChatHeader,
  ConversationList,
  MessageBubble,
  MessageInput,
  TemplateEditor,
} from '@/components/instructor/messages/components';

export default function MessagesPage() {
  const router = useRouter();
  const { user: currentUser, isLoading: isLoadingUser } = useAuthStatus();

  // Core UI state
  const [selectedChat, setSelectedChat] = useState<string | null>(null);
  const [messageText, setMessageText] = useState('');
  const [pendingAttachments, setPendingAttachments] = useState<File[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<'all' | 'student' | 'platform'>('all');
  const [mailSection, setMailSection] = useState<MailSection>('inbox');
  const [messageDisplay, setMessageDisplay] = useState<MessageDisplayMode>('inbox');
  const [composeRecipient, setComposeRecipient] = useState<ConversationEntry | null>(null);
  const [composeRecipientQuery, setComposeRecipientQuery] = useState('');

  // Header dropdowns
  const msgRef = useRef<HTMLDivElement | null>(null);
  const notifRef = useRef<HTMLDivElement | null>(null);
  const [showMessages, setShowMessages] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);

  // Auto-scroll ref
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  // Extracted hooks
  const {
    conversations,
    setConversations,
    isLoading: isLoadingConversations,
    error: conversationError,
    totalUnread,
    unreadConversations,
  } = useConversations({ currentUserId: currentUser?.id, isLoadingUser });

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
    handleArchiveConversation,
    handleDeleteConversation,
    setThreadMessagesForDisplay,
  } = useMessageThread({
    currentUserId: currentUser?.id,
    conversations,
    setConversations,
  });

  // Derived state
  const isComposeView = selectedChat === COMPOSE_THREAD_ID;
  const activeConversation = selectedChat && !isComposeView
    ? conversations.find((conv) => conv.id === selectedChat) ?? null
    : null;
  const selectedBookingId = activeConversation?.primaryBookingId ?? '';

  // Typing indicator
  const sendTypingMutation = useSendTypingIndicator();
  const typingTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const sseTypingTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const handleTyping = useCallback(() => {
    if (!selectedBookingId) return;
    try {
      sendTypingMutation.mutate({ bookingId: selectedBookingId });
    } catch {}
  }, [selectedBookingId, sendTypingMutation]);

  // Auto-scroll to bottom
  const scrollToBottom = useCallback(() => {
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
    }
  }, []);

  // SSE connection (Phase 4: per-user inbox)
  const { subscribe } = useMessageStream();
  const [sseTypingStatus, setSseTypingStatus] = useState<{ userId: string; userName: string; until: number } | null>(null);

  // Use ref to store latest handleSSEMessage to avoid re-render loop
  const handleSSEMessageRef = useRef(handleSSEMessage);
  useEffect(() => {
    handleSSEMessageRef.current = handleSSEMessage;
  }, [handleSSEMessage]);

  // Extract SSE handlers to useCallback for stable references (fixes re-render loop)
  const handleSSEMessageWrapper = useCallback((message: { id: string; content: string; sender_id: string; sender_name: string; created_at: string; booking_id: string }, _isMine: boolean) => {
    if (!selectedChat || !activeConversation || !currentUser?.id) return;
    const sseMessage = {
      id: message.id,
      booking_id: message.booking_id,
      sender_id: message.sender_id,
      content: message.content,
      created_at: message.created_at,
      updated_at: message.created_at, // Use created_at as fallback
      is_deleted: false,
      is_mine: message.sender_id === currentUser.id,
    } as SSEMessageWithOwnership;
    handleSSEMessageRef.current(sseMessage, selectedChat, activeConversation);
  }, [selectedChat, activeConversation, currentUser?.id]);

  const handleSSETyping = useCallback((userId: string, userName: string, isTyping: boolean) => {
    if (isTyping) {
      setSseTypingStatus({ userId, userName, until: Date.now() + 3000 });
      // Clear typing after 3 seconds if no update
      if (sseTypingTimeoutRef.current) clearTimeout(sseTypingTimeoutRef.current);
      sseTypingTimeoutRef.current = setTimeout(() => setSseTypingStatus(null), 3000);
    } else {
      setSseTypingStatus(null);
    }
  }, []);

  // Subscribe to active conversation's events
  useEffect(() => {
    if (!selectedBookingId || messageDisplay !== 'inbox') {
      setSseTypingStatus(null);
      return;
    }

    const unsubscribe = subscribe(selectedBookingId, {
      onMessage: handleSSEMessageWrapper,
      onTyping: handleSSETyping,
    });

    return unsubscribe;
  }, [selectedBookingId, messageDisplay, subscribe, handleSSEMessageWrapper, handleSSETyping]);

  // Filter conversations
  const filteredConversations = useMemo(() => {
    let list = conversations.filter((conv) => {
      const matchesText = conv.name.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesType = typeFilter === 'all' || conv.type === typeFilter;
      return matchesText && matchesType;
    });

    if (messageDisplay === 'archived') {
      list = list.filter((conv) => (archivedMessagesByThread[conv.id]?.length ?? 0) > 0);
    } else if (messageDisplay === 'trash') {
      list = list.filter((conv) => (trashMessagesByThread[conv.id]?.length ?? 0) > 0);
    }

    return list;
  }, [conversations, searchQuery, typeFilter, messageDisplay, archivedMessagesByThread, trashMessagesByThread]);

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
    latestMessageAt: Date.now(),
    latestMessageId: null,
  }), [composeRecipient, currentUser?.id]);

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

  // Get primary booking ID for a thread
  const getPrimaryBookingId = useCallback((threadId: string | null) => {
    if (!threadId) return null;
    const conv = conversations.find((c) => c.id === threadId);
    return conv?.primaryBookingId ?? (conv?.bookingIds[0] ?? null);
  }, [conversations]);

  // Close dropdowns on outside click
  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (msgRef.current?.contains(target) || notifRef.current?.contains(target)) return;
      setShowMessages(false);
      setShowNotifications(false);
    };
    document.addEventListener('click', onDocClick);
    return () => document.removeEventListener('click', onDocClick);
  }, []);

  // Auto-select first conversation
  useEffect(() => {
    if (mailSection !== 'inbox' || selectedChat || filteredConversations.length === 0) return;
    setSelectedChat(filteredConversations[0]?.id ?? null);
  }, [filteredConversations, selectedChat, mailSection]);

  // Load messages when conversation selected
  useEffect(() => {
    if (selectedChat && selectedChat !== COMPOSE_THREAD_ID && activeConversation) {
      loadThreadMessages(selectedChat, activeConversation, messageDisplay);
    }
  }, [selectedChat, activeConversation, messageDisplay, loadThreadMessages]);

  // Update thread messages on display mode change
  useEffect(() => {
    if (selectedChat && selectedChat !== COMPOSE_THREAD_ID) {
      setThreadMessagesForDisplay(selectedChat, messageDisplay);
    }
  }, [messageDisplay, selectedChat, setThreadMessagesForDisplay]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom();
  }, [threadMessages.length, scrollToBottom]);

  // Load draft when switching conversations
  useEffect(() => {
    const draftValue = draftsByThread[getDraftKey(selectedChat)] ?? '';
    if (draftValue !== messageText) {
      setMessageText(draftValue);
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
    if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    typingTimeoutRef.current = setTimeout(() => handleTyping(), 300);
  }, [selectedChat, updateDraft, handleTyping]);

  const handleSend = useCallback(async () => {
    // Cancel typing indicator
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
      typingTimeoutRef.current = null;
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
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Header */}
      <header className="bg-white backdrop-blur-sm border-b border-gray-200 px-4 sm:px-6 py-4 flex-shrink-0">
        <div className="flex items-center justify-between max-w-full">
          <div className="flex items-center gap-4">
            <Link href="/instructor/dashboard" className="inline-block">
              <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-0 sm:pl-4">
                iNSTAiNSTRU
              </h1>
            </Link>
          </div>
          <div className="flex items-center gap-2 pr-0 sm:pr-4">
            {/* Messages dropdown */}
            <div className="relative" ref={msgRef}>
              <button
                type="button"
                onClick={() => { setShowMessages((v) => !v); setShowNotifications(false); }}
                className="group relative inline-flex items-center justify-center w-10 h-10 rounded-full text-[#7E22CE] transition-colors"
                title="Messages"
              >
                <MessageSquare className="w-6 h-6 transition-colors group-hover:fill-current" style={{ fill: showMessages ? 'currentColor' : undefined }} />
                {totalUnread > 0 && (
                  <span className="pointer-events-none absolute -top-0.5 -right-0.5 inline-flex min-w-[1.2rem] h-5 items-center justify-center rounded-full bg-[#7E22CE] px-1 text-[0.65rem] font-semibold text-white">
                    {totalUnread > 9 ? '9+' : totalUnread}
                  </span>
                )}
              </button>
              {showMessages && (
                <div className="absolute right-0 mt-2 w-80 bg-white border border-gray-200 rounded-lg shadow-lg z-50">
                  <ul className="max-h-80 overflow-auto p-2 space-y-2">
                    {unreadConversations.length === 0 ? (
                      <>
                        <li className="px-2 py-2 text-sm text-gray-600">No unread messages.</li>
                        <li>
                          <button type="button" className="w-full text-left text-sm text-gray-700 px-2 py-2 hover:bg-gray-50 rounded" onClick={() => setShowMessages(false)}>
                            Open inbox
                          </button>
                        </li>
                      </>
                    ) : (
                      unreadConversations.map((conv) => (
                        <li key={conv.id}>
                          <button type="button" onClick={() => { setShowMessages(false); handleConversationSelect(conv.id); }} className="w-full rounded-lg px-3 py-2 text-left hover:bg-gray-50">
                            <p className="text-sm font-medium text-gray-900 truncate">{conv.name}</p>
                            <p className="text-xs text-gray-500 truncate">{conv.lastMessage || 'New message'}</p>
                          </button>
                        </li>
                      ))
                    )}
                  </ul>
                </div>
              )}
            </div>
            {/* Notifications dropdown */}
            <div className="relative" ref={notifRef}>
              <button
                type="button"
                onClick={() => { setShowNotifications((v) => !v); setShowMessages(false); }}
                className="group inline-flex items-center justify-center w-10 h-10 rounded-full text-[#7E22CE] transition-colors"
                title="Notifications"
              >
                <Bell className="w-6 h-6 transition-colors group-hover:fill-current" style={{ fill: showNotifications ? 'currentColor' : undefined }} />
              </button>
              {showNotifications && (
                <div className="absolute right-0 mt-2 w-80 bg-white border border-gray-200 rounded-lg shadow-lg z-50">
                  <ul className="max-h-80 overflow-auto p-2 space-y-2">
                    <li className="text-sm text-gray-600 px-2 py-2">No alerts right now.</li>
                    <li>
                      <button type="button" className="w-full text-left text-sm text-gray-700 px-2 py-2 hover:bg-gray-50 rounded" onClick={() => { setShowNotifications(false); router.push('/instructor/settings'); }}>
                        Notification settings
                      </button>
                    </li>
                  </ul>
                </div>
              )}
            </div>
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-hidden">
        <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl h-full flex flex-col">
        {/* Mobile back */}
        <Link href="/instructor/dashboard" className="inline-flex items-center gap-1 text-[#7E22CE] mb-4 sm:hidden">
          <ArrowLeft className="w-4 h-4" />
          <span>Back to dashboard</span>
        </Link>

        {/* Title card */}
        <div className="bg-white rounded-lg p-6 mb-6 border border-gray-200">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
              <MessageSquare className="w-6 h-6 text-[#7E22CE]" />
            </div>
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold text-gray-800">Messages</h1>
              <p className="text-sm text-gray-600">Communicate with students and platform</p>
            </div>
          </div>
        </div>

        {/* Templates toggle */}
        <div className="bg-white rounded-lg border border-gray-200 p-4 mb-4">
          <button
            type="button"
            onClick={() => setMailSection(mailSection === 'templates' ? 'inbox' : 'templates')}
            className="w-full flex items-center justify-between text-left"
          >
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Communication templates</h2>
              <p className="text-xs text-gray-500">Access saved templates for quick replies.</p>
            </div>
            <ChevronDown className={`w-5 h-5 text-gray-500 transition-transform ${mailSection === 'templates' ? 'rotate-180' : ''}`} />
          </button>
        </div>

        {/* Main content */}
        {mailSection === 'templates' ? (
          <TemplateEditor
            templates={templates}
            selectedTemplateId={selectedTemplateId}
            templateDrafts={templateDrafts}
            onTemplateSelect={setSelectedTemplateId}
            onTemplateCreate={() => {
              const newId = `template-${Date.now()}`;
              setTemplates((prev) => [...prev, { id: newId, subject: 'Untitled template', preview: '', body: '' }]);
              setTemplateDrafts((prev) => ({ ...prev, [newId]: '' }));
              setSelectedTemplateId(newId);
            }}
            onTemplateSubjectChange={handleTemplateSubjectChange}
            onTemplateDraftChange={handleTemplateDraftChange}
            onTemplatesUpdate={setTemplates}
          />
        ) : (
          <div className="flex-1 bg-white rounded-lg border border-gray-200 overflow-hidden flex flex-col">
            <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
              {/* Sidebar */}
              <ConversationList
                conversations={conversationSource}
                selectedChat={selectedChat}
                searchQuery={searchQuery}
                typeFilter={typeFilter}
                messageDisplay={messageDisplay}
                isLoading={isLoadingConversations}
                error={conversationError}
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
                      onComposeRecipientQueryChange={setComposeRecipientQuery}
                      onComposeRecipientSelect={(conv) => { setComposeRecipient(conv); setComposeRecipientQuery(''); }}
                      onComposeRecipientClear={() => { setComposeRecipient(null); setComposeRecipientQuery(''); }}
                    />

                    {/* Messages */}
                    <div ref={messagesContainerRef} className="flex-1 overflow-y-auto p-4 space-y-4">
                      {isComposeView && threadMessages.length === 0 && (
                        <div className="flex items-center justify-center py-12">
                          <p className="text-sm text-gray-500">Draft your message and choose who to send it to.</p>
                        </div>
                      )}
                      {threadMessages.map((message, index) => (
                        <MessageBubble
                          key={message.id}
                          message={message}
                          isLastInstructor={message.sender === 'instructor' && index === threadMessages.length - 1}
                        />
                      ))}
                    </div>

                    <div className="flex-shrink-0">
                      <MessageInput
                        messageText={messageText}
                        pendingAttachments={pendingAttachments}
                        isSendDisabled={isSendDisabled}
                        typingUserName={typingUserName}
                        messageDisplay={messageDisplay}
                        onMessageChange={handleMessageChange}
                        onKeyPress={handleKeyPress}
                        onSend={handleSend}
                        onAttachmentAdd={(files) => files && setPendingAttachments((prev) => [...prev, ...Array.from(files)])}
                        onAttachmentRemove={(index) => setPendingAttachments((prev) => prev.filter((_, i) => i !== index))}
                      />
                    </div>
                  </>
                ) : (
                  <div className="flex-1 flex items-center justify-center text-gray-500">
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
      </div>
    </div>
  );
}
