#!/usr/bin/env bash
set -euo pipefail

# verify_beta_production.sh
# Usage: backend/scripts/verify_beta_production.sh [WEB_DOMAIN] [API_BASE]
#  - WEB_DOMAIN defaults to beta.instainstru.com
#  - API_BASE   defaults to $NEXT_PUBLIC_API_URL or http://localhost:8000

WEB_DOMAIN=${1:-beta.instainstru.com}
API_BASE=${2:-${NEXT_PUBLIC_API_URL:-http://localhost:8000}}

echo "=== Beta Production Verification ==="
echo "Web Domain: ${WEB_DOMAIN}"
echo "API Base  : ${API_BASE}"
echo

echo "[1/5] DNS lookup for ${WEB_DOMAIN}"
if command -v dig >/dev/null 2>&1; then
  dig +short A ${WEB_DOMAIN} || true
  dig +short CNAME ${WEB_DOMAIN} || true
else
  nslookup ${WEB_DOMAIN} || true
fi
echo

echo "[2/5] HTTPS HEAD request to https://${WEB_DOMAIN}"
curl -sSI https://${WEB_DOMAIN} | sed 's/^/  /'
echo

echo "[3/5] Check HSTS (Strict-Transport-Security)"
if curl -sSI https://${WEB_DOMAIN} | grep -i "strict-transport-security" >/dev/null; then
  echo "  ✓ HSTS header present"
else
  echo "  ✗ HSTS header missing"
fi
echo

echo "[4/5] Check API health and beta headers"
API_HEALTH_URL="${API_BASE%/}/health"
echo "  GET ${API_HEALTH_URL}"
curl -sSI "${API_HEALTH_URL}" | sed 's/^/    /'
PHASE=$(curl -sSI "${API_HEALTH_URL}" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-beta-phase"{print $2}')
ALLOW=$(curl -sSI "${API_HEALTH_URL}" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-beta-allow-signup"{print $2}')
echo "  Parsed headers: x-beta-phase='${PHASE:-n/a}', x-beta-allow-signup='${ALLOW:-n/a}'"
echo

echo "[5/5] TLS certificate summary for ${WEB_DOMAIN} (issuer/subject/dates)"
if command -v openssl >/dev/null 2>&1; then
  echo | openssl s_client -servername ${WEB_DOMAIN} -connect ${WEB_DOMAIN}:443 2>/dev/null \
    | openssl x509 -noout -issuer -subject -dates | sed 's/^/  /'
else
  echo "  (openssl not installed, skipping)"
fi
echo

echo "Done. Review the outputs above."
