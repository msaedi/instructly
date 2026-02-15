# BotID Architecture and Readiness

## Status
BotID is now integrated with a protected mutation proxy architecture.

## What Is Enforced
1. `frontend/next.config.ts` wraps config with `withBotId(...)`.
2. `frontend/instrumentation-client.ts` initializes `initBotId({ protect: [...] })`.
3. `frontend/app/api/v1/[...path]/route.ts` enforces `checkBotId()` on protected mutation paths.
4. Protected mutation requests are routed to same-origin `/api/v1/...` before proxying to backend.

## Protected Scope
Protected mutation families:
- `/api/v1/auth*`
- `/api/v1/2fa*`
- `/api/v1/bookings*`
- `/api/v1/payments*`
- `/api/v1/reviews*`
- `/api/v1/referrals*`
- `/api/v1/public/referrals*`
- `/api/v1/messages*`
- `/api/v1/conversations*`

HTTP methods:
- `POST`
- `PUT`
- `PATCH`
- `DELETE`

Read traffic remains direct-to-backend for performance.

## Operational Notes
1. `/api/v1/[...path]` is intentionally allowlisted:
   - unprotected mutation paths return `404` (no open proxy behavior).
2. BotID verification failure mode is currently fail-open:
   - if `checkBotId()` throws, request is allowed and logged.
3. `/monitoring` route is unaffected:
   - path is not under `/api/v1/*`.

## Validation Commands
```bash
# Confirm BotID wrapper and initialization
rg -n "withBotId|initBotId|checkBotId" frontend/next.config.ts frontend/instrumentation-client.ts frontend/app/api/v1/[...path]/route.ts

# Confirm protected matcher usage
rg -n "isProtectedMutationRequest|BOTID_PROTECT_RULES" frontend/lib/security/protected-mutation-routes.ts frontend/lib/apiBase.ts frontend/app/api/v1/[...path]/route.ts

# Ensure mutation route exists
test -f 'frontend/app/api/v1/[...path]/route.ts'
```
