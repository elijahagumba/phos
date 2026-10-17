#!/usr/bin/env bash
# Create the four build lanes of docs/build-brief-2026-10.md as git worktrees beside this checkout.
#
# Run from the main checkout, after Step 0's ADR is committed on main:
#
#     scripts/build_lanes.sh            # ../phos-lane-{a,b,c,d}
#     scripts/build_lanes.sh /some/dir  # /some/dir/phos-lane-{a,b,c,d}
#
# Each lane gets its own branch from the current HEAD, links to this checkout's untracked data
# files (data is never committed, so a fresh worktree has none), and its own environment
# (`uv sync`). Re-running skips lanes that already exist.
set -euo pipefail

main=$(git rev-parse --show-toplevel)
parent=${1:-$(dirname "$main")}
cd "$main"

if [[ -n $(git status --porcelain --untracked-files=no) ]]; then
  echo "commit or stash local changes first" >&2
  exit 1
fi

lanes=(
  "a:build/lane-a-sentiel"
  "b:build/lane-b-innocence"
  "c:build/lane-c-reports"
  "d:build/lane-d-commands-naming"
)

for entry in "${lanes[@]}"; do
  lane=${entry%%:*}
  branch=${entry#*:}
  dir="$parent/phos-lane-$lane"
  if [[ -d $dir ]]; then
    echo "lane $lane: $dir exists, skipped"
    continue
  fi
  git worktree add -q -b "$branch" "$dir" HEAD
  # Link every ignored file under data/ (the payloads), keeping tracked manifests and roles.
  # A nested repository is listed once, as a directory with a trailing slash; link it whole.
  git ls-files --others --ignored --exclude-standard -- data | while read -r file; do
    file=${file%/}
    mkdir -p "$dir/$(dirname "$file")"
    ln -sfn "$main/$file" "$dir/$file"
  done
  (cd "$dir" && uv sync -q)
  echo "lane $lane: $dir on $branch"
done

git worktree list
