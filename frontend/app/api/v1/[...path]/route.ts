import { NextRequest, NextResponse } from 'next/server';
import { checkBotId } from 'botid/server';

import { logger } from '@/lib/logger';
import { isProtectedMutationRequest } from '@/lib/security/protected-mutation-routes';

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

const BACKEND_BASE = resolveBackendBase();

function buildRequestPath(pathSegments: string[]): string {
  const safePath = pathSegments.filter(Boolean).join('/');
  return `/api/v1/${safePath}`;
}

function buildForwardHeaders(request: NextRequest): Headers {
  const headers = new Headers();

  request.headers.forEach((value, key) => {
    const lowerKey = key.toLowerCase();
    if (REQUEST_HOP_BY_HOP_HEADERS.has(lowerKey) || lowerKey.startsWith('x-forwarded-')) {
      return;
    }
    headers.set(key, value);
  });

  return headers;
}

function appendSetCookieHeaders(from: Headers, to: Headers): void {
  const getSetCookie = (
    from as Headers & { getSetCookie?: () => string[] }
  ).getSetCookie;

  if (typeof getSetCookie === 'function') {
    const cookieValues = getSetCookie.call(from);
    for (const cookieValue of cookieValues) {
      to.append('set-cookie', cookieValue);
    }
    return;
  }

  const combined = from.get('set-cookie');
  if (combined) {
    to.set('set-cookie', combined);
  }
}

async function proxyMutationRequest(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  const method = request.method.toUpperCase();
  const { path } = await context.params;
  const requestPath = buildRequestPath(path);

  if (!isProtectedMutationRequest(requestPath, method)) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 });
  }

  try {
    const verification = await checkBotId();
    if (verification.isBot) {
      return NextResponse.json({ error: 'Access denied' }, { status: 403 });
    }
  } catch (error) {
    // Fail-open by product decision: preserve availability when BotID verification fails.
    logger.warn('[botid] verification failed, allowing protected mutation', {
      path: requestPath,
      method,
      error: error instanceof Error ? error.message : String(error),
    });
  }

  const targetUrl = `${BACKEND_BASE}${requestPath}${request.nextUrl.search}`;
  const headers = buildForwardHeaders(request);

  const bodyBuffer = await request.arrayBuffer();
  const upstreamInit: RequestInit = {
    method,
    headers,
    cache: 'no-store',
    redirect: 'manual',
    signal: AbortSignal.timeout(30_000),
  };
  if (bodyBuffer.byteLength > 0) {
    upstreamInit.body = bodyBuffer;
  }

  let upstreamResponse: Response;
  try {
    upstreamResponse = await fetch(targetUrl, upstreamInit);
  } catch (error) {
    logger.error('[botid-proxy] failed to reach backend', error, {
      path: requestPath,
      method,
    });
    return NextResponse.json({ error: 'Proxy request failed' }, { status: 502 });
  }

  const upstreamBody = await upstreamResponse.arrayBuffer();
  const proxyResponse = new NextResponse(
    upstreamBody.byteLength > 0 ? upstreamBody : null,
    {
      status: upstreamResponse.status,
      statusText: upstreamResponse.statusText,
    }
  );

  upstreamResponse.headers.forEach((value, key) => {
    const lowerKey = key.toLowerCase();
    if (RESPONSE_HOP_BY_HOP_HEADERS.has(lowerKey) || lowerKey === 'set-cookie') {
      return;
    }
    proxyResponse.headers.set(key, value);
  });

  appendSetCookieHeaders(upstreamResponse.headers, proxyResponse.headers);
  proxyResponse.headers.set('Cache-Control', 'no-store');
  return proxyResponse;
}

export const POST = proxyMutationRequest;
export const PUT = proxyMutationRequest;
export const PATCH = proxyMutationRequest;
export const DELETE = proxyMutationRequest;
