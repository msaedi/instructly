# iNSTAiNSTRU Coding Conventions

Non-negotiable rules for all code changes. These are enforced by CI, pre-commit hooks, and code review.

## Database & Migrations

- **No new Alembic migration files — ever.** Edit existing migrations in `alembic/versions/`. Rebuild with `python scripts/prep_db.py int`.
- **No production data exists.** Schema changes are free — edit and rebuild.
- **No backward compatibility code.** No backfill scripts, no legacy support, no migration compat. Clean breaks only.
- **All IDs are ULIDs** (26-character strings). Never use integer IDs or UUIDs.

## Architecture

- **Repository pattern enforced.** Zero direct `db.query()`, `db.add()`, `db.commit()` in service files. Pre-commit hooks block violations.
- **Service layer pattern.** Routes are thin controllers — all business logic in services.
- **All routes under `/api/v1/*`.** No exceptions (except /docs, /redoc, /openapi.json).
- **React Query mandatory** for all frontend data fetching. No raw fetch in components.
- **Import from canonical source.** Don't duplicate constants — import them. Backend constants in `app/core/constants.py`, frontend in `lib/calendar/bitset.ts`.

## Type Safety

- **TypeScript strictest mode.** Zero errors on `typecheck:strict-all`.
- **Type coverage at 100%.** `type-coverage --at-least 100` enforced. Any new `any` breaks CI.
- **mypy strict on backend.** ~95%+ coverage, trending toward 100%.
- **Pydantic v2 strict mode** for all request/response schemas.

## Suppression Patterns — NEVER Allowed

| Pattern | Why banned |
|---------|-----------|
| `# nosec` | Masks Bandit security findings |
| `# noqa` | Masks ruff/flake8 quality findings |
| `# type: ignore` | Masks mypy type errors |
| `# pragma: no cover` | Masks untested code |
| `@pytest.mark.xfail` | All tests must pass |
| `@pytest.mark.skip` | All tests must run |
| `// @ts-ignore` | Masks TypeScript errors |
| `// @ts-expect-error` | Same |
| `// eslint-disable` | Masks lint findings |
| `as any` / `: any` | Breaks 100% type coverage |
| `@ts-nocheck` | Disables type checking entirely |
| `[[tool.mypy.overrides]]` relaxations | Disables mypy checks for entire modules |
| `tsconfig.json` strict flag loosening | Disables TypeScript checks globally |
| `.eslintrc` rule disabling | Disables lint rules globally |
| `ruff.toml` ignore additions | Disables linting rules globally |

**Config-level suppressions are equivalent to inline suppressions.** Adding `disallow_untyped_decorators = false` for `app.models.*` in pyproject.toml has the same effect as adding `# type: ignore[untyped-decorator]` on every line in every model file. The only acceptable response to a failing check is to fix the code. If a third-party library makes this impossible, escalate — do not reconfigure the tooling.

## Testing

- **Backend coverage: 99%+.** CI threshold enforced.
- **Frontend coverage: 100%** type coverage. Test coverage 97%+.
- **All tests must pass.** No xfail, no skip, no expected failures.
- **No flaky tests.** Use `timedelta(days=7)` for future dates, avoid cross-midnight issues.

## Git & Commits

- **Single squash commit per feature.** Don't create micro-commits.
- **Amend for audit fixes.** Same feature branch, same logical change = amend.
- **Do NOT commit or push unless explicitly asked.** Report results and wait.
- **Commit message format:** `type(scope): short description`
  - Types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`
  - Include test counts for significant work.

## Code Style

- **No `as any` to fix type errors.** Use `unknown` + narrowing instead.
- **No constant duplication.** Import from the source of truth.
- **No hardcoded magic numbers** for slot sizes, byte counts, durations. Use named constants.
- **Bitmap operations:** LSB bit ordering everywhere (Python, TypeScript, PostgreSQL). `bit_index = slot % 8`, set via `1 << bit_index`.
