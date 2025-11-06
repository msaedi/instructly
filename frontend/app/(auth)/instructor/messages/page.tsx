'use client';

import { useState, useRef, useEffect, useMemo, useCallback, type KeyboardEvent, type MouseEvent as ReactMouseEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft,
  MessageSquare,
  Send,
  MoreVertical,
  Search,
  Bell,
  Plus,
  X,
  Paperclip,
  Pencil,
  ChevronDown,
  Copy,
  Sparkles,
  Archive,
  Trash2,
} from 'lucide-react';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { markRead, sendMessage, type MessageItem } from '@/features/shared/api/messages';
import { bookingsApi } from '@/lib/api/bookings';
import { formatDistanceToNow, format as formatDate } from 'date-fns';
import { logger } from '@/lib/logger';
import { messageService, type Message as MessageResponse } from '@/services/messageService';
import { useAuthStatus } from '@/hooks/queries/useAuth';
import type { Booking } from '@/features/shared/api/types';

type MessageAttachment = {
  name: string;
  type: string;
  dataUrl: string;
};

type MessageDelivery =
  | { status: 'sending' }
  | { status: 'delivered'; timeLabel: string }
  | { status: 'read'; timeLabel: string };

type MessageWithAttachments = MessageItem & {
  attachments?: MessageAttachment[];
  delivery?: MessageDelivery;
  createdAt?: string;
  senderId?: string;
  isArchived?: boolean;
  isTrashed?: boolean;
};

const COMPOSE_THREAD_ID = '__compose__';
const DRAFT_COOKIE_NAME = 'instructor_message_drafts';
const TEMPLATE_COOKIE_NAME = 'instructor_message_templates';
const HISTORY_RETRY_DELAY_MS = 10_000;
const ARCHIVED_LABEL = 'All messages archived';
const TRASH_LABEL = 'All messages trashed';

const FILTER_OPTIONS: Array<{ label: string; value: 'all' | 'student' | 'platform' }> = [
  { label: 'All', value: 'all' },
  { label: 'Students', value: 'student' },
  { label: 'Platform', value: 'platform' },
];

type ConversationEntry = {
  id: string;
  name: string;
  lastMessage: string;
  timestamp: string;
  unread: number;
  avatar: string;
  type: 'student' | 'platform';
  bookingIds: string[];
  primaryBookingId: string | null;
  studentId: string | null;
  instructorId: string | null;
  latestMessageAt: number;
  latestMessageId?: string | null;
};

type TemplateItem = {
  id: string;
  subject: string;
  preview: string;
  body: string;
};

type ThreadHistoryMeta = {
  status: 'idle' | 'loading' | 'success' | 'error';
  lastMessageId: string | null;
  timestamp: number;
};

const DEFAULT_TEMPLATES: TemplateItem[] = [
  {
    id: 'welcome',
    subject: 'Welcome to iNSTAiNSTRU',
    preview: 'Thanks for reaching out! Excited to work together…',
    body: `Hi there,

Thanks for reaching out! I'm excited to work with you on your learning goals. Let me know a few dates/times that work for a first session and we can get it on the calendar.

Talk soon,
[Your name]`,
  },
  {
    id: 'availability',
    subject: 'Scheduling your next lesson',
    preview: 'Here are a few time slots I currently have open…',
    body: `Hi there,

Here are a few time slots I currently have open:
- Monday 5:00 PM
- Wednesday 6:30 PM
- Saturday 11:00 AM

Let me know which works best and I’ll send over the booking link.

Best,
[Your name]`,
  },
  {
    id: 'homework',
    subject: 'Lesson recap & practice plan',
    preview: 'Here’s what to focus on before our next session…',
    body: `Hi there,

Great work today! Here’s what to focus on before our next session:
1. Review the technique we covered for 15 minutes each day.
2. Complete exercise set B in the practice booklet.
3. Jot down any questions so we can tackle them together.

See you next time,
[Your name]`,
  },
];

const getDefaultTemplates = (): TemplateItem[] =>
  DEFAULT_TEMPLATES.map((template) => ({ ...template }));

const MOCK_THREADS: Record<string, MessageWithAttachments[]> = {};

const formatRelativeTime = (input: string | Date | null | undefined): string => {
  if (!input) return '';
  const date = typeof input === 'string' ? new Date(input) : input;
  if (Number.isNaN(date.getTime())) return '';
  return formatDistanceToNow(date, { addSuffix: true });
};

const formatTimeLabel = (input: string | Date | null | undefined): string => {
  if (!input) return '';
  const date = typeof input === 'string' ? new Date(input) : input;
  if (Number.isNaN(date.getTime())) return '';
  return formatDate(date, 'p');
};

const formatShortDate = (input: string | Date | null | undefined): string => {
  if (!input) return '';
  const date = typeof input === 'string' ? new Date(input) : input;
  if (Number.isNaN(date.getTime())) return '';
  return formatDate(date, 'MM/dd/yy');
};

const getInitials = (firstName?: string | null, lastName?: string | null): string => {
  const first = (firstName?.[0] ?? '').toUpperCase();
  const last = (lastName?.[0] ?? '').toUpperCase();
  const combined = `${first}${last}`.trim();
  return combined || '??';
};

const formatStudentName = (firstName?: string | null, lastName?: string | null): string => {
  const first = firstName?.trim() ?? '';
  const lastInitial = lastName?.trim()?.[0];
  if (first && lastInitial) return `${first} ${lastInitial}.`;
  return first || lastName || 'Student';
};

const isAbortError = (error: unknown): boolean => {
  if (!error || typeof error !== 'object') return false;
  const name = (error as { name?: unknown }).name;
  return typeof name === 'string' && name === 'AbortError';
};

const getBookingActivityTimestamp = (booking: Booking): string | undefined => {
  const possible = (booking as { updated_at?: string | null }).updated_at;
  return (
    possible ??
    booking.completed_at ??
    booking.confirmed_at ??
    booking.cancelled_at ??
    booking.created_at ??
    booking.booking_date ??
    undefined
  );
};

const mapMessageFromResponse = (
  message: MessageResponse,
  conversation: ConversationEntry | undefined,
  currentUserId: string
): MessageWithAttachments => {
  const senderType: 'instructor' | 'student' | 'platform' =
    message.sender_id === currentUserId
      ? 'instructor'
      : conversation?.studentId && message.sender_id === conversation.studentId
      ? 'student'
      : conversation
      ? 'platform'
      : 'student';

  let delivery: MessageDelivery | undefined;
  if (senderType === 'instructor') {
    const recipientId = conversation?.studentId ?? null;
    const recipientRead = recipientId
      ? (message.read_by ?? []).find((entry) => entry.user_id === recipientId && entry.read_at)
      : undefined;
    if (recipientRead) {
      delivery = {
        status: 'read',
        timeLabel: formatTimeLabel(recipientRead.read_at ?? message.updated_at ?? message.created_at),
      };
    } else if (message.delivered_at) {
      delivery = { status: 'delivered', timeLabel: formatTimeLabel(message.delivered_at) };
    } else {
      delivery = { status: 'delivered', timeLabel: formatTimeLabel(message.created_at) };
    }
  }

  const mapped: MessageWithAttachments = {
    id: message.id,
    text: message.content ?? '',
    sender: senderType,
    timestamp: formatRelativeTime(message.created_at),
  };

  if (delivery) {
    mapped.delivery = delivery;
  }
  if (message.created_at) {
    mapped.createdAt = message.created_at;
  }
  if (message.sender_id) {
    mapped.senderId = message.sender_id;
  }
  if (typeof (message as { is_deleted?: unknown }).is_deleted === 'boolean') {
    mapped.isArchived = Boolean((message as { is_deleted?: boolean }).is_deleted);
  }

  return mapped;
};

const computeUnreadFromMessages = (
  messages: MessageResponse[] | undefined,
  conversation: ConversationEntry | undefined,
  currentUserId: string
): number => {
  if (!messages || !conversation) return 0;
  return messages.reduce((count, msg) => {
    if (msg.sender_id === currentUserId) return count;
    const hasRead = (msg.read_by ?? []).some(
      (entry) => entry.user_id === currentUserId && !!entry.read_at
    );
    return hasRead ? count : count + 1;
  }, 0);
};

const loadInitialDrafts = () => {
  if (typeof document === 'undefined') return {};
  try {
    const cookies = document.cookie.split(';').map((cookie) => cookie.trim());
    const target = cookies.find((cookie) => cookie.startsWith(`${DRAFT_COOKIE_NAME}=`));
    if (!target) return {};
    const raw = decodeURIComponent(target.split('=')[1] ?? '');
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const entries = Object.entries(parsed).filter(([, value]) => typeof value === 'string') as [string, string][];
      return Object.fromEntries(entries);
    }
  } catch {
    // ignore malformed storage
  }
  return {};
};

export default function MessagesPage() {
  const router = useRouter();
  const [selectedChat, setSelectedChat] = useState<string | null>(null);
  const [messageText, setMessageText] = useState('');
  const [pendingAttachments, setPendingAttachments] = useState<File[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<'all' | 'student' | 'platform'>('all');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [mailSection, setMailSection] = useState<'inbox' | 'compose' | 'sent' | 'drafts' | 'templates'>('inbox');
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const initialTemplatesRef = useRef<TemplateItem[]>(loadStoredTemplates());
  const [templates, setTemplates] = useState<TemplateItem[]>(initialTemplatesRef.current);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(
    initialTemplatesRef.current[0]?.id ?? null
  );
  const [templateDrafts, setTemplateDrafts] = useState<Record<string, string>>(() => {
    const entries = initialTemplatesRef.current.map((template) => [template.id, template.body]) as [string, string][];
    return Object.fromEntries(entries);
  });
  const [copiedTemplateId, setCopiedTemplateId] = useState<string | null>(null);
  const [composeRecipientQuery, setComposeRecipientQuery] = useState('');
  const [composeRecipient, setComposeRecipient] = useState<ConversationEntry | null>(null);
  const [draftsByThread, setDraftsByThread] = useState<Record<string, string>>(loadInitialDrafts);
  // Header dropdowns to match dashboard behavior
  const msgRef = useRef<HTMLDivElement | null>(null);
  const notifRef = useRef<HTMLDivElement | null>(null);
  const [showMessages, setShowMessages] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const subjectInputRef = useRef<HTMLInputElement | null>(null);
  const [pendingSubjectFocusId, setPendingSubjectFocusId] = useState<string | null>(null);
  const [rewritingTemplateId, setRewritingTemplateId] = useState<string | null>(null);
  const [templateRewriteCounts, setTemplateRewriteCounts] = useState<Record<string, number>>({});
  const { user: currentUser, isLoading: isLoadingUser } = useAuthStatus();
  const markedReadThreadsRef = useRef<Set<string>>(new Set());
  const markReadFailuresRef = useRef<Set<string>>(new Set());
  const historyLoadMetaRef = useRef<Record<string, ThreadHistoryMeta>>({});
  const messagesByThreadRef = useRef<Record<string, MessageWithAttachments[]>>({});
  const archivedMessagesByThreadRef = useRef<Record<string, MessageWithAttachments[]>>({});
  const trashMessagesByThreadRef = useRef<Record<string, MessageWithAttachments[]>>({});
  const threadMessagesRef = useRef<MessageWithAttachments[]>([]);
  const [messageDisplay, setMessageDisplay] = useState<'inbox' | 'archived' | 'trash'>('inbox');
  const [archivedMessagesByThread, setArchivedMessagesByThread] = useState<
    Record<string, MessageWithAttachments[]>
  >({});
  const [trashMessagesByThread, setTrashMessagesByThread] = useState<Record<string, MessageWithAttachments[]>>({});
  const [pendingArchiveIds, setPendingArchiveIds] = useState<Record<string, boolean>>({});
  const [pendingDeleteIds, setPendingDeleteIds] = useState<Record<string, boolean>>({});
  const activeConversationRef = useRef<ConversationEntry | null>(null);

  const loadConversations = useCallback(async () => {
    if (isLoadingUser) return;
    if (!currentUser?.id) {
      setIsLoadingConversations(false);
      setConversations([]);
      return;
    }

    const currentUserId = currentUser.id;

    const buildConversationFromBooking = async (booking: Booking): Promise<ConversationEntry | null> => {
      const studentInfo = booking.student;
      const name = formatStudentName(studentInfo?.first_name, studentInfo?.last_name);
      const avatar = getInitials(studentInfo?.first_name, studentInfo?.last_name);
      const studentId = booking.student_id ?? (studentInfo as { id?: string } | null)?.id ?? null;
      const conversationId = studentId ? `student-${studentId}` : booking.id;

      const baseDate = getBookingActivityTimestamp(booking);
      const fallbackActivity = baseDate ? new Date(baseDate).getTime() : Date.now();

      let lastMessage = 'No messages yet';
      let timestamp = formatRelativeTime(baseDate);
      let latestMessageAt = fallbackActivity;
      let unread = 0;
      let latestMessageId: string | null = null;

      try {
        const history = await messageService.getMessageHistory(booking.id, 1, 0);
        const latest = history.messages?.[history.messages.length - 1];
        if (latest) {
          lastMessage = latest.content ?? '';
          timestamp = formatRelativeTime(latest.created_at);
          latestMessageAt = latest.created_at ? new Date(latest.created_at).getTime() : fallbackActivity;
          latestMessageId = latest.id ?? null;

          if (latest.sender_id && latest.sender_id !== currentUserId) {
            const readBy = latest.read_by ?? [];
            const hasRead = readBy.some((entry) => entry.user_id === currentUserId && !!entry.read_at);
            if (!hasRead) {
              unread = 1;
            }
          }
        }
      } catch (error) {
        logger.warn('Failed to fetch latest message for booking', { bookingId: booking.id, error });
      }

      return {
        id: conversationId,
        name,
        lastMessage,
        timestamp,
        unread,
        avatar,
        type: 'student',
        bookingIds: [booking.id],
        primaryBookingId: booking.id,
        studentId,
        instructorId: booking.instructor_id ?? null,
        latestMessageAt,
        latestMessageId,
      };
    };

    setIsLoadingConversations(true);
    setConversationError(null);

    try {
      const results = await Promise.allSettled([
        bookingsApi.getMyBookings({ upcoming: true, per_page: 25 }),
        bookingsApi.getMyBookings({ include_past_confirmed: true, per_page: 25 }),
      ]);

      const bookingMap = new Map<string, Booking>();
      for (const result of results) {
        if (result.status === 'fulfilled') {
          result.value.items.forEach((booking) => {
            if (booking.instructor_id !== currentUserId) {
              return;
            }
            bookingMap.set(booking.id, booking);
          });
        } else {
          logger.warn('Booking fetch failed for conversations', { error: result.reason });
        }
      }

      const bookings = Array.from(bookingMap.values());
      bookings.sort((a, b) => {
        const extractTime = (bk: Booking) => {
          const base = getBookingActivityTimestamp(bk);
          return base ? new Date(base).getTime() : 0;
        };
        return extractTime(b) - extractTime(a);
      });

      const conversationsList: ConversationEntry[] = [];
      for (const booking of bookings) {
        const entry = await buildConversationFromBooking(booking);
        if (entry) {
          conversationsList.push(entry);
        }
      }

      const aggregated = new Map<string, ConversationEntry>();
      for (const entry of conversationsList) {
        const existing = aggregated.get(entry.id);
        if (!existing) {
          aggregated.set(entry.id, entry);
          continue;
        }
        const latestIsExisting = existing.latestMessageAt >= entry.latestMessageAt;
        const latestEntry = latestIsExisting ? existing : entry;
        const mergedBookingIds = [
          ...(latestIsExisting ? existing.bookingIds : entry.bookingIds),
          ...(latestIsExisting ? entry.bookingIds : existing.bookingIds),
        ];
        const uniqueBookingIds = Array.from(new Set(mergedBookingIds));
        aggregated.set(entry.id, {
          ...latestEntry,
          bookingIds: uniqueBookingIds,
          primaryBookingId: latestIsExisting
            ? existing.primaryBookingId ?? entry.primaryBookingId
            : entry.primaryBookingId ?? existing.primaryBookingId,
          unread: (existing.unread ?? 0) + (entry.unread ?? 0),
          latestMessageAt: Math.max(existing.latestMessageAt, entry.latestMessageAt),
          latestMessageId: latestEntry.latestMessageId ?? existing.latestMessageId ?? null,
        });
      }

      const mergedConversations = Array.from(aggregated.values());
      mergedConversations.sort((a, b) => b.latestMessageAt - a.latestMessageAt);
      setConversations(mergedConversations);
    } catch (error) {
      logger.error('Failed to load conversations', { error });
      setConversations([]);
      setConversationError('Unable to load conversations');
    } finally {
      setIsLoadingConversations(false);
    }
  }, [currentUser?.id, isLoadingUser]);

  useEffect(() => {
    if (isLoadingUser) return;
    void loadConversations();
  }, [loadConversations, isLoadingUser]);
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

  useEffect(() => {
    if (mailSection === 'templates' && !selectedTemplateId && templates.length) {
      const firstTemplate = templates[0];
      if (firstTemplate) {
        setSelectedTemplateId(firstTemplate.id);
      }
    }
  }, [mailSection, selectedTemplateId, templates]);

  useEffect(() => {
    if (!copiedTemplateId) return;
    const timer = setTimeout(() => setCopiedTemplateId(null), 1500);
    return () => clearTimeout(timer);
  }, [copiedTemplateId]);

  useEffect(() => {
    if (!pendingSubjectFocusId || pendingSubjectFocusId !== selectedTemplateId) return;
    const frame = requestAnimationFrame(() => {
      if (subjectInputRef.current) {
        subjectInputRef.current.focus();
        subjectInputRef.current.select();
      }
      setPendingSubjectFocusId(null);
    });
    return () => cancelAnimationFrame(frame);
  }, [pendingSubjectFocusId, selectedTemplateId]);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    try {
      const payload = encodeURIComponent(JSON.stringify(templates));
      const oneYearInSeconds = 60 * 60 * 24 * 365;
      document.cookie = `${TEMPLATE_COOKIE_NAME}=${payload}; path=/; max-age=${oneYearInSeconds}`;
    } catch {
      // ignore storage write failures
    }
  }, [templates]);

  const [threadMessages, setThreadMessages] = useState<MessageWithAttachments[]>([]);
  useEffect(() => {
    threadMessagesRef.current = threadMessages;
  }, [threadMessages]);
  const [messagesByThread, setMessagesByThread] = useState<Record<string, MessageWithAttachments[]>>({});
  useEffect(() => {
    messagesByThreadRef.current = messagesByThread;
  }, [messagesByThread]);
  useEffect(() => {
    archivedMessagesByThreadRef.current = archivedMessagesByThread;
  }, [archivedMessagesByThread]);
  useEffect(() => {
    trashMessagesByThreadRef.current = trashMessagesByThread;
  }, [trashMessagesByThread]);
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
  const [conversations, setConversations] = useState<ConversationEntry[]>([]);
  const [isLoadingConversations, setIsLoadingConversations] = useState(true);
  const [conversationError, setConversationError] = useState<string | null>(null);
  const totalUnread = useMemo(
    () => conversations.reduce((sum, convo) => sum + (convo.unread ?? 0), 0),
    [conversations]
  );
  const unreadConversations = useMemo(
    () => conversations.filter((convo) => (convo.unread ?? 0) > 0),
    [conversations]
  );

  const filteredConversations = conversations.filter((conv) => {
    const matchesText = conv.name.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType = typeFilter === 'all' ? true : conv.type === typeFilter;
    return matchesText && matchesType;
  });
  const activeConversationList = useMemo(
    () =>
      filteredConversations.filter((conv) => {
        const activeMessages = messagesByThread[conv.id];
        return (activeMessages?.length ?? 0) > 0;
      }),
    [filteredConversations, messagesByThread]
  );
  const archivedConversationList = useMemo(
    () => filteredConversations.filter((conv) => (archivedMessagesByThread[conv.id]?.length ?? 0) > 0),
    [filteredConversations, archivedMessagesByThread]
  );
  const trashConversationList = useMemo(
    () => filteredConversations.filter((conv) => (trashMessagesByThread[conv.id]?.length ?? 0) > 0),
    [filteredConversations, trashMessagesByThread]
  );

  const composeListEntry = useMemo(() => {
    const draftLabel = composeRecipient ? `Draft to ${composeRecipient.name}` : 'Draft a message';
    return {
      id: COMPOSE_THREAD_ID,
      name: 'New Message',
      lastMessage: draftLabel,
      timestamp: '',
      unread: 0,
      avatar: '',
      type: 'platform' as const,
      bookingIds: [],
      primaryBookingId: null,
      studentId: null,
      instructorId: currentUser?.id ?? null,
      latestMessageAt: Date.now(),
      latestMessageId: null,
    };
  }, [composeRecipient, currentUser?.id]);

  const conversationSource = useMemo(() => {
    if (messageDisplay === 'archived') {
      return archivedConversationList;
    }
    if (messageDisplay === 'trash') {
      return trashConversationList;
    }
    return [composeListEntry, ...activeConversationList];
  }, [composeListEntry, activeConversationList, archivedConversationList, trashConversationList, messageDisplay]);
  useEffect(() => {
    if (messageDisplay !== 'inbox' && mailSection !== 'inbox') {
      setMailSection('inbox');
    }
  }, [mailSection, messageDisplay]);
  const isComposeView = selectedChat === COMPOSE_THREAD_ID;
  const activeConversation =
    selectedChat && !isComposeView ? conversations.find((conv) => conv.id === selectedChat) ?? null : null;
  useEffect(() => {
    activeConversationRef.current = activeConversation ?? null;
  }, [activeConversation]);
  const activeConversationLatestMessageId = activeConversation?.latestMessageId ?? null;
  const activeConversationLatestMessageAt = activeConversation?.latestMessageAt ?? null;
  const getDraftKey = (threadId: string | null) => threadId ?? COMPOSE_THREAD_ID;
  const composeSuggestions = useMemo(() => {
    if (!composeRecipientQuery.trim()) return [];
    const query = composeRecipientQuery.toLowerCase();
    return conversations
      .filter((conv) => conv.id !== composeRecipient?.id && conv.name.toLowerCase().includes(query))
      .slice(0, 5);
  }, [composeRecipientQuery, composeRecipient?.id, conversations]);

  // Auto-select the first conversation when none selected and in inbox view
  useEffect(() => {
    if (mailSection !== 'inbox' || selectedChat || activeConversationList.length === 0) return;
    const firstConversation = activeConversationList[0];
    if (firstConversation) {
      setSelectedChat(firstConversation.id);
    }
  }, [activeConversationList, selectedChat, mailSection]);
  useEffect(() => {
    if (messageDisplay === 'archived') {
      if (selectedChat === COMPOSE_THREAD_ID) {
        setSelectedChat(null);
        return;
      }
      if (selectedChat && (archivedMessagesByThread[selectedChat]?.length ?? 0) > 0) return;
      const firstArchived = archivedConversationList[0];
      setSelectedChat(firstArchived ? firstArchived.id : null);
      return;
    }

    if (messageDisplay === 'trash') {
      if (selectedChat === COMPOSE_THREAD_ID) {
        setSelectedChat(null);
        return;
      }
      if (selectedChat && (trashMessagesByThread[selectedChat]?.length ?? 0) > 0) return;
      const firstTrash = trashConversationList[0];
      setSelectedChat(firstTrash ? firstTrash.id : null);
      return;
    }

    const firstActive = activeConversationList[0];
    if (!selectedChat || selectedChat === COMPOSE_THREAD_ID || (messagesByThread[selectedChat]?.length ?? 0) === 0) {
      setSelectedChat(firstActive ? firstActive.id : null);
    }
  }, [
    activeConversationList,
    archivedConversationList,
    archivedMessagesByThread,
    trashConversationList,
    trashMessagesByThread,
    messageDisplay,
    messagesByThread,
    selectedChat,
  ]);

  const readFileAsDataUrl = useMemo(
    () =>
      (file: File) =>
        new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result));
          reader.onerror = () => reject(reader.error);
          reader.readAsDataURL(file);
        }),
    []
  );

  const getPrimaryBookingId = useCallback(
    (threadId: string | null) => {
      if (!threadId) return null;
      const conv = conversations.find((c) => c.id === threadId);
      if (!conv) return threadId;
      const primary = conv.primaryBookingId ?? (conv.bookingIds.length > 0 ? conv.bookingIds[0] : null);
      return primary ?? threadId;
    },
    [conversations]
  );

  const handleSendMessage = async () => {
    const trimmed = messageText.trim();
    const hasAttachments = pendingAttachments.length > 0;
    if (!trimmed && !hasAttachments) return;

    if (!currentUser?.id) {
      logger.warn('Attempted to send a message without an authenticated user');
      return;
    }
    const currentUserId = currentUser.id;

    let targetThreadId = selectedChat;
    let switchingFromCompose = false;
    const chosenRecipient = composeRecipient;

    if (!targetThreadId || targetThreadId === COMPOSE_THREAD_ID) {
      if (!chosenRecipient) return;
      targetThreadId = chosenRecipient.id;
      switchingFromCompose = true;
    }
    if (!targetThreadId) return;
    const shouldUpdateVisibleThread = switchingFromCompose || targetThreadId === selectedChat;

    let attachmentPayload: MessageAttachment[] = [];
    if (hasAttachments) {
      try {
        const dataUrls: string[] = await Promise.all(
          pendingAttachments.map((file) => readFileAsDataUrl(file))
        );
        attachmentPayload = pendingAttachments.map((file, index) => ({
          name: file.name,
          type: file.type,
          dataUrl: dataUrls[index] ?? '',
        }));
      } catch {
        attachmentPayload = pendingAttachments.map((file) => ({
          name: file.name,
          type: file.type,
          dataUrl: '',
        }));
      }
    }

    const optimisticId = `local-${Date.now()}`;
    const optimistic: MessageWithAttachments = {
      id: optimisticId,
      text: trimmed,
      sender: 'instructor',
      timestamp: 'Just now',
      delivery: { status: 'sending' },
      isArchived: false,
    };
    optimistic.createdAt = new Date().toISOString();
    optimistic.senderId = currentUserId;
    if (attachmentPayload.length > 0) {
      optimistic.attachments = attachmentPayload;
    }

    const existingThread = messagesByThread[targetThreadId] || [];
    const updatedThread = [...existingThread, optimistic];

    setMessagesByThread((prev) => ({
      ...prev,
      [targetThreadId]: updatedThread,
    }));

    if (shouldUpdateVisibleThread) {
      setThreadMessages(updatedThread);
    }

    setConversations((prev) => {
      let found = false;
      const mapped = prev.map((c) => {
        if (c.id !== targetThreadId) return c;
        found = true;
        return {
          ...c,
          lastMessage:
            trimmed ||
            (attachmentPayload.length
              ? `Sent ${attachmentPayload.length} attachment${attachmentPayload.length > 1 ? 's' : ''}`
              : c.lastMessage),
          timestamp: 'Just now',
          unread: 0,
          latestMessageAt: Date.now(),
        };
      });

      const nextList = found
        ? mapped
        : [
            ...mapped,
            {
              id: targetThreadId,
              name: composeRecipient?.name ?? 'Conversation',
              lastMessage: trimmed,
              timestamp: 'Just now',
              unread: 0,
              avatar: composeRecipient?.avatar ?? '??',
              type: 'student' as const,
              bookingIds: composeRecipient?.bookingIds ?? [],
              primaryBookingId: composeRecipient?.primaryBookingId ?? null,
              studentId: composeRecipient?.studentId ?? null,
              instructorId: composeRecipient?.instructorId ?? currentUserId,
              latestMessageAt: Date.now(),
              latestMessageId: optimisticId,
            },
          ];

      return nextList.sort((a, b) => b.latestMessageAt - a.latestMessageAt);
    });

    setMessageText('');
    setPendingAttachments([]);
    setDraftsByThread((prev) => {
      const next: Record<string, string> = { ...prev, [targetThreadId]: '' };
      if (switchingFromCompose) {
        next[COMPOSE_THREAD_ID] = '';
      }
      return next;
    });
    if (switchingFromCompose) {
      setComposeRecipient(null);
      setComposeRecipientQuery('');
      setMailSection('inbox');
      setSelectedChat(targetThreadId);
    }

    const composedForServer =
      trimmed ||
      (attachmentPayload.length
        ? attachmentPayload.map((att) => `[Attachment] ${att.name}`).join('\n')
        : '');
    const bookingIdTarget = getPrimaryBookingId(targetThreadId);
    let resolvedServerId: string | undefined;
    try {
      if (bookingIdTarget) {
        const res = await sendMessage(bookingIdTarget, composedForServer);
        resolvedServerId = res?.id ?? undefined;
      }
    } catch (error) {
      logger.warn('Failed to persist instructor message', { error });
    } finally {
      const deliveredAt = new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
      const deliveryInfo: MessageDelivery = { status: 'delivered', timeLabel: deliveredAt };
      const deliveredMessage: MessageWithAttachments = {
        ...optimistic,
        id: resolvedServerId ?? optimisticId,
        delivery: deliveryInfo,
        isArchived: false,
      };

      const applyDeliveryUpdate = (collection: MessageWithAttachments[]) => {
        if (!collection || collection.length === 0) return [deliveredMessage];
        const hasMatch = collection.some((m) => m.id === optimisticId || (resolvedServerId && m.id === resolvedServerId));
        if (!hasMatch) {
          return [...collection, deliveredMessage];
        }
        return collection.map((m) =>
          m.id === optimisticId || (resolvedServerId && m.id === resolvedServerId)
            ? { ...m, id: deliveredMessage.id, delivery: deliveryInfo }
            : m
        );
      };

      if (shouldUpdateVisibleThread) {
        setThreadMessages((prev) => applyDeliveryUpdate(prev));
      }

      setMessagesByThread((prev) => ({
        ...prev,
        [targetThreadId]: applyDeliveryUpdate(prev[targetThreadId] || []),
      }));

      const latestId = resolvedServerId ?? optimisticId;
      setConversations((prev) =>
        prev.map((conv) =>
          conv.id === targetThreadId
            ? {
                ...conv,
                latestMessageId: latestId,
                latestMessageAt: Date.now(),
                primaryBookingId: bookingIdTarget ?? conv.primaryBookingId,
              }
            : conv
        )
      );
    }
  };

  const handleKeyPress = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (selectedChat === COMPOSE_THREAD_ID && !composeRecipient) return;
      void handleSendMessage();
    }
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [threadMessages, selectedChat]);

  const handleAttachmentSelection = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const fileArray = Array.from(files);
    setPendingAttachments((prev) => [...prev, ...fileArray]);
  };

  const removeAttachment = (index: number) => {
    setPendingAttachments((prev) => prev.filter((_, i) => i !== index));
  };

const deriveTemplatePreview = (text: string) => {
  const trimmed = text.trim();
  if (!trimmed) return '';
  const firstLine = trimmed.split('\n').find((line) => line.trim()) ?? trimmed;
  const normalized = firstLine.trim();
  return normalized.length > 80 ? `${normalized.slice(0, 77)}…` : normalized;
};

const BULLET_PATTERN = /^([-*•]|\d+[.)])\s*/;

const ensureSentenceEnding = (text: string) => {
  const trimmed = text.trim();
  if (!trimmed) return '';
  if (/[.!?)]$/.test(trimmed)) return trimmed;
  return `${trimmed}.`;
};

const copyToClipboard = async (text: string) => {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to fallback
  }
  if (typeof document === 'undefined') return false;
  try {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'absolute';
    textarea.style.left = '-9999px';
    textarea.style.top = '0';
    document.body.appendChild(textarea);
    textarea.select();
    const success = document.execCommand('copy');
    document.body.removeChild(textarea);
    return success;
  } catch {
    return false;
  }
};

const looksLikeClosing = (text: string) =>
  /(best|thanks|thank you|regards|sincerely|cheers|talk soon|warmly|take care|see you soon|yours truly)/i.test(
    text.trim()
  );

const normalizeForComparison = (text: string) =>
  text
    .replace(/[^\p{L}\p{N}\s]/gu, '')
    .toLowerCase()
    .trim();

const looksLikeOpener = (text: string) => {
  const normalized = normalizeForComparison(text);
  return (
    normalized.startsWith('quick heads up') ||
    normalized.startsWith('just a quick update') ||
    normalized.startsWith('heres what im thinking') ||
    normalized.startsWith('sharing the latest') ||
    normalized.startsWith('checking in real quick')
  );
};

const sentenceCase = (text: string) => {
  const trimmed = text.trim();
  if (!trimmed) return '';
  const normalized = trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
  return ensureSentenceEnding(normalized);
};

const splitIntoSentences = (text: string) => {
  const sanitized = text.replace(/\s+/g, ' ').trim();
  if (!sanitized) return [];
  const matches = sanitized.match(/[^.!?]+[.!?]?/g);
  if (!matches) return [sentenceCase(sanitized)];
  return matches.map((segment) => sentenceCase(segment));
};

function rotateItems<T>(items: T[], offset: number): T[] {
  if (items.length === 0) return items;
  const normalizedOffset = ((offset % items.length) + items.length) % items.length;
  return [...items.slice(normalizedOffset), ...items.slice(0, normalizedOffset)];
}

const rewriteTemplateContent = (raw: string, iteration = 0) => {
  const normalized = raw.replace(/\r/g, '').trim();
  const variantIndex = Math.max(iteration, 0);

  const openers = [
    'Quick heads-up 💬',
    'Just a quick update ✨',
    'Here’s what I’m thinking 📌',
    'Sharing the latest 👇',
    'Checking in real quick ✅',
  ];
  const closers = [
    'Let me know what you think.',
    'Message me if anything feels off.',
    'Ping me with questions.',
    'Happy to tweak—just say the word.',
    'Thanks! Chat soon.',
  ];
  const bulletSymbols = ['•', '–', '-'];
  const fallbackLines = [
    'Sharing a quick update so we stay aligned.',
    'Here’s the plan I’d go with right now.',
    'These are the next moves I’m seeing.',
    'Keeping things on track with this plan.',
    'This should keep everything moving smoothly.',
  ];

  const opener = openers[variantIndex % openers.length];
  const closer = closers[variantIndex % closers.length];
  const bulletSymbol = bulletSymbols[variantIndex % bulletSymbols.length];

  if (!normalized) {
    return [opener, `${bulletSymbol} ${fallbackLines[variantIndex % fallbackLines.length]}`, closer].join('\n');
  }

  const paragraphs = normalized.split(/\n\s*\n/).map((block) => block.trim()).filter(Boolean);

  const bulletItems: string[] = [];
  const sentenceItems: string[] = [];

  paragraphs.forEach((paragraph) => {
    const lines = paragraph.split('\n').map((line) => line.trim()).filter(Boolean);
    const bulletCandidates = lines.filter((line) => BULLET_PATTERN.test(line));
    if (bulletCandidates.length >= Math.max(2, Math.ceil(lines.length * 0.6))) {
      bulletCandidates.forEach((candidate) => {
        const content = candidate.replace(BULLET_PATTERN, '').trim();
        if (!content) return;
        const cleaned = content.replace(/\s+/g, ' ');
        const formatted = cleaned.charAt(0).toUpperCase() + cleaned.slice(1).replace(/[.!?]+$/, '');
        bulletItems.push(formatted);
      });
    } else {
      const combined = lines.join(' ');
      splitIntoSentences(combined).forEach((sentence) => {
        if (!sentence) return;
        if (looksLikeClosing(sentence)) return;
        if (looksLikeOpener(sentence)) return;
        sentenceItems.push(sentence.replace(/\s+/g, ' ').trim());
      });
    }
  });

  const rotatedSentences = rotateItems(sentenceItems, variantIndex);
  const rotatedBullets = rotateItems(bulletItems, Math.floor(variantIndex / 2));

  const conversationalSentences = rotatedSentences.map((sentence, index) => {
    const trimmed = sentence.replace(/[.!?]+$/, '');
    if (index === 0) return trimmed;
    if (trimmed.length <= 60) return trimmed;
    return ensureSentenceEnding(trimmed);
  });

  const bulletLines = rotatedBullets.map((item) => `${bulletSymbol} ${item}`);

  const combinedLines = [...conversationalSentences, ...bulletLines];

  const seen = new Set<string>();
  const bodyLines = combinedLines.filter((line) => {
    const key = normalizeForComparison(line);
    if (!key) return false;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  if (bodyLines.length === 0) {
    const fallbackLine = fallbackLines[(variantIndex + 1) % fallbackLines.length] ?? '';
    if (fallbackLine) {
      bodyLines.push(fallbackLine);
    }
  }

  return [opener, ...bodyLines, closer].join('\n');
};

function loadStoredTemplates(): TemplateItem[] {
  if (typeof document === 'undefined') return getDefaultTemplates();
  try {
    const cookies = document.cookie.split(';').map((cookie) => cookie.trim());
    const target = cookies.find((cookie) => cookie.startsWith(`${TEMPLATE_COOKIE_NAME}=`));
    if (!target) return getDefaultTemplates();
    const raw = decodeURIComponent(target.split('=')[1] ?? '');
    if (!raw) return getDefaultTemplates();
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return getDefaultTemplates();
    const cleaned = parsed
      .map((item) => {
        if (!item || typeof item !== 'object') return null;
        const id = typeof (item as { id?: unknown }).id === 'string' && (item as { id?: string }).id
          ? (item as { id: string }).id
          : null;
        if (!id) return null;
        const body = typeof (item as { body?: unknown }).body === 'string' ? (item as { body: string }).body : '';
        const subject = typeof (item as { subject?: unknown }).subject === 'string'
          ? (item as { subject: string }).subject
          : '';
        const previewCandidate =
          typeof (item as { preview?: unknown }).preview === 'string'
            ? (item as { preview: string }).preview
            : '';
        const preview = previewCandidate.trim() ? previewCandidate : deriveTemplatePreview(body);
        return {
          id,
          subject,
          body,
          preview,
        };
      })
      .filter((item): item is TemplateItem => item !== null);
    return cleaned.length > 0 ? cleaned : getDefaultTemplates();
  } catch {
    return getDefaultTemplates();
  }
}

  const handleCreateTemplate = () => {
    const newId = `template-${Date.now()}`;
    const newTemplate = {
      id: newId,
      subject: 'Untitled template',
      preview: '',
      body: '',
    };
    setTemplates((prev) => [...prev, newTemplate]);
    setTemplateDrafts((prev) => ({ ...prev, [newId]: '' }));
    setTemplateRewriteCounts((prev) => ({ ...prev, [newId]: 0 }));
    setSelectedTemplateId(newId);
    setPendingSubjectFocusId(newId);
  };

  const handleTemplateSubjectChange = (templateId: string, nextSubject: string) => {
    setTemplates((prev) =>
      prev.map((template) =>
        template.id === templateId
          ? {
              ...template,
              subject: nextSubject,
            }
          : template
      )
    );
  };

  const handleRewriteTemplate = (templateId: string) => {
    const base =
      templateDrafts[templateId] ??
      templates.find((template) => template.id === templateId)?.body ??
      '';
    const variantIndex = templateRewriteCounts[templateId] ?? 0;
    setRewritingTemplateId(templateId);
    try {
      const improved = rewriteTemplateContent(base, variantIndex);
      setTemplateDrafts((prev) => ({ ...prev, [templateId]: improved }));
      setTemplates((prev) =>
        prev.map((template) =>
          template.id === templateId
            ? { ...template, body: improved, preview: deriveTemplatePreview(improved) }
            : template
        )
      );
      setTemplateRewriteCounts((prev) => ({ ...prev, [templateId]: variantIndex + 1 }));
    } finally {
      setRewritingTemplateId(null);
    }
  };

  const handleCopyTemplate = async (templateId: string, content: string) => {
    const ok = await copyToClipboard(content);
    if (ok) {
      setCopiedTemplateId(templateId);
    } else {
      alert('Unable to copy template right now.');
    }
  };

  const handleComposeRecipientSelect = (conversation: ConversationEntry) => {
    setComposeRecipient(conversation);
    setComposeRecipientQuery('');
  };

  const setPendingFlag = (
    setter: React.Dispatch<React.SetStateAction<Record<string, boolean>>>,
    messageId: string,
    value: boolean
  ) => {
    setter((prev) => {
      if (value) {
        if (prev[messageId]) return prev;
        return { ...prev, [messageId]: true };
      }
      if (!prev[messageId]) return prev;
      const next = { ...prev };
      delete next[messageId];
      return next;
    });
  };

  const handleMessageChange = (value: string) => {
    const draftKey = getDraftKey(selectedChat);
    setMessageText(value);
    setDraftsByThread((prev) => {
      if (prev[draftKey] === value) return prev;
      return { ...prev, [draftKey]: value };
    });
  };

  const updateThreadCollections = (
    threadId: string,
    nextActive: MessageWithAttachments[],
    nextArchived: MessageWithAttachments[],
    nextTrash: MessageWithAttachments[]
  ) => {
    setMessagesByThread((prev) => ({ ...prev, [threadId]: nextActive }));
    setArchivedMessagesByThread((prev) => ({ ...prev, [threadId]: nextArchived }));
    setTrashMessagesByThread((prev) => ({ ...prev, [threadId]: nextTrash }));

    if (threadId === selectedChat) {
      if (messageDisplay === 'archived') {
        setThreadMessages(nextArchived);
      } else if (messageDisplay === 'trash') {
        setThreadMessages(nextTrash);
      } else {
        setThreadMessages(nextActive);
      }
    }

    setConversations((prev) => {
      let changed = false;
      const updated = prev.map((conv) => {
        if (conv.id !== threadId) return conv;
        const latestActive = nextActive[nextActive.length - 1] ?? null;
        const latestArchived = nextArchived[nextArchived.length - 1] ?? null;
        const latestTrash = nextTrash[nextTrash.length - 1] ?? null;
        const fallbackMessage = latestActive ?? latestArchived ?? latestTrash ?? null;
        const lastMessage =
          latestActive?.text ??
          (nextActive.length === 0
            ? latestArchived?.text ??
              (nextArchived.length === 0 ? latestTrash?.text ?? (nextTrash.length ? TRASH_LABEL : ARCHIVED_LABEL) : ARCHIVED_LABEL)
            : conv.lastMessage);
        const timestamp = fallbackMessage?.createdAt
          ? formatRelativeTime(fallbackMessage.createdAt)
          : conv.timestamp;
        const latestMessageAt = fallbackMessage?.createdAt
          ? new Date(fallbackMessage.createdAt).getTime()
          : conv.latestMessageAt;
        const latestMessageId = latestActive?.id ?? latestArchived?.id ?? latestTrash?.id ?? conv.latestMessageId ?? null;
        const nextConv: ConversationEntry = {
          ...conv,
          lastMessage,
          timestamp,
          latestMessageAt,
          latestMessageId,
        };
        if (
          nextConv.lastMessage !== conv.lastMessage ||
          nextConv.timestamp !== conv.timestamp ||
          nextConv.latestMessageAt !== conv.latestMessageAt ||
          nextConv.latestMessageId !== conv.latestMessageId
        ) {
          changed = true;
        }
        return nextConv;
      });
      return changed ? [...updated].sort((a, b) => b.latestMessageAt - a.latestMessageAt) : prev;
    });
  };

  const moveMessageToArchive = (
    threadId: string,
    message: MessageWithAttachments,
    overrides: Partial<MessageWithAttachments> = {}
  ) => {
    if (!threadId || threadId === COMPOSE_THREAD_ID) return;
    const existingActive = messagesByThreadRef.current[threadId] ?? [];
    const messageIndex = existingActive.findIndex((item) => item.id === message.id);
    if (messageIndex === -1 && !(overrides.isArchived ?? message.isArchived)) {
      return;
    }
    const nextActive = existingActive.filter((item) => item.id !== message.id);
    const archivedMessage: MessageWithAttachments = {
      ...message,
      ...overrides,
      isArchived: true,
      isTrashed: false,
    };
    const existingArchived = archivedMessagesByThreadRef.current[threadId] ?? [];
    const hasArchivedInstance = existingArchived.some((item) => item.id === archivedMessage.id);
    const mergedArchived = hasArchivedInstance
      ? existingArchived.map((item) => (item.id === archivedMessage.id ? archivedMessage : item))
      : [...existingArchived, archivedMessage];
    const existingTrash = trashMessagesByThreadRef.current[threadId] ?? [];
    const nextTrash = existingTrash.filter((item) => item.id !== message.id);
    const nextArchived = [...mergedArchived].sort((a, b) => {
      const aTime = a.createdAt ? new Date(a.createdAt).getTime() : 0;
      const bTime = b.createdAt ? new Date(b.createdAt).getTime() : 0;
      return aTime - bTime;
    });

    updateThreadCollections(threadId, nextActive, nextArchived, nextTrash);
  };

  const moveMessageToTrash = (threadId: string, message: MessageWithAttachments) => {
    if (!threadId || threadId === COMPOSE_THREAD_ID) return;
    const existingActive = messagesByThreadRef.current[threadId] ?? [];
    const existingArchived = archivedMessagesByThreadRef.current[threadId] ?? [];
    const existingTrash = trashMessagesByThreadRef.current[threadId] ?? [];
    const nextActive = existingActive.filter((item) => item.id !== message.id);
    const nextArchived = existingArchived.filter((item) => item.id !== message.id);
    const trashedMessage: MessageWithAttachments = {
      ...message,
      isArchived: false,
      isTrashed: true,
    };
    const mergedTrash = existingTrash.some((item) => item.id === trashedMessage.id)
      ? existingTrash.map((item) => (item.id === trashedMessage.id ? trashedMessage : item))
      : [...existingTrash, trashedMessage];
    const nextTrash = [...mergedTrash].sort((a, b) => {
      const aTime = a.createdAt ? new Date(a.createdAt).getTime() : 0;
      const bTime = b.createdAt ? new Date(b.createdAt).getTime() : 0;
      return aTime - bTime;
    });

    updateThreadCollections(threadId, nextActive, nextArchived, nextTrash);
  };

  type ThreadStateSnapshot = {
    active: MessageWithAttachments[];
    archived: MessageWithAttachments[];
    trash: MessageWithAttachments[];
  };

  const getThreadSnapshot = (threadId: string): ThreadStateSnapshot => ({
    active: [...(messagesByThreadRef.current[threadId] ?? [])],
    archived: [...(archivedMessagesByThreadRef.current[threadId] ?? [])],
    trash: [...(trashMessagesByThreadRef.current[threadId] ?? [])],
  });

  const restoreThreadSnapshot = (threadId: string, snapshot: ThreadStateSnapshot) => {
    updateThreadCollections(threadId, snapshot.active, snapshot.archived, snapshot.trash);
  };

  const handleArchiveMessageClick = async (threadId: string, message: MessageWithAttachments) => {
    if (!message.id) return;
    const snapshot = getThreadSnapshot(threadId);
    moveMessageToArchive(threadId, message);
    setPendingFlag(setPendingArchiveIds, message.id, true);
    try {
      await messageService.deleteMessage(message.id);
    } catch (error) {
      logger.error('Failed to archive message', { messageId: message.id, error });
      alert('Unable to archive message right now.');
      restoreThreadSnapshot(threadId, snapshot);
    }
    setPendingFlag(setPendingArchiveIds, message.id, false);
  };

  const handleDeleteMessage = async (threadId: string, message: MessageWithAttachments) => {
    if (!message.id) return;
    const snapshot = getThreadSnapshot(threadId);
    moveMessageToTrash(threadId, message);
    setPendingFlag(setPendingDeleteIds, message.id, true);
    try {
      await messageService.deleteMessage(message.id);
    } catch (error) {
      logger.error('Failed to delete message', { messageId: message.id, error });
      alert('Unable to delete message right now.');
      restoreThreadSnapshot(threadId, snapshot);
      setPendingFlag(setPendingDeleteIds, message.id, false);
      return;
    }
    setPendingFlag(setPendingDeleteIds, message.id, false);
  };

  const handleArchiveButtonClick = (
    event: ReactMouseEvent<HTMLButtonElement>,
    threadId: string,
    message: MessageWithAttachments
  ) => {
    event.stopPropagation();
    void handleArchiveMessageClick(threadId, message);
  };

  const handleDeleteButtonClick = (
    event: ReactMouseEvent<HTMLButtonElement>,
    threadId: string,
    message: MessageWithAttachments
  ) => {
    event.stopPropagation();
    void handleDeleteMessage(threadId, message);
  };

  const handleConversationSelect = (conversationId: string) => {
    setShowThreadMenu(false);
    setPendingAttachments([]);
    const currentKey = getDraftKey(selectedChat);
    setDraftsByThread((prev) => {
      if (prev[currentKey] === messageText) return prev;
      return { ...prev, [currentKey]: messageText };
    });

    if (conversationId === COMPOSE_THREAD_ID) {
      setMessageDisplay('inbox');
      setComposeRecipient(null);
      setComposeRecipientQuery('');
      if (mailSection !== 'compose') {
        setMailSection('compose');
      }
      setSelectedChat(COMPOSE_THREAD_ID);
      setThreadMessages(messagesByThread[COMPOSE_THREAD_ID] ?? []);
      if (!messagesByThread[COMPOSE_THREAD_ID]) {
        setMessagesByThread((prev) => ({ ...prev, [COMPOSE_THREAD_ID]: [] }));
      }
      const draftValue = draftsByThread[COMPOSE_THREAD_ID] ?? '';
      setMessageText(draftValue);
      if (!Object.prototype.hasOwnProperty.call(draftsByThread, COMPOSE_THREAD_ID)) {
        setDraftsByThread((prev) => ({ ...prev, [COMPOSE_THREAD_ID]: draftValue }));
      }
      return;
    }

    if (mailSection !== 'inbox') {
      setMailSection('inbox');
    }
    setComposeRecipient(null);
    setComposeRecipientQuery('');
    setSelectedChat(conversationId);
    setConversations((prev) =>
      prev.map((convo) => (convo.id === conversationId ? { ...convo, unread: 0 } : convo))
    );
    const targetMessages =
      messageDisplay === 'archived'
        ? archivedMessagesByThread[conversationId] ?? []
        : messageDisplay === 'trash'
        ? trashMessagesByThread[conversationId] ?? []
        : messagesByThread[conversationId] ?? [];
    setThreadMessages(targetMessages);
    const draftValue = draftsByThread[conversationId] ?? '';
    setMessageText(draftValue);
    if (!Object.prototype.hasOwnProperty.call(draftsByThread, conversationId)) {
      setDraftsByThread((prev) => ({ ...prev, [conversationId]: draftValue }));
    }
  };

  useEffect(() => {
    if (!isComposeView) return;
    if (!messagesByThread[COMPOSE_THREAD_ID]) {
      setMessagesByThread((prev) => ({ ...prev, [COMPOSE_THREAD_ID]: [] }));
    }
    setThreadMessages(messagesByThread[COMPOSE_THREAD_ID] ?? []);
  }, [isComposeView, messagesByThread]);
  useEffect(() => {
    if (!selectedChat || selectedChat === COMPOSE_THREAD_ID) return;
    if (messageDisplay === 'archived') {
      const archived = archivedMessagesByThreadRef.current[selectedChat] ?? [];
      if (threadMessagesRef.current === archived) return;
      setThreadMessages(archived);
    } else if (messageDisplay === 'trash') {
      const trashed = trashMessagesByThreadRef.current[selectedChat] ?? [];
      if (threadMessagesRef.current === trashed) return;
      setThreadMessages(trashed);
    } else {
      const active = messagesByThreadRef.current[selectedChat] ?? [];
      if (threadMessagesRef.current === active) return;
      setThreadMessages(active);
    }
  }, [messageDisplay, selectedChat]);

  const isSendDisabled =
    messageDisplay !== 'inbox'
      ? true
      : isComposeView
      ? !composeRecipient || !currentUser?.id || (!messageText.trim() && pendingAttachments.length === 0)
      : !currentUser?.id || (!messageText.trim() && pendingAttachments.length === 0);

  useEffect(() => {
    const draftKey = getDraftKey(selectedChat);
    const hasDraft = Object.prototype.hasOwnProperty.call(draftsByThread, draftKey);
    const draftValue = hasDraft ? draftsByThread[draftKey] : '';
    if (draftValue !== messageText) {
      setMessageText(draftValue ?? '');
    }
  }, [selectedChat, draftsByThread, messageText]);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    try {
      const filtered = Object.entries(draftsByThread).filter(([, value]) => value !== '');
      if (filtered.length === 0) {
        document.cookie = `${DRAFT_COOKIE_NAME}=; path=/; max-age=0`;
        return;
      }
      const payload = encodeURIComponent(JSON.stringify(Object.fromEntries(filtered)));
      document.cookie = `${DRAFT_COOKIE_NAME}=${payload}; path=/; max-age=604800; SameSite=Lax`;
    } catch {
      // ignore storage errors
    }
  }, [draftsByThread]);

  // Load history when a chat is selected
  useEffect(() => {
    if (mailSection !== 'inbox') return;
    if (!selectedChat || selectedChat === COMPOSE_THREAD_ID) return;

    const bookingIdTarget = getPrimaryBookingId(selectedChat);
    if (!bookingIdTarget) {
      setThreadMessages([]);
      return;
    }

    const cachedActive = messagesByThreadRef.current[selectedChat];
    const cachedArchived = archivedMessagesByThreadRef.current[selectedChat];
    const cachedTrash = trashMessagesByThreadRef.current[selectedChat];
    if (messageDisplay === 'archived') {
      if (cachedArchived) {
        setThreadMessages(cachedArchived);
      } else {
        setThreadMessages([]);
      }
    } else if (messageDisplay === 'trash') {
      if (cachedTrash) {
        setThreadMessages(cachedTrash);
      } else {
        setThreadMessages([]);
      }
    } else if (cachedActive) {
      setThreadMessages(cachedActive);
    } else {
      setThreadMessages([]);
    }

    const conversationEntry = activeConversationRef.current;
    const latestKnownMessageId = activeConversationLatestMessageId;
    const previousMeta = historyLoadMetaRef.current[selectedChat];
    const now = Date.now();
    const alreadyLoading = previousMeta?.status === 'loading';
    const fetchedForLatest =
      previousMeta?.status === 'success' && previousMeta.lastMessageId === latestKnownMessageId;
    const recentError =
      previousMeta?.status === 'error' && now - previousMeta.timestamp < HISTORY_RETRY_DELAY_MS;

    if (alreadyLoading || fetchedForLatest || recentError) {
      return;
    }

    let isCancelled = false;

    historyLoadMetaRef.current[selectedChat] = {
      status: 'loading',
      lastMessageId: previousMeta?.lastMessageId ?? null,
      timestamp: now,
    };

    const loadHistory = async () => {
      try {
        const history = await messageService.getMessageHistory(bookingIdTarget, 100, 0);
        if (isCancelled) return;

        const mapped = (history.messages ?? []).map((msg) =>
          mapMessageFromResponse(msg, conversationEntry ?? undefined, currentUser?.id ?? '')
        );

        const finalMessages = mapped;
        const activeMessages = finalMessages.filter((msg) => !msg.isArchived && !msg.isTrashed);
        const archivedMessages = finalMessages.filter((msg) => msg.isArchived && !msg.isTrashed);
        const latestFetchedId =
          finalMessages.length > 0 ? finalMessages[finalMessages.length - 1]?.id ?? null : null;

        historyLoadMetaRef.current[selectedChat] = {
          status: 'success',
          lastMessageId: latestFetchedId ?? latestKnownMessageId ?? null,
          timestamp: Date.now(),
        };
        setMessagesByThread((prev) => ({ ...prev, [selectedChat]: activeMessages }));
        setArchivedMessagesByThread((prev) => ({ ...prev, [selectedChat]: archivedMessages }));

        const cachedTrash = trashMessagesByThreadRef.current[selectedChat] ?? [];
        const viewMessages =
          messageDisplay === 'archived'
            ? archivedMessages
            : messageDisplay === 'trash'
            ? cachedTrash
            : activeMessages;
        setThreadMessages(viewMessages);

        const lastActiveMessage = activeMessages[activeMessages.length - 1] ?? null;
        const fallbackForTime =
          lastActiveMessage ?? archivedMessages[archivedMessages.length - 1] ?? cachedTrash[cachedTrash.length - 1] ?? null;
        const lastTimestamp = fallbackForTime?.createdAt
          ? new Date(fallbackForTime.createdAt).getTime()
          : activeConversationLatestMessageAt ?? Date.now();
        const unreadCount = computeUnreadFromMessages(
          history.messages,
          conversationEntry ?? undefined,
          currentUser?.id ?? ''
        );

        setConversations((prev) => {
          let changed = false;
          const next = prev.map((conv) => {
            if (conv.id !== selectedChat) return conv;
            const nextConv: ConversationEntry = {
              ...conv,
              lastMessage:
                lastActiveMessage?.text ??
                (activeMessages.length === 0
                  ? archivedMessages[archivedMessages.length - 1]?.text ??
                    (archivedMessages.length === 0
                      ? cachedTrash[cachedTrash.length - 1]?.text ?? (cachedTrash.length ? TRASH_LABEL : ARCHIVED_LABEL)
                      : ARCHIVED_LABEL)
                  : conv.lastMessage),
              timestamp: fallbackForTime?.createdAt
                ? formatRelativeTime(fallbackForTime.createdAt)
                : conv.timestamp,
              unread: unreadCount,
              latestMessageAt: lastTimestamp,
              latestMessageId: lastActiveMessage?.id ?? fallbackForTime?.id ?? conv.latestMessageId ?? null,
              primaryBookingId: bookingIdTarget,
            };
            if (
              nextConv.lastMessage !== conv.lastMessage ||
              nextConv.timestamp !== conv.timestamp ||
              nextConv.unread !== conv.unread ||
              nextConv.latestMessageAt !== conv.latestMessageAt ||
              nextConv.latestMessageId !== conv.latestMessageId ||
              nextConv.primaryBookingId !== conv.primaryBookingId
            ) {
              changed = true;
            }
            return nextConv;
          });
          if (!changed) return prev;
          return [...next].sort((a, b) => b.latestMessageAt - a.latestMessageAt);
        });

        if (
          unreadCount > 0 &&
          !markedReadThreadsRef.current.has(bookingIdTarget) &&
          !markReadFailuresRef.current.has(bookingIdTarget)
        ) {
          markedReadThreadsRef.current.add(bookingIdTarget);
          try {
            await markRead(bookingIdTarget);
            markReadFailuresRef.current.delete(bookingIdTarget);
            if (!isCancelled) {
              setConversations((prev) => {
                let changed = false;
                const next = prev.map((conv) => {
                  if (conv.id !== selectedChat || conv.unread === 0) return conv;
                  changed = true;
                  return { ...conv, unread: 0 };
                });
                return changed ? next : prev;
              });
            }
          } catch (error) {
            markedReadThreadsRef.current.delete(bookingIdTarget);
            markReadFailuresRef.current.add(bookingIdTarget);
            logger.warn('Failed to mark messages as read', { bookingId: bookingIdTarget, error });
          }
        }
      } catch (error) {
        if (isCancelled) return;
        if (isAbortError(error)) {
          if (previousMeta) {
            historyLoadMetaRef.current[selectedChat] = previousMeta;
          } else {
            delete historyLoadMetaRef.current[selectedChat];
          }
          return;
        }
        historyLoadMetaRef.current[selectedChat] = {
          status: 'error',
          lastMessageId: previousMeta?.lastMessageId ?? null,
          timestamp: Date.now(),
        };
        logger.error('Failed to load message history', { bookingId: bookingIdTarget, error });
        if (!cachedActive && !cachedArchived && !cachedTrash) {
          const mockSource = MOCK_THREADS[selectedChat] || [];
          if (mockSource.length > 0) {
            const finalMsgs: MessageWithAttachments[] = mockSource.map((m) => ({ ...m, isArchived: false }));
            setMessagesByThread((prev) => ({ ...prev, [selectedChat]: finalMsgs }));
            setArchivedMessagesByThread((prev) => ({ ...prev, [selectedChat]: [] }));
            if (messageDisplay === 'archived') {
              setThreadMessages([]);
            } else if (messageDisplay === 'trash') {
              setThreadMessages([]);
            } else {
              setThreadMessages(finalMsgs);
            }
          } else {
            setThreadMessages([]);
            setMessagesByThread((prev) => ({ ...prev, [selectedChat]: [] }));
            setArchivedMessagesByThread((prev) => ({ ...prev, [selectedChat]: [] }));
          }
        }
      }
    };

    void loadHistory();

    return () => {
      isCancelled = true;
    };
  }, [
    selectedChat,
    mailSection,
    getPrimaryBookingId,
    activeConversationLatestMessageId,
    activeConversationLatestMessageAt,
    currentUser?.id,
    messageDisplay,
  ]);

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
                className={`group relative inline-flex items-center justify-center w-10 h-10 rounded-full text-[#7E22CE] transition-colors duration-150 focus:outline-none select-none`}
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
                <div role="menu" className="absolute right-0 mt-2 w-80 bg-white border border-gray-200 rounded-lg shadow-lg z-50">
                  <ul className="max-h-80 overflow-auto p-2 space-y-2">
                    {unreadConversations.length === 0 ? (
                      <>
                        <li className="px-2 py-2 text-sm text-gray-600">
                          You’ll see student replies here once someone messages you.
                        </li>
                        <li>
                          <button
                            type="button"
                            className="w-full text-left text-sm text-gray-700 px-2 py-2 hover:bg-gray-50 rounded"
                            onClick={() => {
                              setShowMessages(false);
                              router.push('/instructor/messages');
                            }}
                          >
                            Open inbox
                          </button>
                        </li>
                      </>
                    ) : (
                      unreadConversations.map((conversation) => (
                        <li key={`unread-${conversation.id}`}>
                          <button
                            type="button"
                            onClick={() => {
                              setShowMessages(false);
                              handleConversationSelect(conversation.id);
                            }}
                            className="w-full rounded-lg px-3 py-2 text-left hover:bg-gray-50"
                          >
                            <p className="text-sm font-medium text-gray-900 truncate">{conversation.name}</p>
                            <p className="text-xs text-gray-500 truncate">
                              {conversation.lastMessage || 'New message waiting'}
                            </p>
                          </button>
                        </li>
                      ))
                    )}
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
                  <ul className="max-h-80 overflow-auto p-2 space-y-2">
                    <li className="text-sm text-gray-600 px-2 py-2">
                      No alerts right now. We’ll nudge you when there’s something to review.
                    </li>
                    <li>
                      <button
                        type="button"
                        className="w-full text-left text-sm text-gray-700 px-2 py-2 hover:bg-gray-50 rounded"
                        onClick={() => {
                          setShowNotifications(false);
                          router.push('/instructor/settings');
                        }}
                      >
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
            <button
              type="button"
              onClick={() => {
                const next = mailSection === 'templates' ? 'inbox' : 'templates';
                setMailSection(next);
                if (next === 'templates' && templates.length) {
                  const firstTemplate = templates[0];
                  if (firstTemplate) {
                    setSelectedTemplateId((prev) => prev ?? firstTemplate.id);
                  }
                }
              }}
              className="w-full flex items-center justify-between text-left focus:outline-none focus-visible:ring-0 hover:bg-transparent transform-none select-none"
              aria-expanded={mailSection === 'templates'}
           >
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Communication templates</h2>
              <p className="text-xs text-gray-500">Access saved templates for quick replies.</p>
            </div>
            <ChevronDown
              className={`w-5 h-5 text-gray-500 transition-transform ${mailSection === 'templates' ? 'rotate-180' : ''}`}
              aria-hidden="true"
            />
          </button>
        </div>

        {/* Messages interface */}
        {mailSection === 'templates' ? (
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <div className="flex h-[600px]">
              <div className="w-full md:w-1/3 border-r border-gray-200 flex flex-col">
                <div className="p-4 border-b border-gray-200 flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900">Templates</h3>
                    <p className="text-xs text-gray-500 mt-1">Choose a template to view or copy.</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleCreateTemplate()}
                    className="inline-flex items-center justify-center rounded-full border border-gray-300 bg-white p-2 text-[#7E22CE] hover:bg-purple-50 transition-colors"
                    aria-label="Create template"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                </div>
                <div className="flex-1 overflow-y-auto">
                  {templates.map((template) => {
                    const isActive = template.id === selectedTemplateId;
                    const templateContent = templateDrafts[template.id] ?? template.body ?? '';
                    const previewText =
                      deriveTemplatePreview(templateContent) || template.preview || 'Add template content';
                    const subjectLabel = template.subject?.trim() || 'Untitled template';
                    return (
                      <button
                        key={template.id}
                        type="button"
                        onClick={() => setSelectedTemplateId(template.id)}
                        className={`w-full text-left px-5 py-4 border-b border-gray-100 transition-none ${
                          isActive ? 'bg-purple-50 border-l-4 border-l-[#7E22CE]' : 'hover:bg-gray-50'
                        }`}
                      >
                        <h4 className="text-sm font-medium text-gray-900 truncate">{subjectLabel}</h4>
                        <p className="text-xs text-gray-500 mt-1 truncate">
                          {previewText || 'Add template content'}
                        </p>
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="flex-1 flex flex-col">
                {(() => {
                  const current = templates.find((item) => item.id === selectedTemplateId) || templates[0];
                  const content = current ? templateDrafts[current.id] ?? current.body : '';
                  return current ? (
                    <div className="flex-1 p-6 flex flex-col gap-4">
                      <div className="flex items-center justify-between gap-4 flex-wrap">
                        <div className="flex-1 min-w-[200px]">
                          <div className="rounded-md border border-transparent bg-white px-3 py-2 transition-all focus-within:border-[#E7DCF9] focus-within:shadow-[0_0_0_2px_rgba(219,201,246,0.25)]">
                            <input
                              ref={(element) => {
                                if (current.id === selectedTemplateId) {
                                  subjectInputRef.current = element;
                                }
                              }}
                              value={current.subject}
                              onChange={(event) => handleTemplateSubjectChange(current.id, event.target.value)}
                              placeholder="Template title"
                              aria-label="Template title"
                              className="template-title-input w-full bg-transparent text-lg font-semibold text-gray-900 border-none outline-none focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0 placeholder:text-gray-400"
                            />
                          </div>
                          <p className="text-xs text-gray-500 mt-1">Last updated manually.</p>
                        </div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <button
                            type="button"
                            onClick={() => handleRewriteTemplate(current.id)}
                            disabled={rewritingTemplateId === current.id}
                            className="inline-flex items-center gap-2 rounded-full bg-[#7E22CE] text-white px-3 py-1.5 text-xs font-medium hover:bg-[#5f1aa4] transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                          >
                            <Sparkles className="w-3.5 h-3.5" />
                            <span>{rewritingTemplateId === current.id ? 'Rewriting…' : 'Rewrite with AI'}</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => handleCopyTemplate(current.id, content)}
                            className="inline-flex items-center gap-2 rounded-full bg-white border border-gray-200 px-3 py-1.5 text-xs font-medium text-[#7E22CE] hover:bg-purple-50 transition-colors"
                          >
                            <Copy className="w-3.5 h-3.5" />
                            <span>{copiedTemplateId === current.id ? 'Copied!' : 'Copy'}</span>
                          </button>
                        </div>
                      </div>
                      <textarea
                        value={content}
                        onChange={(event) => {
                          const nextValue = event.target.value;
                          setTemplateDrafts((prev) => ({ ...prev, [current.id]: nextValue }));
                          setTemplates((prev) =>
                            prev.map((template) =>
                              template.id === current.id
                                ? { ...template, body: nextValue, preview: deriveTemplatePreview(nextValue) }
                                : template
                            )
                          );
                        }}
                        className="flex-1 border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500"
                      />
                    </div>
                  ) : (
                    <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
                      No templates available.
                    </div>
                  );
                })()}
              </div>
            </div>
          </div>
        ) : (
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <div className="flex flex-col lg:flex-row min-h-[600px]">
              <aside className="w-full lg:w-80 xl:w-96 border-b border-gray-200 lg:border-b-0 lg:border-r flex flex-col">
                <div className="p-4 border-b border-gray-200 flex items-center gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(event) => setSearchQuery(event.target.value)}
                      placeholder="Search conversations"
                      className="w-full rounded-full border border-gray-300 bg-white pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-[#7E22CE]"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => handleConversationSelect(COMPOSE_THREAD_ID)}
                    className="inline-flex items-center justify-center rounded-full bg-purple-100 p-2 text-[#7E22CE] transition-colors hover:bg-purple-200"
                    aria-label="Compose message"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                </div>
                <div className="px-4 py-3 border-b border-gray-200 flex flex-wrap gap-2 items-center">
                  {FILTER_OPTIONS.map((option) => {
                    const isActive = option.value === typeFilter;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => {
                          setTypeFilter(option.value);
                          setMessageDisplay('inbox');
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
                    onClick={() => setMessageDisplay('archived')}
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
                    onClick={() => setMessageDisplay('trash')}
                    className={`text-xs font-medium rounded-full px-3 py-1 transition-colors ${
                      messageDisplay === 'trash'
                        ? 'bg-[#7E22CE] text-white'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                  >
                    Trash
                  </button>
                </div>
                <div className="flex-1 overflow-y-auto">
                  {isLoadingConversations && conversations.length === 0 ? (
                    <div className="p-4 text-sm text-gray-500">Loading conversations…</div>
                  ) : (
                    <>
                      {conversationError && (
                        <div className="px-4 py-2 text-xs text-red-500">{conversationError}</div>
                      )}
                      {conversationSource.length > 0 ? (
                        <ul className="divide-y divide-gray-100">
                          {conversationSource.map((conversation) => {
                            const isActive = conversation.id === selectedChat;
                            const isCompose = conversation.id === COMPOSE_THREAD_ID;
                            const conversationDate =
                              !isCompose && conversation.latestMessageAt
                                ? formatShortDate(new Date(conversation.latestMessageAt))
                                : '';
                            const archivedCount = archivedMessagesByThread[conversation.id]?.length ?? 0;
                            const trashCount = trashMessagesByThread[conversation.id]?.length ?? 0;
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

                            return (
                              <li key={conversation.id}>
                                <button
                                  type="button"
                                  onClick={() => handleConversationSelect(conversation.id)}
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
                              </li>
                            );
                          })}
                        </ul>
                      ) : (
                        <div className="p-4 text-sm text-gray-500">No conversations found.</div>
                      )}
                    </>
                  )}
                </div>
              </aside>
              <div className="flex-1 flex flex-col">
                {selectedChat ? (
                  <>
                    {/* Chat header */}
                    <div className="p-4 border-b border-gray-200">
                      {isComposeView ? (
                        <div className="flex flex-col gap-3">
                          <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
                            <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">To:</span>
                            {composeRecipient ? (
                              <span className="inline-flex items-center gap-2 rounded-full bg-purple-50 border border-purple-200 px-3 py-1 text-sm text-[#7E22CE]">
                                {composeRecipient.name}
                                <button
                                  type="button"
                                  className="text-[#7E22CE] hover:text-purple-800"
                                  aria-label="Remove recipient"
                                  onClick={() => {
                                    setComposeRecipient(null);
                                    setComposeRecipientQuery('');
                                  }}
                                >
                                  <X className="w-3 h-3" />
                                </button>
                              </span>
                            ) : (
                              <div className="relative w-full sm:max-w-xs">
                                <input
                                  type="text"
                                  value={composeRecipientQuery}
                                  onChange={(event) => setComposeRecipientQuery(event.target.value)}
                                  placeholder="Search contacts..."
                                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-[#7E22CE]"
                                />
                                {composeRecipientQuery && (
                                  <ul className="absolute z-40 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg">
                                    {composeSuggestions.length > 0 ? (
                                      composeSuggestions.map((suggestion) => (
                                        <li key={suggestion.id}>
                                          <button
                                            type="button"
                                            onClick={() => handleComposeRecipientSelect(suggestion)}
                                            className="w-full px-3 py-2 text-left text-sm hover:bg-purple-50"
                                          >
                                            <span className="font-medium text-gray-900">{suggestion.name}</span>
                                            <span className="block text-xs text-gray-500">
                                              {suggestion.type === 'platform' ? 'Platform' : 'Student'}
                                            </span>
                                          </button>
                                        </li>
                                      ))
                                    ) : (
                                      <li className="px-3 py-2 text-xs text-gray-500">No contacts found</li>
                                    )}
                                  </ul>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div
                              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                                activeConversation?.type === 'platform'
                                  ? 'bg-blue-100 text-blue-600'
                                  : 'bg-purple-100 text-purple-600'
                              }`}
                            >
                              {activeConversation?.avatar}
                            </div>
                            <div>
                              <h3 className="font-medium text-gray-900">{activeConversation?.name}</h3>
                              <p className="text-xs text-gray-500">
                                {activeConversation?.type === 'platform' ? 'Platform' : 'Student'}
                              </p>
                            </div>
                          </div>
                          {activeConversation && (
                            <div className="relative" ref={threadMenuRef}>
                              <button
                                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                                onClick={() => setShowThreadMenu((v) => !v)}
                                aria-expanded={showThreadMenu}
                                aria-haspopup="menu"
                              >
                                <MoreVertical className="w-4 h-4 text-gray-500" />
                              </button>
                              {showThreadMenu && (
                                <div
                                  role="menu"
                                  className="absolute right-0 mt-2 w-56 bg-white border border-gray-200 rounded-lg shadow-lg z-40"
                                >
                                  <div className="p-3 border-b border-gray-100">
                                    <p className="text-sm font-medium text-gray-900">Booking IDs</p>
                                  </div>
                                  <ul className="max-h-60 overflow-auto p-2 space-y-1 text-sm">
                                    {(activeConversation.bookingIds || []).length === 0 ? (
                                      <li className="text-gray-500 px-2 py-1">No bookings</li>
                                    ) : (
                                      (activeConversation.bookingIds || []).map((bid) => (
                                        <li key={bid} className="px-2 py-1 text-gray-800 hover:bg-gray-50 rounded">
                                          {bid}
                                        </li>
                                      ))
                                    )}
                                  </ul>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Messages */}
                    <div className="flex-1 overflow-y-auto p-4 space-y-4">
                      {isComposeView && threadMessages.length === 0 && (
                        <div className="flex items-center justify-center py-12">
                          <p className="text-sm text-gray-500">Draft your message and choose who to send it to.</p>
                        </div>
                      )}
                      {threadMessages.map((message, index) => {
                        const attachmentList = (message as MessageWithAttachments).attachments || [];
                        const displayText = message.text?.trim();
                        const bubbleClasses =
                          message.sender === 'instructor'
                            ? 'bg-[#7E22CE] text-white'
                            : message.sender === 'platform'
                            ? 'bg-blue-100 text-blue-800'
                            : 'bg-gray-100 text-gray-800';
                        const attachmentWrapper =
                          message.sender === 'instructor' ? 'bg-white/10 border border-white/20' : 'bg-white border border-gray-200';
                        const isLastInstructor =
                          message.sender === 'instructor' && index === threadMessages.length - 1;
                        const delivery = message.delivery;
                        const deliveryLabel = (() => {
                          if (!delivery) return 'Delivered';
                          if (delivery.status === 'read') return `Read ${delivery.timeLabel}`;
                          if (delivery.status === 'delivered') return `Delivered ${delivery.timeLabel}`;
                          return 'Delivered';
                        })();
                        const threadIdForActions = selectedChat ?? '';
                        const isArchivedMessage = Boolean(message.isArchived);
                        const isTrashedMessage = Boolean(message.isTrashed);
                        const archivePending = !!pendingArchiveIds[message.id];
                        const deletePending = !!pendingDeleteIds[message.id];
                        const canArchive =
                          messageDisplay === 'inbox' &&
                          !isArchivedMessage &&
                          !isTrashedMessage &&
                          threadIdForActions &&
                          threadIdForActions !== COMPOSE_THREAD_ID;
                        const canDelete =
                          messageDisplay === 'inbox' &&
                          message.sender === 'instructor' &&
                          threadIdForActions &&
                          threadIdForActions !== COMPOSE_THREAD_ID;
                        const showControls = canArchive || canDelete;
                        const shortDate =
                          formatShortDate(message.createdAt) ||
                          formatShortDate((message as { timestamp?: string }).timestamp ?? null) ||
                          '';
                        const statusLabelClass =
                          message.sender === 'instructor'
                            ? 'text-white/80'
                            : message.sender === 'platform'
                            ? 'text-blue-700'
                            : 'text-gray-500';

                        return (
                          <div
                            key={message.id}
                            className={`flex ${message.sender === 'instructor' ? 'justify-end' : 'justify-start'}`}
                          >
                            <div
                              className={`group relative max-w-xs lg:max-w-md rounded-lg px-4 pt-6 pb-3 pr-14 ${bubbleClasses}`}
                            >
                              {(shortDate || showControls) && (
                                <div
                                  className={`absolute top-2 right-3 flex flex-col items-end text-[11px] ${
                                    message.sender === 'instructor'
                                      ? 'text-white/80'
                                      : message.sender === 'platform'
                                      ? 'text-blue-700'
                                      : 'text-gray-500'
                                  }`}
                                >
                                  {shortDate && <span className="leading-none mb-2">{shortDate}</span>}
                                  {showControls && (
                                    <div className="flex items-center gap-2">
                                      {canArchive && (
                                        <button
                                          type="button"
                                          aria-label="Archive message"
                                          title="Archive message"
                                          onClick={(event) => handleArchiveButtonClick(event, threadIdForActions, message)}
                                          disabled={archivePending}
                                          className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-white/80 text-gray-600 shadow-sm transition-colors hover:text-[#7E22CE] disabled:cursor-not-allowed disabled:opacity-60"
                                        >
                                          <Archive className="w-3 h-3" />
                                        </button>
                                      )}
                                      {canDelete && (
                                        <button
                                          type="button"
                                          aria-label="Delete message"
                                          title="Delete message"
                                          onClick={(event) => handleDeleteButtonClick(event, threadIdForActions, message)}
                                          disabled={deletePending}
                                          className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-white/80 text-gray-600 shadow-sm transition-colors hover:text-[#E11D48] disabled:cursor-not-allowed disabled:opacity-60"
                                        >
                                          <Trash2 className="w-3 h-3" />
                                        </button>
                                      )}
                                    </div>
                                  )}
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
                              {!shortDate && (
                                <p className="text-xs opacity-70 mt-1">{message.timestamp}</p>
                              )}
                              {isArchivedMessage && (
                                <p className={`text-[10px] uppercase tracking-wide mt-1 ${statusLabelClass}`}>
                                  Archived
                                </p>
                              )}
                              {isTrashedMessage && (
                                <p className={`text-[10px] uppercase tracking-wide mt-1 ${statusLabelClass}`}>
                                  Trashed
                                </p>
                              )}
                              {isLastInstructor && (
                                <p
                                  className={`text-[10px] opacity-80 mt-0.5 ${
                                    message.sender === 'instructor' ? 'text-right' : ''
                                  }`}
                                >
                                  {deliveryLabel}
                                </p>
                              )}
                            </div>
                          </div>
                        );
                      })}
                      <div ref={messagesEndRef} />
                    </div>

                    {/* Message input */}
                    {messageDisplay !== 'inbox' ? (
                      <div className="p-6 border-t border-gray-200 text-sm text-gray-500">
                        {messageDisplay === 'archived'
                          ? 'Archived messages are read-only.'
                          : 'Trashed messages are read-only.'}
                      </div>
                    ) : (
                      <div className="p-4 border-t border-gray-200 space-y-3">
                        {pendingAttachments.length > 0 && (
                          <div className="flex flex-wrap gap-2">
                            {pendingAttachments.map((file, index) => (
                              <span
                                key={`${file.name}-${index}`}
                                className="inline-flex items-center gap-2 rounded-full bg-purple-50 border border-purple-200 px-3 py-1 text-xs text-[#7E22CE]"
                              >
                                <span className="max-w-[8rem] truncate" title={file.name}>
                                  {file.name}
                                </span>
                                <button
                                  type="button"
                                  className="text-[#7E22CE] hover:text-purple-800"
                                  aria-label={`Remove attachment ${file.name}`}
                                  onClick={() => removeAttachment(index)}
                                >
                                  <X className="w-3 h-3" />
                                </button>
                              </span>
                            ))}
                          </div>
                        )}
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            className="h-10 w-10 flex items-center justify-center rounded-full border border-gray-300 text-gray-500 hover:text-[#7E22CE] hover:border-[#D4B5F0] transition-colors"
                            title="Attach file"
                            aria-label="Attach file"
                            onClick={() => fileInputRef.current?.click()}
                          >
                            <Plus className="w-4 h-4" />
                          </button>
                          <input
                            ref={fileInputRef}
                            type="file"
                            multiple
                            className="hidden"
                            onChange={(event) => {
                              handleAttachmentSelection(event.target.files);
                              if (event.target.value) event.target.value = '';
                            }}
                          />
                          <textarea
                            value={messageText}
                            onChange={(e) => handleMessageChange(e.target.value)}
                            onKeyPress={handleKeyPress}
                            placeholder="Type your message..."
                            className="flex-1 resize-none border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] focus:border-purple-500 min-h-[2.5rem]"
                            rows={1}
                          />
                          <button
                            type="button"
                            onClick={handleSendMessage}
                            disabled={isSendDisabled}
                            className="h-10 w-10 flex items-center justify-center bg-[#7E22CE] text-white rounded-full hover:bg-[#5f1aa4] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          >
                            <Send className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    )}
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
  );
}
