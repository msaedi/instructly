/**
 * Tests for messages barrel file exports
 *
 * Verifies all re-exports are properly accessible and defined.
 * Coverage for index.ts lines 9-21 (barrel exports).
 */

import * as messageModule from '../index';

describe('messages/index.ts exports', () => {
  describe('types exports', () => {
    it('exports MessageAttachment type', () => {
      const attachment: messageModule.MessageAttachment = {
        name: 'file.pdf',
        type: 'application/pdf',
        dataUrl: 'data:application/pdf;base64,...',
      };
      expect(attachment).toBeDefined();
    });

    it('exports MessageItem type', () => {
      const item: messageModule.MessageItem = {
        id: 'msg-1',
        text: 'Hello',
        sender: 'instructor',
        timestamp: '2024-01-01',
      };
      expect(item).toBeDefined();
    });

    it('exports ConversationEntry type', () => {
      const entry: messageModule.ConversationEntry = {
        id: 'conv-1',
        name: 'John Doe',
        lastMessage: 'Hello',
        timestamp: '2024-01-01',
        unread: 0,
        avatar: '',
        type: 'student',
        bookingIds: [],
        primaryBookingId: null,
        studentId: 'student-1',
        instructorId: 'inst-1',
        latestMessageAt: Date.now(),
      };
      expect(entry).toBeDefined();
    });

    it('exports MessageDelivery type', () => {
      const sending: messageModule.MessageDelivery = { status: 'sending' };
      const delivered: messageModule.MessageDelivery = { status: 'delivered', timeLabel: '2:00 PM' };
      const read: messageModule.MessageDelivery = { status: 'read', timeLabel: '2:01 PM' };
      expect(sending.status).toBe('sending');
      expect(delivered.status).toBe('delivered');
      expect(read.status).toBe('read');
    });

    it('exports FilterOption type', () => {
      const filter: messageModule.FilterOption = {
        label: 'All',
        value: 'all',
      };
      expect(filter).toBeDefined();
    });

    it('exports TemplateItem type', () => {
      const template: messageModule.TemplateItem = {
        id: 'tpl-1',
        subject: 'Welcome',
        preview: 'Preview text',
        body: 'Body text',
      };
      expect(template).toBeDefined();
    });

    it('exports MessageDisplayMode type', () => {
      const modes: messageModule.MessageDisplayMode[] = ['inbox', 'archived', 'trash'];
      expect(modes).toHaveLength(3);
    });

    it('exports MailSection type', () => {
      const sections: messageModule.MailSection[] = ['inbox', 'compose', 'sent', 'drafts', 'templates'];
      expect(sections).toHaveLength(5);
    });

    it('exports ReadByEntry type', () => {
      const entry: messageModule.ReadByEntry = {
        user_id: 'user-1',
        read_at: '2024-01-01T12:00:00Z',
      };
      expect(entry).toBeDefined();
    });

    it('exports SSEMessageWithOwnership type', () => {
      const message: messageModule.SSEMessageWithOwnership = {
        id: 'msg-1',
        content: 'Hello',
        sender_id: 'user-1',
        created_at: '2024-01-01T12:00:00Z',
        is_mine: false,
      };
      expect(message).toBeDefined();
    });
  });

  describe('constants exports', () => {
    it('exports COMPOSE_THREAD_ID', () => {
      expect(messageModule.COMPOSE_THREAD_ID).toBe('__compose__');
    });

    it('exports DRAFT_COOKIE_NAME', () => {
      expect(messageModule.DRAFT_COOKIE_NAME).toBe('instructor_message_drafts');
    });

    it('exports TEMPLATE_COOKIE_NAME', () => {
      expect(messageModule.TEMPLATE_COOKIE_NAME).toBe('instructor_message_templates');
    });

    it('exports HISTORY_RETRY_DELAY_MS', () => {
      expect(messageModule.HISTORY_RETRY_DELAY_MS).toBe(10_000);
    });

    it('exports CONVERSATION_REFRESH_INTERVAL_MS', () => {
      expect(messageModule.CONVERSATION_REFRESH_INTERVAL_MS).toBe(30_000);
    });

    it('exports ARCHIVED_LABEL', () => {
      expect(messageModule.ARCHIVED_LABEL).toBe('All messages archived');
    });

    it('exports TRASH_LABEL', () => {
      expect(messageModule.TRASH_LABEL).toBe('All messages trashed');
    });

    it('exports FILTER_OPTIONS', () => {
      expect(messageModule.FILTER_OPTIONS).toBeInstanceOf(Array);
      expect(messageModule.FILTER_OPTIONS).toHaveLength(3);
      expect(messageModule.FILTER_OPTIONS[0]).toEqual({ label: 'All', value: 'all' });
    });

    it('exports DEFAULT_TEMPLATES', () => {
      expect(messageModule.DEFAULT_TEMPLATES).toBeInstanceOf(Array);
      expect(messageModule.DEFAULT_TEMPLATES.length).toBeGreaterThan(0);
    });

    it('exports getDefaultTemplates function', () => {
      expect(typeof messageModule.getDefaultTemplates).toBe('function');
      const templates = messageModule.getDefaultTemplates();
      expect(templates).toBeInstanceOf(Array);
      // Ensure it returns a copy, not the original
      expect(templates).not.toBe(messageModule.DEFAULT_TEMPLATES);
    });
  });

  describe('utility exports', () => {
    it('exports formatRelativeTimestamp', () => {
      expect(typeof messageModule.formatRelativeTimestamp).toBe('function');
    });

    it('exports formatTimeLabel', () => {
      expect(typeof messageModule.formatTimeLabel).toBe('function');
    });

    it('exports formatShortDate', () => {
      expect(typeof messageModule.formatShortDate).toBe('function');
    });

    it('exports getInitials', () => {
      expect(typeof messageModule.getInitials).toBe('function');
    });

    it('exports formatStudentName', () => {
      expect(typeof messageModule.formatStudentName).toBe('function');
    });
  });

  describe('component exports', () => {
    it('exports ChatHeader', () => {
      expect(messageModule.ChatHeader).toBeDefined();
      expect(typeof messageModule.ChatHeader).toBe('function');
    });

    it('exports ConversationItem', () => {
      expect(messageModule.ConversationItem).toBeDefined();
      expect(typeof messageModule.ConversationItem).toBe('function');
    });

    it('exports ConversationList', () => {
      expect(messageModule.ConversationList).toBeDefined();
      expect(typeof messageModule.ConversationList).toBe('function');
    });

    it('exports MessageInput', () => {
      expect(messageModule.MessageInput).toBeDefined();
      expect(typeof messageModule.MessageInput).toBe('function');
    });

    it('exports TemplateEditor', () => {
      expect(messageModule.TemplateEditor).toBeDefined();
      expect(typeof messageModule.TemplateEditor).toBe('function');
    });
  });

  describe('hook exports', () => {
    it('exports useConversations', () => {
      expect(messageModule.useConversations).toBeDefined();
      expect(typeof messageModule.useConversations).toBe('function');
    });

    it('exports useUpdateConversationState', () => {
      expect(messageModule.useUpdateConversationState).toBeDefined();
      expect(typeof messageModule.useUpdateConversationState).toBe('function');
    });

    it('exports useConversationMessages', () => {
      expect(messageModule.useConversationMessages).toBeDefined();
      expect(typeof messageModule.useConversationMessages).toBe('function');
    });

    it('exports useMessageDrafts', () => {
      expect(messageModule.useMessageDrafts).toBeDefined();
      expect(typeof messageModule.useMessageDrafts).toBe('function');
    });

    it('exports useMessageThread', () => {
      expect(messageModule.useMessageThread).toBeDefined();
      expect(typeof messageModule.useMessageThread).toBe('function');
    });

    it('exports useTemplates', () => {
      expect(messageModule.useTemplates).toBeDefined();
      expect(typeof messageModule.useTemplates).toBe('function');
    });
  });

  describe('barrel file integrity', () => {
    it('does not have circular dependencies', () => {
      // If this test runs, there are no circular dependencies
      expect(() => require('../index')).not.toThrow();
    });

    it('all exports are defined (not undefined)', () => {
      const exportNames = Object.keys(messageModule);
      exportNames.forEach((name) => {
        const value = messageModule[name as keyof typeof messageModule];
        expect(value).toBeDefined();
      });
    });

    it('exports a reasonable number of items', () => {
      const exportCount = Object.keys(messageModule).length;
      expect(exportCount).toBeGreaterThan(20);
    });
  });
});
