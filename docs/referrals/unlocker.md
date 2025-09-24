# Referral Unlocker

The referral unlocker processes referral rewards in three stages:

- **Pending → Unlocked**: rewards that satisfy the hold period are unlocked and become spendable.
- **Refunded → Voided**: rewards tied to refunded bookings are marked void and emit `reward_voided` events.
- **Expired → Voided**: rewards past their expiry window are voided so balances stay accurate.

## Scheduling

- **Celery task**: `app.tasks.referrals.run_unlocker`
- **Cadence**: every 15 minutes via Celery Beat (`referrals-unlock-every-15m` schedule entry)
- **Queue**: default `celery` queue with moderate priority

## Local debugging

Run the unlocker manually from the backend repository root:

```bash
python -m app.services.referral_unlocker --limit 200 --dry-run
```

`--dry-run` keeps the database unchanged while logging what would happen. Adjust `--limit` to constrain the batch size.

## Operational notes

- Toggle the feature with `REFERRALS_ENABLED`. When set to `false`, the unlocker exits early and reports zero changes.
- Modify the cadence by changing the Celery Beat entry `referrals-unlock-every-15m`.
- The Celery task returns a summary dict (`processed`, `unlocked`, `voided`, `expired`) that surfaces in worker logs and monitoring.
