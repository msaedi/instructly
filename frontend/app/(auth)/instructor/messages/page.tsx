'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import { ArrowLeft, MessageSquare, Send, MoreVertical, Search } from 'lucide-react';

export default function MessagesPage() {
  const [selectedChat, setSelectedChat] = useState<string | null>(null);
  const [messageText, setMessageText] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Mock data for conversations
  const conversations = [
    {
      id: '1',
      name: 'Sarah Johnson',
      lastMessage: 'Thank you for the great lesson!',
      timestamp: '2 hours ago',
      unread: 2,
      avatar: 'SJ',
      type: 'student'
    },
    {
      id: '2',
      name: 'Mike Chen',
      lastMessage: 'Can we schedule another session?',
      timestamp: '1 day ago',
      unread: 0,
      avatar: 'MC',
      type: 'student'
    },
    {
      id: '3',
      name: 'iNSTAiNSTRU Platform',
      lastMessage: 'Your payment has been processed successfully',
      timestamp: '3 days ago',
      unread: 1,
      avatar: 'IP',
      type: 'platform'
    },
    {
      id: '4',
      name: 'Emma Wilson',
      lastMessage: 'The homework was really helpful',
      timestamp: '1 week ago',
      unread: 0,
      avatar: 'EW',
      type: 'student'
    }
  ];

  // Mock messages for selected chat
  const getMessages = (chatId: string) => {
    const mockMessages = {
      '1': [
        { id: '1', text: 'Hi! I have a question about the assignment', sender: 'student', timestamp: '2 hours ago' },
        { id: '2', text: 'Of course! What would you like to know?', sender: 'instructor', timestamp: '2 hours ago' },
        { id: '3', text: 'Thank you for the great lesson!', sender: 'student', timestamp: '2 hours ago' }
      ],
      '2': [
        { id: '1', text: 'Can we schedule another session?', sender: 'student', timestamp: '1 day ago' },
        { id: '2', text: 'Absolutely! I have availability next week', sender: 'instructor', timestamp: '1 day ago' }
      ],
      '3': [
        { id: '1', text: 'Your payment has been processed successfully', sender: 'platform', timestamp: '3 days ago' },
        { id: '2', text: 'You earned $45 from your last lesson', sender: 'platform', timestamp: '3 days ago' }
      ],
      '4': [
        { id: '1', text: 'The homework was really helpful', sender: 'student', timestamp: '1 week ago' }
      ]
    };
    return mockMessages[chatId as keyof typeof mockMessages] || [];
  };

  const filteredConversations = conversations.filter(conv =>
    conv.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleSendMessage = () => {
    if (messageText.trim() && selectedChat) {
      // In a real app, this would send the message to the backend
      setMessageText('');
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [selectedChat]);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="container mx-auto px-8 lg:px-32 max-w-6xl">
          <div className="flex items-center justify-between py-4">
            <div className="flex items-center gap-4">
              <Link href="/instructor/dashboard" className="inline-flex items-center gap-1 text-[#7E22CE] hover:text-[#5f1aa4] transition-colors">
                <ArrowLeft className="w-4 h-4" />
                <span className="hidden sm:inline">Back to dashboard</span>
              </Link>
            </div>
            <div className="flex items-center gap-4">
              <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center">
                <span className="text-sm font-medium text-gray-600">IP</span>
              </div>
            </div>
          </div>
        </div>
      </div>

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

        {/* Messages interface */}
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="flex h-[600px]">
            {/* Conversations list */}
            <div className="w-full md:w-1/3 border-r border-gray-200 flex flex-col">
              {/* Search bar */}
              <div className="p-4 border-b border-gray-200">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search conversations..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500"
                  />
                </div>
              </div>

              {/* Conversations */}
              <div className="flex-1 overflow-y-auto">
                {filteredConversations.map((conversation) => (
                  <div
                    key={conversation.id}
                    onClick={() => setSelectedChat(conversation.id)}
                    className={`p-4 border-b border-gray-100 cursor-pointer hover:bg-gray-50 transition-colors ${
                      selectedChat === conversation.id ? 'bg-purple-50 border-l-4 border-l-[#7E22CE]' : ''
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium ${
                        conversation.type === 'platform'
                          ? 'bg-blue-100 text-blue-600'
                          : 'bg-purple-100 text-purple-600'
                      }`}>
                        {conversation.avatar}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <h3 className="font-medium text-gray-900 truncate">{conversation.name}</h3>
                          <span className="text-xs text-gray-500">{conversation.timestamp}</span>
                        </div>
                        <p className="text-sm text-gray-600 truncate mt-1">{conversation.lastMessage}</p>
                      </div>
                      {conversation.unread > 0 && (
                        <div className="w-5 h-5 bg-[#7E22CE] text-white text-xs rounded-full flex items-center justify-center">
                          {conversation.unread}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Chat area */}
            <div className="flex-1 flex flex-col">
              {selectedChat ? (
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
                    <button className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
                      <MoreVertical className="w-4 h-4 text-gray-500" />
                    </button>
                  </div>

                  {/* Messages */}
                  <div className="flex-1 overflow-y-auto p-4 space-y-4">
                    {getMessages(selectedChat).map((message) => (
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
