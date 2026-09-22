#!/usr/bin/env bash
# Isolated worktree for feat/* or fix/*. Never implement on the primary clone.
set -euo pipefail

ALLOWED_PREFIXES=(feat fix docs refactor test ci chore)

if [ $# -lt 1 ]; then
  echo "Usage: bash scripts/new-feature-worktree.sh <prefix>/<short-name> [base-ref]" >&2
  echo "Example: bash scripts/new-feature-worktree.sh feat/issuer-slice-a" >&2
  exit 1
fi

BRANCH="$1"
BASE_REF="${2:-origin/main}"
PREFIX="${BRANCH%%/*}"
SLUG="${BRANCH#*/}"

if [ -z "$SLUG" ] || [ "$PREFIX" = "$BRANCH" ]; then
  echo "Branch must be <prefix>/<short-name> (got: $BRANCH)" >&2
  exit 1
fi

allowed=0
for p in "${ALLOWED_PREFIXES[@]}"; do
  if [ "$PREFIX" = "$p" ]; then
    allowed=1
    break
  fi
done
if [ "$allowed" -eq 0 ]; then
  echo "Branch prefix must be one of: ${ALLOWED_PREFIXES[*]}" >&2
  exit 1
fi

SLUG="${SLUG//\//-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="$ROOT/.worktrees/$SLUG"

git -C "$ROOT" fetch origin

if git -C "$ROOT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git -C "$ROOT" worktree add "$TARGET" "$BRANCH"
elif git -C "$ROOT" show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
  git -C "$ROOT" worktree add -b "$BRANCH" "$TARGET" "origin/$BRANCH"
else
  git -C "$ROOT" worktree add -b "$BRANCH" "$TARGET" "$BASE_REF"
fi

echo "Worktree ready: $TARGET"
echo "  branch: $BRANCH (from $BASE_REF)"
