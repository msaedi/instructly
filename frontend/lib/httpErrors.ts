export type ProblemEntry = {
  type?: string;
  loc?: Array<string | number>;
  msg?: string;
  message?: string;
  detail?: string;
  input?: unknown;
  url?: string;
  [key: string]: unknown;
};

export type ProblemJson = {
  type?: string;
  title?: string;
  status?: number;
  detail?: string | ProblemEntry[];
  errors?: ProblemEntry[];
  message?: string;
  [key: string]: unknown;
};

export function formatProblemMessages(body: unknown): string[] {
  const out: string[] = [];
  const base = (body ?? {}) as ProblemJson;

  const detail = (base as Record<string, unknown>)['detail'];
  const errors = (base as Record<string, unknown>)['errors'];

  const entries: ProblemEntry[] = [];
  if (Array.isArray(detail)) entries.push(...(detail as ProblemEntry[]));
  if (Array.isArray(errors)) entries.push(...(errors as ProblemEntry[]));

  for (const entry of entries) {
    const rec = entry as Record<string, unknown>;
    const loc = Array.isArray(rec['loc'])
      ? (rec['loc'] as Array<string | number>).filter((part) => part !== 'body')
      : [];
    const message =
      (typeof rec['msg'] === 'string' && (rec['msg'] as string)) ||
      (typeof rec['message'] === 'string' && (rec['message'] as string)) ||
      (typeof rec['detail'] === 'string' && (rec['detail'] as string)) ||
      'Validation error';
    const path = loc.map((part) => String(part)).join('.');
    out.push(path ? `${path}: ${message}` : message);
  }

  if (!out.length) {
    if (typeof (base as Record<string, unknown>)['detail'] === 'string') {
      out.push((base as Record<string, unknown>)['detail'] as string);
    } else if (typeof detail === 'object' && detail !== null && !Array.isArray(detail)) {
      const msg = (detail as Record<string, unknown>)?.['message'];
      if (typeof msg === 'string') out.push(msg);
    } else if (typeof (base as Record<string, unknown>)['message'] === 'string') {
      out.push((base as Record<string, unknown>)['message'] as string);
    }
  }

  return out;
}
