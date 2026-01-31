type MaybeRecord = Record<string, unknown>;

function isRecord(value: unknown): value is MaybeRecord {
  return typeof value === 'object' && value !== null;
}

function getHeaderValue(headers: unknown, names: string[]): string | null {
  if (!headers || typeof (headers as { get?: unknown }).get !== 'function') return null;
  const getter = headers as { get: (name: string) => string | null };
  for (const name of names) {
    const value = getter.get(name);
    if (typeof value === 'string' && value.trim().length > 0) {
      return value;
    }
  }
  return null;
}

function getString(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function getSupportCode(error: unknown): string | null {
  if (!isRecord(error)) return null;

  const directTrace = getString(error['trace_id'] ?? error['traceId']);
  if (directTrace) return directTrace;

  const data = error['data'];
  if (isRecord(data)) {
    const dataTrace = getString(data['trace_id'] ?? data['traceId']);
    if (dataTrace) return dataTrace;
  }

  const problem = error['problem'];
  if (isRecord(problem)) {
    const problemTrace = getString(problem['trace_id'] ?? problem['traceId']);
    if (problemTrace) return problemTrace;
  }

  const direct = getString(error['requestId'] ?? error['request_id']);
  if (direct) return direct;

  if (isRecord(data)) {
    const dataRequestId = getString(data['request_id'] ?? data['requestId']);
    if (dataRequestId) return dataRequestId;
  }

  if (isRecord(problem)) {
    const problemRequestId = getString(problem['request_id'] ?? problem['requestId']);
    if (problemRequestId) return problemRequestId;
  }

  const response = error['response'];
  if (isRecord(response)) {
    const traceHeader = getHeaderValue(response['headers'], ['x-trace-id', 'X-Trace-ID']);
    if (traceHeader) return traceHeader;
    const requestHeader = getHeaderValue(response['headers'], ['x-request-id', 'X-Request-ID']);
    if (requestHeader) return requestHeader;
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
