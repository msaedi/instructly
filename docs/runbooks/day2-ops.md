# Day-2 Ops Guide

This checklist focuses on the background-check (BGC) platform after go-live. Use it during on-call rotations or for routine maintenance.

## 1. Rotate Secrets

### Metrics Basic Auth (`METRICS_BASIC_AUTH_USER`, `METRICS_BASIC_AUTH_PASS`)
1. **Preview**
   - Update Render env group (preview API + `prom-agent-preview`).
   - `SMOKE_AUTH=1` on the agent for one deploy while validating logs.
2. **Verify**
   ```bash
   # Without auth → 401
   curl -I https://preview-api.instainstru.com/internal/metrics
   # With auth → 200
   curl -u 'metrics:<NEWPASS>' -s https://preview-api.instainstru.com/internal/metrics | head
   ```
   - Grafana Explore: `up{cluster="instainstru-preview"} == 1`
3. **Prod**
   - Rotate prod API + `prom-agent` env vars, redeploy agent first, then API.
4. **Clean up**
   - Remove `SMOKE_AUTH` once logs confirm 200 + scrape success.

### BGC Encryption (`BGC_ENCRYPTION_KEY`)
1. **Plan dual-read window**
   - Generate a new 32-byte key (base64).
   - Add both old & new keys via env (primary + fallback) to support rotation.
2. **Rollout**
   - Redeploy preview → run decrypt health check on recent records:
     ```bash
     python backend/scripts/check_bgc_encryption.py --env preview --limit 20
     ```
   - Repeat in prod during low-traffic window.
3. **Cutover & cleanup**
   - Remove old key after verifying decrypt/read for historical rows.
   - Update runbooks / vault entries, noting the rotation timestamp.
4. **Rollback**
   - If decrypt fails, redeploy with previous key pair and open an incident in #platform-oncall.

## 2. Pause / Resume Background Jobs

Env toggles already supported:

| Toggle | Effect |
| ------ | ------ |
| `SCHEDULER_ENABLED=false` | Stops scheduling final-adverse + expiry jobs. |
| `JOBS_WORKER_ENABLED=false` (or equivalent celery scaler) | Keeps worker offline. |

**Pause:**
1. Set the toggle(s) in Render → Save but do **not** restart yet.
2. Announce to #ops-bgc with context.
3. Redeploy API / worker. Confirm log lines `scheduler_enabled=False`.

**Resume:**
1. Re-enable toggles.
2. Redeploy worker first, then API.
3. Confirm queue is draining:
   ```bash
   docker compose -f docker-compose.monitoring.yml --env-file .env.monitoring logs -f worker
   redis-cli LLEN background_jobs_queue
   ```
4. If backlog > 50 or jobs stuck > 15 min → escalate to #platform-oncall.

## 3. BGC Email Test-drive

Tool: `backend/scripts/send_bgc_test_email.py`

```bash
cd backend
source venv/bin/activate  # or poetry shell
python scripts/send_bgc_test_email.py --env-file backend/.env.render \
  --email ops@example.com --type pre_adverse --force
```

- `--force` bypasses suppression flags (use sparingly in prod; notify #ops-bgc).
- Pre-adverse uses live template; final adverse requires decrypted payload.
- Check SendGrid/Resend dashboard for send confirmation.

## 4. Webhook / Job Backlog

1. **DLQ metrics** (`/ops/cache` + `/internal/metrics`)
   - `background_jobs_failed` gauge > 0 → inspect via Admin → Background Jobs.
2. **Logs**
   - Render worker logs (`celery-worker` service) for stack traces.
   - `redis-cli lrange background_jobs_dlq 0 5` for payload samples.
3. **Requeue**
   - Use existing admin CLI (`python backend/scripts/requeue_job.py <JOB_ID>`) after root cause fixed.
4. **Incident triggers**
   - >10 stuck jobs or webhook retries >15 → open incident.
   - Notifications: #platform-oncall + BGC vendor escalation (Checkr support) if root cause external.

## 5. Grafana Cloud + Slack Checklist

1. **Contact point**
   - Grafana Cloud → Alerting → Contact Points → “Add contact point”.
   - Type: Slack → Incoming webhook (`https://hooks.slack.com/services/...`).
2. **Notification policy**
   - Create route: severity `page` → Slack + email; `warn` → Slack only.
3. **Test rule**
   - Temporarily add AlwaysFiring rule:
     ```yaml
     expr: vector(1)
     for: 1m
     labels: {severity: warn}
     annotations: {summary: "Test alert"}
     ```
   - Verify Slack ping → remove the rule immediately.
4. **Ownership**
   - Note contact point URLs + API keys in 1Password entry “Grafana Cloud – BGC”.

---

## Appendices

### Prometheus agent rotation reminder
- Credentials are injected via `monitoring/prod-agent/Dockerfile` (`METRICS_BASIC_AUTH_USER/PASS`).
- Refer to this document when rotating to ensure agent + API stay in sync.
