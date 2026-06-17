#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CANDIDATE="$ROOT/../candidate-cores/VanitySearch"
DEFAULT_OUTPUT="$ROOT/../vanitysearch_tron_cpu_prototype_20260617.patch"
BASE_COMMIT="c8d48ce5f03f5357c0e87cbdb3e1e93cd50af88b"

CANDIDATE_PATH="${1:-$DEFAULT_CANDIDATE}"
OUTPUT_PATH="${2:-$DEFAULT_OUTPUT}"

if [[ ! -d "$CANDIDATE_PATH/.git" ]]; then
  echo "candidate git repo not found: $CANDIDATE_PATH" >&2
  exit 1
fi

if [[ -n "$(git -C "$CANDIDATE_PATH" status --short)" ]]; then
  echo "candidate worktree is not clean: $CANDIDATE_PATH" >&2
  exit 1
fi

git -C "$CANDIDATE_PATH" cat-file -e "$BASE_COMMIT^{commit}"
mkdir -p "$(dirname "$OUTPUT_PATH")"
git -C "$CANDIDATE_PATH" diff --binary "$BASE_COMMIT"..HEAD > "$OUTPUT_PATH"

echo "vanitysearch_patch_exported=$OUTPUT_PATH"
sha256sum "$OUTPUT_PATH" 2>/dev/null || shasum -a 256 "$OUTPUT_PATH"
