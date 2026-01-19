#!/bin/bash
# Phase 3 Guardrails: Ad-Hoc Type Regression Prevention
#
# This script ensures no new ad-hoc Response/Request interfaces are added
# without going through the OpenAPI shim. Legitimate local types are allowlisted.
#
# Usage:
#   ./scripts/audit-adhoc-types.sh        # Full audit
#   ./scripts/audit-adhoc-types.sh --ci   # CI mode (exits with error on violations)

set -e

# Baseline count of legitimate local types (Category C)
# Update this number when intentionally adding new local types
# Last updated: Final audit (2025-01-17) - 10 unique types, 16 grep matches
# Removed: ReviewsResponse (migrated), CancelBookingRequest (dead code)
BASELINE=16

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔍 Phase 3 Guardrails: Ad-Hoc Type Audit"
echo "========================================="

# Determine script location and set search directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(dirname "$SCRIPT_DIR")"

# Count ad-hoc types (interface.*Response or interface.*Request)
# Excluding: generated files, test files, node_modules
COUNT=$(grep -rn "interface.*Response\|interface.*Request" \
  "$FRONTEND_DIR/types" \
  "$FRONTEND_DIR/features" \
  "$FRONTEND_DIR/services" \
  "$FRONTEND_DIR/src" \
  --include="*.ts" --include="*.tsx" 2>/dev/null \
  | grep -v "generated" \
  | grep -v "__tests__" \
  | grep -v ".test." \
  | grep -v ".spec." \
  | grep -v "node_modules" \
  | wc -l | tr -d ' ')

echo ""
echo "📊 Results:"
echo "   Current count: $COUNT"
echo "   Baseline:      $BASELINE"
echo ""

if [ "$COUNT" -gt "$BASELINE" ]; then
  echo -e "${RED}❌ VIOLATION: Ad-hoc type count increased!${NC}"
  echo ""
  echo "New ad-hoc types detected. If this is intentional:"
  echo "  1. If it's a frontend-only utility type → Add to allowlist and update BASELINE"
  echo "  2. If it matches a backend schema → Import from @/features/shared/api/types instead"
  echo ""
  echo "New types found:"
  grep -rn "interface.*Response\|interface.*Request" \
    "$FRONTEND_DIR/types" \
    "$FRONTEND_DIR/features" \
    "$FRONTEND_DIR/services" \
    "$FRONTEND_DIR/src" \
    --include="*.ts" --include="*.tsx" 2>/dev/null \
    | grep -v "generated" \
    | grep -v "__tests__" \
    | grep -v ".test." \
    | grep -v ".spec." \
    | grep -v "node_modules" \
    | tail -n $((COUNT - BASELINE + 5))
  echo ""

  if [ "$1" == "--ci" ]; then
    exit 1
  fi
elif [ "$COUNT" -lt "$BASELINE" ]; then
  echo -e "${YELLOW}⚠️  Count decreased. Consider updating BASELINE to $COUNT${NC}"
  echo ""
  echo -e "${GREEN}✅ No violations detected${NC}"
else
  echo -e "${GREEN}✅ Ad-hoc type count OK (matches baseline)${NC}"
fi

echo ""
echo "Allowlisted local types (10 unique, Category C - legitimate frontend-only):"
echo "  types/common.ts:"
echo "    - PaginatedResponse<T>    (generic utility for paginated endpoints)"
echo "  types/api.ts:"
echo "    - APIResponse<T>          (fetch wrapper utility)"
echo "    - ResponseMeta            (pagination metadata inside APIResponse)"
echo "    - RequestState<T>         (UI loading/error state)"
echo "    - BatchRequest<T>         (batching utility)"
echo "    - BatchResponse<T>        (batching utility)"
echo "  types/booking.ts:"
echo "    - AvailabilityResponse    (frontend aggregate type)"
echo "    - BookedSlotsResponse     (uses frontend-only BookedSlotPreview)"
echo "  features/shared/api/client.ts:"
echo "    - ApiResponse<T>          (fetch wrapper in client)"
echo "    - FetchOptions            (internal fetch options)"
echo ""
