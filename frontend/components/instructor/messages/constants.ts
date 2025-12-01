/**
 * Constants for the Instructor Messages Page
 */

import type { FilterOption, TemplateItem } from './types';

/**
 * Special thread ID for compose view
 */
export const COMPOSE_THREAD_ID = '__compose__';

/**
 * Cookie names for persistence
 */
export const DRAFT_COOKIE_NAME = 'instructor_message_drafts';
export const TEMPLATE_COOKIE_NAME = 'instructor_message_templates';

/**
 * Retry delay for history loading after error (10 seconds)
 */
export const HISTORY_RETRY_DELAY_MS = 10_000;

/**
 * Polling interval for conversation refresh (30 seconds)
 */
export const CONVERSATION_REFRESH_INTERVAL_MS = 30_000;

/**
 * Labels for empty states
 */
export const ARCHIVED_LABEL = 'All messages archived';
export const TRASH_LABEL = 'All messages trashed';

/**
 * Filter options for conversation list
 */
export const FILTER_OPTIONS: FilterOption[] = [
  { label: 'All', value: 'all' },
  { label: 'Students', value: 'student' },
  { label: 'Platform', value: 'platform' },
];

/**
 * Default message templates
 */
export const DEFAULT_TEMPLATES: TemplateItem[] = [
  {
    id: 'welcome',
    subject: 'Welcome to iNSTAiNSTRU',
    preview: 'Thanks for reaching out! Excited to work together...',
    body: `Hi there,

Thanks for reaching out! I'm excited to work with you on your learning goals. Let me know a few dates/times that work for a first session and we can get it on the calendar.

Talk soon,
[Your name]`,
  },
  {
    id: 'availability',
    subject: 'Scheduling your next lesson',
    preview: 'Here are a few time slots I currently have open...',
    body: `Hi there,

Here are a few time slots I currently have open:
- Monday 5:00 PM
- Wednesday 6:30 PM
- Saturday 11:00 AM

Let me know which works best and I'll send over the booking link.

Best,
[Your name]`,
  },
  {
    id: 'homework',
    subject: 'Lesson recap & practice plan',
    preview: "Here's what to focus on before our next session...",
    body: `Hi there,

Great work today! Here's what to focus on before our next session:
1. Review the technique we covered for 15 minutes each day.
2. Complete exercise set B in the practice booklet.
3. Jot down any questions so we can tackle them together.

See you next time,
[Your name]`,
  },
];

/**
 * Get a fresh copy of default templates
 */
export const getDefaultTemplates = (): TemplateItem[] =>
  DEFAULT_TEMPLATES.map((template) => ({ ...template }));
