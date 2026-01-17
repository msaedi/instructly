/**
 * Tests for template management utilities
 */

import {
  deriveTemplatePreview,
  rewriteTemplateContent,
  loadStoredTemplates,
  saveTemplatesToCookie,
  copyToClipboard,
} from '../templates';
import { TEMPLATE_COOKIE_NAME, getDefaultTemplates } from '../../constants';

describe('templates', () => {
  describe('deriveTemplatePreview', () => {
    it('returns empty string for empty text', () => {
      expect(deriveTemplatePreview('')).toBe('');
      expect(deriveTemplatePreview('   ')).toBe('');
    });

    it('returns first non-empty line', () => {
      const text = '\n\nHello there\nSecond line';
      expect(deriveTemplatePreview(text)).toBe('Hello there');
    });

    it('truncates long text to 80 characters with ellipsis', () => {
      const longText = 'A'.repeat(100);
      const result = deriveTemplatePreview(longText);
      expect(result.length).toBe(80);
      expect(result.endsWith('...')).toBe(true);
    });

    it('does not truncate text under 80 characters', () => {
      const shortText = 'This is a short preview';
      expect(deriveTemplatePreview(shortText)).toBe(shortText);
    });

    it('extracts first line from multi-line text', () => {
      const text = 'First line\nSecond line\nThird line';
      expect(deriveTemplatePreview(text)).toBe('First line');
    });

    it('handles text with only whitespace lines initially', () => {
      const text = '   \n   \nActual content';
      expect(deriveTemplatePreview(text)).toBe('Actual content');
    });
  });

  describe('rewriteTemplateContent', () => {
    it('returns fallback content for empty input', () => {
      const result = rewriteTemplateContent('', 0);
      expect(result).toContain('Quick heads-up');
      expect(result).toContain('Let me know what you think.');
    });

    it('varies openers based on iteration', () => {
      const result0 = rewriteTemplateContent('', 0);
      const result1 = rewriteTemplateContent('', 1);
      expect(result0).toContain('Quick heads-up');
      expect(result1).toContain('Just a quick update');
    });

    it('varies closers based on iteration', () => {
      const result0 = rewriteTemplateContent('', 0);
      const result1 = rewriteTemplateContent('', 1);
      expect(result0).toContain('Let me know what you think.');
      expect(result1).toContain('Message me if anything feels off.');
    });

    it('processes bullet points in content', () => {
      const content = `Here are some items:
- First item
- Second item
- Third item`;
      const result = rewriteTemplateContent(content, 0);
      expect(result).toContain('First item');
      expect(result).toContain('Second item');
    });

    it('removes closing phrases from input', () => {
      const content = 'Important info here.\nBest regards,';
      const result = rewriteTemplateContent(content, 0);
      expect(result.toLowerCase()).not.toContain('regards');
    });

    it('adds opener at the start of content', () => {
      const content = 'The meeting is tomorrow at 3pm.\nPlease bring your notes.';
      const result = rewriteTemplateContent(content, 0);
      // Should start with an opener
      expect(result.startsWith('Quick heads-up')).toBe(true);
    });

    it('handles numbered lists', () => {
      const content = `Steps to follow:
1. First step
2. Second step
3. Third step`;
      const result = rewriteTemplateContent(content, 0);
      expect(result).toContain('First step');
    });

    it('rotates content based on iteration', () => {
      const content = 'Sentence one. Sentence two. Sentence three.';
      const result0 = rewriteTemplateContent(content, 0);
      const result1 = rewriteTemplateContent(content, 3);
      // Results should differ due to rotation
      expect(result0).not.toBe(result1);
    });

    it('deduplicates identical lines', () => {
      const content = `Item one.
Item one.
Item two.`;
      const result = rewriteTemplateContent(content, 0);
      const matches = result.match(/item one/gi);
      expect(matches?.length).toBe(1);
    });

    it('handles multiple paragraphs', () => {
      const content = `First paragraph with content.

Second paragraph with more content.`;
      const result = rewriteTemplateContent(content, 0);
      expect(result).toContain('First paragraph');
      expect(result).toContain('Second paragraph');
    });

    it('handles negative iteration gracefully', () => {
      const result = rewriteTemplateContent('Test content', -1);
      expect(result).toBeTruthy();
      expect(result).toContain('Quick heads-up');
    });
  });

  describe('loadStoredTemplates', () => {
    beforeEach(() => {
      // Clear all cookies
      document.cookie.split(';').forEach((cookie) => {
        const name = cookie.split('=')[0]?.trim();
        if (name) {
          document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
        }
      });
    });

    it('returns default templates when no cookie exists', () => {
      const templates = loadStoredTemplates();
      expect(templates).toHaveLength(getDefaultTemplates().length);
    });

    it('returns default templates when cookie is invalid JSON', () => {
      document.cookie = `${TEMPLATE_COOKIE_NAME}=invalid-json; path=/`;
      const templates = loadStoredTemplates();
      expect(templates).toHaveLength(getDefaultTemplates().length);
    });

    it('returns default templates when cookie contains non-array', () => {
      document.cookie = `${TEMPLATE_COOKIE_NAME}=${encodeURIComponent(JSON.stringify({ not: 'an array' }))}; path=/`;
      const templates = loadStoredTemplates();
      expect(templates).toHaveLength(getDefaultTemplates().length);
    });

    it('parses valid templates from cookie', () => {
      const storedTemplates = [
        { id: 'test-1', subject: 'Test Subject', body: 'Test body', preview: 'Test preview' },
      ];
      document.cookie = `${TEMPLATE_COOKIE_NAME}=${encodeURIComponent(JSON.stringify(storedTemplates))}; path=/`;
      const templates = loadStoredTemplates();
      expect(templates).toHaveLength(1);
      expect(templates[0]?.id).toBe('test-1');
    });

    it('filters out invalid template items', () => {
      const storedTemplates = [
        { id: 'valid-1', subject: 'Valid', body: 'Body', preview: 'Preview' },
        { noId: 'invalid' },
        null,
        { id: 'valid-2', subject: 'Valid 2', body: 'Body 2', preview: 'Preview 2' },
      ];
      document.cookie = `${TEMPLATE_COOKIE_NAME}=${encodeURIComponent(JSON.stringify(storedTemplates))}; path=/`;
      const templates = loadStoredTemplates();
      expect(templates).toHaveLength(2);
    });

    it('derives preview from body when preview is empty', () => {
      const storedTemplates = [
        { id: 'test-1', subject: 'Test', body: 'This is the body text', preview: '' },
      ];
      document.cookie = `${TEMPLATE_COOKIE_NAME}=${encodeURIComponent(JSON.stringify(storedTemplates))}; path=/`;
      const templates = loadStoredTemplates();
      expect(templates[0]?.preview).toBe('This is the body text');
    });
  });

  describe('saveTemplatesToCookie', () => {
    beforeEach(() => {
      // Clear all cookies
      document.cookie.split(';').forEach((cookie) => {
        const name = cookie.split('=')[0]?.trim();
        if (name) {
          document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
        }
      });
    });

    it('saves templates to cookie', () => {
      const templates = [
        { id: 'test-1', subject: 'Test', body: 'Body', preview: 'Preview' },
      ];
      saveTemplatesToCookie(templates);

      expect(document.cookie).toContain(TEMPLATE_COOKIE_NAME);
    });

    it('handles empty templates array', () => {
      expect(() => saveTemplatesToCookie([])).not.toThrow();
    });
  });

  describe('copyToClipboard', () => {
    const originalClipboard = navigator.clipboard;
    const originalExecCommand = document.execCommand;

    beforeEach(() => {
      // Reset mocks
      jest.restoreAllMocks();
    });

    afterEach(() => {
      // Restore
      if (originalClipboard) {
        Object.defineProperty(navigator, 'clipboard', {
          value: originalClipboard,
          writable: true,
          configurable: true,
        });
      }
      document.execCommand = originalExecCommand;
    });

    it('uses clipboard API when available', async () => {
      const writeTextMock = jest.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: writeTextMock },
        writable: true,
        configurable: true,
      });

      const result = await copyToClipboard('test text');
      expect(result).toBe(true);
      expect(writeTextMock).toHaveBeenCalledWith('test text');
    });

    it('falls back to execCommand when clipboard API fails', async () => {
      const writeTextMock = jest.fn().mockRejectedValue(new Error('Not allowed'));
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: writeTextMock },
        writable: true,
        configurable: true,
      });

      const execCommandMock = jest.fn().mockReturnValue(true);
      document.execCommand = execCommandMock;

      const result = await copyToClipboard('fallback text');
      expect(result).toBe(true);
      expect(execCommandMock).toHaveBeenCalledWith('copy');
    });

    it('returns false when execCommand fails', async () => {
      const writeTextMock = jest.fn().mockRejectedValue(new Error('Not allowed'));
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: writeTextMock },
        writable: true,
        configurable: true,
      });

      const execCommandMock = jest.fn().mockReturnValue(false);
      document.execCommand = execCommandMock;

      const result = await copyToClipboard('text');
      expect(result).toBe(false);
    });

    it('handles clipboard API not available', async () => {
      Object.defineProperty(navigator, 'clipboard', {
        value: undefined,
        writable: true,
        configurable: true,
      });

      const execCommandMock = jest.fn().mockReturnValue(true);
      document.execCommand = execCommandMock;

      const result = await copyToClipboard('test');
      expect(result).toBe(true);
      expect(execCommandMock).toHaveBeenCalledWith('copy');
    });
  });
});
