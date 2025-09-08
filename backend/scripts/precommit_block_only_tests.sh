#!/usr/bin/env sh
set -eu

# Find staged backend Python files
FILES="$(git diff --cached --name-only | grep -E '^backend/.*\.py$' || true)"

# Nothing to check
[ -z "$FILES" ] && exit 0

violations=""

# 1) pytest.mark.only or decorator
v1=$(printf "%s\n" "$FILES" | xargs grep -nEH 'pytest\.mark\.only|@pytest\.mark\.only' 2>/dev/null || true)
[ -n "$v1" ] && violations="$violations$v1\n"

# 2) -k "...only..."
v2=$(printf "%s\n" "$FILES" | xargs grep -nEH '\\s-k\\s+"[^"]*only[^"]*"' 2>/dev/null || true)
[ -n "$v2" ] && violations="$violations$v2\n"

# 3) -k '\''...only...\''
v3=$(printf "%s\n" "$FILES" | xargs grep -nEH "\\s-k\\s+'[^']*only[^']*'" 2>/dev/null || true)
[ -n "$v3" ] && violations="$violations$v3\n"

if [ -n "$violations" ]; then
  echo "Focused tests are not allowed in commits. Offending lines:" >&2
  printf "%s" "$violations" | sed '/^$/d' >&2
  exit 2
fi

exit 0
