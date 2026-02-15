/** @jest-environment node */

import { GET, HEAD, POST } from '@/app/monitoring/route';

describe('/monitoring route handler', () => {
  const originalFetch = global.fetch;
  const originalSentryDsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

  beforeEach(() => {
    Object.defineProperty(process.env, 'NEXT_PUBLIC_SENTRY_DSN', {
      value: '',
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    Object.defineProperty(global, 'fetch', {
      value: originalFetch,
      writable: true,
      configurable: true,
    });
    if (originalSentryDsn === undefined) {
      delete process.env.NEXT_PUBLIC_SENTRY_DSN;
    } else {
      Object.defineProperty(process.env, 'NEXT_PUBLIC_SENTRY_DSN', {
        value: originalSentryDsn,
        writable: true,
        configurable: true,
      });
    }
    jest.restoreAllMocks();
  });

  it('keeps GET and HEAD responses available', () => {
    expect(GET().status).toBe(204);
    expect(HEAD().status).toBe(204);
  });

  it('forwards valid Sentry envelope payloads using ingest-style DSN', async () => {
    const fetchMock = jest.fn().mockResolvedValue(new Response(null, { status: 202 }));
    Object.defineProperty(global, 'fetch', {
      value: fetchMock,
      writable: true,
      configurable: true,
    });

    const body = [
      '{"dsn":"https://public@example.ingest.us.sentry.io/ingest/123456"}',
      '{"type":"event"}',
      '{"message":"hello"}',
    ].join('\n');
    const request = new Request('http://localhost/monitoring', {
      method: 'POST',
      body,
    });

    const response = await POST(request);

    expect(response.status).toBe(202);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('https://example.ingest.us.sentry.io/api/123456/envelope/');
    expect(init.method).toBe('POST');
    expect(init.body).toBe(body);
    expect(init.headers).toEqual({ 'content-type': 'application/x-sentry-envelope' });
  });

  it('forwards valid Sentry envelope payloads using legacy DSN path', async () => {
    const fetchMock = jest.fn().mockResolvedValue(new Response(null, { status: 200 }));
    Object.defineProperty(global, 'fetch', {
      value: fetchMock,
      writable: true,
      configurable: true,
    });

    const body = [
      '{"dsn":"https://public@o12345.ingest.sentry.io/7890"}',
      '{"type":"event"}',
      '{"message":"legacy"}',
    ].join('\n');
    const request = new Request('http://localhost/monitoring', {
      method: 'POST',
      headers: { 'content-type': 'text/plain' },
      body,
    });

    const response = await POST(request);

    expect(response.status).toBe(200);
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('https://o12345.ingest.sentry.io/api/7890/envelope/');
  });

  it('returns 400 when body is empty', async () => {
    const request = new Request('http://localhost/monitoring', {
      method: 'POST',
      body: '',
    });

    const response = await POST(request);
    const payload = await response.json();

    expect(response.status).toBe(400);
    expect(payload).toEqual({ error: 'Request body is required' });
  });

  it('returns 400 for malformed envelope first line', async () => {
    const request = new Request('http://localhost/monitoring', {
      method: 'POST',
      body: 'not-json\n{"type":"event"}',
    });

    const response = await POST(request);
    const payload = await response.json();

    expect(response.status).toBe(400);
    expect(payload).toEqual({ error: 'Invalid Sentry envelope payload' });
  });

  it('returns 400 when envelope header has no DSN', async () => {
    const request = new Request('http://localhost/monitoring', {
      method: 'POST',
      body: '{"trace":{"foo":"bar"}}\n{"type":"event"}',
    });

    const response = await POST(request);
    const payload = await response.json();

    expect(response.status).toBe(400);
    expect(payload).toEqual({ error: 'Invalid Sentry envelope payload' });
  });

  it('returns 400 for disallowed DSN hosts', async () => {
    const request = new Request('http://localhost/monitoring', {
      method: 'POST',
      body: '{"dsn":"https://public@evil.example.com/123"}\n{"type":"event"}',
    });

    const response = await POST(request);
    const payload = await response.json();

    expect(response.status).toBe(400);
    expect(payload).toEqual({ error: 'Invalid Sentry envelope payload' });
  });

  it('returns 502 when envelope forwarding throws', async () => {
    const fetchMock = jest.fn().mockRejectedValue(new Error('network error'));
    Object.defineProperty(global, 'fetch', {
      value: fetchMock,
      writable: true,
      configurable: true,
    });

    const request = new Request('http://localhost/monitoring', {
      method: 'POST',
      body: '{"dsn":"https://public@o123.ingest.sentry.io/456"}\n{"type":"event"}',
    });

    const response = await POST(request);
    const payload = await response.json();

    expect(response.status).toBe(502);
    expect(payload).toEqual({ error: 'Upstream monitoring service unavailable' });
  });

  it('accepts CSP reports and returns 200', async () => {
    const fetchMock = jest.fn();
    Object.defineProperty(global, 'fetch', {
      value: fetchMock,
      writable: true,
      configurable: true,
    });

    const request = new Request('http://localhost/monitoring', {
      method: 'POST',
      headers: { 'content-type': 'application/csp-report' },
      body: JSON.stringify({
        'csp-report': {
          'blocked-uri': 'https://bad.example.com/script.js',
          'violated-directive': 'script-src',
        },
      }),
    });

    const response = await POST(request);
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload).toEqual({ ok: true });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
