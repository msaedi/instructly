/** @jest-environment node */

import { NextRequest } from 'next/server';

import { GET } from '@/app/r/[slug]/route';

describe('/r/[slug] referral route', () => {
  const originalFetch = global.fetch;
  const originalApiBase = process.env.NEXT_PUBLIC_API_BASE;

  beforeEach(() => {
    Object.defineProperty(process.env, 'NEXT_PUBLIC_API_BASE', {
      value: 'https://api.example.test',
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

    if (originalApiBase === undefined) {
      Reflect.deleteProperty(process.env, 'NEXT_PUBLIC_API_BASE');
    } else {
      Object.defineProperty(process.env, 'NEXT_PUBLIC_API_BASE', {
        value: originalApiBase,
        writable: true,
        configurable: true,
      });
    }

    jest.restoreAllMocks();
  });

  it('forwards to the backend resolver and mirrors redirect responses', async () => {
    const upstreamHeaders = new Headers({
      location: 'https://frontend.test/signup?ref=FNVC6KDW',
      'content-type': 'text/plain',
    });
    upstreamHeaders.append('set-cookie', 'referral_code=FNVC6KDW; Path=/; HttpOnly');

    const fetchMock = jest.fn().mockResolvedValue(new Response(null, { status: 307, headers: upstreamHeaders }));
    Object.defineProperty(global, 'fetch', {
      value: fetchMock,
      writable: true,
      configurable: true,
    });

    const request = new NextRequest('https://frontend.test/r/FNVC6KDW?utm_source=test', {
      headers: {
        cookie: 'session=abc',
        'accept-language': 'en-US',
      },
    });

    const response = await GET(request, {
      params: Promise.resolve({ slug: 'FNVC6KDW' }),
    });

    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.example.test/api/v1/r/FNVC6KDW?utm_source=test',
      expect.objectContaining({
        method: 'GET',
        cache: 'no-store',
        redirect: 'manual',
        headers: expect.any(Headers),
        signal: expect.any(AbortSignal),
      })
    );

    const forwardedHeaders = fetchMock.mock.calls[0][1].headers as Headers;
    expect(forwardedHeaders.get('cookie')).toBe('session=abc');
    expect(forwardedHeaders.get('accept-language')).toBe('en-US');

    expect(response.status).toBe(307);
    expect(response.headers.get('location')).toBe('https://frontend.test/signup?ref=FNVC6KDW');
    expect(response.headers.get('set-cookie')).toContain('referral_code=FNVC6KDW');
    expect(response.headers.get('cache-control')).toBe('no-store');
  });

  it('passes through non-redirect responses', async () => {
    const fetchMock = jest.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Referral not found' }), {
        status: 404,
        headers: { 'content-type': 'application/json' },
      })
    );
    Object.defineProperty(global, 'fetch', {
      value: fetchMock,
      writable: true,
      configurable: true,
    });

    const request = new NextRequest('https://frontend.test/r/UNKNOWN');
    const response = await GET(request, {
      params: Promise.resolve({ slug: 'UNKNOWN' }),
    });

    expect(response.status).toBe(404);
    await expect(response.json()).resolves.toEqual({ detail: 'Referral not found' });
  });
});
