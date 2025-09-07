### Guardrails: How to run and interpret checks (warn-mode)

This project ships non-breaking guardrails to improve correctness, size/perf, and type safety. These checks do not change runtime behavior and run in warn-mode unless noted.

#### Frontend checks
- size-limit (bundle budget)
  - Run: `npm run size`
  - Budget: 600 kB brotli (warn now; tighten later). Prints bundle size summary.
- Lighthouse CI (performance, accessibility, best-practices)
  - Run: `npm run audit:lhci`
  - Behavior: Builds statically and runs LHCI locally. In CI, results are non-blocking; artifacts are saved under `frontend/.artifacts/lhci`.
- Dead-code audit (Knip)
  - Run: `npm run audit:deadcode` (local), `npm run audit:deadcode:ci` (CI)
  - Behavior: Warn-mode wrapper always exits 0. Output is a short summary; investigative only.
- Type coverage
  - Run: `npm run audit:typecov`
  - Config: `typeCoverage.atLeast = 95` (warn-mode). Use to identify low-coverage areas to improve.
- Type smoke tests (TSD)
  - Run: `npm run type:smoke`
  - Behavior: Compile-time assertions for critical API shapes. Currently warn-mode (non-fatal).
- ESLint (typed rules scoped)
  - Scope: `features/shared/api/**` uses stricter `@typescript-eslint` rules. Normal `npm run lint:ci` is green.

Core frontend commands (must stay green):
```bash
npm run lint:ci
npm run typecheck:strict-all
npm run build
npm run size
```

Audit commands (warn-mode; exit 0):
```bash
npm run type:smoke
npm run audit:deadcode
npm run audit:deadcode:ci
npm run audit:lhci
npm run audit:typecov
```

#### Backend checks (warn-mode)
- Ruff (lint)
  - Run: `ruff check backend || true`
  - Config: Focused on app code; tests/migrations/scripts excluded; minimal rules initially.
- MyPy (scoped type-check)
  - Run: `mypy backend/app/schemas/base.py backend/app/schemas/search_history_responses.py backend/app/routes/internal.py || true`
  - Config: Strict only for a narrow subset; ignore-missing-imports globally, then expand strictly over time.

#### Interpreting results
- Warn-mode: CI will not fail; treat findings as actionable TODOs.
- Regressions vs informational:
  - Regressions are red in core commands (lint:ci, strict-all typecheck, build). These must remain green.
  - Audit output is informational. Prioritize items with the biggest impact (bundle size, a11y violations, dead-code hotspots).

#### Tightening plan (future)
- Lower size budget and fail CI on exceed.
- Flip `@typescript-eslint/prefer-nullish-coalescing` to error.
- Make TSD smoke tests fail CI.
- Raise type coverage threshold (e.g., 97%+).
- Expand MyPy coverage module-by-module.
- Promote more DTOs to strict Pydantic base as safe.

#### Notes
- No runtime behavior is affected by these checks. All additions are config, CI glue, and docs.

#### How to fix (cheat‑sheet)
- no‑floating‑promises: Prefer `await`. For fire‑and‑forget, use `void fn().catch(handle)` to satisfy the rule and capture errors.
- type‑smoke (tsd): Add/adjust `type-tests/*.test-d.ts` assertions. Avoid runtime imports; use `import type { ... }` only.
- size‑limit: Watch large deps (e.g., `recharts`). Prefer subpath imports (e.g., `date-fns/format`), avoid accidental polyfills.
- LHCI: Run `npm run audit:lhci` locally; artifacts in `.artifacts/lhci`. Read the HTML report to spot perf/a11y regressions.
- MyPy (narrow): `mypy backend/app/schemas/base.py backend/app/schemas/search_history_responses.py backend/app/routes/internal.py`
- Ruff: `ruff check --fix backend/app` to auto‑sort imports and quick‑fix lint issues.
