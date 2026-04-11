---
name: instainstru-verify
description: Runs the full iNSTAiNSTRU verification suite (ruff, mypy, pre-commit, pytest, eslint, TypeScript strict, type-coverage, npm audit) and enforces quality gates. Use after every code change, bug fix, feature implementation, test update, or dependency change — before reporting any task as complete. Also use when asked to "verify", "check", "validate", "run tests", "is it passing", or "are we green". Includes a deterministic, fail-fast verification script, forbidden suppression patterns, and self-check protocol.
---

# iNSTAiNSTRU Verification & Quality Gates

**This skill is mandatory.** Before reporting ANY task as done, run the verification script and the self-check protocol. No exceptions.

---

## 1. Run the Verification Script

After every change, run the appropriate verification:

```bash
# Detect which skill directory this is and run from there
# Backend only
bash scripts/verify.sh backend

# Frontend only
bash scripts/verify.sh frontend

# Both stacks (after cross-cutting changes)
bash scripts/verify.sh all
```

The script is at `scripts/verify.sh` inside this skill's directory. It runs every check in order, stops after the first failed step in a scope, and outputs a structured report with pass/fail per step.

### Execution Rules

- **Step-gated verification.** Do not start step N+1 until step N has passed.
- **Never interrupt a running step.** Let the current command finish naturally. If `pytest` or `jest` is running and failures appear in the output, wait for the full test step to complete so you can fix all failures from that step in one pass.
- **After a failed step, fix first, then rerun the same scope from the top.**
  - If `verify.sh backend` fails, fix the backend issue and rerun `verify.sh backend`.
  - If `verify.sh frontend` fails, fix the frontend issue and rerun `verify.sh frontend`.
- **`verify.sh all` is sequential, not sticky.** It runs backend first, then frontend.
  - If backend fails, stop immediately. Fix backend and rerun `verify.sh backend`.
  - If backend passes and frontend fails, fix frontend and rerun `verify.sh frontend` only.
  - Do not rerun backend after a frontend-only fix unless the fix touched backend code or another shared cross-stack dependency.

### Check Order

- **Backend:** `ruff check backend/` → `mypy` → `pre-commit` → `pytest`
- **Frontend:** `jest --coverage` → `eslint` → `typecheck:strict-all` → `audit:typecov` → `npm audit --omit=dev`

### When to run which

| Change scope | Command |
|-------------|---------|
| Backend-only | `verify.sh backend` |
| Frontend-only | `verify.sh frontend` |
| Both stacks | `verify.sh all` |
| DB migration | Run `cd backend && python scripts/prep_db.py int` first, then `verify.sh all` |

### When NOT to re-run the full suite

Ask this before re-running the suite: **did production code change since the last green run?**

If the answer is **no**, targeted verification is sufficient.

After fixing stale tests where production code did not change:

- Run only the specific test file(s) that were modified, directly via `pytest` and not `verify.sh`.
- Confirm those individual tests pass.
- Do **not** re-run `verify.sh backend` or the full backend suite.
- Report: `Fixed stale tests in [files]. Verified directly with pytest [files] — passing. Production code unchanged, full suite re-run not needed.`

After modifying production code:

- Always run the appropriate `verify.sh` scope.
- This is the legitimate case for the full suite.

Discipline:

- If production code changed since the last green run, a full suite re-run is required.
- If production code did not change since the last green run, targeted verification of the modified stale tests is enough.

---

## 2. Self-Check Protocol

**After claiming a fix, verify your changes actually landed.** This catches the most common agent failure: reporting work done when the file wasn't saved.

```bash
# For every file you modified, verify the change is present:
grep -n '[key pattern from your change]' [file you modified]

# For every function you added:
grep -n 'def [name]\|function [name]' [file]

# For every constant you changed:
grep -n '[CONSTANT_NAME]' [file]
```

**If grep returns empty, the change did not save. Fix it before proceeding.**

---

## 3. Forbidden Patterns

If a check fails, fix the root cause. NEVER suppress. See `references/conventions.md` for the complete list.

**Backend — never add:** `# nosec`, `# noqa`, `# type: ignore`, `# pragma: no cover`, `@pytest.mark.xfail`, `@pytest.mark.skip`

**Frontend — never add:** `// @ts-ignore`, `// @ts-expect-error`, `// eslint-disable`, `as any`, `: any`, `@ts-nocheck`

### Config-Level Suppressions — Also Forbidden

Do NOT disable checks by modifying tool configuration files. This includes:

- Adding `[[tool.mypy.overrides]]` with `disallow_untyped_decorators = false` or similar relaxations in `pyproject.toml`
- Adding `skipLibCheck`, loosening `strict` flags, or adding path exclusions in `tsconfig.json`
- Adding rule overrides or file ignores in `.eslintrc` / `eslint.config.js`
- Adding ignore patterns in `ruff.toml` or `pyproject.toml [tool.ruff]`
- Widening `exclude` patterns in any linting/type checking config

Moving a suppression from inline code to a config file is still a suppression. If a check fails, fix the code — do not reconfigure the tool to stop reporting the error.

If a third-party library causes an unfixable type error (e.g., untyped decorator in SQLAlchemy stubs), find a typed workaround (cast, event listener, explicit annotation). If no workaround exists, flag it to the orchestrator — do not silently disable the check category.

---

## 4. Reporting Format

When reporting task completion, include:

```
## Verification Results

### Backend
- Ruff: [clean / N errors]
- mypy: [clean / N errors]
- Pre-commit: [all passed / N failures]
- Tests: [count] passed, [count] failed, [count] skipped

### Frontend
- Tests: [count] passed across [count] suites
- Lint: [clean / N errors]
- TypeScript strict-all: [0 errors / N errors]
- Type coverage: [percentage] ([identifiers]/[total])
- npm audit: [0 vulnerabilities / details]

### Self-Check
- [file1]: verified [change description]
- [file2]: verified [change description]
```

**If any line shows failures, do NOT report the task as complete.**

---

## 5. Additional Resources

- **Troubleshooting common failures:** `references/troubleshooting.md`
- **Project coding conventions:** `references/conventions.md`

Read the relevant reference when you encounter a specific failure type.
