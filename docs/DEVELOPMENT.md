# Local Multi-Origin Development

This project runs two local frontends that point at the same FastAPI backend:

- `http://localhost:3000` — staff preview
- `http://beta-local.instainstru.com:3000` — beta onboarding, mirrors `beta.instainstru.com`

## Hosts file setup

Add the beta alias to your hosts file so the beta UI resolves locally:

```bash
sudo sh -c 'echo "127.0.0.1 beta-local.instainstru.com" >> /etc/hosts'
```

Restart any running Next.js dev servers after updating hosts.

## Environment files

- Frontend: use `frontend/.env.local` for local development. Leave `NEXT_PUBLIC_API_BASE`
  unset so the client resolver can derive the correct backend per host (localhost,
  beta-local, LAN IPs, etc.). Set `NEXT_PUBLIC_APP_ENV=development` and adjust
  `NEXT_PUBLIC_APP_URL` as needed. If you temporarily set `NEXT_PUBLIC_API_BASE`, it will
  override the resolver, matching remote preview/beta behaviour.
- Backend: set `ALLOWED_ORIGINS` in `backend/.env` (comma-separated). Example values:
  - Local dev (fallback if unset): `ALLOWED_ORIGINS=http://localhost:3000,http://beta-local.instainstru.com:3000`
  - Preview: `ALLOWED_ORIGINS=https://preview.instainstru.com`
  - Beta: `ALLOWED_ORIGINS=https://beta.instainstru.com`
  - Production: mirror the public domains only.
  The backend runs with `allow_credentials=true`, so wildcards (`*`) are disallowed by design.
  Legacy env names (`CORS_ALLOW_ORIGINS`, `CORS_ALLOWED_ORIGINS`) are still honoured but
  should be migrated to `ALLOWED_ORIGINS`.
- Always export `SITE_MODE=local` for local servers (backend + scripts). Preview/prod site
  modes enforce stricter CSRF/cookie behaviour and require SSL + subdomains.

### R2 uploads (local beta)

- Local beta posts profile-picture files to `/api/uploads/r2/proxy` so the backend pushes to R2; hosted envs keep the direct signed PUT.
- Optional R2 CORS snippet: allow origin `http://beta-local.instainstru.com:3000`, methods `PUT,GET,HEAD`, and headers `content-type,x-amz-*`.

## Session cookies & auth flow

- Authentication cookies are always set by the FastAPI backend and are host-only. Hosted
  deployments (preview/beta/prod) use the `__Host-` prefix with `Secure`, `Path=/`, and no
  `Domain` attribute so cookies scope strictly to the API origin.
- Legacy `.instainstru.com` cookies are expired during the migration window; the server
  still accepts them as a fallback until the rollout completes.
- Local development keeps the original cookie names (no prefix, `Secure=false`) while still
  omitting the `Domain` attribute so localhost and beta-local remain isolated.
- Frontend code never proxies auth in hosted environments; `fetchWithAuth` / `http` resolve
  requests to the configured API base. The optional `/api/proxy` route is gated behind
  `NEXT_PUBLIC_USE_PROXY=true` with `NEXT_PUBLIC_APP_ENV=development`.
- CORS middleware is registered before router includes so 401/403 responses expose
  `Access-Control-Allow-Origin` / `Access-Control-Allow-Credentials`, avoiding opaque
  “network error” messages during auth debugging.

### Profile quick checks

- Service areas smoke test: start the backend + frontend locally, then run
  `npm run e2e:local:profile` to verify “select two → save → reload” persistence.
- Preferred places smoke test (mocked by default): run `npm run e2e:local:places`
  with no additional services required. To exercise the live API instead, start the
  frontend on port 3100 and backend on 8000, then run
  `npm run e2e:local:places:live` (which sets `E2E_APP_ORIGIN`/`E2E_API_ORIGIN`).
- The service-areas save button is StrictMode safe; double-clicks are ignored while the request is running.
- To inspect outgoing payloads during development, set `NEXT_PUBLIC_PROFILE_SAVE_DEBUG=1`
  and watch the console for `[PROFILE_DEBUG]` key lists after each profile save.
- Preferred places: `/instructors/me` exposes `preferred_teaching_locations` (address + optional label)
  and `preferred_public_spaces`. PUT the same arrays (max two entries each) to persist, or send
  empty arrays to clear them. The backend currently stores display strings only; `place_id`, `lat`,
  and `lng` are reserved for future provider integrations.
- Instructor services: `/instructors/me` and `/instructors/{id}` now return `service_catalog_name`
  alongside each `service_catalog_id`. Frontend pages consume that value first and only fall back to
  client-side catalog hydration if the API omits it (useful during local dev against stale data).

## Running the stack

1. Start the backend: `cd backend && uvicorn app.main:app --reload`
2. Start the frontend: `cd frontend && npm run dev`
3. Visit the preview UI at `http://localhost:3000`
4. Visit the beta UI at `http://beta-local.instainstru.com:3000`

Invites generated in the preview admin (`/admin/beta/invites`) can now be
consumed on the beta origin without CORS failures.

### Local host mapping

Add the following entries to your `/etc/hosts` file so both the preview and beta
local hosts resolve to your machine:

```
127.0.0.1  beta-local.instainstru.com
127.0.0.1  api.beta-local.instainstru.com
```

No additional `.env` overrides are required for local testing—the API resolver
detects the current host at runtime. Vercel preview/beta environments continue
to rely on `NEXT_PUBLIC_API_BASE`.

## Local invite redemption e2e

The `invite-e2e` job now runs inside the `e2e-tests` workflow and uses the same
`python scripts/prep_db.py int --migrate --seed-all --force --yes` bootstrap as the
rest of our end-to-end suites. To reproduce the flow locally:

```bash
export SITE_MODE=local
export ALLOWED_ORIGINS=http://localhost:3000,http://beta-local.instainstru.com:3000
python backend/scripts/prep_db.py int --migrate --seed-all --force --yes
uvicorn backend.app.main:app --port 8000

npm --prefix frontend install
NEXT_PUBLIC_API_BASE=http://localhost:8000 NEXT_PUBLIC_APP_ENV=local npm --prefix frontend run dev

# In another terminal (after adding the /etc/hosts alias mentioned above)
CI_LOCAL_E2E=1 npx --yes playwright test frontend/e2e/invites.invite-redemption.spec.ts
```

The test logs in as `admin@instainstru.com / Test1234`, issues a beta invite from the
preview host, and redeems it on `beta-local.instainstru.com` to ensure CORS and cookies
behave correctly.

## Database prep cheatsheet

```
# Integration / Mock data
python backend/scripts/reset_schema.py int --force --yes
python backend/scripts/prep_db.py int --migrate --seed-all --force --yes

# Production system data only (roles, catalog, baseline admin)
python backend/scripts/prep_db.py prod --migrate --seed-system-only --force --yes

# Production with demo/mock users (pre-launch only)
python backend/scripts/prep_db.py prod --migrate --seed-all-prod --force --yes
```

Baseline admin credentials seeded by the scripts default to `admin@instainstru.com`
with the password `Test1234!` outside production. Override (and require in prod):

```
ADMIN_EMAIL="admin@instainstru.com"
ADMIN_NAME="Instainstru Admin"
ADMIN_PASSWORD="<strong unique password>"
```

When working against Supabase-hosted preview/prod data with row-level security,
optionally provide service-role DSNs for seeding without changing runtime configs:

```
PROD_SERVICE_DATABASE_URL="postgresql://service_role:...@db.supabase.co:5432/postgres"
PREVIEW_SERVICE_DATABASE_URL="postgresql://service_role:...@db.supabase.co:5432/postgres"
```

### Cache clears per environment

- `int`: cache clear is skipped (no remote state).
- `stg`: runs `python backend/scripts/clear_cache.py --scope all` locally after seeding/migrations.
- `preview` / `prod`: prep_db triggers a Render one-off job on the backend service followed by a redis redeploy. Service names are fixed:
  - Backend: `instainstru-api-preview` / `instainstru-api`
  - Redis: `redis-preview` / `redis`

Set `RENDER_API_KEY` in your shell or via `backend/.env.render` (the helper scripts load this file automatically) so preview/prod cache clears succeed.
