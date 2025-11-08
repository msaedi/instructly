# Availability Bitmap Guardrails

These environment flags tune the bitmap availability pipeline to keep instructor past-edits safe while ensuring operations and metrics remain predictable.

| Flag | Description | Recommended defaults |
| --- | --- | --- |
| `PAST_EDIT_WINDOW_DAYS` | Maximum age (in days) of past dates that bitmap saves will modify. Values ≤ 0 disable the clamp. | **prod/stg:** 30<br>**local/test:** 0 |
| `CLAMP_COPY_TO_FUTURE` | When true, `apply-to-date-range` skips target dates earlier than “today” for the instructor. | **prod/stg:** true<br>**local/test:** false |
| `SUPPRESS_PAST_AVAILABILITY_EVENTS` | Suppresses availability outbox events that reference only past dates (cache invalidation still runs). | **prod/stg:** true<br>**local/test:** false |

### Notes
- “Today” is computed in the instructor’s timezone (`get_user_today_by_id`).
- Past-day saves continue to respond with `X-Allow-Past`, `ETag`, and `Last-Modified` headers.
- Suppressed events still update the audit log and warm caches; they simply skip the notification pipeline.
