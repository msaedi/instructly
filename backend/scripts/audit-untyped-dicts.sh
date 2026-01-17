#!/bin/bash
# Guardrail: Untyped Dict[str, Any] Detection in Schemas
#
# This script prevents new untyped Dict[str, Any] fields from being added to
# API response schemas. Such fields generate untyped TypeScript ({[key: string]: unknown}).
#
# Usage:
#   ./scripts/audit-untyped-dicts.sh        # Full audit
#   ./scripts/audit-untyped-dicts.sh --ci   # CI mode (exits with error on violations)

set -e

# Baseline count of Dict[str, Any] usages in schemas
# Update this number ONLY when:
#   1. You've properly typed a Dict[str, Any] field (decrease baseline)
#   2. You've added a legitimately dynamic field (increase baseline + add to allowlist)
#
# Last updated: 2025-01-17 - Phase 3 Complete + Discriminated Unions
#   - Phase 3 migration: 24 occurrences fixed with typed models
#   - Additional fixes:
#     * main_responses.py: Deleted duplicate dead-code PerformanceMetricsResponse (1 removed)
#     * privacy.py: statistics → PrivacyStatistics, stats → RetentionStats (2 removed)
#   - Discriminated Union fixes (2 removed):
#     * alert_responses.py: details → AlertDetailsUnion (5 alert type models)
#     * nl_search.py: details → PipelineStageDetailsUnion (9 stage models)
#   - NOT converted (kept as Dict[str, Any]):
#     * base_responses.py: data field - Generic[T] caused mypy errors at 5+ callsites
#   - Remaining 14 are ALLOWLIST (truly dynamic/external):
#     * 10 model fields with legitimate Dict[str, Any] needs
#     * 2 comments documenting allowlist decisions
#     * 2 method signatures (internal Pydantic serializer)
#
# This baseline prevents NEW additions without review
BASELINE=14

# Determine script location and set search directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔍 Backend Guardrails: Untyped Dict Audit"
echo "=========================================="

# Count Dict[str, Any] in schemas (excluding __pycache__)
COUNT=$(grep -rn "Dict\[str, Any\]" \
  "$BACKEND_DIR/app/schemas/" \
  --include="*.py" 2>/dev/null \
  | grep -v "__pycache__" \
  | wc -l | tr -d ' ')

echo ""
echo "📊 Results:"
echo "   Current count: $COUNT"
echo "   Baseline:      $BASELINE"
echo ""

if [ "$COUNT" -gt "$BASELINE" ]; then
  echo -e "${RED}❌ VIOLATION: Untyped Dict[str, Any] count increased!${NC}"
  echo ""
  echo "New untyped dicts detected. Options:"
  echo "  1. Replace Dict[str, Any] with a properly typed Pydantic model"
  echo "  2. If legitimately dynamic (metrics/audit), add to allowlist and update BASELINE"
  echo ""
  echo "New violations (last $((COUNT - BASELINE + 5)) matches):"
  grep -rn "Dict\[str, Any\]" \
    "$BACKEND_DIR/app/schemas/" \
    --include="*.py" 2>/dev/null \
    | grep -v "__pycache__" \
    | tail -n $((COUNT - BASELINE + 5))
  echo ""

  if [ "$1" == "--ci" ]; then
    exit 1
  fi
elif [ "$COUNT" -lt "$BASELINE" ]; then
  echo -e "${YELLOW}⚠️  Count decreased! Consider updating BASELINE to $COUNT${NC}"
  echo ""
  echo -e "${GREEN}✅ No violations detected${NC}"
else
  echo -e "${GREEN}✅ Untyped Dict[str, Any] count OK (matches baseline)${NC}"
fi

echo ""
echo "Allowlisted patterns (14 total - all legitimate uses of Dict[str, Any]):"
echo ""
echo "  External/Dynamic Data (10 model fields):"
echo "    - audit.py: before/after (2) - audit logs capture arbitrary model snapshots"
echo "    - address.py: location_metadata (1) - external geocoding provider response"
echo "    - address_responses.py: features (1) - GeoJSON standard format"
echo "    - payment_schemas.py: settings, details (2) - Stripe external API responses"
echo "    - privacy.py: data (1) - GDPR export varies by user's data"
echo "    - monitoring_responses.py: redis_info (2) - external Redis INFO output"
echo "    - base_responses.py: data (1) - SuccessResponse used widely, Generic[T] breaks callsites"
echo ""
echo "  Non-model-field matches (4 grep matches):"
echo "    - monitoring_responses.py: 2 comments documenting allowlist decisions"
echo "    - password_reset.py: 2 method signature type hints (internal Pydantic)"
echo ""
echo "  Converted to typed patterns:"
echo "    - alert_responses.py: details → AlertDetailsUnion (discriminated union)"
echo "    - nl_search.py: details → PipelineStageDetailsUnion (discriminated union)"
echo ""
echo "All fixable patterns have been converted to typed models."
echo ""
