import {
  mapMessageFromResponse,
  isAbortError,
  getBookingActivityTimestamp,
  computeUnreadFromMessages,
} from '@/components/instructor/messages/utils/messages';
import type { ConversationEntry } from '@/components/instructor/messages/types';
import type { Booking } from '@/features/shared/api/types';

describe('isAbortError', () => {
  it('should return true for AbortError', () => {
    const abortError = new DOMException('Aborted', 'AbortError');
    expect(isAbortError(abortError)).toBe(true);
  });

  it('should return false for other errors', () => {
    const error = new Error('Some error');
    expect(isAbortError(error)).toBe(false);
  });

  it('should return false for null', () => {
    expect(isAbortError(null)).toBe(false);
  });

  it('should return false for undefined', () => {
    expect(isAbortError(undefined)).toBe(false);
  });

  it('should return false for non-object values', () => {
    expect(isAbortError('string')).toBe(false);
    expect(isAbortError(123)).toBe(false);
    expect(isAbortError(true)).toBe(false);
  });

  it('should return false for objects with non-string name', () => {
    expect(isAbortError({ name: 123 })).toBe(false);
    expect(isAbortError({ name: null })).toBe(false);
  });
});

describe('getBookingActivityTimestamp', () => {
  it('should return updated_at when available', () => {
    const booking = {
      updated_at: '2024-01-05T12:00:00Z',
      completed_at: '2024-01-04T12:00:00Z',
      confirmed_at: '2024-01-03T12:00:00Z',
      created_at: '2024-01-01T12:00:00Z',
    } as unknown as Booking;
    expect(getBookingActivityTimestamp(booking)).toBe('2024-01-05T12:00:00Z');
  });

  it('should return completed_at when updated_at is null', () => {
    const booking = {
      updated_at: null,
      completed_at: '2024-01-04T12:00:00Z',
      confirmed_at: '2024-01-03T12:00:00Z',
      created_at: '2024-01-01T12:00:00Z',
    } as unknown as Booking;
    expect(getBookingActivityTimestamp(booking)).toBe('2024-01-04T12:00:00Z');
  });

  it('should return confirmed_at when prior fields are null', () => {
    const booking = {
      updated_at: null,
      completed_at: null,
      confirmed_at: '2024-01-03T12:00:00Z',
      created_at: '2024-01-01T12:00:00Z',
    } as unknown as Booking;
    expect(getBookingActivityTimestamp(booking)).toBe('2024-01-03T12:00:00Z');
  });

  it('should return cancelled_at when prior fields are null', () => {
    const booking = {
      updated_at: null,
      completed_at: null,
      confirmed_at: null,
      cancelled_at: '2024-01-02T12:00:00Z',
      created_at: '2024-01-01T12:00:00Z',
    } as unknown as Booking;
    expect(getBookingActivityTimestamp(booking)).toBe('2024-01-02T12:00:00Z');
  });

  it('should return created_at when prior fields are null', () => {
    const booking = {
      created_at: '2024-01-01T12:00:00Z',
    } as unknown as Booking;
    expect(getBookingActivityTimestamp(booking)).toBe('2024-01-01T12:00:00Z');
  });

  it('should return booking_date when all other fields are null', () => {
    const booking = {
      booking_date: '2024-01-01',
    } as unknown as Booking;
    expect(getBookingActivityTimestamp(booking)).toBe('2024-01-01');
  });

  it('should return undefined when no timestamp fields exist', () => {
    const booking = {} as unknown as Booking;
    expect(getBookingActivityTimestamp(booking)).toBeUndefined();
  });
});

describe('computeUnreadFromMessages', () => {
  const currentUserId = 'user-1';
  const baseConversation: ConversationEntry = {
    id: 'conv-1',
    studentId: 'student-1',
    name: 'Student',
    lastMessage: '',
    timestamp: '',
    unread: 0,
    avatar: '',
    type: 'student' as const,
    bookingIds: ['booking-1'],
    primaryBookingId: 'booking-1',
    instructorId: 'instructor-1',
    latestMessageAt: Date.now(),
  };

  it('should return 0 for undefined messages', () => {
    expect(computeUnreadFromMessages(undefined, baseConversation, currentUserId)).toBe(0);
  });

  it('should return 0 for undefined conversation', () => {
    expect(computeUnreadFromMessages([], undefined, currentUserId)).toBe(0);
  });

  it('should return 0 for empty messages array', () => {
    expect(computeUnreadFromMessages([], baseConversation, currentUserId)).toBe(0);
  });

  it('should not count messages from current user', () => {
    const messages = [
      { id: 'msg-1', sender_id: currentUserId, read_by: [] },
      { id: 'msg-2', sender_id: currentUserId, read_by: [] },
    ];
    expect(computeUnreadFromMessages(messages, baseConversation, currentUserId)).toBe(0);
  });

  it('should count unread messages from other users', () => {
    const messages = [
      { id: 'msg-1', sender_id: 'other-user', read_by: [] },
      { id: 'msg-2', sender_id: 'other-user', read_by: null },
    ];
    expect(computeUnreadFromMessages(messages, baseConversation, currentUserId)).toBe(2);
  });

  it('should not count messages that are already read by current user', () => {
    const messages = [
      {
        id: 'msg-1',
        sender_id: 'other-user',
        read_by: [{ user_id: currentUserId, read_at: '2024-01-01T12:00:00Z' }],
      },
      { id: 'msg-2', sender_id: 'other-user', read_by: [] },
    ];
    expect(computeUnreadFromMessages(messages, baseConversation, currentUserId)).toBe(1);
  });

  it('should handle mixed messages correctly', () => {
    const messages = [
      { id: 'msg-1', sender_id: currentUserId, read_by: [] }, // own - skip
      { id: 'msg-2', sender_id: 'other-user', read_by: [] }, // unread
      {
        id: 'msg-3',
        sender_id: 'other-user',
        read_by: [{ user_id: currentUserId, read_at: '2024-01-01T12:00:00Z' }],
      }, // read
      { id: 'msg-4', sender_id: 'other-user', read_by: [] }, // unread
    ];
    expect(computeUnreadFromMessages(messages, baseConversation, currentUserId)).toBe(2);
  });
});

describe('mapMessageFromResponse', () => {
  const currentUserId = 'instructor1';
  const studentId = 'student1';

  const baseConversation: ConversationEntry = {
    id: 'booking1',
    studentId,
    name: 'John Student',
    lastMessage: '',
    timestamp: '',
    unread: 0,
    avatar: '',
    type: 'student' as const,
    bookingIds: ['booking1'],
    primaryBookingId: 'booking1',
    instructorId: 'instructor1',
    latestMessageAt: Date.now(),
  };

  const baseMessage = {
    id: 'msg1',
    content: 'Hello',
    sender_id: studentId,
    conversation_id: 'conversation1',
    created_at: '2024-01-01T12:00:00Z',
    booking_id: 'booking1',
  };

  describe('delivered_at field preservation', () => {
    it('should preserve delivered_at field when present', () => {
      const message = {
        ...baseMessage,
        sender_id: currentUserId, // Instructor sending
        delivered_at: '2024-01-01T12:00:01Z',
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.delivered_at).toBe('2024-01-01T12:00:01Z');
    });

    it('should handle null delivered_at', () => {
      const message = {
        ...baseMessage,
        sender_id: currentUserId,
        delivered_at: null,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.delivered_at).toBeUndefined();
    });

    it('should handle missing delivered_at field', () => {
      const message = {
        ...baseMessage,
        sender_id: currentUserId,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.delivered_at).toBeUndefined();
    });
  });

  describe('read_by field preservation', () => {
    it('should preserve read_by array when present', () => {
      const message = {
        ...baseMessage,
        sender_id: currentUserId,
        read_by: [
          { user_id: 'user2', read_at: '2024-01-01T12:00:02Z' },
          { user_id: 'user3', read_at: '2024-01-01T12:00:03Z' },
        ],
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.read_by).toEqual([
        { user_id: 'user2', read_at: '2024-01-01T12:00:02Z' },
        { user_id: 'user3', read_at: '2024-01-01T12:00:03Z' },
      ]);
    });

    it('should handle empty read_by array', () => {
      const message = {
        ...baseMessage,
        sender_id: currentUserId,
        read_by: [],
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.read_by).toEqual([]);
    });

    it('should handle missing read_by field', () => {
      const message = {
        ...baseMessage,
        sender_id: currentUserId,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.read_by).toBeUndefined();
    });
  });

  describe('delivery status calculation', () => {
    it('should set delivery status to "read" when message has been read by recipient', () => {
      const message = {
        ...baseMessage,
        sender_id: currentUserId,
        delivered_at: '2024-01-01T12:00:01Z',
        read_by: [{ user_id: studentId, read_at: '2024-01-01T12:00:05Z' }],
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.delivery?.status).toBe('read');
    });

    it('should set delivery status to "delivered" when message has delivered_at but not read', () => {
      const message = {
        ...baseMessage,
        sender_id: currentUserId,
        delivered_at: '2024-01-01T12:00:01Z',
        read_by: [],
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.delivery?.status).toBe('delivered');
    });

    it('should default to "delivered" status when delivered_at is missing', () => {
      const message = {
        ...baseMessage,
        sender_id: currentUserId,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.delivery?.status).toBe('delivered');
    });
  });

  describe('sender type detection', () => {
    it('should identify instructor as sender when sender_id matches currentUserId', () => {
      const message = {
        ...baseMessage,
        sender_id: currentUserId,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.sender).toBe('instructor');
    });

    it('should identify student as sender when sender_id matches studentId', () => {
      const message = {
        ...baseMessage,
        sender_id: studentId,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.sender).toBe('student');
    });

    it('should identify platform as sender for system messages', () => {
      const platformUserId = 'platform-system';
      const message = {
        ...baseMessage,
        sender_id: platformUserId,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.sender).toBe('platform');
    });
  });

  describe('message mapping completeness', () => {
    it('should map all essential message fields', () => {
      const message = {
        id: 'msg1',
        content: 'Test message',
        sender_id: currentUserId,
        conversation_id: 'conversation1',
        created_at: '2024-01-01T12:00:00Z',
        booking_id: 'booking1',
        delivered_at: '2024-01-01T12:00:01Z',
        read_by: [{ user_id: studentId, read_at: '2024-01-01T12:00:05Z' }],
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result).toMatchObject({
        id: 'msg1',
        text: 'Test message',
        sender: 'instructor',
        senderId: currentUserId,
        createdAt: '2024-01-01T12:00:00Z',
        delivered_at: '2024-01-01T12:00:01Z',
        read_by: [{ user_id: studentId, read_at: '2024-01-01T12:00:05Z' }],
      });
      expect(result.timestamp).toBeDefined(); // Formatted timestamp
      expect(result.delivery).toBeDefined(); // Delivery status
    });
  });

  describe('reaction handling', () => {
    it('should count reactions from array format', () => {
      const message = {
        ...baseMessage,
        reactions: [
          { emoji: '👍', user_id: 'user1' },
          { emoji: '👍', user_id: 'user2' },
          { emoji: '❤️', user_id: 'user3' },
        ],
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.reactions).toEqual({ '👍': 2, '❤️': 1 });
    });

    it('should handle reactions as object format (pre-aggregated)', () => {
      const message = {
        ...baseMessage,
        reactions: { '👍': 3, '❤️': 2 },
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.reactions).toEqual({ '👍': 3, '❤️': 2 });
    });

    it('should skip invalid items in reactions array', () => {
      const message = {
        ...baseMessage,
        reactions: [
          { emoji: '👍', user_id: 'user1' },
          null,
          undefined,
          { emoji: 123, user_id: 'user2' }, // invalid emoji type
          { user_id: 'user3' }, // missing emoji
          { emoji: '❤️', user_id: 'user4' },
        ],
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.reactions).toEqual({ '👍': 1, '❤️': 1 });
    });

    it('should return undefined reactions when raw is null', () => {
      const message = {
        ...baseMessage,
        reactions: null,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.reactions).toBeUndefined();
    });

    it('should return undefined reactions when raw is undefined', () => {
      const message = {
        ...baseMessage,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.reactions).toBeUndefined();
    });
  });

  describe('my_reactions handling', () => {
    it('should extract my_reactions from explicit array', () => {
      const message = {
        ...baseMessage,
        my_reactions: ['👍', '❤️'],
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.my_reactions).toEqual(['👍', '❤️']);
    });

    it('should filter non-string values from my_reactions array', () => {
      const message = {
        ...baseMessage,
        my_reactions: ['👍', null, undefined, 123, '❤️'] as unknown as string[],
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.my_reactions).toEqual(['👍', '❤️']);
    });

    it('should extract my_reactions from reactions array when my_reactions not explicit', () => {
      const message = {
        ...baseMessage,
        reactions: [
          { emoji: '👍', user_id: currentUserId },
          { emoji: '❤️', user_id: 'other-user' },
          { emoji: '🎉', user_id: currentUserId },
        ],
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.my_reactions).toEqual(['👍', '🎉']);
    });

    it('should skip invalid items when extracting from reactions array', () => {
      const message = {
        ...baseMessage,
        reactions: [
          { emoji: '👍', user_id: currentUserId },
          null,
          { emoji: 123, user_id: currentUserId }, // invalid emoji
          { user_id: currentUserId }, // missing emoji
          { emoji: '❤️', user_id: currentUserId },
        ],
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.my_reactions).toEqual(['👍', '❤️']);
    });

    it('should return undefined my_reactions when reactions is not an array and no explicit my_reactions', () => {
      const message = {
        ...baseMessage,
        reactions: { '👍': 2 }, // object format, not array
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.my_reactions).toBeUndefined();
    });
  });

  describe('deleted message handling', () => {
    it('should replace content with deleted message text when is_deleted is true', () => {
      const message = {
        ...baseMessage,
        content: 'Original content',
        is_deleted: true,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.text).toBe('This message was deleted');
      expect(result.isDeleted).toBe(true);
    });

    it('should preserve original content when is_deleted is false', () => {
      const message = {
        ...baseMessage,
        content: 'Original content',
        is_deleted: false,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.text).toBe('Original content');
      expect(result.isDeleted).toBe(false);
    });
  });

  describe('edited message handling', () => {
    it('should set isEdited and editedAt when message was edited', () => {
      const message = {
        ...baseMessage,
        edited_at: '2024-01-02T12:00:00Z',
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.isEdited).toBe(true);
      expect(result.editedAt).toBe('2024-01-02T12:00:00Z');
    });

    it('should set isEdited to false when edited_at is null', () => {
      const message = {
        ...baseMessage,
        edited_at: null,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.isEdited).toBe(false);
      expect(result.editedAt).toBeUndefined();
    });
  });

  describe('sender detection without conversation', () => {
    it('should default to student sender when conversation is undefined', () => {
      const message = {
        ...baseMessage,
        sender_id: 'unknown-user',
      };

      const result = mapMessageFromResponse(message, undefined, currentUserId);

      expect(result.sender).toBe('student');
    });
  });
});
