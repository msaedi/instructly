import type { ApiErrorResponse } from '@/features/shared/api/types';

/**
 * Extract a human-readable error message from an API error response.
 *
 * Handles both string `detail` (simple errors) and structured
 * `{ message, code, details }` objects (DomainException responses).
 */
export function extractApiErrorMessage(
  response: ApiErrorResponse,
  fallback: string = 'An error occurred'
): string {
  const { detail, message } = response;

  if (typeof detail === 'string' && detail.trim().length > 0) {
    return detail;
  }

  if (typeof detail === 'object' && detail !== null) {
    if (typeof detail.message === 'string' && detail.message.trim().length > 0) {
      return detail.message;
    }
  }

  if (typeof message === 'string' && message.trim().length > 0) {
    return message;
  }

  return fallback;
}
