import { NextResponse } from 'next/server';

import { logger } from '@/lib/logger';

const EMPTY_RESPONSE = new NextResponse(null, { status: 204 });

export function GET() {
  return EMPTY_RESPONSE;
}

export function HEAD() {
  return EMPTY_RESPONSE;
}

const CSP_REPORT_CONTENT_TYPES = ['application/csp-report', 'application/reports+json'] as const;

function isCspReportRequest(contentTypeHeader: string | null): boolean {
  if (!contentTypeHeader) {
    return false;
  }
  const contentType = contentTypeHeader.toLowerCase();
  return CSP_REPORT_CONTENT_TYPES.some((candidate) => contentType.includes(candidate));
}

function extractEnvelopeHeaderLine(rawBody: string): string | null {
  const firstNewlineIndex = rawBody.indexOf('\n');
  const firstLine = firstNewlineIndex >= 0 ? rawBody.slice(0, firstNewlineIndex) : rawBody;
  const trimmed = firstLine.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function extractProjectIdFromDsnPath(pathname: string): string | null {
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length === 0) {
    return null;
  }

  const ingestIndex = segments.findIndex((segment) => segment === 'ingest');
  if (ingestIndex >= 0 && ingestIndex + 1 < segments.length) {
    const projectId = segments[ingestIndex + 1];
    return typeof projectId === 'string' ? projectId : null;
  }

  if (segments.length === 1) {
    const projectId = segments[0];
    return typeof projectId === 'string' ? projectId : null;
  }

  return null;
}

function isAllowedSentryHost(hostname: string): boolean {
  const normalizedHost = hostname.toLowerCase();
  const configuredDsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

  if (configuredDsn) {
    try {
      const configuredHost = new URL(configuredDsn).hostname.toLowerCase();
      if (configuredHost && normalizedHost === configuredHost) {
        return true;
      }
    } catch {
      // Ignore invalid configured DSN and continue with official-domain validation.
    }
  }

  return (
    normalizedHost === 'sentry.io' ||
    normalizedHost.endsWith('.sentry.io') ||
    normalizedHost.endsWith('.ingest.sentry.io')
  );
}

function parseEnvelopeTarget(rawBody: string): { forwardUrl: string; dsnHost: string } | null {
  const headerLine = extractEnvelopeHeaderLine(rawBody);
  if (!headerLine) {
    return null;
  }

  let parsedHeader: unknown;
  try {
    parsedHeader = JSON.parse(headerLine);
  } catch {
    return null;
  }

  if (!parsedHeader || typeof parsedHeader !== 'object') {
    return null;
  }

  const dsn =
    'dsn' in parsedHeader && typeof parsedHeader.dsn === 'string' ? parsedHeader.dsn : null;
  if (!dsn) {
    return null;
  }

  let parsedDsn: URL;
  try {
    parsedDsn = new URL(dsn);
  } catch {
    return null;
  }

  if (!isAllowedSentryHost(parsedDsn.hostname)) {
    return null;
  }

  const projectId = extractProjectIdFromDsnPath(parsedDsn.pathname);
  if (!projectId || !/^\d+$/.test(projectId)) {
    return null;
  }

  const forwardUrl = `${parsedDsn.protocol}//${parsedDsn.host}/api/${projectId}/envelope/`;
  return { forwardUrl, dsnHost: parsedDsn.hostname };
}

export async function POST(request: Request) {
  const rawBody = await request.text();
  if (!rawBody.trim()) {
    return NextResponse.json({ error: 'Request body is required' }, { status: 400 });
  }

  if (isCspReportRequest(request.headers.get('content-type'))) {
    try {
      const parsed = JSON.parse(rawBody) as Record<string, unknown>;
      const report = parsed['csp-report'] ?? parsed;
      logger.warn('[monitoring] CSP report received', report);
    } catch {
      logger.warn('[monitoring] CSP report received but failed to parse JSON body');
    }
    return NextResponse.json({ ok: true }, { status: 200 });
  }

  const target = parseEnvelopeTarget(rawBody);
  if (!target) {
    return NextResponse.json({ error: 'Invalid Sentry envelope payload' }, { status: 400 });
  }

  try {
    const upstreamResponse = await fetch(target.forwardUrl, {
      method: 'POST',
      headers: { 'content-type': 'application/x-sentry-envelope' },
      body: rawBody,
    });
    return new NextResponse(null, { status: upstreamResponse.status });
  } catch (error) {
    logger.error('[monitoring] Failed forwarding Sentry envelope', error, {
      host: target.dsnHost,
    });
    return NextResponse.json({ error: 'Upstream monitoring service unavailable' }, { status: 502 });
  }
}
