'use client';

import { fetchWithAuth } from '@/lib/api';

export type MessageItem = {
  id: string;
  text: string;
  sender: 'instructor' | 'student' | 'platform';
  timestamp: string;
};

export type ConversationSummary = {
  id: string; // booking_id or thread id
  name: string;
  lastMessage: string;
  timestamp: string;
  unread: number;
  avatar: string; // initials
  type: 'student' | 'platform';
};

export async function getUnreadCount(): Promise<number> {
  const res = await fetchWithAuth('/api/messages/unread-count');
  if (!res.ok) return 0;
  const data = (await res.json()) as { unread_count?: number };
  return Number(data?.unread_count ?? 0);
}

// Basic history fetch by booking_id; backend guarantees chronological order
export async function getHistory(bookingId: string): Promise<MessageItem[]> {
  const res = await fetchWithAuth(`/api/messages/history/${encodeURIComponent(bookingId)}`);
  if (!res.ok) return [];
  const data = (await res.json()) as { messages: Array<{ id: string; text: string; sender?: string; created_at?: string }> };
  return (data?.messages || []).map((m) => ({
    id: String(m.id),
    text: String(m.text ?? ''),
    sender: (m.sender as 'instructor' | 'student' | 'platform') ?? 'platform',
    timestamp: String(m.created_at ?? ''),
  }));
}

export async function sendMessage(bookingId: string, text: string): Promise<{ id: string } | null> {
  const res = await fetchWithAuth('/api/messages/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ booking_id: bookingId, content: text }),
  });
  if (!res.ok) return null;
  const data = (await res.json()) as { id?: string; message?: { id?: string } };
  const messageId = data?.message?.id ?? data?.id;
  return messageId ? { id: messageId } : null;
}

export async function markRead(bookingId: string): Promise<number> {
  const res = await fetchWithAuth('/api/messages/mark-read', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ booking_id: bookingId }),
  });
  if (!res.ok) return 0;
  const data = (await res.json()) as { messages_marked?: number };
  return Number(data?.messages_marked ?? 0);
}
