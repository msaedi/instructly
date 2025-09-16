export type Problem = {
  type: string;
  title: string;
  detail?: string;
  status?: number;
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
      return record as unknown as Problem;
    }
  }

  return {
    type: "about:blank",
    title: "Unknown error",
    status: (res as Response).status ?? ("status" in res ? (res as { status?: number }).status : undefined),
  };
}
