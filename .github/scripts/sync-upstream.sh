#!/usr/bin/env bash
# Merge the public insidejob repo's main into this copy, on a `sync/upstream` branch.
#
# Run from the root of a checkout with full history (fetch-depth: 0). Prints one of:
#   up-to-date   nothing to do
#   ready        sync/upstream now holds the merge (caller pushes it and opens a PR)
#   conflict     the merge needs a human; nothing was changed
# Your own files always win: config.yaml (and anything else listed in KEEP) is put back
# to this copy's version after the merge, so an update never touches your settings.
set -euo pipefail

UPSTREAM_URL="${UPSTREAM_URL:-https://github.com/WainoVanska/insidejob.git}"
BASE="${BASE:-main}"
KEEP=(config.yaml CLAUDE.local.md)

# Only ever touch the repo we're in, never a parent one that happens to contain it.
top=$(git rev-parse --show-toplevel 2>/dev/null || true)
if [ -z "$top" ] || [ "$(cd "$top" && pwd -P)" != "$(pwd -P)" ]; then
  echo "run this from the root of the repo to sync" >&2
  exit 2
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

git remote get-url upstream > /dev/null 2>&1 || git remote add upstream "$UPSTREAM_URL"
git fetch --quiet upstream main

if git merge-base --is-ancestor upstream/main "$BASE"; then
  echo "up-to-date"
  exit 0
fi

git switch --quiet -C sync/upstream "$BASE"
message="Update from insidejob ($(git rev-parse --short upstream/main))"

if git merge-base "$BASE" upstream/main > /dev/null; then
  # Shared history (a fork or a clone): a normal merge. Conflicts only in KEEP files are
  # settled in this copy's favour; any other conflict needs a human, so stop.
  if ! git merge --quiet --no-edit -m "$message" upstream/main > /dev/null 2>&1; then
    others=$(git diff --name-only --diff-filter=U | grep -vxF -f <(printf '%s\n' "${KEEP[@]}") || true)
    if [ -n "$others" ] || [ -z "$(git diff --name-only --diff-filter=U)" ]; then
      git merge --abort 2>/dev/null || true
      git switch --quiet "$BASE"
      echo "conflict"
      exit 0
    fi
    git diff --name-only --diff-filter=U | while read -r file; do
      git checkout "$BASE" -- "$file"
    done
    git commit --quiet --no-edit
  fi
else
  # A "Use this template" copy shares no history with upstream: every file looks like a
  # conflict the first time. Take upstream's version of the code; KEEP files are restored
  # below. After this merge the histories are joined and later syncs are normal merges.
  git merge --quiet --no-edit -m "$message" --allow-unrelated-histories -X theirs upstream/main > /dev/null
fi

restored=0
for file in "${KEEP[@]}"; do
  if git cat-file -e "$BASE:$file" 2>/dev/null; then
    git checkout "$BASE" -- "$file"
    restored=1
  fi
done
if [ "$restored" = 1 ] && ! git diff --cached --quiet; then
  git commit --quiet --amend --no-edit
fi

echo "ready"
