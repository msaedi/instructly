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

- Frontend: use `frontend/.env.local` for both preview and beta. The build reads
  `NEXT_PUBLIC_APP_URL` and `NEXT_PUBLIC_API_BASE` for routing. When running multiple
  origins, set `NEXTAUTH_URL` per host (e.g. `http://localhost:3000` vs `http://beta-local.instainstru.com:3000`), enable
  `trustHost: true`, and keep cookies `secure=false` / `sameSite=Lax` for local HTTP. (We
  use a custom FastAPI session system, but these settings keep Auth.js experiments aligned.)
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
