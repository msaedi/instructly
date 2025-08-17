# Email Templates

This directory contains Jinja2 templates for all platform emails.

## Structure
- `email/base.html` — Base template with shared layout and styles
- `email/booking/` — Booking-related emails (confirmation, cancellation, reminders)
- `email/auth/` — Authentication emails (welcome, password flows)
- `email/referrals/` — Referral-related emails (invite)
- `email/components/` — Reusable partials

## Usage
Templates are rendered via `TemplateService` and typically sent through `EmailService`.

Example:
```python
from app.services.template_service import TemplateService
from app.services.email import EmailService

# Render
template_service = TemplateService(db, cache)
html = template_service.render_template(
    "email/referrals/invite.html",
    context={"inviter_name": "Emma", "referral_link": "https://instainstru.com/ref/EMM123"},
)

# Send
email_service = EmailService(db)
email_service.send_email(
    to_email="test@example.com",
    subject="Emma invited you to try InstaInstru",
    html_content=html,
    from_email="invites@instainstru.com",
    from_name="InstaInstru",
)
```

## Common Variables (auto-injected)
- `brand_name` — "iNSTAiNSTRU"
- `current_year` — Current year
- `frontend_url` — Frontend base URL

## Creating New Templates
1. Add a file under `email/<category>/<name>.html` and extend `email/base.html`.
2. Keep content concise, include a clear CTA, and provide a plain link fallback.
3. Add a method in `EmailService` that renders and sends the template (preferred over inline HTML).
4. Use a dedicated sender (e.g., `invites@instainstru.com` for referrals, `security@instainstru.com` for password/security).
