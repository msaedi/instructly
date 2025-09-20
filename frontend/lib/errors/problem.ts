export type Problem = {
  type: string;
  title: string;
  detail: string;
  status: number;
  code?: string;
  request_id?: string;
  instance?: string;
  errors?: unknown;
};

export function isProblemJsonContentType(contentType: string | null | undefined): boolean {
  if (!contentType) return false;
  return contentType.toLowerCase().startsWith("application/problem+json");
}

type ResponseLike = Response | { headers: { get: (k: string) => string | null }; status?: number };

export function parseProblem(res: ResponseLike, body: unknown): Problem | null {
  const ct = res.headers?.get("content-type") ?? "";
  if (!isProblemJsonContentType(ct)) return null;

  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    const maybeTitle = record["title"];
    if (typeof maybeTitle === "string") {
      return normalizeProblem(record, res.status ?? undefined);
    }
  }

  return normalizeProblem({}, res.status ?? undefined);
}

export function normalizeProblem(problem: Record<string, unknown>, fallbackStatus?: number): Problem {
  const type = typeof problem.type === 'string' && problem.type.length > 0 ? problem.type : 'about:blank';
  const title = typeof problem.title === 'string' && problem.title.length > 0 ? problem.title : 'Unknown error';
  const statusSource = problem.status;
  const status = typeof statusSource === 'number' ? statusSource : fallbackStatus ?? 500;
  const detail = typeof problem.detail === 'string' ? problem.detail : '';
  const instance = typeof problem.instance === 'string' ? problem.instance : '';
  const code = typeof problem.code === 'string' ? problem.code : undefined;
  const requestId = typeof problem.request_id === 'string' ? problem.request_id : undefined;
  const errors = problem.errors;

  return {
    type,
    title,
    status,
    detail,
    instance,
    code,
    request_id: requestId,
    errors,
  };
}
