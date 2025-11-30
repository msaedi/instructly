# Background Check System

*Last Updated: November 2025 (Session v117)*

## Overview

InstaInstru uses **Checkr** for instructor background verification. The system handles the complete lifecycle from FCRA consent collection through adverse action workflows, with full compliance with Fair Credit Reporting Act (FCRA) requirements.

### Key Characteristics

| Aspect | Implementation |
|--------|---------------|
| Provider | Checkr (hosted invitations) |
| Check Type | Configurable package (e.g., `basic_plus`) |
| Validity Period | 1 year from completion |
| Consent Window | 24 hours (FCRA requirement) |
| Adverse Action | 5 business days waiting period |
| Environment Support | Sandbox + Production |

### BGC Status Flow

```
not_started → pending → passed (valid 1 year)
                 ↓
              review → dispute? → final_adverse → failed
                 ↓
              canceled
```

---

## Architecture

### Database Fields (InstructorProfile)

| Field | Type | Purpose |
|-------|------|---------|
| `bgc_status` | String(20) | Current status: pending/review/passed/failed/canceled |
| `bgc_report_id` | Text | Checkr report identifier |
| `bgc_completed_at` | DateTime | When check completed |
| `bgc_report_result` | String(32) | Raw result: clear/consider/suspended |
| `bgc_env` | String(20) | Environment: sandbox/production |
| `bgc_valid_until` | DateTime | Expiration date (1 year from pass) |
| `bgc_eta` | DateTime | Estimated completion time |
| `bgc_invited_at` | DateTime | When invitation was sent (rate limiting) |
| `bgc_includes_canceled` | Boolean | Report includes canceled screenings |
| `bgc_in_dispute` | Boolean | Candidate has disputed findings |
| `bgc_dispute_opened_at` | DateTime | When dispute was opened |

### Service Layer

| Component | Location | Purpose |
|-----------|----------|---------|
| `CheckrClient` | `app/integrations/checkr_client.py` | Async HTTP client for Checkr API |
| `FakeCheckrClient` | Same file | In-memory stub for non-production |
| `BackgroundCheckService` | `app/services/background_check_service.py` | Initiate checks, update status |
| `BackgroundCheckWorkflowService` | `app/services/background_check_workflow_service.py` | Webhook processing, adverse actions |

### Repository Layer

| Repository | Key Methods |
|------------|-------------|
| `InstructorProfileRepository` | `update_bgc()`, `update_bgc_by_report_id()`, `bind_report_to_candidate()` |
| `BGCWebhookLogRepository` | `record()` - Audit trail for webhooks |
| `BackgroundJobRepository` | `enqueue()` - Deferred job processing |

---

## Key Components

### 1. Checkr API Client

Located in `backend/app/integrations/checkr_client.py`:

```python
class CheckrClient:
    """Async client for Checkr REST API."""

    def __init__(self, *, api_key: str | SecretStr, base_url: str = "https://api.checkr.com/v1"):
        # Uses HTTP Basic Auth (API key as username, empty password)
        self._auth = httpx.BasicAuth(api_key, "")

    async def create_candidate(self, *, idempotency_key: str | None = None, **payload) -> Dict:
        """Create a Checkr candidate."""

    async def create_invitation(self, **payload) -> Dict:
        """Create hosted invitation for a candidate."""

    async def get_report(self, report_id: str) -> Dict:
        """Fetch report by ID."""
```

**FakeCheckrClient** provides identical interface for testing without API calls.

### 2. FCRA Consent Flow

Instructors must provide consent before background checks:

```python
# Route: POST /api/v1/instructors/{id}/bgc/consent
@router.post("/{instructor_id}/bgc/consent")
async def record_background_check_consent(payload: ConsentPayload, ...):
    """Record FCRA disclosure consent."""

    consent = repo.record_bgc_consent(
        instructor_id,
        consent_version=payload.disclosure_version,
        ip_address=request.client.host,
    )
    # Consent valid for 24 hours
```

**Consent Requirements:**
- `consent_version` - Version of consent form
- `disclosure_version` - Version of FCRA disclosure
- IP address automatically captured
- Expires after 24 hours

### 3. Invitation Flow

```python
# From BackgroundCheckService.invite()
async def invite(self, instructor_id: str, *, package_override: str | None = None):
    # 1. Validate instructor exists
    profile = self.repository.get_by_id(instructor_id)

    # 2. Resolve work location from ZIP code
    work_location = await self._resolve_work_location(user.zip_code)
    # Returns: {"country": "US", "state": "NY", "city": "New York"}

    # 3. Create Checkr candidate (idempotent)
    idempotency_key = f"candidate-{site_mode}-{profile.id}"
    candidate = await self.client.create_candidate(
        idempotency_key=idempotency_key,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        zipcode=normalized_zip,
        work_location=work_location,
    )

    # 4. Create hosted invitation
    invitation = await self.client.create_invitation(
        candidate_id=candidate["id"],
        package=resolved_package,
        redirect_url=f"{frontend_url}/instructor/onboarding/status",
        work_locations=[work_location],
    )

    # 5. Update profile
    self.repository.update_bgc(instructor_id, status="pending", ...)
```

### 4. Webhook Processing

Located in `backend/app/routes/v1/webhooks_checkr.py`:

**Security Layers:**
1. HTTP Basic Authentication
2. HMAC signature verification (X-Checkr-Signature header)
3. Delivery deduplication (in-memory cache, 5-minute TTL)

```python
@router.post("", response_model=WebhookAckResponse)
async def handle_checkr_webhook(request: Request, ...):
    # 1. Verify authentication
    _require_basic_auth(request)
    _verify_checkr_signature(request, raw_body)

    # 2. Check for duplicate delivery
    if _delivery_seen(delivery_key):
        return WebhookAckResponse(ok=True)

    # 3. Route by event type
    if event_type == "report.completed":
        workflow_service.handle_report_completed(...)
    elif event_type == "report.canceled":
        workflow_service.handle_report_canceled(...)
    # ... other event types
```

**Handled Webhook Events:**

| Event | Action |
|-------|--------|
| `invitation.created` | Mark status as pending |
| `invitation.completed` | Instructor submitted info |
| `report.created` | Report processing started |
| `report.updated` | ETA changed |
| `report.completed` | Final result available |
| `report.canceled` | Check was canceled |
| `report.suspended` | Check on hold |

### 5. Adverse Action Workflow

When a background check returns "consider" or fails, FCRA requires a specific process:

```python
# 5 business days waiting period
FINAL_ADVERSE_BUSINESS_DAYS: Final[int] = 5

def _schedule_final_adverse_action(self, profile_id: str, ...):
    """Schedule final adverse action after FCRA waiting period."""

    holidays = _collect_holidays(sent_at)  # US federal holidays
    available_at = add_us_business_days(sent_at, 5, holidays)

    job_repo.enqueue(
        type="background_check.final_adverse_action",
        payload={
            "profile_id": profile_id,
            "pre_adverse_notice_id": notice_id,
            "pre_adverse_sent_at": sent_at.isoformat(),
        },
        available_at=available_at,
    )
```

**Adverse Action Timeline:**
1. **Day 0**: Report returns "consider" → Send pre-adverse notice email
2. **Days 1-5**: Waiting period (5 business days, excluding holidays)
3. **Day 5+**: Execute final adverse action → Send final adverse email

**Dispute Handling:**
```python
async def resolve_dispute_and_resume_final_adverse(self, instructor_id: str, ...):
    """Resume workflow after dispute resolution."""

    if now >= final_ready_at:
        # Dispute resolved after waiting period - execute immediately
        job_repo.enqueue(..., available_at=now)
        return True, None
    else:
        # Reschedule for remaining waiting period
        job_repo.enqueue(..., available_at=final_ready_at)
        return False, final_ready_at
```

---

## Data Flow

### Invitation Flow

```
1. Instructor clicks "Start Background Check"
   POST /api/v1/instructors/{id}/bgc/invite

2. Server validates:
   - Recent FCRA consent (within 24 hours)
   - Not rate-limited (24 hours since last invite)
   - No check already in progress

3. Geocode ZIP code → work location
   - Uses Google/Mapbox geocoding provider
   - Returns city, state, country

4. Create Checkr candidate + invitation
   - Idempotent via instructor ID
   - Returns invitation_id, candidate_id, report_id

5. Update instructor profile
   - bgc_status = "pending"
   - bgc_report_id = report ID from Checkr
   - bgc_env = "sandbox" or "production"
```

### Webhook Flow

```
1. Checkr sends webhook
   POST /api/v1/webhooks/checkr

2. Security validation:
   - Basic auth (CHECKR_WEBHOOK_USER:CHECKR_WEBHOOK_PASS)
   - HMAC signature (X-Checkr-Signature)

3. Deduplication check
   - Cache key: delivery_id or event_type:resource_id
   - TTL: 5 minutes

4. Log webhook to bgc_webhook_logs table

5. Process by event type:
   - Bind report to profile (via candidate_id or invitation_id)
   - Update status, completed_at, result
   - For "review" results: send pre-adverse email

6. Return 200 OK (always, per Checkr best practices)
```

---

## Error Handling

### API Error Classification

```python
def _is_package_not_found_error(err: CheckrError) -> bool:
    """Detect missing package configuration."""
    return err.status_code == 404 and "package not found" in str(err).lower()

def _is_work_location_error(err: CheckrError) -> bool:
    """Detect invalid work location."""
    return err.status_code in {400, 422} and "work_location" in str(err).lower()
```

| Error Type | HTTP Status | User Message |
|------------|-------------|--------------|
| Missing consent | 400 | "FCRA consent required" |
| Rate limited | 429 | "Wait 24 hours before trying again" |
| Invalid ZIP | 400 | "Couldn't verify your teaching ZIP code" |
| Geocoding failure | 400 | "Address verification service unavailable" |
| Checkr auth error | 400 | "Checkr API key invalid" |
| Package not found | 400 | "Checkr package misconfigured" |

### Deferred Processing

When database writes fail, webhooks are queued for retry:

```python
try:
    workflow_service.handle_report_completed(...)
except RepositoryException as exc:
    # Queue for later processing
    job_repository.enqueue(
        type="webhook.report_completed",
        payload={...},
    )
    logger.warning("Background check workflow deferred: %s", str(exc))
```

---

## Monitoring

### Prometheus Metrics

```python
# From app/core/metrics.py
BGC_INVITES_TOTAL = Counter("bgc_invites_total", "Background check invites", ["outcome"])
# Labels: ok, error, rate_limited, consent_required, recheck_ok

CHECKR_WEBHOOK_TOTAL = Counter("checkr_webhook_total", "Checkr webhooks processed", ["result", "outcome"])
# result: clear, consider, canceled, other
# outcome: success, queued, error

BGC_FINAL_ADVERSE_SCHEDULED_TOTAL = Counter("bgc_final_adverse_scheduled_total", "Final adverse actions scheduled")
BGC_FINAL_ADVERSE_EXECUTED_TOTAL = Counter("bgc_final_adverse_executed_total", "Final adverse actions executed", ["outcome"])
# outcome: finalized, superseded, skipped_status, skipped_dispute
```

### Structured Logging

```python
logger.info(
    "Background check invite success",
    extra={
        "evt": "bgc_invite",
        "marker": "invite:success",
        "instructor_id": instructor_id,
        "package": package_slug,
        "hosted_workflow": hosted_workflow,
    },
)
```

**Key Log Events:**
- `bgc_invite` - Invitation attempts and outcomes
- `bgc_consent` - Consent recordings
- `checkr_webhook` - Webhook processing
- `bgc_final_adverse` - Adverse action execution

---

## Common Operations

### Check BGC Status

```bash
# API: GET /api/v1/instructors/{id}/bgc/status
curl /api/v1/instructors/01K2.../bgc/status \
  -H "Authorization: Bearer $TOKEN"

# Response:
{
  "status": "pending",
  "report_id": "rpt_abc123",
  "completed_at": null,
  "env": "sandbox",
  "consent_recent": true,
  "valid_until": null,
  "expires_in_days": null,
  "eta": "2025-12-05T14:00:00Z"
}
```

### Mock Pass (Non-Production)

```bash
# For testing in development/staging
POST /api/v1/instructors/{id}/bgc/mock/pass
POST /api/v1/instructors/{id}/bgc/mock/review
POST /api/v1/instructors/{id}/bgc/mock/reset
```

### Simulate Webhook (Development)

```bash
# Use the simulation script
python backend/scripts/simulate_checkr_webhook.py \
  --report-id rpt_abc123 \
  --event-type report.completed \
  --result clear
```

### Query Webhook History

```sql
SELECT * FROM bgc_webhook_logs
WHERE resource_id = 'rpt_abc123'
ORDER BY created_at DESC;
```

---

## Troubleshooting

### Instructor Stuck in "Pending"

1. **Check if report exists in Checkr Dashboard**
   - Log into Checkr Dashboard
   - Search by email or report ID

2. **Verify report is bound to profile**:
   ```sql
   SELECT id, bgc_report_id, bgc_status, bgc_candidate_id
   FROM instructor_profiles
   WHERE id = '01K2...';
   ```

3. **Check webhook logs**:
   ```sql
   SELECT event_type, http_status, payload, created_at
   FROM bgc_webhook_logs
   WHERE resource_id = 'rpt_...'
   ORDER BY created_at DESC;
   ```

4. **Re-run deferred job** if webhook failed:
   ```sql
   SELECT * FROM background_jobs
   WHERE type LIKE 'webhook.%'
   AND payload->>'report_id' = 'rpt_...';
   ```

### Webhook Not Received

1. **Verify webhook endpoint configuration in Checkr Dashboard**:
   - URL: `https://api.instainstru.com/api/v1/webhooks/checkr`
   - Auth: Basic auth credentials set

2. **Check environment variables**:
   - `CHECKR_WEBHOOK_USER` and `CHECKR_WEBHOOK_PASS` set
   - `CHECKR_API_KEY` matches webhook signing

3. **Review application logs** for 401/403 errors

### BGC Valid Until Not Set

This happens when the webhook doesn't find the profile:

```python
# In handle_report_completed
if status_value == "passed":
    valid_until = completed_at + timedelta(days=365)
    self.repo.update_valid_until(profile.id, valid_until)
```

**Fix**: Manually bind report and re-run:
```sql
UPDATE instructor_profiles
SET bgc_report_id = 'rpt_...', bgc_env = 'production'
WHERE id = '01K2...';
```

Then simulate the webhook again.

### Pre-Adverse Email Not Sent

Check configuration:
```python
# In settings
bgc_suppress_adverse_emails = True  # Suppresses all adverse emails
```

Check if already sent:
```sql
SELECT bgc_review_email_sent_at FROM instructor_profiles WHERE id = '01K2...';
```

---

## Configuration

### Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `CHECKR_API_KEY` | Yes* | API authentication |
| `CHECKR_FAKE` | No | Use fake client (default: true in non-prod) |
| `CHECKR_ENV` | No | Environment: sandbox/production (default: sandbox) |
| `CHECKR_PACKAGE` | No | Default package slug |
| `CHECKR_HOSTED_WORKFLOW` | No | Workflow ID for hosted flow |
| `CHECKR_WEBHOOK_USER` | Yes | Basic auth username for webhooks |
| `CHECKR_WEBHOOK_PASS` | Yes | Basic auth password for webhooks |
| `BGC_SUPPRESS_ADVERSE_EMAILS` | No | Suppress adverse action emails |
| `CHECKR_APPLICANT_PORTAL_URL` | No | URL for applicant to view status |
| `BGC_SUPPORT_EMAIL` | No | Support email in notifications |

*Not required if `CHECKR_FAKE=true`

### Fake Client Mode

For development without Checkr API access:

```bash
# In .env
CHECKR_FAKE=true  # Uses FakeCheckrClient
```

The fake client:
- Generates fake candidate/invitation/report IDs
- Always returns `result: clear`
- No network calls made

---

## Related Documentation

- [Checkr API Documentation](https://docs.checkr.com/)
- [FCRA Compliance Guide](https://www.ftc.gov/business-guidance/privacy-security/credit-reporting)
- Backend routes: `backend/app/routes/v1/instructor_bgc.py`
- Webhook handler: `backend/app/routes/v1/webhooks_checkr.py`
- Services: `backend/app/services/background_check_*.py`
