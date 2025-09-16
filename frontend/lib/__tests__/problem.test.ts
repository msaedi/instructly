import { isProblemJsonContentType, parseProblem, type Problem } from "../errors/problem";

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
    const body: Problem = { type: "about:blank", title: "Not Found", status: 404 };
    const p = parseProblem(res, body);
    expect(p).not.toBeNull();
    expect(p!.title).toBe("Not Found");
    expect(p!.status).toBe(404);
  });

  test("returns minimal problem when body shape unknown", () => {
    const res = makeRes({ "content-type": "application/problem+json" }, 500);
    const p = parseProblem(res, { unexpected: true });
    expect(p).not.toBeNull();
    expect(p!.title).toBe("Unknown error");
    expect(p!.status).toBe(500);
  });

  test("returns null when not problem json", () => {
    const res = makeRes({ "content-type": "application/json" }, 400);
    const p = parseProblem(res, { title: "Bad Request" });
    expect(p).toBeNull();
  });
});
