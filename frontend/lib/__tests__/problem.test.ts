import { isProblemJsonContentType, parseProblem, type Problem, normalizeProblem } from "../errors/problem";

function makeRes(headers: Record<string, string>, status = 422) {
  // Minimal Response-like object for our parser
  return {
    headers: {
      get: (k: string) => headers[k.toLowerCase()] || (headers as Record<string, string>)[k] || null,
    } as { get: (k: string) => string | null },
    status,
  };
}

describe("problem+json parser", () => {
  test("detects content-type", () => {
    expect(isProblemJsonContentType("application/problem+json; charset=utf-8")).toBe(true);
    expect(isProblemJsonContentType("application/json")).toBe(false);
    expect(isProblemJsonContentType(null)).toBe(false);
  });

  test("parses valid problem body", () => {
    const res = makeRes({ "content-type": "application/problem+json" }, 404);
    const body: Problem = { type: "about:blank", title: "Not Found", status: 404, detail: "", instance: "" };
    const p = parseProblem(res, body);
    expect(p).not.toBeNull();
    expect(p!.title).toBe("Not Found");
    expect(p!.status).toBe(404);
    expect(p!.detail).toBe("");
  });

  test("returns minimal problem when body shape unknown", () => {
    const res = makeRes({ "content-type": "application/problem+json" }, 500);
    const p = parseProblem(res, { unexpected: true });
    expect(p).not.toBeNull();
    expect(p!.title).toBe("Unknown error");
    expect(p!.status).toBe(500);
    expect(p!.detail).toBe("");
  });

  test("returns null when not problem json", () => {
    const res = makeRes({ "content-type": "application/json" }, 400);
    const p = parseProblem(res, { title: "Bad Request" });
    expect(p).toBeNull();
  });

  test("parses FastAPI-style detail object and surfaces code/message", () => {
    const res = makeRes({ "content-type": "application/json" }, 429);
    const body = {
      detail: {
        status: 429,
        code: "bgc_invite_rate_limited",
        title: "Too Many Requests",
        message: "You recently requested a background check. Please wait 24 hours.",
      },
    };
    const p = parseProblem(res, body);
    expect(p).not.toBeNull();
    expect(p!.code).toBe("bgc_invite_rate_limited");
    expect(p!.detail).toBe("You recently requested a background check. Please wait 24 hours.");
    expect(p!.status).toBe(429);
  });

  test("normalizer fills defaults and preserves code", () => {
    const normalized = normalizeProblem({ title: "Bad Request", code: "SOME_CODE" }, 400);
    expect(normalized.title).toBe("Bad Request");
    expect(normalized.type).toBe("about:blank");
    expect(normalized.status).toBe(400);
    expect(normalized.detail).toBe("");
    expect(normalized.code).toBe("SOME_CODE");
  });

  test("normalizer preserves trace_id", () => {
    const normalized = normalizeProblem({ trace_id: "trace-123" }, 500);
    expect(normalized.trace_id).toBe("trace-123");
  });
});
