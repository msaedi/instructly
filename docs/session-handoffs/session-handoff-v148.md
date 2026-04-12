# InstaInstru Session Handoff v148
*Generated: 2026-04-11*
*Previous: v147 | Current: v148 | Next: v149*

## 🎯 Session Summary

**Tooling foundation: graphify, CARL, Conductor, and the matured X-Team workflow**

This session was almost entirely about engineering tooling, not feature work. Six refactor PRs landed in parallel using Conductor (covered separately in the audit follow-up), but the lasting changes from v148 are infrastructural: a persistent codebase knowledge graph, dynamic JIT rule injection for coding agents, parallel workspace orchestration with isolated databases, and an updated orchestrator process that ties them all together.

| Objective | Status |
|-----------|--------|
| **Graphify integration** | ✅ Installed, indexed 48K-node graph, husky hooks wired, Codex + Claude Code support |
| **CARL dynamic rules** | ✅ Installed globally, 7 domains configured, 4 decisions logged |
| **Conductor workspace setup** | ✅ Setup script + archive script, per-workspace DB isolation, husky activation |
| **Verify skill hardening** | ✅ Backend venv path bugs fixed, no-redundant-rerun rule added |
| **Orchestrator skill v2** | ✅ Updated with 7-step lifecycle, conductor/graphify/CARL awareness |
| **X-Team guide v3** | ✅ Slimmed to briefing document, defers to skill for process |

---

## Graphify Knowledge Graph (Complete)

Graphify is now the structural navigation layer for the codebase. Coding agents auto-consult it before grepping raw files via PreToolUse hook (Claude Code) and AGENTS.md (Codex). The graph contains 48,484 nodes, 152,893 edges, and 1,096 communities across the full 3,250-file codebase.

Key facts agents need to know:
- God nodes are domain entities (User, BookingStatus, Booking, InstructorProfile, InstructorService) — expected for a marketplace
- Cross-directory edges have a known false-positive class: same-named modules (`config.py`, `models.py`, `types.py`) get collapsed into single graph nodes. Always verify with grep before acting on a "surprising connection"
- This false positive bit us twice in v148 — both turned out to be benign (MCP→backend Settings was actually relative imports; referral tests→MCP OAuth models was also a basename collapse)

### Key Files
- `graphify-out/` — graph data, gitignored, local per developer
- `scripts/post-commit.sh` — backgrounded rebuild on commit (code files only)
- `scripts/post-checkout.sh` — backgrounded rebuild on branch switch
- `.graphifyignore` — excludes noise dirs (temp logs, grafana data, venv, node_modules)
- `CLAUDE.md` and `AGENTS.md` — graphify section appended for agent awareness

### Known issue
Post-commit hook uses system `python3` for graphify rebuild, which fails on machines without graphify in system Python. Coding agents worked around this 4+ times this session by manually invoking `backend/venv/bin/python`. Fix scheduled for cleanup PR.

---

## CARL Dynamic Rules (Complete)

CARL is installed globally in Claude Code. It auto-injects domain rules and decisions based on prompt keyword matching. Coding agents see rules and decisions in their context the moment a prompt mentions trigger words.

Domains configured:
- **GLOBAL** (always on) — ULID IDs, `/api/v1/*`, repository pattern, no suppressions, no backward compat shims, no new migrations
- **BACKEND** — service/repository/endpoint/migration triggers; rules around service layer, BaseService.measure_operation, repository pattern enforcement
- **FRONTEND** — React/Next.js/TypeScript/Tailwind triggers; React Query mandatory, strictest mode, no @ts-ignore
- **COPY** — email/outreach/landing triggers; no em dashes, sentence case, brand stylization
- **ORCHESTRATOR** — prompt/audit/commit triggers; markdown textboxes, graphify queries, audit batching
- **TESTING** — test/coverage triggers; no focused tests, audit prompts skip full suite
- **INFRASTRUCTURE** — deploy/Render/Vercel/Supabase triggers; provisioned Twilio number warning, Sentry NL search broken, Render MCP availability

Decisions logged:
- `backend-001`: Stripe destination charges (not direct charges)
- `backend-002`: Neighborhood selector uses display_keys not IDs
- `backend-003`: Founding instructors lock in 8% commission permanently (confidential)
- `backend-004`: Graphify falsely reports cross-directory imports for same-named modules — always grep verify
- `global-001`: No production data exists — safe to drop/rebuild schema
- `frontend-001`: Brand color palette (#7C3AED, #7E22CE, #F3E8FF, #FFD93D, #059669)

### Key Files
- `~/.carl/carl.json` — domains, rules, decisions, config
- `~/.carl/carl-mcp/` — MCP server for runtime management
- `~/.claude/hooks/carl-hook.py` — injection engine
- `CLAUDE.md` — CARL integration block

---

## Conductor Workspace Orchestration (Complete)

Conductor enables running multiple coding tasks in parallel, each in its own git worktree workspace. Setup and teardown are scripted so workspaces are fully wired (venv, env files, graphify graph, husky hooks, isolated DB) within ~60s of creation.

### scripts/conductor-setup.sh

Runs on workspace creation. Wires the workspace to the canonical repo:
- Symlinks `backend/venv` (shared Python environment, saves disk + install time)
- Symlinks `backend/.env`, `frontend/.env.local`, `mcp-server/.env` (kept in sync with source)
- Symlinks `graphify-out/` (shared knowledge graph, single source of truth)
- Runs `npm ci` for `frontend/node_modules` (Turbopack rejects symlinks pointing outside project root)
- Generates per-workspace `backend/.env` with isolated `test_database_url` (`instainstru_test_<workspace_name>`)
- Creates the per-workspace database via `psql` against the `postgres` maintenance DB
- Runs `reset_schema.py int` and `prep_db.py int --force --yes --migrate --seed-all` to seed it
- Activates husky hooks via `git config core.hooksPath .husky` (Conductor's fresh `.git/config` doesn't inherit this)

### scripts/conductor-archive.sh

Runs on workspace archival via Conductor's Archive script field. Drops the per-workspace database via psql with strict safety guards (only drops databases matching the exact `instainstru_test_<workspace_name>` pattern).

### Conductor Repository Settings
- **Setup script:** `bash scripts/conductor-setup.sh`
- **Archive script:** `bash scripts/conductor-archive.sh`
- Run script and others: not configured (not needed for current workflow)

### Bugs encountered and fixed in v148
- Husky hooks weren't firing in workspaces (fresh `.git/config` doesn't set `core.hooksPath`) — fixed by explicit `git config` in setup script
- Per-workspace DB creation was failing because `reset_schema.py` expected the DB to exist — fixed by adding a `CREATE DATABASE` step via psql before reset
- psql variable interpolation (`:'dbname'`) was broken because variables weren't passed via `-v` — fixed by inlining the DB name into the SQL string
- `frontend/node_modules` was symlinked, breaking Turbopack (Next.js 16 rejects symlinks pointing outside project root) — fixed by always running `npm ci` instead of symlinking
- `.codex/hooks.json` initially granted blanket Bash auto-allow permissions — fixed by removing `permissionDecision` field, leaving advisory text only
- Post-commit hook was synchronous and blocked terminal for minutes — fixed by backgrounding via `nohup ... &` to `graphify-out/rebuild.log`
- Post-checkout hook had same blocking issue — fixed the same way
- Post-commit hook had a shell-quoting bug from f-string in inline `python -c` heredoc — fixed by extracting logic to `scripts/_graphify_rebuild.py`

### Pre-existing bugs surfaced by Conductor (clean checkout exposed latent issues)

Conductor workspaces are a fresh checkout test. Several bugs that "worked" in `~/instructly` only because of accumulated cruft surfaced immediately:

- **Stray `~/instructly/venv` shim** with a single `pre-commit` script — left over from an earlier coding agent's workaround for a verify.sh path bug. Deleted, verify.sh fixed properly.
- **`verify.sh` used `cd backend && python ../venv/bin/pre-commit`** — relative path only resolved against the stray top-level venv. Fixed to use `backend/venv/bin/pre-commit` consistently for all tools (ruff, mypy, pre-commit, pytest).
- **`verify.sh` pre-commit wrapper miscounted failures** — grepped for "Failed" lines in pre-commit output, but pre-commit only emits that for actual hook failures. When pre-commit died for non-hook reasons (env errors, missing deps), wrapper falsely reported "0 hook(s) failed" while exiting non-zero. Fixed to fall back to last output line, then to raw exit status, with PIPESTATUS handling.
- **`.gitignore` missing nested patterns** — `venv/` and `graphify-out/` only matched top-level. Added `**/venv` and `**/graphify-out` (no trailing slash — git treats symlinks-to-directories as files, so trailing-slash patterns don't match).

### Key files
- `scripts/conductor-setup.sh`
- `scripts/conductor-archive.sh`
- `scripts/_graphify_rebuild.py`
- `scripts/post-commit.sh`
- `scripts/post-checkout.sh`
- `.husky/post-commit`
- `.husky/post-checkout`
- `.codex/hooks.json`
- `AGENTS.md`
- `.graphifyignore`

---

## instainstru-verify Skill Hardening (Complete)

Two structural fixes to the verification skill:

1. **Backend venv path consistency** — All tool invocations (`ruff`, `mypy`, `pre-commit`, `pytest`) now use `backend/venv/bin/<tool>` consistently instead of brittle relative paths
2. **Pre-commit failure reporting** — Fixed wrapper to report meaningful errors instead of "0 hook(s) failed" when pre-commit dies for non-hook reasons
3. **No-redundant-rerun rule** — Added section "When NOT to re-run the full suite": after fixing stale tests where production code didn't change, run only the modified test files directly with pytest. Don't re-run `verify.sh backend` (10+ minutes for no additional confidence)

### Key files
- `.claude/skills/instainstru-verify/SKILL.md`
- `.claude/skills/instainstru-verify/scripts/verify.sh`

---

## Orchestrator Skill v2 + X-Team Guide v3 (Complete)

Two documents updated to reflect the matured workflow.

### `instainstru-orchestrator` skill (Claude.ai chat skill)

Added sections:
- **Section 0 — Operating Environment** covering Conductor, graphify, CARL
- **Core Workflow** replaced flat diagram with the 7-step lifecycle
- **Section 4 — Branch vs Direct-to-Main Decision** with explicit criteria
- **Section 5 — Local Audit Prompt** rule (read-only, no pytest, parallel collision prevention)
- **Section 7 — Verification Scope Discipline** (never default to `verify.sh all`)
- Updated existing sections with graphify query suggestions and CARL invariant deduplication notes

All existing sections (prompts, audit format, commit messages, PR creation, session handoffs, decision patterns, common patterns) preserved.

### X-Team Orchestrator Guide v3

Slimmed from the v2 process-heavy version into a briefing document. Key change: orchestrators are now told to read the `instainstru-orchestrator` skill first as the operating manual. The guide is the briefing — what tools exist and current state. Skill is the manual — process discipline and rules. When they appear to disagree, the skill wins.

New sections:
- First Action — mandatory skill read at session start
- Operating Environment — Conductor, graphify, CARL, instainstru-verify
- Common Misalignments to Watch For — practical examples of when to push back on coding agents

Removed sections (now owned by the skill):
- 7-step lifecycle (kept only as a brief reference)
- Branch decision criteria
- Verification scope rules
- Process duplication

### Key files
- Claude.ai skill: `instainstru-orchestrator` (skill description preserved, instructions field updated)
- Project file: replace v2 guide with v3 in project documents

---

## 📊 Platform Health (Post-v148)

| Metric | Value | Change from v147 |
|--------|-------|---------------------|
| Test counts (backend + frontend) | Unchanged | — |
| Backend coverage | 95.45% (CI locked) | — |
| Frontend coverage | 95.08% | — |
| API endpoints | 333 | — |
| MCP admin tools | 36 | — |
| Repositories decomposed (cumulative) | +6 in this session | — |
| Knowledge graph nodes | 48,484 | New |
| CARL domains active | 7 | New |
| Conductor workspaces (parallel-capable) | 5 active | New |

---

## 🏛️ Architecture Decisions

- **Graphify is structural navigation, not source of truth.** Cross-directory edges have a basename-collapse false positive class. Always verify with grep before acting on a "surprising connection."
- **CARL persists architectural decisions across sessions.** New decisions worth keeping should be logged via `carl_v2_log_decision` in the appropriate domain. The decision becomes ambient context for every future session that mentions related keywords.
- **Conductor workspaces are fresh-checkout tests.** They expose latent bugs that the main repo papers over with accumulated state. This is a feature, not a bug — ship the workspace as the canonical environment, fix anything that doesn't work in it.
- **Per-workspace database isolation is mandatory for parallel pytest.** Five agents running pytest against a shared `int` DB will collide. Conductor setup script generates `instainstru_test_<workspace_name>` per workspace.
- **Verification scope must match change scope.** Backend suite is 10+ minutes. Never default to `verify.sh all` for a frontend-only change. The instainstru-verify skill enforces this for coding agents; the orchestrator skill enforces it at the planning level.
- **Skills > inline guides for process.** The orchestrator skill is the operating manual; the X-Team guide is the briefing. Process documentation belongs in skills because skills auto-load in every session. Briefings can drift; process can't.

---

## 📋 Remaining Work

| Item | Priority | Notes |
|------|----------|-------|
| Audit the 6 refactor PRs from this session | High | Started in v149 |
| Cleanup PR A — auth_cache email path Redis caching + tests | High | Real performance risk under load |
| Cleanup PR B — `_execute_final_adverse_action` session ownership | High | Codex flagged worker job-stuck-running risk |
| Cleanup PR C — Low-priority polish (logger consistency, redundant TYPE_CHECKING, test flush/commit consistency) | Low | Bundle into one PR when ready |
| Tooling debt — Graphify post-commit hook venv-aware Python | Medium | Bit agents 4+ times this session |
| Convention — `pre-existing-issues-tracker.md` location (root vs docs/) | Low | Was deleted; document was sloppy organization |
| Founding instructor activation | High | Ongoing, not affected by tooling work |
| Day Zero database prep | High | Pending |
| `student_launch_enabled` flip | Critical | Pending |

---

**STATUS: Tooling foundation complete. Ready to verify the 6 refactor PRs from this session and resume launch preparation.**
