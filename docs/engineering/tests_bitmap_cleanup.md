# Tests after Bitmap-Only Cleanup

## Skipped by default

- `backend/tests/integration/repository_patterns/*` — legacy slot-era tests (bitmap-only now).
- `backend/tests/scripts/*` — gated behind `RUN_SCRIPT_TESTS=1`.

## How to run scripts tests locally

```bash
export RUN_SCRIPT_TESTS=1
pytest backend/tests/scripts -q
```

## Test Infrastructure Changes

### DB Isolation

Function-scoped `db` fixture provides isolation:
- Each test gets a fresh session via `TestSessionLocal()`
- Automatic cleanup via session rollback and explicit table deletion
- Prevents duplicate email errors via `unique_email()` helper

### Event Outbox Guard (`ensure_outbox_table()`)

Prevents DDL conflicts when multiple tests create `event_outbox` table:
- Checks `inspect(engine).has_table("event_outbox")` before CREATE
- Used in `_prepare_database()` and wherever outbox DDL is needed
- Prevents "table already exists" errors during parallel test runs

### Auth Test Mode (`_auth_test_mode`)

Auto-use fixture forces app into test-friendly auth mode:
- Sets `APP_ENV=local` and `ALLOW_COOKIE_ONLY_AUTH=1`
- Allows cookie-based authentication in tests (prevents 401s)
- Patches settings object if app reads from config instead of env

### Unique Email Helper (`unique_email()`)

Prevents email collisions across tests:
- Generates `{prefix}+{ULID}@insta.test` emails
- Used in `test_student`, `test_instructor`, `test_instructor_2` fixtures
- ULID ensures uniqueness even in parallel test runs

## Follow-up (separate PR)

- Re-align scripts tests with new CLI/log output.
- Delete or rewrite repository patterns against bitmap repos if still desired.
