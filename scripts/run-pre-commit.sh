#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Locate pre-commit binary: prefer backend venv, then PATH
if [[ -x "backend/venv/bin/pre-commit" ]]; then
  PRECOMMIT="backend/venv/bin/pre-commit"
else
  PRECOMMIT="$(command -v pre-commit || true)"
fi

if [[ -z "${PRECOMMIT}" ]]; then
  echo "[run-pre-commit] pre-commit not found." >&2
  echo "Install into backend venv:\n  cd backend && python -m venv venv && source venv/bin/activate && pip install pre-commit" >&2
  exit 127
fi

# Staged files only (portable, works on bash 3.x)
STAGED=()
while IFS= read -r line; do
  [[ -n "$line" ]] && STAGED+=("$line")
done < <(git diff --name-only --cached || true)

if [[ ${#STAGED[@]} -eq 0 ]]; then
  exit 0
fi

"${PRECOMMIT}" run --config .pre-commit-config.yaml --hook-stage pre-commit --files "${STAGED[@]}"
