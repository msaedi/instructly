#!/bin/bash
set -euo pipefail

# Only check staged TS/TSX files passed by pre-commit
FILES=("$@")

if [ ${#FILES[@]} -eq 0 ]; then
  exit 0
fi

FAILED=0
for f in "${FILES[@]}"; do
  # ignore tests, e2e, logger implementation, server.js
  if [[ "$f" == *"/__tests__/"* || "$f" == *"/e2e/"* ]]; then
    continue
  fi
  if [[ "$f" == *"/lib/logger.ts" || "$f" == *"/server.js" ]]; then
    continue
  fi
  if grep -nE "\bconsole\.(log|warn|error|info|debug)\b" "$f" >/dev/null 2>&1; then
    echo "no-console violation: $f"
    grep -nE "\bconsole\.(log|warn|error|info|debug)\b" "$f" | sed "s/^/  /"
    FAILED=1
  fi
done

exit $FAILED
