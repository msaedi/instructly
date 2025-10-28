'use client';

import { useState, useRef, useEffect, type KeyboardEvent } from 'react';
import Link from 'next/link';
import { ArrowLeft, MessageSquare, Send, MoreVertical, Search, Bell, Inbox, FileText, Pencil } from 'lucide-react';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { getHistory, markRead, sendMessage, type MessageItem } from '@/features/shared/api/messages';

const MOCK_THREADS: Record<string, MessageItem[]> = {
  '1': [
    { id: 'm1', text: 'Hi! I have a question about the assignment', sender: 'student', timestamp: '2 hours ago' },
    { id: 'm2', text: 'Of course! What would you like to know?', sender: 'instructor', timestamp: '2 hours ago' },
    { id: 'm3', text: 'Thank you for the great lesson!', sender: 'student', timestamp: '2 hours ago' },
  ],
  '2': [
    { id: 'm1', text: 'Can we schedule another session?', sender: 'student', timestamp: '1 day ago' },
    { id: 'm2', text: 'Absolutely! I have availability next week', sender: 'instructor', timestamp: '1 day ago' },
  ],
  '3': [
    { id: 'm1', text: 'Your payment has been processed successfully', sender: 'platform', timestamp: '3 days ago' },
    { id: 'm2', text: 'You earned $45 from your last lesson', sender: 'platform', timestamp: '3 days ago' },
  ],
  '4': [
    { id: 'm1', text: 'The homework was really helpful', sender: 'student', timestamp: '1 week ago' },
  ],
};

export default function MessagesPage() {
  const [selectedChat, setSelectedChat] = useState<string | null>(null);
  const [messageText, setMessageText] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<'all' | 'student' | 'platform'>('all');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [mailSection, setMailSection] = useState<'inbox' | 'compose' | 'sent' | 'drafts' | 'templates'>('inbox');
  // Header dropdowns to match dashboard behavior
  const msgRef = useRef<HTMLDivElement | null>(null);
  const notifRef = useRef<HTMLDivElement | null>(null);
  const [showMessages, setShowMessages] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (msgRef.current && msgRef.current.contains(target)) return;
      if (notifRef.current && notifRef.current.contains(target)) return;
      setShowMessages(false);
      setShowNotifications(false);
    };
    document.addEventListener('click', onDocClick);
    return () => document.removeEventListener('click', onDocClick);
  }, []);

  // Mock data for conversations (initial load)
  const initialConversations = [
    {
      id: '1',
      name: 'Sarah Johnson',
      lastMessage: 'Thank you for the great lesson!',
      timestamp: '2 hours ago',
      unread: 2,
      avatar: 'SJ',
      type: 'student',
      bookingIds: ['BKG-1A2B3C', 'BKG-9XY7Z1']
    },
    {
      id: '2',
      name: 'Mike Chen',
      lastMessage: 'Can we schedule another session?',
      timestamp: '1 day ago',
      unread: 0,
      avatar: 'MC',
      type: 'student',
      bookingIds: ['BKG-77HH42']
    },
    {
      id: '3',
      name: 'iNSTAiNSTRU Platform',
      lastMessage: 'Your payment has been processed successfully',
      timestamp: '3 days ago',
      unread: 1,
      avatar: 'IP',
      type: 'platform',
      bookingIds: []
    },
    {
      id: '4',
      name: 'Emma Wilson',
      lastMessage: 'The homework was really helpful',
      timestamp: '1 week ago',
      unread: 0,
      avatar: 'EW',
      type: 'student',
      bookingIds: ['BKG-ABCD12']
    }
  ];

  const [threadMessages, setThreadMessages] = useState<MessageItem[]>([]);
  const [messagesByThread, setMessagesByThread] = useState<Record<string, MessageItem[]>>({});
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
  const [conversations, setConversations] = useState(initialConversations);

  // Fallback mock threads for demo IDs (used when API returns no history)
  const filteredConversations = conversations.filter((conv) => {
    const matchesText = conv.name.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType = typeFilter === 'all' ? true : conv.type === typeFilter;
    return matchesText && matchesType;
  });

  // Auto-select the first conversation when none selected and in inbox view
  useEffect(() => {
    if (mailSection !== 'inbox' || selectedChat || filteredConversations.length === 0) return;
    const firstConversation = filteredConversations[0];
    if (firstConversation) {
      setSelectedChat(firstConversation.id);
    }
  }, [filteredConversations, selectedChat, mailSection]);

  const handleSendMessage = async () => {
    if (!messageText.trim() || !selectedChat) return;
    const optimistic: MessageItem = {
      id: `local-${Date.now()}`,
      text: messageText.trim(),
      sender: 'instructor',
      timestamp: 'Just now',
    };
    setThreadMessages((prev) => [...prev, optimistic]);
    setMessagesByThread((prev) => ({
      ...prev,
      [selectedChat]: [...(prev[selectedChat] || []), optimistic],
    }));
    // Update conversation preview
    setConversations((prev) => prev.map((c) => (c.id === selectedChat ? { ...c, lastMessage: optimistic.text, timestamp: 'Just now', unread: 0 } : c)));
    setMessageText('');
    const res = await sendMessage(selectedChat, optimistic.text);
    if (res?.id) {
      setThreadMessages((prev) => prev.map((m) => (m.id === optimistic.id ? { ...m, id: res.id } : m)));
      setMessagesByThread((prev) => ({
        ...prev,
        [selectedChat]: (prev[selectedChat] || []).map((m) => (m.id === optimistic.id ? { ...m, id: res.id } : m)),
      }));
    }
  };

  const handleKeyPress = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSendMessage();
    }
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [threadMessages, selectedChat]);

  // Load history when a chat is selected
  useEffect(() => {
    (async () => {
      if (!selectedChat) return;
      // Ensure we are not in compose mode when a chat is chosen
      if (mailSection !== 'inbox') setMailSection('inbox');
      try {
        // Use cache if available
        if (messagesByThread[selectedChat]) {
          setThreadMessages(messagesByThread[selectedChat]);
        } else {
          const msgs = await getHistory(selectedChat);
          const finalMsgs = msgs.length > 0 ? msgs : (MOCK_THREADS[selectedChat] || []);
          setThreadMessages(finalMsgs);
          setMessagesByThread((prev) => ({ ...prev, [selectedChat]: finalMsgs }));
        }
        void markRead(selectedChat);
      } catch {
        const finalMsgs = MOCK_THREADS[selectedChat] || [];
        setThreadMessages(finalMsgs);
        setMessagesByThread((prev) => ({ ...prev, [selectedChat]: finalMsgs }));
      }
    })();
  }, [selectedChat, mailSection, messagesByThread]);

  return (
    <div className="min-h-screen">
      {/* Header - match dashboard */}
      <header className="bg-white backdrop-blur-sm border-b border-gray-200 px-4 sm:px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
          <div className="flex items-center gap-4">
            <Link href="/instructor/dashboard" className="inline-block">
              <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-0 sm:pl-4">iNSTAiNSTRU</h1>
            </Link>
          </div>
          <div className="flex items-center gap-2 pr-0 sm:pr-4">
            <div className="relative" ref={msgRef}>
              <button
                type="button"
                onClick={() => { setShowMessages((v) => !v); setShowNotifications(false); }}
                aria-expanded={showMessages}
                aria-haspopup="menu"
                className={`group inline-flex items-center justify-center w-10 h-10 rounded-full text-[#7E22CE] transition-colors duration-150 focus:outline-none select-none`}
                title="Messages"
              >
                <MessageSquare className="w-6 h-6 transition-colors group-hover:fill-current" style={{ fill: showMessages ? 'currentColor' : undefined }} />
              </button>
              {showMessages && (
                <div role="menu" className="absolute right-0 mt-2 w-80 bg-white border border-gray-200 rounded-lg shadow-lg z-50">
                  <div className="p-3 border-b border-gray-100">
                    <p className="text-sm font-medium text-gray-900">Messages</p>
                  </div>
                  <ul className="max-h-80 overflow-auto p-2 space-y-2">
                    <li>
                      <button className="w-full text-left text-sm text-gray-700 px-2 py-2 hover:bg-gray-50 rounded" onClick={() => setShowMessages(false)}>
                        No new messages
                      </button>
                    </li>
                  </ul>
                </div>
              )}
            </div>
            <div className="relative" ref={notifRef}>
              <button
                type="button"
                onClick={() => { setShowNotifications((v) => !v); setShowMessages(false); }}
                aria-expanded={showNotifications}
                aria-haspopup="menu"
                className={`group inline-flex items-center justify-center w-10 h-10 rounded-full text-[#7E22CE] transition-colors duration-150 focus:outline-none select-none`}
                title="Notifications"
              >
                <Bell className="w-6 h-6 transition-colors group-hover:fill-current" style={{ fill: showNotifications ? 'currentColor' : undefined }} />
              </button>
              {showNotifications && (
                <div role="menu" className="absolute right-0 mt-2 w-80 bg-white border border-gray-200 rounded-lg shadow-lg z-50">
                  <div className="p-3 border-b border-gray-100">
                    <p className="text-sm font-medium text-gray-900">Notifications</p>
                  </div>
                  <ul className="max-h-80 overflow-auto p-2 space-y-2">
                    <li className="text-sm text-gray-600 px-2 py-2">No new notifications</li>
                  </ul>
                </div>
              )}
            </div>
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        {/* Mobile back arrow */}
        <Link href="/instructor/dashboard" className="inline-flex items-center gap-1 text-[#7E22CE] mb-4 sm:hidden">
          <ArrowLeft className="w-4 h-4" />
          <span>Back to dashboard</span>
        </Link>

        {/* Title card */}
        <div className="bg-white rounded-lg p-6 mb-6 border border-gray-200">
          <div className="flex items-center justify-between">
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
        </div>

        {/* Mail controls card */}
        <div className="bg-white rounded-lg border border-gray-200 p-4 mb-4">
          <div className="flex items-center justify-between">
            <div role="tablist" aria-label="Mail folders" className="flex items-center gap-2">
              <button
                type="button"
                role="tab"
                aria-selected={mailSection === 'inbox'}
                onClick={() => setMailSection('inbox')}
                className={`inline-flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${mailSection === 'inbox' ? 'bg-purple-50 text-[#7E22CE] border border-purple-200' : 'text-gray-700 hover:bg-gray-50 border border-transparent'}`}
                title="Inbox"
              >
                <Inbox className="w-4 h-4" />
                <span>Inbox</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mailSection === 'sent'}
                onClick={() => setMailSection('sent')}
                className={`inline-flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${mailSection === 'sent' ? 'bg-purple-50 text-[#7E22CE] border border-purple-200' : 'text-gray-700 hover:bg-gray-50 border border-transparent'}`}
                title="Sent"
              >
                <Send className="w-4 h-4" />
                <span>Sent</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mailSection === 'drafts'}
                onClick={() => setMailSection('drafts')}
                className={`inline-flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${mailSection === 'drafts' ? 'bg-purple-50 text-[#7E22CE] border border-purple-200' : 'text-gray-700 hover:bg-gray-50 border border-transparent'}`}
                title="Drafts"
              >
                <FileText className="w-4 h-4" />
                <span>Drafts</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mailSection === 'templates'}
                onClick={() => setMailSection('templates')}
                className={`inline-flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${mailSection === 'templates' ? 'bg-purple-50 text-[#7E22CE] border border-purple-200' : 'text-gray-700 hover:bg-gray-50 border border-transparent'}`}
                title="Templates"
              >
                <FileText className="w-4 h-4" />
                <span>Templates</span>
              </button>
            </div>
            <div>
              <button
                type="button"
                onClick={() => setMailSection('compose')}
                className="inline-flex items-center gap-2 rounded-full bg-[#7E22CE] text-white px-4 py-2 text-sm font-semibold transition hover:bg-[#6b1fb8] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE] focus-visible:ring-offset-2"
                title="Compose"
              >
                <Pencil className="w-4 h-4" />
                <span>Compose</span>
              </button>
            </div>
          </div>
        </div>

        {/* Messages interface */}
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="flex h-[600px]">
            {/* Conversations list */}
            <div className="w-full md:w-1/3 border-r border-gray-200 flex flex-col">
              {/* Search bar */}
              <div className="p-4 border-b border-gray-200">
                {/* Search row */}
                <div className="mb-3 flex items-center gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                      type="text"
                      placeholder="Search conversations..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => setMailSection('compose')}
                    aria-label="Start a new conversation"
                    title="Start a new conversation"
                    className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-white border border-gray-200 text-[#7E22CE] hover:bg-purple-50"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                </div>
                {/* Filter row */}
                <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setTypeFilter('all')}
                    className={`min-w-[80px] text-center px-2.5 py-1.5 rounded-md text-sm font-medium transition-colors border ${
                        typeFilter === 'all' ? 'bg-purple-50 text-[#7E22CE] border-purple-200' : 'text-gray-700 hover:bg-gray-50 border-gray-200'
                      }`}
                    >
                      All
                    </button>
                    <button
                      type="button"
                      onClick={() => setTypeFilter('student')}
                    className={`min-w-[80px] text-center px-2.5 py-1.5 rounded-md text-sm font-medium transition-colors border ${
                        typeFilter === 'student' ? 'bg-purple-50 text-[#7E22CE] border-purple-200' : 'text-gray-700 hover:bg-gray-50 border-gray-200'
                      }`}
                    >
                      Students
                    </button>
                    <button
                      type="button"
                      onClick={() => setTypeFilter('platform')}
                    className={`min-w-[80px] text-center px-2.5 py-1.5 rounded-md text-sm font-medium transition-colors border ${
                        typeFilter === 'platform' ? 'bg-purple-50 text-[#7E22CE] border-purple-200' : 'text-gray-700 hover:bg-gray-50 border-gray-200'
                      }`}
                    >
                      Platform
                    </button>
                </div>
              </div>

              {/* Conversations (single list) */}
              <div className="flex-1 overflow-y-auto">
                {filteredConversations.map((conversation) => (
                  <div
                    key={conversation.id}
                    onClick={() => {
                      setMailSection('inbox');
                      setSelectedChat(conversation.id);
                      setShowMessages(false);
                      setConversations((prev) => prev.map((c) => (c.id === conversation.id ? { ...c, unread: 0 } : c)));
                    }}
                    className={`pl-5 pr-4 py-4 border-b border-gray-100 cursor-pointer hover:bg-gray-50 transition-colors ${
                      selectedChat === conversation.id ? 'bg-purple-50 border-l-4 border-l-[#7E22CE]' : ''
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`relative w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium ${
                        conversation.type === 'platform'
                          ? 'bg-blue-100 text-blue-600'
                          : 'bg-purple-100 text-purple-600'
                      }`}>
                        {conversation.avatar}
                        {conversation.unread > 0 && (
                          <span className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-3.5 w-2 h-2 rounded-full bg-[#7E22CE]" aria-hidden="true" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <h3 className="font-medium text-gray-900 truncate">{conversation.name}</h3>
                          <span className="text-xs text-gray-500 whitespace-nowrap flex-shrink-0">{conversation.timestamp}</span>
                        </div>
                        <p className="text-sm text-gray-600 truncate mt-1">{conversation.lastMessage}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Chat area */}
            <div className="flex-1 flex flex-col">
              {mailSection === 'compose' ? (
                <div className="flex-1 p-6">
                  <div className="max-w-2xl mx-auto">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">New message</h3>
                    <div className="space-y-3">
                      <input type="text" placeholder="To: name@example.com" className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500" />
                      <input type="text" placeholder="Subject" className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500" />
                      <textarea placeholder="Write your message..." rows={8} className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500" />
                      <div className="flex items-center justify-end gap-2">
                        <button type="button" className="px-4 py-2 rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50">Save draft</button>
                        <button type="button" className="px-4 py-2 rounded-md bg-[#7E22CE] text-white hover:bg-[#6b1fb8]">Send</button>
                      </div>
                    </div>
                  </div>
                </div>
              ) : selectedChat ? (
                <>
                  {/* Chat header */}
                  <div className="p-4 border-b border-gray-200 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                        conversations.find(c => c.id === selectedChat)?.type === 'platform'
                          ? 'bg-blue-100 text-blue-600'
                          : 'bg-purple-100 text-purple-600'
                      }`}>
                        {conversations.find(c => c.id === selectedChat)?.avatar}
                      </div>
                      <div>
                        <h3 className="font-medium text-gray-900">
                          {conversations.find(c => c.id === selectedChat)?.name}
                        </h3>
                        <p className="text-xs text-gray-500">
                          {conversations.find(c => c.id === selectedChat)?.type === 'platform' ? 'Platform' : 'Student'}
                        </p>
                      </div>
                    </div>
                    <div className="relative" ref={threadMenuRef}>
                      <button className="p-2 hover:bg-gray-100 rounded-lg transition-colors" onClick={() => setShowThreadMenu((v) => !v)} aria-expanded={showThreadMenu} aria-haspopup="menu">
                        <MoreVertical className="w-4 h-4 text-gray-500" />
                      </button>
                      {showThreadMenu && (
                        <div role="menu" className="absolute right-0 mt-2 w-56 bg-white border border-gray-200 rounded-lg shadow-lg z-40">
                          <div className="p-3 border-b border-gray-100">
                            <p className="text-sm font-medium text-gray-900">Booking IDs</p>
                          </div>
                          <ul className="max-h-60 overflow-auto p-2 space-y-1 text-sm">
                            {(conversations.find(c => c.id === selectedChat)?.bookingIds || []).length === 0 ? (
                              <li className="text-gray-500 px-2 py-1">No bookings</li>
                            ) : (
                              (conversations.find(c => c.id === selectedChat)?.bookingIds || []).map((bid) => (
                                <li key={bid} className="px-2 py-1 text-gray-800 hover:bg-gray-50 rounded">{bid}</li>
                              ))
                            )}
                          </ul>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Messages */}
                  <div className="flex-1 overflow-y-auto p-4 space-y-4">
                    {threadMessages.map((message) => (
                      <div
                        key={message.id}
                        className={`flex ${message.sender === 'instructor' ? 'justify-end' : 'justify-start'}`}
                      >
                        <div
                          className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
                            message.sender === 'instructor'
                              ? 'bg-[#7E22CE] text-white'
                              : message.sender === 'platform'
                              ? 'bg-blue-100 text-blue-800'
                              : 'bg-gray-100 text-gray-800'
                          }`}
                        >
                          <p className="text-sm">{message.text}</p>
                          <p className="text-xs opacity-70 mt-1">{message.timestamp}</p>
                        </div>
                      </div>
                    ))}
                    <div ref={messagesEndRef} />
                  </div>

                  {/* Message input */}
                  <div className="p-4 border-t border-gray-200">
                    <div className="flex items-center gap-2">
                      <textarea
                        value={messageText}
                        onChange={(e) => setMessageText(e.target.value)}
                        onKeyPress={handleKeyPress}
                        placeholder="Type your message..."
                        className="flex-1 resize-none border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500"
                        rows={2}
                      />
                      <button
                        onClick={handleSendMessage}
                        disabled={!messageText.trim()}
                        className="p-2 bg-[#7E22CE] text-white rounded-lg hover:bg-[#5f1aa4] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        <Send className="w-4 h-4" />
                      </button>
                    </div>
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
      </div>
    </div>
  );
}
