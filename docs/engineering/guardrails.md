### Guardrails (current, no runtime behavior changes)

All checks are non-functional changes focused on type safety, async hygiene, secrets, and CI health.

#### Frontend (must stay green)
- Lint: `npm run lint:ci`
- Type check: `npm run typecheck:strict-all`
- Build: `npm run build`
- Size budget: `npm run size` (≤ 550 kB brotli)
- Type smoke: `npm run type:smoke:ci`
- Contract audit (fail-gate): `npm run audit:contract:ci`
- Runtime validation bundle check: `npm run verify:runtime-validation-bundle`

#### Frontend audits
- LHCI (warn): `npm run audit:lhci`
- Dead code (warn): `npm run audit:deadcode` (or `:ci`)
- Dependency rules (fail-gate): dep-cruiser runs in CI and pre-push (fast), fails on any error
- Unused exports (ts-prune fail-gate): runs in CI and pre-push (fast), fails unless empty (allowlist supported)

#### Type coverage (fail-gate ≥ 99.0%)
- Local: `npm run audit:typecov`
- CI (fail-gate): `npm run audit:typecov:ci`
- Notes: uses `frontend/tsconfig.type-coverage.json` to avoid OOM, with ignores passed via CLI. Weekly % summary is posted to CI job summary.

#### ESLint async hygiene
- Rule: `@typescript-eslint/no-floating-promises: error`
- Scope: `app/**`, `components/**`, `features/**`, `hooks/**`, `lib/**`
- Guidance: prefer `await`; for fire‑and‑forget use `void fn()` (optionally `.catch(logger.error)` when background errors must be surfaced).

#### Block focused tests
- Frontend: `eslint-plugin-no-only-tests` enabled in test surfaces.
- Backend: pre-commit script `backend/scripts/precommit_block_only_tests.sh` blocks `pytest.mark.only` and `-k "...only..."` patterns on staged backend files.

#### Secrets scanning (fast, local system binary)
- Install once on macOS: `brew install gitleaks` (min v8.18)
- Pre-commit hook: `gitleaks (system)` via `scripts/run-gitleaks.sh` (uses `gitleaks detect --no-git --redact`).
- Scope: only `frontend/` and `backend/` paths. Excludes non-source caches/artifacts (e.g., `frontend/.next`, `node_modules/`, `backend/.venv`, `alembic/`).
- Override (emergencies only): `SKIP=gitleaks-system git commit -m "..."`

#### Backend
- Ruff fail-gate (F+I) on `backend/app`: `ruff check app --select F,I`
- MyPy fail-gate (scoped): `mypy app/schemas app/routes/internal.py`
  - Runs as fail-gate in CI and in `scripts/prepush.sh`.

#### Local hooks and pre-push
- Pre-commit (on staged files):
  - Black (backend/app), Ruff (backend/app), Frontend ESLint, public env verify, backend repo checks, backend focused-tests block, gitleaks (system)
- Pre-push (CI‑like, fail-mode):
  - Backend: Ruff, MyPy (schemas+internal), pytest smoke (optional when present)
  - Frontend: typecheck:strict-all, build, size, type:smoke:ci, verify:runtime-validation-bundle, audit:contract:ci
  - Warn-mode (skippable with `FAST_HOOKS=1`): deadcode, local typecov

#### Interpreting results
- Fail-gates must be green locally and in CI.
- Warn-mode audits are informational and should not block commits.

#### Imports & layering
- components/** must not import feature internals. Use:
  - `features/<feature>/public/**` facades; or
  - `features/shared/**` presentational utilities.
- features/* must not import other features/* (except `features/shared/**`).
- Only `features/shared/api/types` may import `types/generated/**`.

##### Adding a facade (example)
If a component needs a feature-owned modal, expose a thin facade under `features/<feature>/public/` that re-exports or lazy-wraps the internal component without changing behavior:

```tsx
// features/foo/public/ThingFacade.tsx
import type { ComponentProps } from 'react';
import Thing from '../components/Thing';
export type ThingFacadeProps = ComponentProps<typeof Thing>;
export default function ThingFacade(props: ThingFacadeProps) { return <Thing {...props} />; }
```

Then import from `features/foo/public` in `components/**`.

#### Cheat‑sheet: common fixes
- dependency-cruiser: break cycles by extracting shared modules or re-exporting via shared; honor layer rules and use public facades.
- ts-prune: remove unused exports or add to `frontend/ts-prune-allowlist.txt` with justification (public API types, etc.).
- no‑floating‑promises: `await fn()`; or `void fn()` when fire‑and‑forget; add `.catch(logger.error)` if background errors must be logged.
- Type coverage: add narrow annotations/JSDoc where values from `response.json()` are used; avoid logic changes.
- Size‑limit: prefer subpath imports, watch heavy deps.
- LHCI: run locally and inspect `frontend/.artifacts/lhci` if needed.
- Ruff: `ruff check --select F,I --fix backend/app` to fix import/flake issues.

#### Notes
- No runtime behavior changes are introduced by these guardrails.

### Security audits
- Backend: `pip-audit` runs in CI (warn-mode initially). To ignore a specific CVE temporarily, add to `backend/pip-audit.ignore.json` with justification in PR.
- Frontend: `npm audit --omit=dev --audit-level=high` summarized via `scripts/parse-npm-audit.js`; allowlist via `frontend/audit-allowlist.json` (ids), with justification.

### Env-contract smoke (optional)
- A lightweight Playwright test can run if `PLAYWRIGHT_BASE_URL` is provided in CI to probe `/health` headers and 429 UX. Skipped by default.
