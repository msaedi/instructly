# Authorization Matrix

Cross-reference: [Public API Inventory](public_api_inventory.md)

| Method | Path | Handler / Tag | Required Roles | Required Scopes | Open? |
|--------|------|----------------|----------------|-----------------|-------|
| GET | `/health` | `app.main.health_check` | — | — | Yes |
| POST | `/auth/login` | `app.routes.auth.login` | — | — | Yes |
| POST | `/auth/register` | `app.routes.auth.register` | — | — | Yes |
| POST | `/api/auth/password-reset/request` | `app.routes.password_reset.request_password_reset` | — | — | Yes |
| GET | `/api/public/instructors/{id}/availability` | `app.routes.public.get_instructor_public_availability` | — | — | Yes |
| POST | `/bookings` | `app.routes.bookings.create_booking` | Student | TBD (`booking:create`) | No |
| GET | `/bookings/upcoming` | `app.routes.bookings.get_upcoming_bookings` | Student / Instructor (per user) | TBD | No |
| POST | `/instructors/availability/week` | `app.routes.availability_windows.save_week_availability` | Instructor | TBD (`availability:write`) | No |
| POST | `/api/referrals/claim` | `app.routes.referrals.claim_referral_code` | — | — | Yes (anonymous) |
| GET | `/api/admin/config/pricing` | `app.routes.admin_config.get_pricing_config` | Admin | TBD (`config:read`) | No |
| PATCH | `/api/admin/config/pricing` | `app.routes.admin_config.update_pricing_config` | Admin | TBD (`config:write`) | No |
| GET | `/metrics` | `app.routes.metrics.get_metrics` | TBD | TBD | TBD |

**TBD** items indicate routes where explicit scope/permission bindings are not yet declared. Additions should update both the required dependency chain and this matrix.

## Adding a New Route

1. Decide whether the route is public (available without auth) or protected:
   - Public-only routes must be added to the `open_paths` or `open_prefixes` when wiring `public_guard` (see `app/main.py`).
   - Protected routes should include dependencies such as `Depends(require_roles("student"))`, `Depends(require_scopes("booking:create"))`, or existing permission helpers.
2. Update the [Public API Inventory](public_api_inventory.md) by rerunning `python backend/scripts/dev/list_routes.py > docs/security/public_api_inventory.md`.
3. Extend this matrix with the new endpoint, recording the method, path, handler/tag, required roles, scopes, and whether the endpoint is open.
4. Add or update authZ tests that cover the new behavior (see `backend/tests/integration/security/`).
5. Ensure the deny-by-default guard still enforces the intended access pattern.
