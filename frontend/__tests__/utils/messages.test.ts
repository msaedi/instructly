import { mapMessageFromResponse } from '@/components/instructor/messages/utils/messages';
import type { MessageResponse } from '@/src/api/generated/instructly.schemas';
import type { ConversationEntry } from '@/components/instructor/messages/types';

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

  const baseMessage: MessageResponse = {
    id: 'msg1',
    content: 'Hello',
    sender_id: studentId,
    conversation_id: 'conversation1',
    created_at: '2024-01-01T12:00:00Z',
    booking_id: 'booking1',
    updated_at: '2024-01-01T12:00:00Z',
  };

  describe('delivered_at field preservation', () => {
    it('should preserve delivered_at field when present', () => {
      const message: MessageResponse = {
        ...baseMessage,
        sender_id: currentUserId, // Instructor sending
        delivered_at: '2024-01-01T12:00:01Z',
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.delivered_at).toBe('2024-01-01T12:00:01Z');
    });

    it('should handle null delivered_at', () => {
      const message: MessageResponse = {
        ...baseMessage,
        sender_id: currentUserId,
        delivered_at: null,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.delivered_at).toBeUndefined();
    });

    it('should handle missing delivered_at field', () => {
      const message: MessageResponse = {
        ...baseMessage,
        sender_id: currentUserId,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.delivered_at).toBeUndefined();
    });
  });

  describe('read_by field preservation', () => {
    it('should preserve read_by array when present', () => {
      const message: MessageResponse = {
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
      const message: MessageResponse = {
        ...baseMessage,
        sender_id: currentUserId,
        read_by: [],
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.read_by).toEqual([]);
    });

    it('should handle missing read_by field', () => {
      const message: MessageResponse = {
        ...baseMessage,
        sender_id: currentUserId,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.read_by).toBeUndefined();
    });
  });

  describe('delivery status calculation', () => {
    it('should set delivery status to "read" when message has been read by recipient', () => {
      const message: MessageResponse = {
        ...baseMessage,
        sender_id: currentUserId,
        delivered_at: '2024-01-01T12:00:01Z',
        read_by: [{ user_id: studentId, read_at: '2024-01-01T12:00:05Z' }],
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.delivery?.status).toBe('read');
    });

    it('should set delivery status to "delivered" when message has delivered_at but not read', () => {
      const message: MessageResponse = {
        ...baseMessage,
        sender_id: currentUserId,
        delivered_at: '2024-01-01T12:00:01Z',
        read_by: [],
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.delivery?.status).toBe('delivered');
    });

    it('should default to "delivered" status when delivered_at is missing', () => {
      const message: MessageResponse = {
        ...baseMessage,
        sender_id: currentUserId,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.delivery?.status).toBe('delivered');
    });
  });

  describe('sender type detection', () => {
    it('should identify instructor as sender when sender_id matches currentUserId', () => {
      const message: MessageResponse = {
        ...baseMessage,
        sender_id: currentUserId,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.sender).toBe('instructor');
    });

    it('should identify student as sender when sender_id matches studentId', () => {
      const message: MessageResponse = {
        ...baseMessage,
        sender_id: studentId,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.sender).toBe('student');
    });

    it('should identify platform as sender for system messages', () => {
      const platformUserId = 'platform-system';
      const message: MessageResponse = {
        ...baseMessage,
        sender_id: platformUserId,
      };

      const result = mapMessageFromResponse(message, baseConversation, currentUserId);

      expect(result.sender).toBe('platform');
    });
  });

  describe('message mapping completeness', () => {
    it('should map all essential message fields', () => {
      const message: MessageResponse = {
        id: 'msg1',
        content: 'Test message',
        sender_id: currentUserId,
        conversation_id: 'conversation1',
        created_at: '2024-01-01T12:00:00Z',
        updated_at: '2024-01-01T12:00:00Z',
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
});
