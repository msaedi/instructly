import type { ApiErrorResponse } from '@/features/shared/api/types';

const getTrimmedMessage = (value: unknown): string | null => {
  if (typeof value !== 'string') {
    return null;
  }

  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
};

const extractUnknownErrorMessageInternal = (
  source: unknown,
  seen: WeakSet<object>
): string | null => {
  if (typeof source === 'string') {
    return getTrimmedMessage(source);
  }

  if (!source || typeof source !== 'object') {
    return null;
  }

  if (seen.has(source)) {
    return null;
  }
  seen.add(source);

  const record = source as Record<string, unknown>;

  if ('data' in record) {
    const nestedMessage = extractUnknownErrorMessageInternal(record['data'], seen);
    if (nestedMessage) {
      return nestedMessage;
    }
  }

  const detail = record['detail'];
  const detailMessage = getTrimmedMessage(detail);
  if (detailMessage) {
    return detailMessage;
  }

  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const structuredMessage = getTrimmedMessage((detail as Record<string, unknown>)['message']);
    if (structuredMessage) {
      return structuredMessage;
    }
  }

  return getTrimmedMessage(record['message']);
};

export function extractUnknownErrorMessage(source: unknown): string | null {
  return extractUnknownErrorMessageInternal(source, new WeakSet<object>());
}

/**
 * Extract a human-readable error message from an API error response.
 *
 * Handles both string `detail` (simple errors) and structured
 * `{ message, code, details }` objects (DomainException responses).
 */
export function extractApiErrorMessage(
  response: ApiErrorResponse | unknown,
  fallback: string = 'An error occurred'
): string {
  return extractUnknownErrorMessage(response) ?? fallback;
}

export function extractApiErrorCode(response: ApiErrorResponse): string | undefined {
  const { detail } = response;

  if (typeof detail === 'object' && detail !== null && typeof detail.code === 'string') {
    return detail.code;
  }

  const topLevelCode = (response as ApiErrorResponse & { code?: unknown }).code;
  return typeof topLevelCode === 'string' ? topLevelCode : undefined;
}
