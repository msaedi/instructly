/** @jest-environment node */

import { NextRequest } from 'next/server';

import { POST } from '@/app/api/v1/[...path]/route';
import * as routeModule from '@/app/api/v1/[...path]/route';

const checkBotIdMock = jest.fn();

jest.mock('botid/server', () => ({
  checkBotId: (...args: unknown[]) => checkBotIdMock(...args),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

describe('/api/v1/[...path] protected mutation proxy', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    checkBotIdMock.mockReset();
    checkBotIdMock.mockResolvedValue({
      isHuman: true,
      isBot: false,
      isVerifiedBot: false,
      bypassed: true,
    });
  });

  afterEach(() => {
    Object.defineProperty(global, 'fetch', {
      value: originalFetch,
      writable: true,
      configurable: true,
    });
    jest.restoreAllMocks();
  });

  it('forwards protected human mutations and preserves headers/cookies', async () => {
    const upstreamHeaders = new Headers({
      'content-type': 'application/json',
      'x-backend': 'ok',
    });
    upstreamHeaders.append('set-cookie', 'sid=abc; Path=/; HttpOnly');
    upstreamHeaders.append('set-cookie', 'csrf=def; Path=/');

    const fetchMock = jest.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 201,
        headers: upstreamHeaders,
      })
    );
    Object.defineProperty(global, 'fetch', {
      value: fetchMock,
      writable: true,
      configurable: true,
    });

    const request = new NextRequest('https://frontend.test/api/v1/auth/login?source=ui', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        cookie: 'session=abc',
        'idempotency-key': 'idem-123',
        'x-csrf-token': 'csrf-token',
      },
      body: JSON.stringify({ username: 'user@example.com' }),
    });

    const response = await POST(request, {
      params: Promise.resolve({ path: ['auth', 'login'] }),
    });

    expect(response.status).toBe(201);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [targetUrl, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(targetUrl).toContain('/api/v1/auth/login?source=ui');

    const forwardedHeaders = init.headers as Headers;
    expect(forwardedHeaders.get('cookie')).toBe('session=abc');
    expect(forwardedHeaders.get('content-type')).toContain('application/json');
    expect(forwardedHeaders.get('idempotency-key')).toBe('idem-123');
    expect(forwardedHeaders.get('x-csrf-token')).toBe('csrf-token');

    expect(response.headers.get('x-backend')).toBe('ok');
    const setCookie = response.headers.get('set-cookie') ?? '';
    expect(setCookie).toContain('sid=abc');
    expect(setCookie).toContain('csrf=def');
  });

  it('returns 403 for BotID-classified bots', async () => {
    checkBotIdMock.mockResolvedValue({
      isHuman: false,
      isBot: true,
      isVerifiedBot: false,
      bypassed: false,
    });
    const fetchMock = jest.fn();
    Object.defineProperty(global, 'fetch', {
      value: fetchMock,
      writable: true,
      configurable: true,
    });

    const request = new NextRequest('https://frontend.test/api/v1/bookings', {
      method: 'POST',
      body: JSON.stringify({}),
    });
    const response = await POST(request, {
      params: Promise.resolve({ path: ['bookings'] }),
    });
    const payload = await response.json();

    expect(response.status).toBe(403);
    expect(payload).toEqual({ error: 'Access denied' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('continues forwarding when BotID verification throws (fail-open)', async () => {
    checkBotIdMock.mockRejectedValue(new Error('botid unavailable'));
    const fetchMock = jest.fn().mockResolvedValue(new Response(null, { status: 204 }));
    Object.defineProperty(global, 'fetch', {
      value: fetchMock,
      writable: true,
      configurable: true,
    });

    const request = new NextRequest('https://frontend.test/api/v1/messages/mark-read', {
      method: 'POST',
      body: JSON.stringify({}),
      headers: { 'content-type': 'application/json' },
    });
    const response = await POST(request, {
      params: Promise.resolve({ path: ['messages', 'mark-read'] }),
    });

    expect(response.status).toBe(204);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('returns 404 for unprotected mutation paths', async () => {
    const fetchMock = jest.fn();
    Object.defineProperty(global, 'fetch', {
      value: fetchMock,
      writable: true,
      configurable: true,
    });

    const request = new NextRequest('https://frontend.test/api/v1/health', {
      method: 'POST',
      body: JSON.stringify({}),
      headers: { 'content-type': 'application/json' },
    });
    const response = await POST(request, {
      params: Promise.resolve({ path: ['health'] }),
    });
    const payload = await response.json();

    expect(response.status).toBe(404);
    expect(payload).toEqual({ error: 'Not found' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does not export GET so Next returns 405 for unsupported methods', () => {
    expect((routeModule as { GET?: unknown }).GET).toBeUndefined();
  });
});
