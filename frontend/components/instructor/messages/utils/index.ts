/**
 * Utility exports for instructor messages
 */

// Re-export formatters from shared messaging location
export {
  formatRelativeTimestamp,
  formatTimeLabel,
  formatShortDate,
  getInitials,
  formatStudentName,
} from '@/components/messaging/formatters';

export * from './messages';
export * from './templates';
