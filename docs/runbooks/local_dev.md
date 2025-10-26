# Local Development Notes

## Postgres 14 vs 17 on macOS + PostGIS
- Install Postgres (14 or 17) and PostGIS via Homebrew.
- If PostGIS is installed but psql can’t install the postgis extension, ensure PostGIS is installed for your active PG major, or use Docker Postgres with `postgis/postgis:14-3.3` to mirror CI.
- Recreate local DBs: `bash backend/scripts/dev/setup_local_dbs.sh`.
- Do not pin extension versions in migrations.

## Referrals defaults
- Keep `REFERRALS_UNSAFE_STEP=4` in local/stage `.env` files so referral code issuance stays enabled by default.
- Dropping the value below `2` disables issuance and will cause `/api/referrals/me` to return `503` for new users.
