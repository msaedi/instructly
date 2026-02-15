/**
 * API fetch helper.
 *
 * TRACE PROPAGATION:
 * This helper uses native fetch(), which is automatically instrumented by
 * @vercel/otel (configured in instrumentation.ts). The traceparent header
 * is injected into requests matching these patterns:
 * - https://api.instainstru.com/*
 * - https://*.onrender.com/*
 *
 * No manual header injection is needed.
 */
import { withApiBaseForRequest } from '@/lib/apiBase';
import { fetchWithSessionRefresh } from '@/lib/auth/sessionRefresh';
import { logger } from '@/lib/logger';
import { parseProblem, normalizeProblem, type Problem } from '@/lib/errors/problem';

export class ApiProblemError extends Error {
  readonly problem: Problem;
  readonly response: Response;
  readonly requestId?: string;
  readonly traceId?: string;
  constructor(problem: Problem, response: Response) {
    super(problem.title || 'API error');
    this.problem = problem;
    this.response = response;
    const resolvedTraceId =
      problem.trace_id ||
      response.headers?.get?.('x-trace-id') ||
      response.headers?.get?.('X-Trace-ID') ||
      '';
    if (resolvedTraceId) {
      this.traceId = resolvedTraceId;
    }
    const resolvedRequestId =
      problem.request_id ||
      response.headers?.get?.('x-request-id') ||
      response.headers?.get?.('X-Request-ID') ||
      '';
    if (resolvedRequestId) {
      this.requestId = resolvedRequestId;
    }
  }
}

export type FetchOptions = RequestInit & {
  dedupeKey?: string;
  retries?: number;
  onRateLimit?: (info: { endpoint: string; attempt: number; retryAfterMs: number }) => void;
  financial?: boolean;
};

const inflight = new Map<string, Promise<unknown>>();

async function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function jitter(baseMs: number): number {
  const spread = Math.floor(baseMs * 0.25);
  return baseMs + Math.floor(Math.random() * (spread + 1));
}

export async function fetchJson<T = unknown>(endpoint: string, init: FetchOptions = {}): Promise<T> {
  const method = (init.method || 'GET').toUpperCase();
  const url = withApiBaseForRequest(endpoint, method);
  const key = init.dedupeKey;
  const maxRetries = init.retries ?? 1;

  const run = async () => {
    // Note: @vercel/otel automatically injects traceparent headers into fetch()
    // calls matching propagateContextUrls (see instrumentation.ts).
    const res = await fetchWithSessionRefresh(url, { credentials: 'include', ...init });
    if (res.status === 429) {
      if (init.financial) return res;
      const retryAfterHeader = res.headers.get('Retry-After');
      const raSeconds = Number(retryAfterHeader ?? '0');
      const base = raSeconds ? raSeconds * 1000 : 500;
      const waitMs = jitter(base);
      init.onRateLimit?.({ endpoint, attempt: 1, retryAfterMs: waitMs });
      await sleep(waitMs);
      return fetchWithSessionRefresh(url, { credentials: 'include', ...init });
    }
    return res;
  };

  const doRequest = async (): Promise<T> => {
    logger.info(`API ${method} ${endpoint}`, { hasBody: !!init.body });
    const timer = `API ${method} ${endpoint}`;
    logger.time(timer);
    let timerEnded = false;
    try {
      let res = await run();
      let attempt = 1;
      while (!res.ok && res.status === 429 && attempt <= maxRetries) {
        attempt += 1;
        const retryAfterHeader = res.headers.get('Retry-After');
        const raSeconds = Number(retryAfterHeader ?? '0');
        const base = raSeconds ? raSeconds * 1000 : 800;
        const waitMs = jitter(base);
        init.onRateLimit?.( { endpoint, attempt, retryAfterMs: waitMs } );
        await sleep(waitMs);
        res = await fetchWithSessionRefresh(url, { credentials: 'include', ...init });
      }

      logger.timeEnd(timer);
      timerEnded = true;

      const contentType = (res.headers.get('content-type') ?? '').toLowerCase();
      let body: unknown = null;
      if (contentType.includes('json')) {
        try { body = await res.clone().json(); } catch { /* ignore */ }
      }

      let problem = parseProblem(res, body);
      if (!problem && body && typeof body === 'object') {
        const record = body as Record<string, unknown>;
        if (typeof record['code'] === 'string' || typeof record['title'] === 'string') {
          problem = normalizeProblem(record, res.status ?? undefined);
        } else {
          const nested = record['detail'];
          if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
            problem = normalizeProblem(nested as Record<string, unknown>, res.status ?? undefined);
          }
        }
      }
      if (!res.ok && problem) {
        logger.warn('API problem response', { endpoint, status: res.status, problem });
        throw new ApiProblemError(problem, res);
      }

      if (!res.ok) {
        logger.warn('API non-problem error', { endpoint, status: res.status });
        const message = (body && typeof body === 'object' && (body as { detail?: unknown }).detail) || res.statusText || 'Request failed';
        throw new Error(String(message));
      }

      if (contentType.includes('json')) {
        return (await res.json()) as T;
      }
      try { return (await res.json()) as T; } catch { /* fallthrough */ }
      return undefined as unknown as T;
    } catch (err) {
      if (!timerEnded) {
        try {
          logger.timeEnd(timer);
        } catch {
          // ignore timing cleanup failures
        }
      }
      if ((err as { name?: string } | null)?.name === 'AbortError') {
        return undefined as unknown as T;
      }
      if (err instanceof ApiProblemError) {
        logger.warn(`API ${method} ${endpoint} problem`, { problem: err.problem, status: err.response.status });
      } else {
        logger.error(`API ${method} ${endpoint} error`, err);
      }
      throw err;
    }
  };

  if (key) {
    const existing = inflight.get(key) as Promise<T> | undefined;
    if (existing) return existing;
    const p = doRequest();
    inflight.set(key, p);
    try {
      const result = await p;
      return result;
    } finally {
      inflight.delete(key);
    }
  }

  return doRequest();
}
