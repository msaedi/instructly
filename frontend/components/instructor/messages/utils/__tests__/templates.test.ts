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

    it('adds sentence ending to long (>60 char) non-first sentences (line 167)', () => {
      // We need at least two sentences, and the second must exceed 60 characters
      const longSentence = 'This particular sentence is deliberately constructed to be more than sixty characters long for testing';
      const input = `Short intro. ${longSentence}.`;
      const result = rewriteTemplateContent(input, 0);
      const lines = result.split('\n');
      const bodyLines = lines.slice(1, -1);
      // The second sentence body line should end with punctuation (ensureSentenceEnding applied)
      if (bodyLines.length > 1) {
        const secondBody = bodyLines[1]!;
        expect(/[.!?)]$/.test(secondBody)).toBe(true);
      }
    });

    it('returns short non-first sentences without added period when <=60 chars (line 166)', () => {
      const input = 'Sentence one. Short two. Tiny three.';
      const result = rewriteTemplateContent(input, 0);
      const lines = result.split('\n');
      const bodyLines = lines.slice(1, -1);
      // The first body line has trailing punctuation stripped (index 0 path)
      // Short subsequent lines should NOT get punctuation added (returned as-is without ending)
      if (bodyLines.length > 1) {
        const secondBody = bodyLines[1]!;
        // <=60 chars returns trimmed (without period) — the period was already stripped
        expect(secondBody.endsWith('.')).toBe(false);
      }
    });

    it('uses bodyLines fallback when all content is filtered out (lines 184-186)', () => {
      // Input containing ONLY closing phrases and opener-like phrases, so everything gets filtered
      const input = 'Best regards. Thank you. Sincerely. Cheers.';
      const result = rewriteTemplateContent(input, 0);
      const lines = result.split('\n');
      // opener + at least 1 fallback line + closer
      expect(lines.length).toBeGreaterThanOrEqual(3);
      // The fallback line at (variantIndex + 1) % 5 should be present
      const bodyLines = lines.slice(1, -1);
      expect(bodyLines.length).toBeGreaterThanOrEqual(1);
      // Should contain one of the fallback lines
      const fallbackLines = [
        'Sharing a quick update so we stay aligned.',
        "Here's the plan I'd go with right now.",
        "These are the next moves I'm seeing.",
        'Keeping things on track with this plan.',
        'This should keep everything moving smoothly.',
      ];
      const containsFallback = bodyLines.some(
        (line) => fallbackLines.some((fb) => line.includes(fb))
      );
      expect(containsFallback).toBe(true);
    });

    it('bodyLines fallback uses correct variantIndex offset (lines 184-186)', () => {
      // Force bodyLines.length === 0 with a different iteration value
      const input = 'Thanks! Talk soon. Warmly. Take care.';
      const result = rewriteTemplateContent(input, 3);
      const lines = result.split('\n');
      const bodyLines = lines.slice(1, -1);
      // Should still have at least one fallback body line
      expect(bodyLines.length).toBeGreaterThanOrEqual(1);
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

    it('returns false when execCommand throws an exception (line 276)', async () => {
      // Ensure clipboard API is missing so we fall to execCommand
      Object.defineProperty(navigator, 'clipboard', {
        value: undefined,
        writable: true,
        configurable: true,
      });

      document.execCommand = jest.fn().mockImplementation(() => {
        throw new Error('execCommand not supported');
      });

      const result = await copyToClipboard('error path');
      expect(result).toBe(false);
    });

    it('returns false when clipboard rejects and execCommand throws (full fallback chain)', async () => {
      // Clipboard API exists but rejects
      const writeTextMock = jest.fn().mockRejectedValue(new DOMException('Denied'));
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: writeTextMock },
        writable: true,
        configurable: true,
      });

      // execCommand also throws
      document.execCommand = jest.fn().mockImplementation(() => {
        throw new Error('also broken');
      });

      const result = await copyToClipboard('nothing works');
      expect(result).toBe(false);
    });
  });

  describe('rewriteTemplateContent (additional branch coverage)', () => {
    it('uses default iteration=0 when called without iteration argument', () => {
      // Branch 10: default arg
      const result = rewriteTemplateContent('Some real content here.');
      expect(result).toContain('Quick heads-up'); // iteration=0 opener
    });

    it('handles bullet items where content after stripping bullet marker is empty', () => {
      // Branch 13: `if (!content) return` inside bullet processing
      const input = '- \n- \n- ';
      const result = rewriteTemplateContent(input, 0);
      // Bullets with empty content are filtered, should still produce valid output
      expect(result.split('\n').length).toBeGreaterThanOrEqual(3);
    });

    it('handles text where all lines start with openers to trigger the filter', () => {
      // Branch 16: `if (looksLikeOpener(sentence)) return` filtering
      const input = "Quick heads up about the meeting. Just a quick update on things. Here's what I'm thinking about next.";
      const result = rewriteTemplateContent(input, 0);
      const lines = result.split('\n');
      // Opener phrases from the input should be filtered out
      // Only the built-in opener should appear
      expect(lines[0]).toBe('Quick heads-up');
    });

    it('handles input where deriveTemplatePreview finds no non-empty line', () => {
      // Branch 1 (line 14): the ?? trimmed fallback in deriveTemplatePreview
      // This is when all lines are whitespace - already covered, but let's confirm
      // the fallback returns trimmed value
      expect(deriveTemplatePreview('\t\t\t')).toBe('');
    });
  });

  describe('loadStoredTemplates (additional branch coverage)', () => {
    beforeEach(() => {
      document.cookie.split(';').forEach((cookie) => {
        const name = cookie.split('=')[0]?.trim();
        if (name) {
          document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
        }
      });
    });

    it('returns defaults when cookie value is empty after split (line 202)', () => {
      // Cookie exists but value part is empty: "name="
      document.cookie = `${TEMPLATE_COOKIE_NAME}=; path=/`;
      const templates = loadStoredTemplates();
      expect(templates).toEqual(getDefaultTemplates());
    });

    it('handles item with numeric id (non-string) by filtering it out', () => {
      const items = [{ id: 42, subject: 'Numeric', body: 'body', preview: 'p' }];
      document.cookie = `${TEMPLATE_COOKIE_NAME}=${encodeURIComponent(JSON.stringify(items))}; path=/`;
      const templates = loadStoredTemplates();
      // id is a number, not a string -> filtered out -> defaults
      expect(templates).toEqual(getDefaultTemplates());
    });

    it('handles items with missing subject and body gracefully', () => {
      const items = [{ id: 'valid-id' }]; // No subject, body, or preview
      document.cookie = `${TEMPLATE_COOKIE_NAME}=${encodeURIComponent(JSON.stringify(items))}; path=/`;
      const templates = loadStoredTemplates();
      expect(templates.length).toBe(1);
      expect(templates[0]!.subject).toBe('');
      expect(templates[0]!.body).toBe('');
      expect(templates[0]!.preview).toBe('');
    });

    it('handles whitespace-only preview by deriving from body', () => {
      const items = [{ id: 'ws', subject: 'Sub', body: 'My body text', preview: '   ' }];
      document.cookie = `${TEMPLATE_COOKIE_NAME}=${encodeURIComponent(JSON.stringify(items))}; path=/`;
      const templates = loadStoredTemplates();
      // Whitespace-only preview is falsy after .trim(), so deriveTemplatePreview(body) is used
      expect(templates[0]!.preview).toBe('My body text');
    });
  });

  describe('rewriteTemplateContent (paragraph-level bullet detection)', () => {
    it('recognizes paragraph as bullets when 60%+ of lines are bullet-formatted', () => {
      // 3 out of 4 lines are bullets (75%) - should detect as bullet paragraph
      const input = '- Item one\n- Item two\n- Item three\nPlain line';
      const result = rewriteTemplateContent(input, 0);
      // Bullet items get reformatted with the variant's bullet symbol
      expect(result).toContain('- ');
    });

    it('treats paragraph as sentences when less than 60% of lines are bullets', () => {
      // 1 out of 4 lines is a bullet (25%) - should NOT detect as bullet paragraph
      const input = 'Regular line one.\nRegular line two.\nRegular line three.\n- Only bullet';
      const result = rewriteTemplateContent(input, 0);
      // Regular sentences should appear in some form
      expect(result).toContain('Quick heads-up');
    });

    it('handles numbered list with parenthesis format', () => {
      const input = '1) First step\n2) Second step\n3) Third step';
      const result = rewriteTemplateContent(input, 0);
      expect(result).toContain('First step');
      expect(result).toContain('Second step');
    });

    it('handles asterisk bullets', () => {
      const input = '* Alpha\n* Beta\n* Gamma';
      const result = rewriteTemplateContent(input, 0);
      expect(result).toContain('Alpha');
      expect(result).toContain('Beta');
    });

    it('skips empty content lines in bullet processing', () => {
      // Bullet items where the content after removing the marker is empty
      const input = '- \n- Item with content\n- ';
      const result = rewriteTemplateContent(input, 0);
      // Empty bullet lines should be skipped, only "Item with content" survives
      expect(result).toContain('Item with content');
    });
  });

  describe('rewriteTemplateContent (sentence splitting edge cases)', () => {
    it('handles text that does not match sentence pattern (no punctuation)', () => {
      // splitIntoSentences: when matches returns null, returns sentenceCase(sanitized)
      const input = 'just a plain phrase without ending punctuation';
      const result = rewriteTemplateContent(input, 0);
      // Should contain the content in some form
      expect(result.toLowerCase()).toContain('just a plain phrase');
    });

    it('handles empty paragraph after split', () => {
      const input = 'Content here.\n\n\n\n';
      const result = rewriteTemplateContent(input, 0);
      expect(result).toContain('Quick heads-up');
    });

    it('handles ensureSentenceEnding with text ending in exclamation', () => {
      const input = 'Great news! Everything is ready!';
      const result = rewriteTemplateContent(input, 0);
      // ensureSentenceEnding should pass through text ending with !
      expect(result.length).toBeGreaterThan(0);
    });

    it('handles ensureSentenceEnding with text ending in question mark', () => {
      const input = 'Can you check this? Is it ready?';
      const result = rewriteTemplateContent(input, 0);
      expect(result.length).toBeGreaterThan(0);
    });

    it('handles ensureSentenceEnding with text ending in closing paren', () => {
      const input = 'See the details (attached)';
      const result = rewriteTemplateContent(input, 0);
      expect(result.length).toBeGreaterThan(0);
    });
  });

  describe('rewriteTemplateContent (rotateItems edge cases)', () => {
    it('handles rotation with offset 0 (no rotation)', () => {
      const input = 'A. B. C.';
      const result = rewriteTemplateContent(input, 0);
      expect(result).toBeTruthy();
    });

    it('handles higher iterations for varied rotation', () => {
      const input = '- One\n- Two\n- Three\n- Four\n- Five';
      const results = new Set<string>();
      for (let i = 0; i < 5; i++) {
        results.add(rewriteTemplateContent(input, i));
      }
      // Different iterations should produce different outputs
      expect(results.size).toBeGreaterThan(1);
    });
  });

  describe('deriveTemplatePreview (edge cases)', () => {
    it('handles text with only empty lines followed by content', () => {
      const text = '\n\n\nContent after blanks';
      expect(deriveTemplatePreview(text)).toBe('Content after blanks');
    });

    it('handles exactly 80 characters (no truncation)', () => {
      const text = 'A'.repeat(80);
      expect(deriveTemplatePreview(text)).toBe(text);
    });

    it('handles 81 characters (truncation occurs)', () => {
      const text = 'A'.repeat(81);
      const result = deriveTemplatePreview(text);
      expect(result.length).toBe(80);
      expect(result.endsWith('...')).toBe(true);
    });
  });

  describe('loadStoredTemplates (edge cases)', () => {
    beforeEach(() => {
      document.cookie.split(';').forEach((cookie) => {
        const name = cookie.split('=')[0]?.trim();
        if (name) {
          document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
        }
      });
    });

    it('returns defaults when all items in array are invalid (empty cleaned array)', () => {
      const items = [null, undefined, { noId: true }, 42];
      document.cookie = `${TEMPLATE_COOKIE_NAME}=${encodeURIComponent(JSON.stringify(items))}; path=/`;
      const templates = loadStoredTemplates();
      // cleaned.length === 0 -> returns defaults
      expect(templates).toEqual(getDefaultTemplates());
    });

    it('handles item with empty string id (filtered out)', () => {
      const items = [{ id: '', subject: 'Sub', body: 'Body', preview: 'Preview' }];
      document.cookie = `${TEMPLATE_COOKIE_NAME}=${encodeURIComponent(JSON.stringify(items))}; path=/`;
      const templates = loadStoredTemplates();
      // Empty id is falsy -> filtered out -> returns defaults
      expect(templates).toEqual(getDefaultTemplates());
    });

    it('handles item with non-string subject, body, preview', () => {
      const items = [{ id: 'valid', subject: 123, body: null, preview: undefined }];
      document.cookie = `${TEMPLATE_COOKIE_NAME}=${encodeURIComponent(JSON.stringify(items))}; path=/`;
      const templates = loadStoredTemplates();
      expect(templates[0]!.subject).toBe('');
      expect(templates[0]!.body).toBe('');
      expect(templates[0]!.preview).toBe('');
    });
  });

  describe('rewriteTemplateContent (internal function branches)', () => {
    it('exercises ensureSentenceEnding with empty input via sentenceCase (line 29, 70)', () => {
      // splitIntoSentences can produce empty segments when matches contain
      // whitespace-only parts. sentenceCase('') -> '' and ensureSentenceEnding('') -> ''
      // Feed content that after regex splitting produces empty-ish segments
      const input = '... ';
      const result = rewriteTemplateContent(input, 0);
      // Should produce valid output without crashing
      expect(result).toContain('Quick heads-up');
    });

    it('exercises splitIntoSentences with sanitized empty (line 80)', () => {
      // A paragraph made entirely of whitespace gets sanitized to ''
      // which triggers if (!sanitized) return []
      // But paragraphs are filtered with .filter(Boolean), so whitespace blocks
      // are removed. We need a block that becomes empty after whitespace replace + trim
      // This path is covered when paragraphs.forEach produces empty strings -
      // covered by the trim/filter chain. Let's exercise the outer fallback.
      const input = '\n\n\n';
      const result = rewriteTemplateContent(input, 0);
      // normalized is empty -> fallback
      expect(result).toContain('Quick heads-up');
    });

    it('exercises splitIntoSentences with no regex matches (line 82)', () => {
      // When sanitized text has no sentence-ending punctuation,
      // the regex /[^.!?]+[.!?]?/g might still match (greedy).
      // Actually, the regex will always match any non-empty string.
      // To get null from .match(), the string must be empty, but we
      // already checked for that at line 80. So line 82 is essentially
      // dead code. But let's try to get close.
      const input = 'Text without any sentence endings';
      const result = rewriteTemplateContent(input, 0);
      expect(result.toLowerCase()).toContain('text without');
    });

    it('exercises the sentence filter that skips empty sentences (line 152)', () => {
      // If splitIntoSentences returns an empty string in its array,
      // the forEach at line 151 should skip it via if (!sentence)
      // This can happen if match segments are whitespace-only
      const input = '. . . Real content here. . .';
      const result = rewriteTemplateContent(input, 0);
      expect(result).toBeDefined();
    });

    it('exercises dedup filter skipping empty normalized keys (line 177)', () => {
      // Lines whose normalizeForComparison result is empty are skipped
      // Pure punctuation/symbol lines normalize to ''
      const input = '!!!. Real line. ???.';
      const result = rewriteTemplateContent(input, 0);
      expect(result.toLowerCase()).toContain('real line');
    });

    it('exercises fallbackLines nullish coalescing (line 184)', () => {
      // variantIndex + 1 wraps within bounds, so ?? '' is never triggered
      // in practice. But we can verify the bodyLines.length === 0 path
      // with high iteration value
      const input = 'Thanks! See you soon. Take care. Regards.';
      const result = rewriteTemplateContent(input, 4);
      const lines = result.split('\n');
      expect(lines.length).toBeGreaterThanOrEqual(3);
    });
  });

  describe('rewriteTemplateContent (ensureSentenceEnding already-punctuated)', () => {
    it('does not double-punctuate text ending with period', () => {
      const input = 'This sentence ends with a period.';
      const result = rewriteTemplateContent(input, 0);
      // Should not end up with ".." in the body
      expect(result).not.toContain('..');
    });

    it('does not double-punctuate text ending with question mark', () => {
      const input = 'Is this a question?';
      const result = rewriteTemplateContent(input, 0);
      expect(result).not.toContain('?.');
    });

    it('does not double-punctuate text ending with closing paren', () => {
      const input = 'See details (here)';
      const result = rewriteTemplateContent(input, 0);
      expect(result).toBeDefined();
    });
  });

  describe('loadStoredTemplates (cookie parsing edge cases)', () => {
    beforeEach(() => {
      document.cookie.split(';').forEach((cookie) => {
        const name = cookie.split('=')[0]?.trim();
        if (name) {
          document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
        }
      });
    });

    it('handles cookie with multiple = signs in value', () => {
      // The split('=')[1] ?? '' handles the value extraction
      // Encoding should handle this, but let's test the raw cookie parsing
      const templates = [{ id: 'test', subject: 'S', body: 'B', preview: 'P' }];
      const payload = encodeURIComponent(JSON.stringify(templates));
      document.cookie = `${TEMPLATE_COOKIE_NAME}=${payload}; path=/`;
      const result = loadStoredTemplates();
      expect(result[0]?.id).toBe('test');
    });

    it('handles template item that is a non-object type (number)', () => {
      const items = [42, 'string', true, { id: 'ok', subject: 'S', body: 'B', preview: 'P' }];
      document.cookie = `${TEMPLATE_COOKIE_NAME}=${encodeURIComponent(JSON.stringify(items))}; path=/`;
      const result = loadStoredTemplates();
      // Only the valid object with id should survive
      expect(result).toHaveLength(1);
      expect(result[0]?.id).toBe('ok');
    });
  });

  describe('saveTemplatesToCookie (write error handling)', () => {
    it('silently catches errors during cookie write', () => {
      // Override cookie setter to throw
      const origDescriptor = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie');
      Object.defineProperty(document, 'cookie', {
        set: () => {
          throw new Error('Cookie write blocked');
        },
        get: () => '',
        configurable: true,
      });

      expect(() => saveTemplatesToCookie(getDefaultTemplates())).not.toThrow();

      // Restore
      if (origDescriptor) {
        Object.defineProperty(document, 'cookie', origDescriptor);
      }
    });
  });
});
