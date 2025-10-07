# Background Check Operations

## Feature Toggles & Key Settings
- `BGC_SUPPRESS_ADVERSE_EMAILS`: When true, pre/final adverse emails are skipped. Use for dry-runs or if downstream mailer issues arise.
- `BGC_SUPPRESS_EXPIRY_EMAILS`: Suppresses expiry re-check reminders. Leave false in production unless messaging should pause.
- `SCHEDULER_ENABLED`: Turns background schedulers on/off. Disable during migrations or incident triage to stop new jobs from being queued.
- `JOBS_MAX_ATTEMPTS`: Dead-letter threshold for background jobs. Default 5. Increase temporarily if an integration is flaky but recoverable.
- `CHECKR_ENV`: `sandbox` vs `production`. Must match the environment that Checkr webhooks are sourced from.
- `CHECKR_FAKE`: When true we use the fake client. For prod this should be false unless doing a controlled test.

## Core Workflows
1. **Pre → Final Adverse (5 business days)**
   - `report.completed` with `consider` result sends the pre-adverse email and schedules final adverse +5 business days.
   - If a dispute is opened, the job is paused until `bgc_in_dispute` clears.
   - Final adverse email fires automatically once the delay expires and no dispute remains.
2. **Dispute Pause**
   - Any profile with `bgc_in_dispute = true` blocks final adverse actions and disables rejection in the admin review drawer.
3. **Re-check & Expiry**
   - Scheduler sweeps daily: reminders for profiles expiring within 30 days, forced re-check and deactivation for expired entries.
   - Admins can trigger manual re-check from the review drawer when appropriate.
4. **Admin Actions**
   - Approve → marks background check complete and makes the profile eligible to go live.
   - Reject → sends final adverse (unless in dispute). Copy ID/email helpers aid escalations.

## Playbooks
### Webhook Errors (Sustained)
1. Inspect Checkr webhook logs (`infra/logs`, Render dashboard) and application logs for stack traces.
2. Verify signature using `simulate_checkr_webhook.py --env-file backend/.env --dry-run`.
3. Requeue jobs stuck in DLQ if the root cause is resolved.
4. Escalate to Checkr if payloads are malformed or missing.

### Dead-letter Queue Non-empty
1. Query `background_jobs` table for `status='failed'` to identify affected job IDs.
2. Check `payload` type; if transient, re-enqueue via admin CLI; if permanent, handle manually or purge.
3. Adjust `JOBS_MAX_ATTEMPTS` only if jobs are failing due to temporary integration issues.

### Pending > 7 Days
1. Review `bgc_pending_over_7d` metric or the admin queue filter.
2. Contact Checkr for county searches or outstanding documents.
3. If stuck, request the instructor initiates a re-check via admin action or send manual communication.

## Sender Profiles
- Defaults live in `backend/config/email_senders.json`.
- Runtime overlay via `EMAIL_SENDER_PROFILES_JSON` (field-by-field priority over the file).
- Missing keys fall back to `EMAIL_FROM_NAME`, `EMAIL_FROM_ADDRESS`, and `EMAIL_REPLY_TO`.
- **Render guidance:** commit file changes for long-lived defaults; set `EMAIL_SENDER_PROFILES_JSON` per environment for targeted overrides (local `.env` works the same).

## Tools
- `backend/scripts/simulate_checkr_webhook.py` — replay Checkr events (`--email`, `--result`, `--env-file`).
- `backend/scripts/send_bgc_test_email.py` — send template previews. Supports `--sender`, `--force`, and `--env-file` for profile testing.

## Alerting
- Alertmanager config: `monitoring/alertmanager/alertmanager.yml`.
  - Set `ALERT_SLACK_WEBHOOK` (Render/secret store) pointing to `#bgc-alerts`.
  - Deploy alongside Prometheus in your infra stack.
- Grafana dashboard: `monitoring/grafana/dashboards/bgc-overview.json` (import into Grafana, provide Prometheus datasource UID).
- Example rules already exist under `infra/alerts/` — wire them into Prometheus Alertmanager for production.
