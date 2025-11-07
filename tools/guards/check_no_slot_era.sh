#!/usr/bin/env bash
# One-time bitmap guard: fail if slot-era tokens are present in prod code (and optionally scripts).
# Usage:
#   tools/guards/check_no_slot_era.sh            # scan prod code only (backend/app)
#   tools/guards/check_no_slot_era.sh --all      # scan prod + scripts (backend/app + backend/scripts)

set -euo pipefail

scan_all=false
if [[ "${1:-}" == "--all" ]]; then
  scan_all=true
fi

PATTERN=$'\b(AvailabilitySlot|availability_slots|SlotManager|get_?slots_by_date|delete_?slots_by_dates|get_?week_slots|get_?slots_with_booking_status|slots_?created)\b'

echo "== Slot-era token scan =="
echo "Pattern: $PATTERN"
echo

# Always scan prod code
TARGETS=("backend/app")
# Optionally include scripts
if [[ "$scan_all" == true ]]; then
  TARGETS+=("backend/scripts")
fi

# Build ripgrep args (exclude obvious non-sources)
EXCLUDES=(--glob '!**/__pycache__/**' --glob '!**/legacy/**' --glob '!**/.venv/**' --glob '!**/venv/**')

FOUND=0
for tgt in "${TARGETS[@]}"; do
  if rg -n --hidden "${EXCLUDES[@]}" "$PATTERN" "$tgt"; then
    echo
    echo "❌ Found slot-era tokens in: $tgt"
    FOUND=1
  else
    echo "✅ No slot-era tokens in: $tgt"
  fi
  echo

done

if [[ $FOUND -ne 0 ]]; then
  echo "Summary: Slot-era tokens were found. Please remove them before proceeding."
  exit 1
fi

echo "Summary: All clear. Bitmap-only code paths confirmed for scanned targets."
