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
  const ct = (res.headers?.get("content-type") ?? "").toLowerCase();

  if (isProblemJsonContentType(ct)) {
    if (body && typeof body === "object") {
      const record = body as Record<string, unknown>;
      const maybeTitle = record["title"];
      if (typeof maybeTitle === "string") {
        return normalizeProblem(record, res.status ?? undefined);
      }
    }
    return normalizeProblem({}, res.status ?? undefined);
  }

  // Handle FastAPI/Starlette structured errors in application/json
  if (ct.includes("application/json") && body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    // Check for { detail: { ... } } pattern used by HTTPException for structured errors
    if (record['detail'] && typeof record['detail'] === 'object' && !Array.isArray(record['detail'])) {
      const detailObj = record['detail'] as Record<string, unknown>;
      // We treat it as a problem if it has a 'code' or 'title' and looks like our structured error
      if (typeof detailObj['code'] === 'string' || typeof detailObj['title'] === 'string') {
        // Pass the inner object as the problem
        return normalizeProblem(detailObj, res.status ?? undefined);
      }
    }
  }

  return null;
}

export function normalizeProblem(problem: Record<string, unknown>, fallbackStatus?: number): Problem {
  const typeValue = problem['type'];
  const titleValue = problem['title'];
  const statusSource = problem['status'];
  const status = typeof statusSource === 'number' ? statusSource : fallbackStatus ?? 500;
  const detailValue = problem['detail'];
  const messageValue = problem['message'];
  const instanceValue = problem['instance'];
  const codeValue = problem['code'];
  const requestIdValue = problem['request_id'];
  const errors = problem['errors'];

  const result: Problem = {
    type: typeof typeValue === 'string' && typeValue.length > 0 ? typeValue : 'about:blank',
    title: typeof titleValue === 'string' && titleValue.length > 0 ? titleValue : 'Unknown error',
    status,
    detail:
      typeof detailValue === 'string' && detailValue.trim().length > 0
        ? detailValue
        : typeof messageValue === 'string'
          ? messageValue
          : '',
    instance: typeof instanceValue === 'string' ? instanceValue : '',
  };

  if (typeof codeValue === 'string' && codeValue.length > 0) {
    result.code = codeValue;
  }
  if (typeof requestIdValue === 'string' && requestIdValue.length > 0) {
    result.request_id = requestIdValue;
  }
  if (errors !== undefined) {
    result.errors = errors;
  }

  return result;
}
