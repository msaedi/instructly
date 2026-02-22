/**
 * Tests for message processing utilities
 */

import {
  isAbortError,
  getBookingActivityTimestamp,
  mapMessageFromResponse,
  computeUnreadFromMessages,
} from '../messages';
import type { Booking } from '@/features/shared/api/types';
import type { ConversationEntry } from '../../types';

jest.mock('@/components/messaging/formatters', () => ({
  formatRelativeTimestamp: jest.fn((input: string) => `relative(${input})`),
  formatTimeLabel: jest.fn((input: string) => `time(${input})`),
}));

const makeConversation = (overrides?: Partial<ConversationEntry>): ConversationEntry => ({
  id: 'conv-1',
  name: 'Test Student',
  lastMessage: 'Hello',
  timestamp: '2025-01-01T12:00:00Z',
  unread: 0,
  avatar: '',
  type: 'student',
  bookingIds: [],
  primaryBookingId: null,
  studentId: 'student-1',
  instructorId: 'instructor-1',
  latestMessageAt: 0,
  ...overrides,
});

describe('messages', () => {
  describe('isAbortError', () => {
    it('returns true for an AbortError', () => {
      const err = new DOMException('Aborted', 'AbortError');
      expect(isAbortError(err)).toBe(true);
    });

    it('returns false for a regular error', () => {
      expect(isAbortError(new Error('fail'))).toBe(false);
    });

    it('returns false for null', () => {
      expect(isAbortError(null)).toBe(false);
    });

    it('returns false for undefined', () => {
      expect(isAbortError(undefined)).toBe(false);
    });

    it('returns false for a non-object', () => {
      expect(isAbortError('string')).toBe(false);
    });

    it('returns false when name is not a string', () => {
      expect(isAbortError({ name: 42 })).toBe(false);
    });

    it('returns false when name is a different string', () => {
      expect(isAbortError({ name: 'TypeError' })).toBe(false);
    });
  });

  describe('getBookingActivityTimestamp', () => {
    it('returns updated_at when present', () => {
      const booking = { updated_at: '2025-01-05' } as unknown as Booking;
      expect(getBookingActivityTimestamp(booking)).toBe('2025-01-05');
    });

    it('falls back to completed_at', () => {
      const booking = { completed_at: '2025-01-04' } as unknown as Booking;
      expect(getBookingActivityTimestamp(booking)).toBe('2025-01-04');
    });

    it('falls back to confirmed_at', () => {
      const booking = { confirmed_at: '2025-01-03' } as unknown as Booking;
      expect(getBookingActivityTimestamp(booking)).toBe('2025-01-03');
    });

    it('falls back to cancelled_at', () => {
      const booking = { cancelled_at: '2025-01-02' } as unknown as Booking;
      expect(getBookingActivityTimestamp(booking)).toBe('2025-01-02');
    });

    it('falls back to created_at', () => {
      const booking = { created_at: '2025-01-01' } as unknown as Booking;
      expect(getBookingActivityTimestamp(booking)).toBe('2025-01-01');
    });

    it('falls back to booking_date', () => {
      const booking = { booking_date: '2025-01-01' } as unknown as Booking;
      expect(getBookingActivityTimestamp(booking)).toBe('2025-01-01');
    });

    it('returns undefined when no timestamps exist', () => {
      const booking = {} as unknown as Booking;
      expect(getBookingActivityTimestamp(booking)).toBeUndefined();
    });

    it('skips null updated_at and returns next available', () => {
      const booking = { updated_at: null, completed_at: null, confirmed_at: '2025-01-03' } as unknown as Booking;
      expect(getBookingActivityTimestamp(booking)).toBe('2025-01-03');
    });
  });

  describe('mapMessageFromResponse', () => {
    const currentUserId = 'user-1';

    it('marks message as instructor when sender matches currentUserId', () => {
      const msg = { id: 'm1', content: 'Hello', sender_id: 'user-1', created_at: '2025-01-01T10:00:00Z' };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.sender).toBe('instructor');
    });

    it('marks message as student when sender matches studentId', () => {
      const msg = { id: 'm1', content: 'Hi', sender_id: 'student-1', created_at: '2025-01-01T10:00:00Z' };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.sender).toBe('student');
    });

    it('marks message as platform when sender is neither instructor nor student', () => {
      const msg = { id: 'm1', content: 'System msg', sender_id: 'system-1', created_at: '2025-01-01T10:00:00Z' };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.sender).toBe('platform');
    });

    it('defaults to student when conversation is undefined', () => {
      const msg = { id: 'm1', content: 'Hi', sender_id: 'unknown', created_at: '2025-01-01T10:00:00Z' };
      const result = mapMessageFromResponse(msg, undefined, currentUserId);
      expect(result.sender).toBe('student');
    });

    it('sets delivery status to read when recipientRead exists', () => {
      const msg = {
        id: 'm1',
        content: 'Hello',
        sender_id: 'user-1',
        created_at: '2025-01-01T10:00:00Z',
        read_by: [{ user_id: 'student-1', read_at: '2025-01-01T10:05:00Z' }],
      };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.delivery).toEqual({
        status: 'read',
        timeLabel: 'time(2025-01-01T10:05:00Z)',
      });
    });

    it('uses created_at when recipientRead.read_at is null', () => {
      const msg = {
        id: 'm1',
        content: 'Hello',
        sender_id: 'user-1',
        created_at: '2025-01-01T10:00:00Z',
        read_by: [{ user_id: 'student-1', read_at: null }],
        delivered_at: '2025-01-01T10:01:00Z',
      };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      // read_at is null/falsy so recipientRead is not found, falls to delivered_at
      expect(result.delivery).toEqual({
        status: 'delivered',
        timeLabel: 'time(2025-01-01T10:01:00Z)',
      });
    });

    it('sets delivery status to delivered when delivered_at exists', () => {
      const msg = {
        id: 'm1',
        content: 'Hello',
        sender_id: 'user-1',
        created_at: '2025-01-01T10:00:00Z',
        delivered_at: '2025-01-01T10:01:00Z',
        read_by: [],
      };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.delivery).toEqual({
        status: 'delivered',
        timeLabel: 'time(2025-01-01T10:01:00Z)',
      });
    });

    it('falls back to created_at for delivery when no delivered_at', () => {
      const msg = {
        id: 'm1',
        content: 'Hello',
        sender_id: 'user-1',
        created_at: '2025-01-01T10:00:00Z',
        read_by: [],
      };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.delivery).toEqual({
        status: 'delivered',
        timeLabel: 'time(2025-01-01T10:00:00Z)',
      });
    });

    it('does not set delivery for non-instructor messages', () => {
      const msg = {
        id: 'm1',
        content: 'Hello',
        sender_id: 'student-1',
        created_at: '2025-01-01T10:00:00Z',
      };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.delivery).toBeUndefined();
    });

    it('handles deleted message', () => {
      const msg = {
        id: 'm1',
        content: 'original text',
        sender_id: 'student-1',
        created_at: '2025-01-01T10:00:00Z',
        is_deleted: true,
      };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.text).toBe('This message was deleted');
      expect(result.isDeleted).toBe(true);
      expect(result.isArchived).toBe(true);
    });

    it('handles edited message', () => {
      const msg = {
        id: 'm1',
        content: 'edited text',
        sender_id: 'student-1',
        created_at: '2025-01-01T10:00:00Z',
        edited_at: '2025-01-01T11:00:00Z',
      };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.isEdited).toBe(true);
      expect(result.editedAt).toBe('2025-01-01T11:00:00Z');
    });

    it('handles null content', () => {
      const msg = { id: 'm1', content: null, sender_id: 'student-1' };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.text).toBe('');
    });

    it('preserves delivered_at and read_by from API response', () => {
      const msg = {
        id: 'm1',
        content: 'msg',
        sender_id: 'student-1',
        delivered_at: '2025-01-01T10:01:00Z',
        read_by: [{ user_id: 'user-1', read_at: '2025-01-01T10:05:00Z' }],
      };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.delivered_at).toBe('2025-01-01T10:01:00Z');
      expect(result.read_by).toEqual([{ user_id: 'user-1', read_at: '2025-01-01T10:05:00Z' }]);
    });

    it('handles reactions as array of objects', () => {
      const msg = {
        id: 'm1',
        content: 'msg',
        sender_id: 'student-1',
        reactions: [
          { emoji: '👍', user_id: 'user-1' },
          { emoji: '👍', user_id: 'student-1' },
          { emoji: '❤️', user_id: 'user-1' },
        ],
      };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.reactions).toEqual({ '👍': 2, '❤️': 1 });
    });

    it('handles reactions as a pre-computed object', () => {
      const msg = {
        id: 'm1',
        content: 'msg',
        sender_id: 'student-1',
        reactions: { '👍': 3, '❤️': 1 },
      };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.reactions).toEqual({ '👍': 3, '❤️': 1 });
    });

    it('returns undefined reactions when reactions is null', () => {
      const msg = { id: 'm1', content: 'msg', sender_id: 'student-1', reactions: null };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.reactions).toBeUndefined();
    });

    it('returns undefined reactions for non-object/non-array value', () => {
      const msg = { id: 'm1', content: 'msg', sender_id: 'student-1', reactions: 'invalid' };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      // 'invalid' is typeof 'string', not object -> undefined
      expect(result.reactions).toBeUndefined();
    });

    it('skips invalid items in reactions array', () => {
      const msg = {
        id: 'm1',
        content: 'msg',
        sender_id: 'student-1',
        reactions: [
          null,
          'not an object',
          { emoji: 42 }, // emoji is not a string
          { emoji: '👍', user_id: 'user-1' },
        ],
      };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.reactions).toEqual({ '👍': 1 });
    });

    it('derives my_reactions from explicit my_reactions array', () => {
      const msg = {
        id: 'm1',
        content: 'msg',
        sender_id: 'student-1',
        my_reactions: ['👍', '❤️'],
      };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.my_reactions).toEqual(['👍', '❤️']);
    });

    it('filters out non-string values in my_reactions', () => {
      const msg = {
        id: 'm1',
        content: 'msg',
        sender_id: 'student-1',
        my_reactions: ['👍', 42, null, '❤️'] as unknown as string[],
      };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.my_reactions).toEqual(['👍', '❤️']);
    });

    it('derives my_reactions from reactions array when my_reactions is null', () => {
      const msg = {
        id: 'm1',
        content: 'msg',
        sender_id: 'student-1',
        my_reactions: null,
        reactions: [
          { emoji: '👍', user_id: 'user-1' },
          { emoji: '❤️', user_id: 'student-1' },
        ],
      };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.my_reactions).toEqual(['👍']);
    });

    it('returns undefined my_reactions when reactions is not array and my_reactions is null', () => {
      const msg = {
        id: 'm1',
        content: 'msg',
        sender_id: 'student-1',
        my_reactions: null,
        reactions: { '👍': 1 },
      };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.my_reactions).toBeUndefined();
    });

    it('skips invalid items when deriving my_reactions from reactions array', () => {
      const msg = {
        id: 'm1',
        content: 'msg',
        sender_id: 'student-1',
        my_reactions: null,
        reactions: [
          null,
          { user_id: 'user-1', emoji: 42 }, // emoji not string
          { user_id: 'user-1', emoji: '👍' },
        ],
      };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.my_reactions).toEqual(['👍']);
    });

    it('handles instructor message with no recipientId (studentId is null)', () => {
      const conv = makeConversation({ studentId: null });
      const msg = {
        id: 'm1',
        content: 'msg',
        sender_id: 'user-1',
        created_at: '2025-01-01T10:00:00Z',
        read_by: [{ user_id: 'someone', read_at: '2025-01-01T10:05:00Z' }],
      };
      const result = mapMessageFromResponse(msg, conv, currentUserId);
      // recipientId is null, so recipientRead is undefined, falls to delivered fallback
      expect(result.delivery?.status).toBe('delivered');
    });

    it('preserves senderId when sender_id is present', () => {
      const msg = { id: 'm1', content: 'msg', sender_id: 'student-1', created_at: '2025-01-01T10:00:00Z' };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.senderId).toBe('student-1');
    });

    it('does not set senderId when sender_id is null', () => {
      const msg = { id: 'm1', content: 'msg', sender_id: null };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.senderId).toBeUndefined();
    });

    it('does not set isArchived when is_deleted is undefined', () => {
      const msg = { id: 'm1', content: 'msg', sender_id: 'student-1' };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.isArchived).toBeUndefined();
    });

    it('sets isArchived to false when is_deleted is false', () => {
      const msg = { id: 'm1', content: 'msg', sender_id: 'student-1', is_deleted: false };
      const result = mapMessageFromResponse(msg, makeConversation(), currentUserId);
      expect(result.isArchived).toBe(false);
    });
  });

  describe('computeUnreadFromMessages', () => {
    it('returns 0 when messages is undefined', () => {
      expect(computeUnreadFromMessages(undefined, makeConversation(), 'user-1')).toBe(0);
    });

    it('returns 0 when conversation is undefined', () => {
      expect(computeUnreadFromMessages([], undefined, 'user-1')).toBe(0);
    });

    it('counts messages not sent by current user and not read', () => {
      const messages = [
        { id: 'm1', sender_id: 'student-1', read_by: [] },
        { id: 'm2', sender_id: 'student-1', read_by: [{ user_id: 'user-1', read_at: '2025-01-01T10:00:00Z' }] },
        { id: 'm3', sender_id: 'student-1', read_by: [] },
      ];
      expect(computeUnreadFromMessages(messages, makeConversation(), 'user-1')).toBe(2);
    });

    it('skips messages sent by current user', () => {
      const messages = [
        { id: 'm1', sender_id: 'user-1', read_by: [] },
        { id: 'm2', sender_id: 'user-1', read_by: [] },
      ];
      expect(computeUnreadFromMessages(messages, makeConversation(), 'user-1')).toBe(0);
    });

    it('counts messages with null read_by as unread', () => {
      const messages = [
        { id: 'm1', sender_id: 'student-1', read_by: null },
      ];
      expect(computeUnreadFromMessages(messages, makeConversation(), 'user-1')).toBe(1);
    });

    it('does not count message as unread when read_at is present', () => {
      const messages = [
        {
          id: 'm1',
          sender_id: 'student-1',
          read_by: [{ user_id: 'user-1', read_at: '2025-01-01T10:00:00Z' }],
        },
      ];
      expect(computeUnreadFromMessages(messages, makeConversation(), 'user-1')).toBe(0);
    });

    it('counts message as unread when read_at is null in read_by entry', () => {
      const messages = [
        {
          id: 'm1',
          sender_id: 'student-1',
          read_by: [{ user_id: 'user-1', read_at: null }],
        },
      ];
      // read_at is null, so !!null is false -> hasRead is false -> counted as unread
      expect(computeUnreadFromMessages(messages, makeConversation(), 'user-1')).toBe(1);
    });
  });
});
