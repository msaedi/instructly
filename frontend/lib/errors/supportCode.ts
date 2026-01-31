type MaybeRecord = Record<string, unknown>;

function isRecord(value: unknown): value is MaybeRecord {
  return typeof value === 'object' && value !== null;
}

function getHeaderValue(headers: unknown): string | null {
  if (!headers || typeof (headers as { get?: unknown }).get !== 'function') return null;
  const getter = headers as { get: (name: string) => string | null };
  return getter.get('x-request-id') || getter.get('X-Request-ID');
}

export function getSupportCode(error: unknown): string | null {
  if (!isRecord(error)) return null;

  const direct = error['requestId'] ?? error['request_id'];
  if (typeof direct === 'string' && direct.trim().length > 0) {
    return direct;
  }

  const data = error['data'];
  if (isRecord(data)) {
    const dataRequestId = data['request_id'] ?? data['requestId'];
    if (typeof dataRequestId === 'string' && dataRequestId.trim().length > 0) {
      return dataRequestId;
    }
  }

  const problem = error['problem'];
  if (isRecord(problem)) {
    const problemRequestId = problem['request_id'] ?? problem['requestId'];
    if (typeof problemRequestId === 'string' && problemRequestId.trim().length > 0) {
      return problemRequestId;
    }
  }

  const response = error['response'];
  if (isRecord(response)) {
    const headerValue = getHeaderValue(response['headers']);
    if (typeof headerValue === 'string' && headerValue.trim().length > 0) {
      return headerValue;
    }
  }

  return null;
}

export function formatSupportCode(code: string): string {
  return code.trim();
}

export function formatSupportCodeShort(code: string, length = 8): string {
  const trimmed = code.trim();
  if (trimmed.length <= length) return trimmed;
  return trimmed.slice(0, length);
}
