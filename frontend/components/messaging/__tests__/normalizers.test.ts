import {
  isSystemMessage,
  normalizeStudentMessage,
  normalizeInstructorMessage,
} from '../normalizers';
import type { NormalizedReaction, NormalizedAttachment } from '../types';

describe('normalizers', () => {
  describe('isSystemMessage', () => {
    it('returns false for undefined', () => {
      expect(isSystemMessage(undefined)).toBe(false);
    });

    it('returns false for null', () => {
      expect(isSystemMessage(null)).toBe(false);
    });

    it('returns false for empty string', () => {
      expect(isSystemMessage('')).toBe(false);
    });

    it('returns true for "system"', () => {
      expect(isSystemMessage('system')).toBe(true);
    });

    it('returns true for "system_joined"', () => {
      expect(isSystemMessage('system_joined')).toBe(true);
    });

    it('returns true for "system_left"', () => {
      expect(isSystemMessage('system_left')).toBe(true);
    });

    it('returns true for any string starting with "system_"', () => {
      expect(isSystemMessage('system_booking_created')).toBe(true);
      expect(isSystemMessage('system_notification')).toBe(true);
    });

    it('returns false for "user"', () => {
      expect(isSystemMessage('user')).toBe(false);
    });

    it('returns false for strings not starting with "system"', () => {
      expect(isSystemMessage('notification')).toBe(false);
      expect(isSystemMessage('message')).toBe(false);
    });
  });

  describe('normalizeStudentMessage', () => {
    const currentUserId = 'user-123';
    const baseMessage = {
      id: 'msg-1',
      content: 'Hello world',
      created_at: '2024-01-15T12:00:00Z',
      sender_id: 'other-user',
      sender_name: 'John Doe',
    };

    it('normalizes basic message fields', () => {
      const result = normalizeStudentMessage(baseMessage, currentUserId);

      expect(result.id).toBe('msg-1');
      expect(result.content).toBe('Hello world');
      expect(result.timestamp).toEqual(new Date('2024-01-15T12:00:00Z'));
      expect(result.senderName).toBe('John Doe');
    });

    it('sets isOwn to true when sender_id matches currentUserId', () => {
      const ownMessage = { ...baseMessage, sender_id: currentUserId };
      const result = normalizeStudentMessage(ownMessage, currentUserId);

      expect(result.isOwn).toBe(true);
    });

    it('sets isOwn to false when sender_id does not match currentUserId', () => {
      const result = normalizeStudentMessage(baseMessage, currentUserId);

      expect(result.isOwn).toBe(false);
    });

    it('sets isEdited to true when edited_at is present', () => {
      const editedMessage = { ...baseMessage, edited_at: '2024-01-15T13:00:00Z' };
      const result = normalizeStudentMessage(editedMessage, currentUserId);

      expect(result.isEdited).toBe(true);
    });

    it('sets isEdited to false when edited_at is null', () => {
      const result = normalizeStudentMessage(baseMessage, currentUserId);

      expect(result.isEdited).toBe(false);
    });

    it('sets isDeleted to true when is_deleted is true', () => {
      const deletedMessage = { ...baseMessage, is_deleted: true };
      const result = normalizeStudentMessage(deletedMessage, currentUserId);

      expect(result.isDeleted).toBe(true);
    });

    it('sets isDeleted to false when is_deleted is false or undefined', () => {
      const result = normalizeStudentMessage(baseMessage, currentUserId);

      expect(result.isDeleted).toBe(false);
    });

    it('handles null content', () => {
      const nullContentMessage = { ...baseMessage, content: null };
      const result = normalizeStudentMessage(nullContentMessage, currentUserId);

      expect(result.content).toBe('');
    });

    it('handles null sender_name', () => {
      const noNameMessage = { ...baseMessage, sender_name: null };
      const result = normalizeStudentMessage(noNameMessage, currentUserId);

      expect(result.senderName).toBeUndefined();
    });

    it('handles null sender_id', () => {
      const noSenderMessage = { ...baseMessage, sender_id: null };
      const result = normalizeStudentMessage(noSenderMessage, currentUserId);

      expect(result.isOwn).toBe(false);
    });

    it('applies options.reactions when provided', () => {
      const reactions: NormalizedReaction[] = [
        { emoji: '👍', count: 2, isMine: true },
      ];
      const result = normalizeStudentMessage(baseMessage, currentUserId, { reactions });

      expect(result.reactions).toEqual(reactions);
    });

    it('applies options.currentUserReaction when provided', () => {
      const result = normalizeStudentMessage(baseMessage, currentUserId, {
        currentUserReaction: '👍',
      });

      expect(result.currentUserReaction).toBe('👍');
    });

    it('applies options.timestampLabel when provided', () => {
      const result = normalizeStudentMessage(baseMessage, currentUserId, {
        timestampLabel: '2:30 PM',
      });

      expect(result.timestampLabel).toBe('2:30 PM');
    });

    it('applies options.readStatus when provided', () => {
      const result = normalizeStudentMessage(baseMessage, currentUserId, {
        readStatus: 'delivered',
      });

      expect(result.readStatus).toBe('delivered');
    });

    it('applies options.readTimestampLabel when provided', () => {
      const result = normalizeStudentMessage(baseMessage, currentUserId, {
        readTimestampLabel: 'Read at 3:00 PM',
      });

      expect(result.readTimestampLabel).toBe('Read at 3:00 PM');
    });

    it('defaults reactions to empty array when not provided', () => {
      const result = normalizeStudentMessage(baseMessage, currentUserId);

      expect(result.reactions).toEqual([]);
    });

    it('defaults currentUserReaction to null when not provided', () => {
      const result = normalizeStudentMessage(baseMessage, currentUserId);

      expect(result.currentUserReaction).toBeNull();
    });

    it('stores raw message in _raw', () => {
      const result = normalizeStudentMessage(baseMessage, currentUserId);

      expect(result._raw).toBe(baseMessage);
    });
  });

  describe('normalizeInstructorMessage', () => {
    const currentUserId = 'instructor-123';
    const baseMessage = {
      id: 'msg-1',
      text: 'Hello from instructor',
      sender: 'student' as const,
      senderId: 'student-456',
      timestamp: '5 mins ago',
      createdAt: '2024-01-15T12:00:00Z',
      isArchived: false,
      delivery: { status: 'delivered' as const, timeLabel: '5 mins ago' },
    };

    it('normalizes basic message fields', () => {
      const result = normalizeInstructorMessage(baseMessage, currentUserId);

      expect(result.id).toBe('msg-1');
      expect(result.content).toBe('Hello from instructor');
      expect(result.timestamp).toEqual(new Date('2024-01-15T12:00:00Z'));
    });

    it('sets isOwn to true when senderId matches currentUserId', () => {
      const ownMessage = { ...baseMessage, senderId: currentUserId };
      const result = normalizeInstructorMessage(ownMessage, currentUserId);

      expect(result.isOwn).toBe(true);
    });

    it('sets isOwn to true when sender is "instructor"', () => {
      const instructorMessage = {
        ...baseMessage,
        sender: 'instructor' as const,
        senderId: undefined,
      };
      const result = normalizeInstructorMessage(instructorMessage, currentUserId);

      expect(result.isOwn).toBe(true);
    });

    it('sets isOwn to false for student messages', () => {
      const result = normalizeInstructorMessage(baseMessage, currentUserId);

      expect(result.isOwn).toBe(false);
    });

    it('sets isEdited to true when isEdited is true', () => {
      const editedMessage = { ...baseMessage, isEdited: true };
      const result = normalizeInstructorMessage(editedMessage, currentUserId);

      expect(result.isEdited).toBe(true);
    });

    it('sets isEdited to true when editedAt is present', () => {
      const editedMessage = { ...baseMessage, editedAt: '2024-01-15T13:00:00Z' };
      const result = normalizeInstructorMessage(editedMessage, currentUserId);

      expect(result.isEdited).toBe(true);
    });

    it('sets isDeleted to true when isDeleted is true', () => {
      const deletedMessage = { ...baseMessage, isDeleted: true };
      const result = normalizeInstructorMessage(deletedMessage, currentUserId);

      expect(result.isDeleted).toBe(true);
    });

    it('handles null text', () => {
      const nullTextMessage = { ...baseMessage, text: null as unknown as string };
      const result = normalizeInstructorMessage(nullTextMessage, currentUserId);

      expect(result.content).toBe('');
    });

    it('handles undefined text', () => {
      const undefinedTextMessage = { ...baseMessage, text: undefined as unknown as string };
      const result = normalizeInstructorMessage(undefinedTextMessage, currentUserId);

      expect(result.content).toBe('');
    });

    it('uses timestamp as timestampLabel when no options provided', () => {
      const result = normalizeInstructorMessage(baseMessage, currentUserId);

      expect(result.timestampLabel).toBe('5 mins ago');
    });

    it('applies options.timestampLabel when provided', () => {
      const result = normalizeInstructorMessage(baseMessage, currentUserId, {
        timestampLabel: 'Custom label',
      });

      expect(result.timestampLabel).toBe('Custom label');
    });

    it('applies options.reactions when provided', () => {
      const reactions: NormalizedReaction[] = [
        { emoji: '❤️', count: 3, isMine: false },
      ];
      const result = normalizeInstructorMessage(baseMessage, currentUserId, { reactions });

      expect(result.reactions).toEqual(reactions);
    });

    it('applies options.attachments when provided', () => {
      const attachments: NormalizedAttachment[] = [
        { id: 'att-1', url: 'https://example.com/image.jpg', type: 'image', name: 'photo.jpg' },
      ];
      const result = normalizeInstructorMessage(baseMessage, currentUserId, { attachments });

      expect(result.attachments).toEqual(attachments);
    });

    it('handles missing createdAt by using current date', () => {
      const noCreatedAtMessage = { ...baseMessage, createdAt: undefined };
      const result = normalizeInstructorMessage(noCreatedAtMessage, currentUserId);

      expect(result.timestamp).toBeInstanceOf(Date);
    });

    it('stores raw message in _raw', () => {
      const result = normalizeInstructorMessage(baseMessage, currentUserId);

      expect(result._raw).toBe(baseMessage);
    });

    it('defaults senderName to undefined', () => {
      const result = normalizeInstructorMessage(baseMessage, currentUserId);

      expect(result.senderName).toBeUndefined();
    });
  });
});
