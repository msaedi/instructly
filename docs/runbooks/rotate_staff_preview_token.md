# Rotate staff_preview_token (Preview API)

Preconditions:
- allow_preview_header=false by default; only turn on during transition.
- Staff SSO works; the token is a fallback.

Steps:
1) Generate new token T_NEW.
2) Set env on preview API: STAFF_PREVIEW_TOKEN_NEW=T_NEW (keep STAFF_PREVIEW_TOKEN=T_OLD).
3) Update preview proxy to send T_NEW when enabled.
4) Deploy preview; verify /health and one gated endpoint = 200.
5) Switch API to accept only T_NEW (remove T_OLD); redeploy.
6) Verify logs show via=header with new token only.
7) Set allow_preview_header=false again; document rotation timestamp.

Notes:
- Monitor Prometheus panel for instainstru_preview_bypass_total{via="header"}; expect a spike during rotation only.
