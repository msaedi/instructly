import { getSupportCode } from '../errors/supportCode';

function makeHeaders(values: Record<string, string>) {
  return {
    get: (name: string) => values[name] ?? values[name.toLowerCase()] ?? null,
  };
}

describe('getSupportCode', () => {
  test('prefers trace_id over request_id when both present', () => {
    const error = { trace_id: 'trace-123', request_id: 'req-456' };
    expect(getSupportCode(error)).toBe('trace-123');
  });

  test('uses request_id when trace_id missing', () => {
    const error = { request_id: 'req-999' };
    expect(getSupportCode(error)).toBe('req-999');
  });

  test('falls back to X-Trace-ID header before X-Request-ID', () => {
    const error = {
      response: { headers: makeHeaders({ 'x-trace-id': 'trace-hdr', 'x-request-id': 'req-hdr' }) },
    };
    expect(getSupportCode(error)).toBe('trace-hdr');
  });

  test('falls back to X-Request-ID header when no trace found', () => {
    const error = { response: { headers: makeHeaders({ 'x-request-id': 'req-hdr' }) } };
    expect(getSupportCode(error)).toBe('req-hdr');
  });

  test('uses request_id before header trace when only request_id present', () => {
    const error = {
      request_id: 'req-body',
      response: { headers: makeHeaders({ 'x-trace-id': 'trace-hdr' }) },
    };
    expect(getSupportCode(error)).toBe('req-body');
  });
});
