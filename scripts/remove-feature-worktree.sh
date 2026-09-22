#!/usr/bin/env bash
# Remove a feature worktree after merge. Pass branch (feat/foo) or path.
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: bash scripts/remove-feature-worktree.sh feat/<short-name>|fix/<short-name>|.worktrees/<slug>" >&2
  exit 1
fi

ARG="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ -d "$ARG" ]; then
  TARGET="$(cd "$ARG" && pwd)"
  BRANCH="$(git -C "$TARGET" branch --show-current || true)"
else
  BRANCH="$ARG"
  SLUG="${BRANCH#*/}"
  SLUG="${SLUG//\//-}"
  TARGET="$ROOT/.worktrees/$SLUG"
fi

if [ -d "$TARGET" ]; then
  git -C "$ROOT" worktree remove --force "$TARGET" || {
    rm -rf "$TARGET"
    git -C "$ROOT" worktree prune
  }
fi

if [ -n "${BRANCH:-}" ] && git -C "$ROOT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  if git -C "$ROOT" merge-base --is-ancestor "$BRANCH" origin/main 2>/dev/null; then
    git -C "$ROOT" branch -d "$BRANCH" || true
  fi
fi

echo "Removed worktree ${TARGET:-} ($BRANCH)"
