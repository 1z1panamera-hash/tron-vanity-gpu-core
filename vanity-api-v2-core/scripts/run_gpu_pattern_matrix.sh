#!/usr/bin/env bash
set -euo pipefail

BINARY="${1:-}"
PATTERN_FILE="${2:-}"
SEED="${3:-round52-v2-fixed-seed}"
OUT_DIR="${4:-./pattern-matrix-results}"

if [ ! -x "$BINARY" ] || [ ! -f "$PATTERN_FILE" ]; then
  echo "usage: $0 /path/to/binary patterns.tsv [seed] [output-dir]" >&2
  exit 2
fi

mkdir -p "$OUT_DIR"
passed=0
failed=0

while IFS=$'\t' read -r total prefix_length suffix_length pattern expected_address; do
  if [ "$total" = "total" ] || [ -z "$total" ]; then
    continue
  fi
  case_name="total${total}_prefix${prefix_length}_suffix${suffix_length}"
  log_file="$OUT_DIR/${case_name}.log"
  set +e
  TRON_SUPPRESS_SECRET_OUTPUT=1 timeout 45 \
    "$BINARY" -stop -gpu -g 160,128 -s "$SEED" "$pattern" >"$log_file" 2>&1
  rc=$?
  set -e
  address="$(sed -n 's/^PubAddress: //p' "$log_file" | tail -1)"
  valid="$({ python3 - "$pattern" "$address" <<'PY'
import sys
pattern, address = sys.argv[1:]
prefix, suffix = pattern[1:].split("*", 1)
ok = (
    len(address) == 34
    and address.startswith("T" + prefix)
    and address.endswith(suffix)
)
print("yes" if ok else "no")
PY
  } 2>/dev/null)"
  if [ "$rc" -eq 0 ] && [ "$valid" = "yes" ] && \
     grep -q '^SensitiveOutput: suppressed$' "$log_file"; then
    passed=$((passed + 1))
    printf 'PASS %s pattern=%s address=%s\n' "$case_name" "$pattern" "$address"
  else
    failed=$((failed + 1))
    printf 'FAIL %s pattern=%s rc=%s valid=%s\n' "$case_name" "$pattern" "$rc" "$valid" >&2
  fi
done < "$PATTERN_FILE"

printf 'pattern_matrix passed=%s failed=%s\n' "$passed" "$failed"
test "$passed" -eq 24
test "$failed" -eq 0
