import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';

const REQUEST_HOP_BY_HOP_HEADERS = new Set([
  'host',
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
  'content-length',
]);

const RESPONSE_HOP_BY_HOP_HEADERS = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
  'content-length',
  'content-encoding',
]);

function resolveBackendBase(): string {
  const explicitBase = (process.env['NEXT_PUBLIC_API_BASE'] ?? '').trim();
  if (explicitBase) {
    return explicitBase.replace(/\/+$/, '');
  }

  const appEnv = (
    process.env['NEXT_PUBLIC_APP_ENV'] ??
    process.env['NEXT_PUBLIC_SITE_MODE'] ??
    ''
  ).toLowerCase();

  if (appEnv === 'preview') {
    return 'https://preview-api.instainstru.com';
  }

  if (appEnv === 'beta' || appEnv === 'prod' || appEnv === 'production') {
    return 'https://api.instainstru.com';
  }

  return 'http://localhost:8000';
}

function buildForwardHeaders(request: NextRequest): Headers {
  const headers = new Headers();

  request.headers.forEach((value, key) => {
    const normalizedKey = key.toLowerCase();
    if (REQUEST_HOP_BY_HOP_HEADERS.has(normalizedKey) || normalizedKey.startsWith('x-forwarded-')) {
      return;
    }
    headers.set(key, value);
  });

  return headers;
}

function appendSetCookieHeaders(from: Headers, to: Headers): void {
  const getSetCookie = (from as Headers & { getSetCookie?: () => string[] }).getSetCookie;

  if (typeof getSetCookie === 'function') {
    const values = getSetCookie.call(from);
    for (const value of values) {
      to.append('set-cookie', value);
    }
    return;
  }

  const combined = from.get('set-cookie');
  if (combined) {
    to.set('set-cookie', combined);
  }
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ slug: string }> }
): Promise<NextResponse> {
  const { slug } = await context.params;
  const backendBase = resolveBackendBase();
  const targetUrl = `${backendBase}/api/v1/r/${encodeURIComponent(slug)}${request.nextUrl.search}`;

  let upstreamResponse: Response;
  try {
    upstreamResponse = await fetch(targetUrl, {
      method: 'GET',
      headers: buildForwardHeaders(request),
      cache: 'no-store',
      redirect: 'manual',
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    return NextResponse.json({ error: 'Referral route failed' }, { status: 502 });
  }

  const location = upstreamResponse.headers.get('location');
  const isRedirect =
    upstreamResponse.status >= 300 && upstreamResponse.status < 400 && typeof location === 'string';

  const response = isRedirect
    ? NextResponse.redirect(location, { status: upstreamResponse.status })
    : new NextResponse(await upstreamResponse.arrayBuffer(), {
        status: upstreamResponse.status,
        statusText: upstreamResponse.statusText,
      });

  upstreamResponse.headers.forEach((value, key) => {
    const normalizedKey = key.toLowerCase();
    if (RESPONSE_HOP_BY_HOP_HEADERS.has(normalizedKey) || normalizedKey === 'set-cookie') {
      return;
    }
    if (!isRedirect || normalizedKey !== 'location') {
      response.headers.set(key, value);
    }
  });

  appendSetCookieHeaders(upstreamResponse.headers, response.headers);
  response.headers.set('Cache-Control', 'no-store');
  return response;
}
