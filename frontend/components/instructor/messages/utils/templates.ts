/**
 * Template management utilities
 */

import type { TemplateItem } from '../types';
import { TEMPLATE_COOKIE_NAME, getDefaultTemplates } from '../constants';

/**
 * Derive preview text from template body
 */
export const deriveTemplatePreview = (text: string): string => {
  const trimmed = text.trim();
  if (!trimmed) return '';
  const firstLine = trimmed.split('\n').find((line) => line.trim()) ?? trimmed;
  const normalized = firstLine.trim();
  return normalized.length > 80 ? `${normalized.slice(0, 77)}...` : normalized;
};

/**
 * Bullet pattern for parsing template content
 */
const BULLET_PATTERN = /^([-*]|\d+[.)])\s*/;

/**
 * Ensure text ends with sentence ending punctuation
 */
const ensureSentenceEnding = (text: string): string => {
  const trimmed = text.trim();
  if (!trimmed) return '';
  if (/[.!?)]$/.test(trimmed)) return trimmed;
  return `${trimmed}.`;
};

/**
 * Check if text looks like a closing phrase
 */
const looksLikeClosing = (text: string): boolean =>
  /(best|thanks|thank you|regards|sincerely|cheers|talk soon|warmly|take care|see you soon|yours truly)/i.test(
    text.trim()
  );

/**
 * Normalize text for comparison
 */
const normalizeForComparison = (text: string): string =>
  text
    .replace(/[^\p{L}\p{N}\s]/gu, '')
    .toLowerCase()
    .trim();

/**
 * Check if text looks like an opener
 */
const looksLikeOpener = (text: string): boolean => {
  const normalized = normalizeForComparison(text);
  return (
    normalized.startsWith('quick heads up') ||
    normalized.startsWith('just a quick update') ||
    normalized.startsWith('heres what im thinking') ||
    normalized.startsWith('sharing the latest') ||
    normalized.startsWith('checking in real quick')
  );
};

/**
 * Convert text to sentence case
 */
const sentenceCase = (text: string): string => {
  const trimmed = text.trim();
  if (!trimmed) return '';
  const normalized = trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
  return ensureSentenceEnding(normalized);
};

/**
 * Split text into sentences
 */
const splitIntoSentences = (text: string): string[] => {
  const sanitized = text.replace(/\s+/g, ' ').trim();
  if (!sanitized) return [];
  const matches = sanitized.match(/[^.!?]+[.!?]?/g);
  if (!matches) return [sentenceCase(sanitized)];
  return matches.map((segment) => sentenceCase(segment));
};

/**
 * Rotate array items by offset
 */
function rotateItems<T>(items: T[], offset: number): T[] {
  if (items.length === 0) return items;
  const normalizedOffset = ((offset % items.length) + items.length) % items.length;
  return [...items.slice(normalizedOffset), ...items.slice(0, normalizedOffset)];
}

/**
 * Rewrite template content with AI-style variations
 */
export const rewriteTemplateContent = (raw: string, iteration = 0): string => {
  const normalized = raw.replace(/\r/g, '').trim();
  const variantIndex = Math.max(iteration, 0);

  const openers = [
    'Quick heads-up',
    'Just a quick update',
    "Here's what I'm thinking",
    'Sharing the latest',
    'Checking in real quick',
  ];
  const closers = [
    'Let me know what you think.',
    'Message me if anything feels off.',
    'Ping me with questions.',
    "Happy to tweak-just say the word.",
    'Thanks! Chat soon.',
  ];
  const bulletSymbols = ['-', '-', '-'];
  const fallbackLines = [
    'Sharing a quick update so we stay aligned.',
    "Here's the plan I'd go with right now.",
    "These are the next moves I'm seeing.",
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

/**
 * Load templates from cookie storage
 */
export const loadStoredTemplates = (): TemplateItem[] => {
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
};

/**
 * Save templates to cookie storage
 */
export const saveTemplatesToCookie = (templates: TemplateItem[]): void => {
  if (typeof document === 'undefined') return;
  try {
    const payload = encodeURIComponent(JSON.stringify(templates));
    const oneYearInSeconds = 60 * 60 * 24 * 365;
    document.cookie = `${TEMPLATE_COOKIE_NAME}=${payload}; path=/; max-age=${oneYearInSeconds}`;
  } catch {
    // ignore storage write failures
  }
};

/**
 * Copy text to clipboard with fallback
 */
export const copyToClipboard = async (text: string): Promise<boolean> => {
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
