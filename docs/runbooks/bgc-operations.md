# Background Check Operations

## Sender Profiles

We keep the default background-check sender identities in `backend/config/email_senders.json`. The values in this file ship with the application and cover the `trust`, `bookings`, `payments`, `account`, and `referrals` mail streams, including `from`, `from_name`, and `reply_to` fields.

At runtime the service loads that file first, then overlays any JSON present in the `EMAIL_SENDER_PROFILES_JSON` environment variable. Keys defined in the env var win field-by-field, so you can override only the pieces you need (for example, just `reply_to` for a single profile) without touching the other values.

If neither the file nor the env var provides a profile, the system falls back to the global defaults taken from `EMAIL_FROM_NAME`, `EMAIL_FROM_ADDRESS`, and `EMAIL_REPLY_TO`.

**Render guidance:** commit changes to `backend/config/email_senders.json` for long-lived defaults. For environment-specific tweaks, set `EMAIL_SENDER_PROFILES_JSON` in Render (or the respective deployment env) with just the overrides you need. Local development can do the same via `.env`.
