# Troubleshooting Common Verification Failures

## Table of Contents
1. [Tests pass but mypy fails](#tests-pass-but-mypy-fails)
2. [TypeScript strict passes but type-coverage fails](#typescript-strict-passes-but-type-coverage-fails)
3. [Pre-commit fails on repository pattern](#pre-commit-fails-on-repository-pattern)
4. [npm audit shows vulnerabilities](#npm-audit-shows-vulnerabilities)
5. [Tests pass but coverage is below threshold](#tests-pass-but-coverage-is-below-threshold)
6. [Pre-commit fails on timezone check](#pre-commit-fails-on-timezone-check)
7. [Agent reports fix but grep shows old code](#agent-reports-fix-but-grep-shows-old-code)

---

## Tests pass but mypy fails

**Cause:** You introduced a type error. Common patterns:
- Missing return type annotation on new function
- Passing wrong type to existing function
- Using `Optional[X]` without null check before access
- New import not recognized by mypy

**Fix:** Add proper type annotations. Do NOT add `# type: ignore`.

```bash
# See exact errors
cd backend && ./venv/bin/mypy --no-incremental app 2>&1 | head -30
```

---

## TypeScript strict passes but type-coverage fails

**Cause:** You introduced an `any`. Common patterns:
- `JSON.parse()` returns `any` — cast to `unknown` and narrow
- Third-party library returns `any` — add explicit type annotation
- `Array.isArray()` on `unknown` produces `any[]` — use `isUnknownArray()` from `lib/typesafe.ts`
- `event` param in SSE callback — type as `MessageEvent<string>`
- `jest.requireMock()` without generic — add type param

**Fix:** Add explicit type annotations. Do NOT use `as any`.

```bash
# Find the exact any identifiers
cd frontend && npx type-coverage --detail 2>&1 | grep "any" | head -20
```

---

## Pre-commit fails on repository pattern

**Cause:** You have a direct `db.query()`, `db.add()`, `db.commit()`, or `db.execute()` in a service file.

**Fix:** All data access must go through repositories. Add a repository method and call it from the service.

```bash
# See what's flagged
cd backend && python scripts/check_repository_pattern.py 2>&1
```

The only acceptable exception marker is `# repo-pattern-ignore` with explicit team approval documented in the comment.

---

## npm audit shows vulnerabilities

**Cause:** A dependency has a known security issue.

**Fix:**
1. Check if a patched version exists: `npm audit fix --dry-run`
2. If yes, update: `npm audit fix`
3. If no fix available, document it and flag to the orchestrator

Do NOT add to `.npmrc` ignore list without explicit approval.

---

## Tests pass but coverage is below threshold

**Cause:** New code paths without tests.

```bash
# Backend — see uncovered lines
cd backend && pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=99

# Frontend — see uncovered lines
cd frontend && npm test -- --coverage
```

**Fix:** Add tests for the uncovered paths. Do NOT add `# pragma: no cover`.

---

## Pre-commit fails on timezone check

**Cause:** You used `datetime.now()`, `date.today()`, or `datetime.utcnow()` in a service or route file without timezone awareness.

**Fix:** Use the project's timezone utilities:
- `from app.core.timezone import now_utc, today_local`
- Never use bare `datetime.now()` in `app/routes/` or `app/services/`

Note: Seed scripts (`scripts/`) are exempt from this hook.

---

## Agent reports fix but grep shows old code

**Cause:** The file was not actually saved. This is the most common agent failure mode.

**Fix:** Re-apply the change and verify with grep before reporting:

```bash
# After making a change to function_name in file.py:
grep -n 'function_name' file.py
# Must show your new code, not the old version
```

**Prevention:** Always run the self-check protocol from the main SKILL.md after every change.
