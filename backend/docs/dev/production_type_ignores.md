# Production `# type: ignore` Allowlist

Machine-readable source of truth: [type_ignore_allowlist.json](/Users/mehdisaedi/instructly/backend/type_ignore_allowlist.json)

This allowlist exists for production backend code in [app](/Users/mehdisaedi/instructly/backend/app) only. It excludes:

- [main.py](/Users/mehdisaedi/instructly/backend/app/main.py)
- [openapi_app.py](/Users/mehdisaedi/instructly/backend/app/openapi_app.py)
- tests
- scripts
- migrations and Alembic files

Policy:

- Prefer fixing the underlying type issue over adding `# type: ignore`.
- Only framework typing gaps, third-party typing gaps, or deliberate sentinel/inheritance patterns should be allowlisted.
- Every approved ignore must have a reason in the JSON allowlist and must remain narrow.
- The pre-commit audit fails on both new unapproved ignores and stale allowlist entries.

Current approved production ignores: `11`

## Approved Entries

| File | Ignore(s) | Why it is allowed |
| --- | --- | --- |
| [app/core/config.py](/Users/mehdisaedi/instructly/backend/app/core/config.py) | `assignment` | Conditional `SecretStr` default uses `...` outside CI, which mypy flags even though the runtime pattern is intentional. |
| [app/core/privacy_auditor.py](/Users/mehdisaedi/instructly/backend/app/core/privacy_auditor.py) | `import-untyped` | `yaml` is untyped in the current environment. |
| [app/models/availability_day.py](/Users/mehdisaedi/instructly/backend/app/models/availability_day.py) | `misc`, unscoped, unscoped | SQLAlchemy custom `ClauseElement` plus `@compiles` hooks are dynamically typed. |
| [app/models/types.py](/Users/mehdisaedi/instructly/backend/app/models/types.py) | `misc`, `misc`, `misc` | Custom `TypeDecorator[Any]` subclasses hit SQLAlchemy generic typing limitations. |
| [app/repositories/referral_repository.py](/Users/mehdisaedi/instructly/backend/app/repositories/referral_repository.py) | `override` | The repository intentionally narrows `create(**kwargs)` to a typed keyword-only API. |
| [app/routes/v1/uploads.py](/Users/mehdisaedi/instructly/backend/app/routes/v1/uploads.py) | `attr-defined` | FastAPI import typing is incomplete for this import form in the current toolchain. |
| [app/utils/strict_router.py](/Users/mehdisaedi/instructly/backend/app/utils/strict_router.py) | `assignment` | A sentinel default is required to detect missing `response_model` values. |

## Maintenance

Run the audit directly with:

```bash
cd backend
python scripts/audit_production_type_ignores.py --ci
```

If a new ignore is truly necessary:

1. Add the narrowest possible `# type: ignore[...]`.
2. Add an allowlist entry with a concrete reason.
3. Update this document if the justification introduces a new category of approved ignore.
